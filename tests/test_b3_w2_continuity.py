"""Versioned W2 continuity: synthetic evidence and disposable packages only."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import serving_fixtures
from serving.baseline import open_baseline
from serving.query import parse_associations
from serving.w2_continuity import FORMAT, ContinuityError, build_continuity, canonical_rows

REPO = Path(__file__).resolve().parents[1]
A, B = 'INE002A01018', 'INE467B01029'


def observation(file, date, ticker, isin=A, valid='VALID', family='legacy13', line=1, series='EQ'):
    udiff = family == 'udiff34'
    return (file, {'business_date': date, 'format_family': family, 'source_line_number': line,
                   'isin_normalized': isin, 'isin_validity': valid,
                   'provenance': {'member_name': file, 'archive_sha256': 'synthetic-hash'},
                   'source_values': {'listing_symbol': '500325' if udiff else ticker,
                                     'underlying_symbol': ticker if udiff else None,
                                     'series': series, 'segment': 'CM' if udiff else None,
                                     'instrument_type': 'STK' if udiff else None, 'security_isin': isin}})


class ContinuityContractTests(unittest.TestCase):
    def derive(self, rows):
        return build_continuity(rows, 'manifest-digest')

    def test_observed_transition_and_raw_lineage(self):
        rows = [observation('old', '2020-01-01', 'OLD'),
                observation('new', '2020-01-02', 'NEW', family='udiff34')]
        result = self.derive(rows)
        self.assertEqual(result['format'], FORMAT)
        group = result['identities'][0]
        self.assertEqual(group['status'], 'observed')
        self.assertEqual([i['symbol'] for i in group['intervals']], ['OLD', 'NEW'])
        self.assertEqual(group['transitions'], [{'from_symbol': 'OLD', 'to_symbol': 'NEW',
            'from_last_observed': '2020-01-01', 'to_first_observed': '2020-01-02',
            'basis': 'observed-transition-not-validity'}])
        evidence = group['intervals'][1]['evidence'][0]
        self.assertEqual((evidence['published_listing_symbol'], evidence['observed_symbol'], evidence['raw_isin']), ('500325', 'NEW', A))
        self.assertEqual(evidence['symbol_source'], 'TckrSymb')
        self.assertEqual(evidence['provenance']['member_name'], 'new')
        self.assertEqual(result['unresolved'], [])

    def test_reuse_different_isins_and_overlapping_bounds_are_ambiguous(self):
        rows = [observation('one', '2020-01-01', 'SHARED', A), observation('two', '2021-01-01', 'SHARED', B)]
        groups = self.derive(rows)['identities']
        self.assertEqual([g['security_id'] for g in groups], [A, B])
        self.assertTrue(all(g['status'] == 'ambiguous' and not g['transitions'] for g in groups))
        self.assertTrue(all('multiple valid ISINs' in g['ambiguities'][0] for g in groups))
        overlap = [observation('a', '2020-01-01', 'OLD'), observation('b', '2020-01-02', 'NEW'),
                   observation('c', '2020-01-03', 'OLD')]
        group = self.derive(overlap)['identities'][0]
        self.assertEqual(group['status'], 'ambiguous')
        self.assertFalse(group['transitions'])
        self.assertIn('overlapping observed ticker ranges', group['ambiguities'][0])

    def test_boundary_same_day_is_ambiguous(self):
        group = self.derive([observation('a', '2020-01-01', 'OLD'), observation('b', '2020-01-01', 'NEW')])['identities'][0]
        self.assertEqual(group['status'], 'ambiguous')
        self.assertEqual(group['transitions'], [])
        self.assertEqual({i['symbol'] for i in group['intervals']}, {'OLD', 'NEW'})

    def test_invalid_missing_identity_and_overlays_retained_unresolved(self):
        rows = [observation('blank', '2020-01-01', 'AA', '', 'BLANK'),
                observation('invalid', '2020-01-01', 'BB', 'BAD', 'INVALID_LENGTH'),
                observation('date', '', 'CC'), observation('overlay', '2020-01-01', 'DD', series='BL')]
        result = self.derive(rows)
        self.assertEqual(result['identities'], [])
        self.assertEqual([r['reason'] for r in result['unresolved']],
                         ['invalid-missing-isin-or-date', 'invalid-missing-isin-or-date',
                          'invalid-missing-isin-or-date', 'overlay-excluded'])
        self.assertEqual([r['source_file'] for r in result['unresolved']], ['blank', 'date', 'invalid', 'overlay'])

    def test_determinism_replay_and_duplicates(self):
        rows = [observation('a', '2020-01-01', 'OLD'), observation('b', '2020-01-02', 'NEW')]
        first = self.derive(rows)
        self.assertEqual(first, self.derive(reversed(copy.deepcopy(rows))))
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(self.derive(rows), sort_keys=True))
        with self.assertRaises(ContinuityError):
            self.derive(rows + [copy.deepcopy(rows[0])])

    def test_fixture_compatibility_immutable_original_and_cli_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); pkg = root / 'pkg'
            facts = serving_fixtures.build_fixture_package(str(pkg))
            baseline = open_baseline(str(pkg), spec=facts['spec'])
            before = {str(p.relative_to(pkg)): p.read_bytes() for p in pkg.rglob('*') if p.is_file()}
            old_docs = parse_associations(baseline)
            result = build_continuity(canonical_rows(baseline), baseline.manifest_digest)
            actual = next(g for g in result['identities'] if g['security_id'] == A and g['series'] == 'EQ')
            self.assertEqual([i['symbol'] for i in actual['intervals']], ['RELIANCE'])
            self.assertEqual(actual['intervals'][0]['observed_to'], '2024-03-05')
            self.assertEqual(parse_associations(baseline), old_docs)
            self.assertEqual(before, {str(p.relative_to(pkg)): p.read_bytes() for p in pkg.rglob('*') if p.is_file()})
            env = dict(os.environ, PYTHONPATH=str(REPO / 'src'), PYTHONDONTWRITEBYTECODE='1')
            command = [sys.executable, '-m', 'serving.w2_continuity', '--package', str(pkg)]
            r1 = subprocess.run(command, cwd=tmp, env=env, capture_output=True, text=True)
            r2 = subprocess.run(command, cwd=tmp, env=env, capture_output=True, text=True)
            self.assertEqual((r1.returncode, r2.returncode), (0, 0), r1.stderr + r2.stderr)
            self.assertEqual(r1.stdout, r2.stdout)
            self.assertEqual(json.loads(r1.stdout), result)
            self.assertEqual(before, {str(p.relative_to(pkg)): p.read_bytes() for p in pkg.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
