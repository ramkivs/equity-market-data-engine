"""Synthetic transactional draft snapshots; never a serving publication."""
import json
import os
import sqlite3
import subprocess
import sys
import threading
import unittest
from unittest import mock

from serving.baseline import Baseline
from serving.incremental_drafts import _schema, create_draft, list_drafts
from serving.incremental_registry import RegistryError, conflicts
from serving.index import build_index, write_index, ServingIndexError
from serving.saved import execute_query_definition
from tests import test_incremental_staging as staging
from tests import serving_fixtures as fixtures


class DraftTests(unittest.TestCase):
    setUp = staging.StagingTests.setUp
    tearDown = staging.StagingTests.tearDown
    stage = staging.StagingTests.stage

    def init(self):
        write_index(self.args[2], build_index(self.baseline))
        return self.stage()['record']

    def db(self):
        return sqlite3.connect(os.path.join(self.args[1], 'source_registry.sqlite3'))

    def test_snapshot_is_atomic_deterministic_and_does_not_read_baseline_rows(self):
        candidate = self.init()
        with mock.patch.object(Baseline, 'path', side_effect=AssertionError('baseline row read')):
            first = create_draft(*self.args)
            again = create_draft(*self.args)
        self.assertEqual(first, again)
        self.assertEqual(first['state'], 'DRAFT-NOT-SERVEABLE')
        self.assertEqual(first['rows'], candidate['rows'])
        self.assertEqual(list_drafts(*self.args), [{'draft_id': first['draft_id'], 'state': 'DRAFT-NOT-SERVEABLE'}])
        with self.db() as db:
            text = db.execute('SELECT manifest FROM draft_generations').fetchone()[0]
            doc = json.loads(text)
            self.assertEqual(doc['baseline_manifest_sha256'], self.baseline.manifest_digest)
            self.assertEqual(doc['delta_index_fragments'][0]['row_count'], candidate['rows'])
            self.assertEqual(doc['delta_only_b3']['format'], 'w2-trading-symbol-associations/1.0')
            self.assertTrue(doc['delta_b2_observations'])
            self.assertEqual(db.execute('SELECT count(*) FROM accepted').fetchone()[0], fixtures.EXPECTED_MEMBERS)
            self.assertEqual(db.execute('SELECT count(*) FROM draft_members').fetchone()[0], 1)
        self.assertEqual(conflicts(*self.args), [])

    def test_interruption_rolls_back_and_retry_is_complete(self):
        self.init()
        with self.db() as db:
            _schema(db)
            db.execute("CREATE TRIGGER fail_member BEFORE INSERT ON draft_members BEGIN SELECT RAISE(ABORT, 'interrupted'); END")
        with self.assertRaises(RegistryError):
            create_draft(*self.args)
        self.assertEqual(list_drafts(*self.args), [])
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM draft_members').fetchone()[0], 0)
            db.execute('DROP TRIGGER fail_member')
        self.assertEqual(create_draft(*self.args)['state'], 'DRAFT-NOT-SERVEABLE')

    def test_corrupted_stage_rejected_without_snapshot(self):
        self.init()
        with self.db() as db:
            db.execute("UPDATE staged_candidates SET rows = rows || 'bad'")
        with self.assertRaisesRegex(RegistryError, 'digest mismatch'):
            create_draft(*self.args)
        self.assertEqual(list_drafts(*self.args), [])

    def test_missing_index_fails_closed_and_nothing_accepted(self):
        self.stage()
        with self.assertRaises(ServingIndexError):
            create_draft(*self.args)
        self.assertEqual(list_drafts(*self.args), [])
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM accepted').fetchone()[0], fixtures.EXPECTED_MEMBERS)

    def test_abrupt_process_exit_recovers_transaction_on_reopen(self):
        self.init()
        with self.db() as db:
            _schema(db)
            db.execute("CREATE TRIGGER abrupt AFTER INSERT ON draft_generations BEGIN SELECT terminate_for_test(); END")
        code = r'''
import json, os, sys
from serving.baseline import open_baseline
import serving.incremental_drafts as d
args=json.loads(sys.argv[1])
base=open_baseline(args[0])
original=d._open
def opened(*a):
    db, meta=original(*a)
    db.create_function("terminate_for_test", 0, lambda: os._exit(47))
    return db, meta
d._open=opened
d.create_draft(base, *args[1:])
'''
        args = [str(self.pkg), *self.args[1:]]
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run([sys.executable, '-c', code, json.dumps(args)], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 47, proc.stderr)
        # Opening the SQLite store rolls the interrupted transaction back.
        self.assertEqual(list_drafts(*self.args), [])
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM draft_members').fetchone()[0], 0)
            db.execute('DROP TRIGGER abrupt')
        self.assertEqual(create_draft(*self.args)['state'], 'DRAFT-NOT-SERVEABLE')

    def test_existing_reader_snapshot_never_sees_partial_draft(self):
        self.init()
        with self.db() as db:
            _schema(db)
        reader = self.db()
        ready, result = threading.Event(), []
        import serving.incremental_drafts as drafts
        real_schema = drafts._schema
        def signal_schema(db):
            real_schema(db)
            ready.set()
        def writer():
            try:
                result.append(create_draft(*self.args))
            except Exception as exc:
                result.append(exc)
        try:
            reader.execute('BEGIN')
            self.assertEqual(reader.execute('SELECT count(*) FROM draft_generations').fetchone()[0], 0)
            with mock.patch('serving.incremental_drafts._schema', side_effect=signal_schema):
                thread = threading.Thread(target=writer)
                thread.start()
                self.assertTrue(ready.wait(3), 'writer did not reach transaction')
                self.assertEqual(reader.execute('SELECT count(*) FROM draft_generations').fetchone()[0], 0)
                self.assertEqual(reader.execute('SELECT count(*) FROM draft_members').fetchone()[0], 0)
                reader.commit()
                thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(result), 1)
            self.assertIsInstance(result[0], dict, str(result[0]))
            with self.db() as fresh:
                self.assertEqual(fresh.execute('SELECT count(*) FROM draft_generations').fetchone()[0], 1)
                self.assertEqual(fresh.execute('SELECT count(*) FROM draft_members').fetchone()[0], 1)
        finally:
            reader.close()

    def test_draft_member_tampering_is_detected_on_reopen(self):
        self.init()
        create_draft(*self.args)
        with self.db() as db:
            db.execute("UPDATE draft_members SET rows=rows || 'tampered'")
        with self.assertRaisesRegex(RegistryError, 'digest mismatch'):
            list_drafts(*self.args)

    def test_snapshot_is_detached_from_subsequent_stage_changes(self):
        self.init()
        first = create_draft(*self.args)
        with self.db() as db:
            db.execute("UPDATE staged_candidates SET rows=rows || 'tampered'")
        self.assertEqual(list_drafts(*self.args)[0]['draft_id'], first['draft_id'])
        with self.assertRaisesRegex(RegistryError, 'digest mismatch'):
            create_draft(*self.args)

    def test_byte_limit_rejects_before_loading_a_snapshot(self):
        self.init()
        with mock.patch('serving.incremental_drafts.MAX_DRAFT_BYTES', 1):
            with self.assertRaisesRegex(RegistryError, 'byte limit'):
                create_draft(*self.args)
        self.assertEqual(list_drafts(*self.args), [])

    def test_draft_cli_exposes_only_non_serveable_status(self):
        self.init()
        base, reg, state, saved, history, roots = self.args
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        prefix = [sys.executable, '-m', 'serving.incremental_registry', '--package', base.root,
                  '--registry', reg, '--state', state, '--saved-state', saved, '--history-state', history,
                  '--legacy-root', roots['LEGACY'], '--udiff-root', roots['UDIFF']]
        def run(command):
            proc = subprocess.run(prefix + [command], env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return json.loads(proc.stdout)['data']
        draft = run('draft')
        self.assertEqual(draft['state'], 'DRAFT-NOT-SERVEABLE')
        self.assertEqual(run('drafts'), [{'draft_id': draft['draft_id'], 'state': 'DRAFT-NOT-SERVEABLE'}])

    def test_existing_q3_q4_q5_do_not_serve_drafts(self):
        write_index(self.args[2], build_index(self.baseline))
        requests = [('Q3-instrument', {'symbol': 'RELIANCE', 'series': 'EQ'}),
                    ('Q4-filter', {'filters': {'series': 'EQ'}}),
                    ('Q5-association', {'security_id': 'INE002A01018'})]
        def results():
            return [execute_query_definition(mode, params, self.baseline, self.args[2]) for mode, params in requests]
        before = results()
        self.stage()
        create_draft(*self.args)
        self.assertEqual(results(), before)

    def test_cli_reports_missing_index_as_failure(self):
        self.stage()
        base, reg, state, saved, history, roots = self.args
        env = dict(os.environ, PYTHONPATH=os.path.abspath('src'), PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-m', 'serving.incremental_registry', '--package', base.root,
                   '--registry', reg, '--state', state, '--saved-state', saved, '--history-state', history,
                   '--legacy-root', roots['LEGACY'], '--udiff-root', roots['UDIFF'], 'draft']
        proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)['result'], 'fail')
        self.assertNotIn('Traceback', proc.stderr)
