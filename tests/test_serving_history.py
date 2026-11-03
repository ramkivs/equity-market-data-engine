"""Serving slice — query history: the explicit-recording slice (D16-10 item 5;
D37-DEC C2(a); standing D23 authority; D39 record).

All cases run against the synthetic fixture package (tests/serving_fixtures.py) —
never against, and never represented as, the qualified M2 baseline. The
real-package leg is D24_M2_ROOT-gated in tests/test_serving_m2_integration.py.

Covered contract (docs/architecture/D37_SAVED_QUERY_HISTORY_DECISION.md §7,
docs/implementation/D39_QUERY_HISTORY_SLICE.md):

* the single explicit recording operation (``history record``) executes the
  given mode + parameters and records the ACTUAL outcome — success or error —
  with its check id; an execution that never happened is never recorded;
* **C2(a): ordinary query execution and saved-query execution NEVER write the
  history store** (asserted byte-for-byte);
* deterministic serialization; ascending ``seq`` ordering; seq is stable and
  **never reused** (the ``next_seq`` counter is monotonic across deletions);
  repeated identical descriptions are NOT collapsed;
* no result rows, no result counts, no timestamps, no invented provenance;
* fail-closed on corrupt, truncated, unknown-format, or schema-violating
  persisted state; invalid descriptions are rejected with NO entry published;
* isolation: the history root is distinct from the derived-state root
  (``history-state-conflict``); saved-query state is unchanged by history
  operations; the derived-state rebuild leaves history unchanged;
* the qualified package's bytes are unchanged after successful and failed
  history operations; existing saved-query and query behavior stays intact.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest

from tests import serving_fixtures
from serving import cli as serving_cli
from serving.baseline import open_baseline
from serving.index import build_index, canonical_json, write_index
from serving.query import QueryError, query_date_range, query_instrument
from serving.rebuild import rebuild_state
from serving.saved import create_saved, execute_saved
from serving.history import (
    HISTORY_DIGEST_FILENAME,
    HISTORY_FILENAME,
    HISTORY_FORMAT,
    HistoryError,
    delete_history,
    get_history,
    list_history,
    load_history,
    record_execution,
)


class HistoryBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d39-serving-history-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]
        self.handle = open_baseline(self.pkg, spec=self.spec)
        self.index = build_index(self.handle)
        self.state = os.path.join(self.root, "state")
        write_index(self.state, self.index)
        self.hist = os.path.join(self.root, "history-state")
        self.saved = os.path.join(self.root, "saved-state")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def store_files(self, root=None):
        root = root or self.hist
        out = {}
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                full = os.path.join(root, name)
                if os.path.isfile(full):
                    with open(full, "rb") as handle:
                        out[name] = hashlib.sha256(handle.read()).hexdigest()
        return out

    def package_digests(self):
        digests = {}
        for dirpath, dirnames, filenames in os.walk(self.pkg):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                with open(full, "rb") as handle:
                    digests[os.path.relpath(full, self.pkg)] = hashlib.sha256(handle.read()).hexdigest()
        return digests

    def write_hist_doc(self, document, root=None):
        root = root or self.hist
        os.makedirs(root, exist_ok=True)
        text = canonical_json(document) + "\n"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with open(os.path.join(root, HISTORY_FILENAME), "w", encoding="utf-8") as handle:
            handle.write(text)
        with open(os.path.join(root, HISTORY_DIGEST_FILENAME), "w", encoding="utf-8") as handle:
            handle.write("%s  %s\n" % (digest, HISTORY_FILENAME))

    def assertHistRaises(self, fn, *args, check=None, **kwargs):
        with self.assertRaises(HistoryError) as ctx:
            fn(*args, **kwargs)
        if check is not None:
            self.assertEqual(ctx.exception.check, check)
        return ctx.exception

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = serving_cli.main(list(args))
        return code, buf.getvalue()

    def good_entry(self, seq=1, mode="Q8-data-quality"):
        return {"seq": seq, "mode": mode, "params": {}, "outcome": "success"}


class ExplicitRecordingTests(HistoryBase):
    """The explicit operation: executes and records the ACTUAL outcome."""

    def test_record_creates_durable_success_entry(self):
        entry, output, detail, digest = record_execution(
            self.hist, "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"}, self.handle, self.state
        )
        self.assertEqual(entry, {"seq": 1, "mode": "Q3-instrument",
                                 "params": {"series": "EQ", "symbol": "RELIANCE"}, "outcome": "success"})
        self.assertIsNone(detail)
        self.assertEqual(output["query"], "Q3-instrument")
        self.assertGreater(output["result_count"], 0)
        self.assertEqual(self.store_files(), {
            HISTORY_FILENAME: digest,
            HISTORY_DIGEST_FILENAME: hashlib.sha256(
                ("%s  %s\n" % (digest, HISTORY_FILENAME)).encode()
            ).hexdigest(),
        })
        self.assertEqual(list_history(self.hist), [entry])

    def test_record_creates_durable_error_entry_with_check(self):
        entry, output, detail, _digest = record_execution(
            self.hist, "Q4-filter", {"filters": {"bogus": "x"}}, self.handle, self.state
        )
        self.assertEqual(entry, {"seq": 1, "mode": "Q4-filter", "params": {"filters": {"bogus": "x"}},
                                 "outcome": "error", "check": "query-input"})
        self.assertIsNone(output)
        self.assertIn("unknown Q4 filter field", detail)
        (stored,) = list_history(self.hist)
        self.assertEqual(stored, entry)

    def test_record_never_invents_outcomes(self):
        # an invalid description is rejected BEFORE any execution and no entry
        # is published (there is no execution to record). A fresh-input
        # definition-contract violation raises the shared SavedQueryError.
        from serving.saved import SavedQueryError

        before = self.store_files()
        for mode, params in (
            ("Q0-nope", {}),
            ("Q2-date-range", {"date_from": "2016-01-04"}),
        ):
            with self.assertRaises(SavedQueryError) as ctx:
                record_execution(self.hist, mode, params, self.handle, self.state)
            self.assertEqual(ctx.exception.check, "saved-query-invalid")
        self.assertEqual(self.store_files(), before)

    def test_record_records_all_supported_modes(self):
        # the recording operation reuses the existing Q1-Q10 execution layer
        specs = [
            ("Q1-dataset", {"year": 2016}),
            ("Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"}),
            ("Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"}),
            ("Q4-filter", {"filters": {"series": "EQ"}}),
            ("Q5-association", {"security_id": "INE002A01018"}),
            ("Q6-calendar", {}),
            ("Q8-data-quality", {}),
            ("Q9-archive-inventory", {}),
            ("Q10-qualification", {}),
        ]
        rows = query_date_range(self.handle, self.index, "2016-01-04", "2016-01-05")
        specs.insert(6, ("Q7-record-detail",
                         {"source_file": rows[0]["serving"]["source_file"],
                          "source_line_number": rows[0]["source_line_number"]}))
        for i, (mode, params) in enumerate(specs, start=1):
            entry, output, _detail, _d = record_execution(self.hist, mode, params, self.handle, self.state)
            self.assertEqual(entry["seq"], i)
            self.assertEqual(entry["outcome"], "success")
            self.assertEqual(entry["mode"], mode)
        self.assertEqual(len(list_history(self.hist)), len(specs))


class C2AIsolationTests(HistoryBase):
    """Ordinary query and saved-run execution never write history."""

    def test_ordinary_query_execution_does_not_modify_history(self):
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        before = self.store_files()
        self.run_cli("query", "--package", self.pkg, "--state", self.state, "RELIANCE", "EQ")
        self.run_cli("query", "--package", self.pkg, "--state", self.state,
                     "--from", "2016-01-04", "--to", "2016-01-05")
        self.run_cli("dataset", "--package", self.pkg, "--state", self.state)
        self.run_cli("quality", "--package", self.pkg, "--state", self.state)
        self.assertEqual(self.store_files(), before)

    def test_saved_run_does_not_modify_history(self):
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        create_saved(self.saved, "q3", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        before = self.store_files()
        execute_saved(self.saved, "q3", self.handle, self.state)
        self.run_cli("saved", "run", "--package", self.pkg, "--state", self.state,
                     "--saved-state", self.saved, "--id", "q3")
        self.assertEqual(self.store_files(), before)

    def test_history_starts_absent_until_explicit_record(self):
        self.run_cli("query", "--package", self.pkg, "--state", self.state, "RELIANCE", "EQ")
        self.assertEqual(self.store_files(), {})  # nothing created implicitly
        self.assertHistRaises(list_history, self.hist, check="history-missing")


class IdentityOrderingTests(HistoryBase):
    """Stable seq identity; deterministic ordering; no collapsing."""

    def test_seq_is_stable_and_never_reused(self):
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        record_execution(self.hist, "Q9-archive-inventory", {}, self.handle, self.state)
        delete_history(self.hist, 2)
        entry, _o, _d, _dig = record_execution(self.hist, "Q10-qualification", {}, self.handle, self.state)
        self.assertEqual(entry["seq"], 3)  # not 2
        document = load_history(self.hist)
        self.assertEqual([e["seq"] for e in document["entries"]], [1, 3])
        self.assertEqual(document["next_seq"], 4)

    def test_repeated_identical_descriptions_are_not_collapsed(self):
        for _ in range(3):
            record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        entries = list_history(self.hist)
        self.assertEqual([e["seq"] for e in entries], [1, 2, 3])
        self.assertTrue(all(e["mode"] == "Q8-data-quality" for e in entries))

    def test_ordering_is_ascending_seq(self):
        record_execution(self.hist, "Q1-dataset", {"year": 2016}, self.handle, self.state)
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        record_execution(self.hist, "Q9-archive-inventory", {}, self.handle, self.state)
        self.assertEqual([e["seq"] for e in list_history(self.hist)], [1, 2, 3])

    def test_serialization_is_deterministic(self):
        other = os.path.join(self.root, "hist-again")
        for root in (self.hist, other):
            record_execution(root, "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"}, self.handle, self.state)
            record_execution(root, "Q4-filter", {"filters": {"bogus": "x"}}, self.handle, self.state)
        with open(os.path.join(self.hist, HISTORY_FILENAME), "rb") as handle:
            a = handle.read()
        with open(os.path.join(other, HISTORY_FILENAME), "rb") as handle:
            b = handle.read()
        self.assertEqual(a, b)

    def test_no_timestamps_no_rows_no_counts_in_entries(self):
        record_execution(self.hist, "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"}, self.handle, self.state)
        entry, _output, _detail, _digest = record_execution(
            self.hist, "Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"},
            self.handle, self.state,
        )
        for e in list_history(self.hist):
            self.assertEqual(set(e) - {"check"}, {"seq", "mode", "params", "outcome"})
            self.assertNotIn("rows", json.dumps(e))
            self.assertNotIn("count", json.dumps(e))
            self.assertNotIn("timestamp", json.dumps(e))
            self.assertNotIn("time", json.dumps(e))


class FailClosedStateTests(HistoryBase):
    """Corrupt / truncated / incompatible / non-contract persisted state."""

    def test_missing_store_fails_closed(self):
        self.assertHistRaises(list_history, self.hist, check="history-missing")
        self.assertHistRaises(get_history, self.hist, 1, check="history-missing")
        self.assertHistRaises(delete_history, self.hist, 1, check="history-missing")

    def test_partial_store_fails_closed(self):
        os.makedirs(self.hist, exist_ok=True)
        with open(os.path.join(self.hist, HISTORY_FILENAME), "w", encoding="utf-8") as handle:
            handle.write(canonical_json({"format": HISTORY_FORMAT, "entries": [], "next_seq": 1}) + "\n")
        self.assertHistRaises(list_history, self.hist, check="history-missing")

    def test_sidecar_mismatch_fails_closed(self):
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        path = os.path.join(self.hist, HISTORY_FILENAME)
        with open(path, "rb") as handle:
            data = bytearray(handle.read())
        data[5] ^= 1
        with open(path, "wb") as handle:
            handle.write(bytes(data))
        self.assertHistRaises(list_history, self.hist, check="history-corrupt")

    def test_truncated_sidecar_fails_closed(self):
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        path = os.path.join(self.hist, HISTORY_DIGEST_FILENAME)
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text[:5])
        self.assertHistRaises(load_history, self.hist, check="history-corrupt")

    def test_unparseable_json_fails_closed(self):
        os.makedirs(self.hist, exist_ok=True)
        with open(os.path.join(self.hist, HISTORY_FILENAME), "w", encoding="utf-8") as handle:
            handle.write("{not json\n")
        with open(os.path.join(self.hist, HISTORY_DIGEST_FILENAME), "w", encoding="utf-8") as handle:
            handle.write("0" * 64 + "  %s\n" % HISTORY_FILENAME)
        self.assertHistRaises(load_history, self.hist, check="history-corrupt")

    def test_unknown_format_version_fails_closed(self):
        self.write_hist_doc({"format": "serving-query-history/9.9", "entries": [], "next_seq": 1})
        self.assertHistRaises(load_history, self.hist, check="history-format")

    def test_schema_violations_fail_closed(self):
        good = self.good_entry()
        cases = [
            # non-contract top-level keys
            ({"format": HISTORY_FORMAT, "entries": [good], "next_seq": 2, "extra": 1}, "history-schema"),
            # entries not a list
            ({"format": HISTORY_FORMAT, "entries": {}, "next_seq": 1}, "history-schema"),
            # next_seq missing / non-int / too small
            ({"format": HISTORY_FORMAT, "entries": [good]}, "history-schema"),
            ({"format": HISTORY_FORMAT, "entries": [good], "next_seq": "2"}, "history-schema"),
            ({"format": HISTORY_FORMAT, "entries": [good], "next_seq": 1}, "history-schema"),
            ({"format": HISTORY_FORMAT, "entries": [good], "next_seq": 0}, "history-schema"),
            # seq not strictly ascending
            ({"format": HISTORY_FORMAT, "entries": [good, dict(good, seq=1)], "next_seq": 3}, "history-schema"),
            ({"format": HISTORY_FORMAT, "entries": [good, dict(good, seq=2, next_seq=3)], "next_seq": 4}, "history-schema"),
            # seq < 1 / non-int
            ({"format": HISTORY_FORMAT, "entries": [dict(good, seq=0)], "next_seq": 1}, "history-schema"),
            ({"format": HISTORY_FORMAT, "entries": [dict(good, seq="1")], "next_seq": 2}, "history-schema"),
            # outcome not in the set
            ({"format": HISTORY_FORMAT, "entries": [dict(good, outcome="bogus")], "next_seq": 2}, "history-schema"),
            # error entry without check / success entry with check
            ({"format": HISTORY_FORMAT, "entries": [dict(good, outcome="error")], "next_seq": 2}, "history-schema"),
            ({"format": HISTORY_FORMAT, "entries": [dict(good, check="x")], "next_seq": 2}, "history-schema"),
            # error entry with blank check
            ({"format": HISTORY_FORMAT, "entries": [dict(good, outcome="error", check="")], "next_seq": 2}, "history-schema"),
            # non-contract entry keys
            ({"format": HISTORY_FORMAT, "entries": [dict(good, description="x")], "next_seq": 2}, "history-schema"),
            # stored mode/params violating the definition contract
            ({"format": HISTORY_FORMAT, "entries": [dict(good, mode="Q0-nope")], "next_seq": 2}, "history-invalid"),
            ({"format": HISTORY_FORMAT,
              "entries": [dict(good, mode="Q3-instrument", params={"symbol": "X"})], "next_seq": 2}, "history-invalid"),
        ]
        for document, wanted in cases:
            self.write_hist_doc(document)
            self.assertHistRaises(load_history, self.hist, check=wanted)

    def test_invalid_record_rejected_without_partial_publication(self):
        from serving.saved import SavedQueryError

        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        before = self.store_files()
        with self.assertRaises(SavedQueryError):
            record_execution(
                self.hist, "Q2-date-range", {"date_from": "2016-13-01", "date_to": "2016-01-05"},
                self.handle, self.state,
            )
        self.assertEqual(self.store_files(), before)
        self.assertEqual([e["seq"] for e in list_history(self.hist)], [1])

    def test_baseline_state_failure_publishes_no_entry(self):
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        before = self.store_files()
        from serving.index import ServingIndexError

        with self.assertRaises(ServingIndexError):
            record_execution(self.hist, "Q8-data-quality", {}, self.handle, os.path.join(self.root, "missing-state"), m2=False)
        # no derived-state root at missing-state -> no execution completed -> no entry
        self.assertEqual(self.store_files(), before)


class LifecycleTests(HistoryBase):
    """list / show / delete semantics; explicit deletion only."""

    def test_list_show_delete(self):
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        record_execution(self.hist, "Q9-archive-inventory", {}, self.handle, self.state)
        self.assertEqual([e["seq"] for e in list_history(self.hist)], [1, 2])
        self.assertEqual(get_history(self.hist, 2), list_history(self.hist)[1])
        delete_history(self.hist, 1)
        self.assertEqual([e["seq"] for e in list_history(self.hist)], [2])
        self.assertHistRaises(get_history, self.hist, 1, check="history-not-found")
        self.assertHistRaises(delete_history, self.hist, 1, check="history-not-found")

    def test_delete_unknown_seq_fails_closed(self):
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        before = self.store_files()
        self.assertHistRaises(delete_history, self.hist, 99, check="history-not-found")
        self.assertEqual(self.store_files(), before)


class IsolationTests(HistoryBase):
    """History vs saved state vs derived state vs the qualified package."""

    def test_same_root_record_fails_closed(self):
        with self.assertRaises(HistoryError) as ctx:
            record_execution(self.state, "Q8-data-quality", {}, self.handle, self.state)
        self.assertEqual(ctx.exception.check, "history-state-conflict")

    def test_saved_state_unchanged_by_history_operations(self):
        create_saved(self.saved, "q3", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        before = self.store_files(self.saved)
        record_execution(self.hist, "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"}, self.handle, self.state)
        record_execution(self.hist, "Q4-filter", {"filters": {"bogus": "x"}}, self.handle, self.state)
        list_history(self.hist)
        delete_history(self.hist, 1)
        self.assertEqual(self.store_files(self.saved), before)

    def test_rebuild_leaves_history_unchanged(self):
        record_execution(self.hist, "Q8-data-quality", {}, self.handle, self.state)
        before = self.store_files()
        rebuild_state(self.handle, self.state)
        self.assertEqual(self.store_files(), before)
        self.assertEqual(len(list_history(self.hist)), 1)

    def test_package_bytes_unchanged_after_history_operations(self):
        before = self.package_digests()
        record_execution(self.hist, "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"}, self.handle, self.state)
        record_execution(self.hist, "Q4-filter", {"filters": {"bogus": "x"}}, self.handle, self.state)
        list_history(self.hist)
        get_history(self.hist, 1)
        delete_history(self.hist, 2)
        self.assertHistRaises(get_history, self.hist, 99)
        self.assertEqual(self.package_digests(), before)

    def test_existing_query_and_saved_behavior_intact(self):
        # spot-checks that the D38 surface is unchanged
        entry, output, _detail, _digest = record_execution(
            self.hist, "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"}, self.handle, self.state
        )
        direct = query_instrument(self.handle, self.index, "RELIANCE", "EQ")
        self.assertEqual(output, {"query": "Q3-instrument", "result_count": len(direct), "rows": list(direct)})
        create_saved(self.saved, "q3", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        self.assertEqual(execute_saved(self.saved, "q3", self.handle, self.state), output)


class HistoryCliTests(HistoryBase):
    """CLI surface: record/list/show/delete; exit codes; output contract."""

    def test_cli_record_success_includes_query_output(self):
        code, out = self.run_cli(
            "history", "record", "--package", self.pkg, "--state", self.state,
            "--history-state", self.hist, "--mode", "Q3-instrument",
            "--symbol", "RELIANCE", "--series", "EQ",
        )
        self.assertEqual(code, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["result"], "recorded")
        self.assertEqual(parsed["outcome"], "success")
        self.assertEqual(parsed["entry"]["seq"], 1)
        self.assertEqual(parsed["query"]["query"], "Q3-instrument")
        self.assertGreater(parsed["query"]["result_count"], 0)
        self.assertEqual(parsed["store_sha256"], self.store_files()[HISTORY_FILENAME])

    def test_cli_record_error_outcome_is_data_not_failure(self):
        code, out = self.run_cli(
            "history", "record", "--package", self.pkg, "--state", self.state,
            "--history-state", self.hist, "--mode", "Q4-filter", "--field", "bogus=x",
        )
        self.assertEqual(code, 0)  # the ENTRY was durably recorded
        parsed = json.loads(out)
        self.assertEqual(parsed["result"], "recorded")
        self.assertEqual(parsed["outcome"], "error")
        self.assertEqual(parsed["entry"]["check"], "query-input")
        self.assertIn("detail", parsed)
        self.assertNotIn("query", parsed)
        (entry,) = list_history(self.hist)
        self.assertEqual(entry["outcome"], "error")

    def test_cli_record_invalid_description_exits_2_no_entry(self):
        code, out = self.run_cli(
            "history", "record", "--package", self.pkg, "--state", self.state,
            "--history-state", self.hist, "--mode", "Q0-nope",
        )
        self.assertEqual(code, 2)
        self.assertIn("saved-query-invalid", json.loads(out)["detail"])
        self.assertEqual(self.store_files(), {})

    def test_cli_list_show_delete_flow(self):
        self.run_cli("history", "record", "--package", self.pkg, "--state", self.state,
                     "--history-state", self.hist, "--mode", "Q8-data-quality")
        code, out = self.run_cli("history", "list", "--history-state", self.hist)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["count"], 1)
        code, out = self.run_cli("history", "show", "--history-state", self.hist, "--seq", "1")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["entry"]["mode"], "Q8-data-quality")
        code, out = self.run_cli("history", "delete", "--history-state", self.hist, "--seq", "1")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["seq"], 1)
        code, out = self.run_cli("history", "show", "--history-state", self.hist, "--seq", "1")
        self.assertEqual(code, 2)
        self.assertIn("history-not-found", json.loads(out)["detail"])

    def test_cli_exit_codes(self):
        code, out = self.run_cli("history", "list", "--history-state", os.path.join(self.root, "none"))
        self.assertEqual(code, 3)
        self.assertIn("history-missing", json.loads(out)["detail"])
        code, out = self.run_cli(
            "history", "record", "--package", self.pkg, "--state", self.state,
            "--history-state", self.state, "--mode", "Q8-data-quality",
        )
        self.assertEqual(code, 3)
        self.assertIn("history-state-conflict", json.loads(out)["detail"])
