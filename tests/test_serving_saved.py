"""Serving slice — saved-query CRUD (D16-10 item 5; D37-DEC C1(a)/C2(a); D23 §17(c)).

All cases run against the synthetic fixture package (tests/serving_fixtures.py) —
never against, and never represented as, the qualified M2 baseline. The
real-package leg is D24_M2_ROOT-gated in tests/test_serving_m2_integration.py.

Covered contract (docs/architecture/D37_SAVED_QUERY_HISTORY_DECISION.md):

* create / read / list / update (full replacement) / delete — explicit operations,
  stable deterministic identifiers, sorted deterministic listing;
* load-and-execute through the existing Q1–Q10 query layer with EXACT output
  parity to the corresponding CLI query/view commands (no new query semantics);
* fail-closed on corrupt, truncated, unknown-format, non-contract, or unknown-mode
  persisted state; duplicate-identifier and invalid-update handling;
* C1(a): the derived-state rebuild (b) never deletes or alters the saved store
  (distinct root); a same-root run fails closed;
* C2(a): executing a saved query never mutates the store (no history is written —
  history is deferred and has no surface in this slice);
* the qualified package's bytes are unchanged after successful and failed
  saved-query operations.
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

from tests import serving_fixtures, support
from serving import cli as serving_cli
from serving.baseline import open_baseline
from serving.index import (
    build_index,
    canonical_json,
    load_index,
    write_index,
)
from serving.query import (
    query_associations,
    query_calendar,
    query_date_range,
    query_dataset_summary,
    query_filters,
    query_instrument,
    parse_associations,
    parse_calendar,
)
from serving.archive import query_archive_inventory
from serving.detail import query_record_detail
from serving.quality import query_data_quality
from serving.qualification import query_qualification
from serving.rebuild import KNOWN_STATE_FILES, rebuild_state
from serving.index import ServingIndexError
from serving.query import QueryError
from serving.saved import (
    SAVED_DIGEST_FILENAME,
    SAVED_FILENAME,
    SAVED_FORMAT,
    SavedQueryError,
    create_saved,
    delete_saved,
    execute_saved,
    get_saved,
    list_saved,
    load_saved,
    update_saved,
    validate_saved_definition,
)


class SavedBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d38-serving-saved-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]
        self.handle = open_baseline(self.pkg, spec=self.spec)
        self.index = build_index(self.handle)
        self.state = os.path.join(self.root, "state")
        write_index(self.state, self.index)
        self.saved = os.path.join(self.root, "saved-state")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def store_files(self, root=None):
        """{file name: sha256} over the saved-store directory (deterministic map)."""
        root = root or self.saved
        out = {}
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                full = os.path.join(root, name)
                if os.path.isfile(full):
                    with open(full, "rb") as handle:
                        out[name] = hashlib.sha256(handle.read()).hexdigest()
        return out

    def package_digests(self, root=None):
        root = root or self.pkg
        digests = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root)
                with open(full, "rb") as handle:
                    digests[rel] = hashlib.sha256(handle.read()).hexdigest()
        return digests

    def write_store_doc(self, document, root=None):
        """Persist a raw document (bypassing validation) with a correct sidecar."""
        root = root or self.saved
        os.makedirs(root, exist_ok=True)
        text = canonical_json(document) + "\n"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with open(os.path.join(root, SAVED_FILENAME), "w", encoding="utf-8") as handle:
            handle.write(text)
        with open(os.path.join(root, SAVED_DIGEST_FILENAME), "w", encoding="utf-8") as handle:
            handle.write("%s  %s\n" % (digest, SAVED_FILENAME))

    def assertSavedRaises(self, fn, *args, check=None, **kwargs):
        with self.assertRaises(SavedQueryError) as ctx:
            fn(*args, **kwargs)
        if check is not None:
            self.assertEqual(ctx.exception.check, check)
        return ctx.exception

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = serving_cli.main(list(args))
        return code, buf.getvalue()


class SavedStoreLifecycleTests(SavedBase):
    """Create/read/list/update/delete semantics; store integrity; fail-closed load."""

    def test_create_bootstraps_store_and_sidecar(self):
        record, digest = create_saved(self.saved, "q3-rel", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        self.assertEqual(record, {"id": "q3-rel", "mode": "Q3-instrument", "params": {"series": "EQ", "symbol": "RELIANCE"}})
        self.assertEqual(self.store_files(), {SAVED_FILENAME: digest, SAVED_DIGEST_FILENAME: hashlib.sha256(("%s  %s\n" % (digest, SAVED_FILENAME)).encode()).hexdigest()})

    def test_create_read_list_round_trip(self):
        create_saved(self.saved, "q2-jan", "Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"})
        create_saved(self.saved, "q8", "Q8-data-quality", {})
        document = load_saved(self.saved)
        self.assertEqual(document["format"], SAVED_FORMAT)
        self.assertEqual(set(document["queries"]), {"q2-jan", "q8"})
        self.assertEqual(get_saved(self.saved, "q2-jan")["params"], {"date_from": "2016-01-04", "date_to": "2016-01-05"})
        records = list_saved(self.saved)
        self.assertEqual([r["id"] for r in records], ["q2-jan", "q8"])

    def test_listing_is_sorted_by_identifier(self):
        create_saved(self.saved, "zeta", "Q8-data-quality", {})
        create_saved(self.saved, "alpha", "Q9-archive-inventory", {})
        create_saved(self.saved, "mid", "Q10-qualification", {})
        self.assertEqual([r["id"] for r in list_saved(self.saved)], ["alpha", "mid", "zeta"])

    def test_store_bytes_are_deterministic(self):
        other = os.path.join(self.root, "saved-again")
        for root in (self.saved, other):
            create_saved(root, "q2-jan", "Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"})
            create_saved(root, "q3-rel", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        with open(os.path.join(self.saved, SAVED_FILENAME), "rb") as handle:
            a = handle.read()
        with open(os.path.join(other, SAVED_FILENAME), "rb") as handle:
            b = handle.read()
        self.assertEqual(a, b)
        self.assertEqual(self.store_files(), self.store_files(other))

    def test_duplicate_create_fails_closed(self):
        create_saved(self.saved, "dup", "Q8-data-quality", {})
        before = self.store_files()
        self.assertSavedRaises(
            create_saved, self.saved, "dup", "Q9-archive-inventory", {}, check="saved-query-duplicate"
        )
        self.assertEqual(self.store_files(), before)

    def test_update_is_full_replacement(self):
        create_saved(self.saved, "q2-jan", "Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"})
        record, _digest = update_saved(self.saved, "q2-jan", "Q3-instrument", {"symbol": "TCS", "series": "EQ"})
        self.assertEqual(record, {"id": "q2-jan", "mode": "Q3-instrument", "params": {"series": "EQ", "symbol": "TCS"}})
        # the previous range parameters are GONE (no merge)
        self.assertNotIn("date_from", get_saved(self.saved, "q2-jan")["params"])

    def test_update_unknown_identifier_fails_closed(self):
        create_saved(self.saved, "keep", "Q8-data-quality", {})
        before = self.store_files()
        self.assertSavedRaises(
            update_saved, self.saved, "ghost", "Q8-data-quality", {}, check="saved-query-not-found"
        )
        self.assertEqual(self.store_files(), before)

    def test_delete_removes_exactly_one(self):
        create_saved(self.saved, "a", "Q8-data-quality", {})
        create_saved(self.saved, "b", "Q9-archive-inventory", {})
        delete_saved(self.saved, "a")
        self.assertEqual([r["id"] for r in list_saved(self.saved)], ["b"])

    def test_delete_unknown_identifier_fails_closed(self):
        create_saved(self.saved, "a", "Q8-data-quality", {})
        before = self.store_files()
        self.assertSavedRaises(delete_saved, self.saved, "ghost", check="saved-query-not-found")
        self.assertEqual(self.store_files(), before)

    def test_show_and_list_missing_store_fail_closed(self):
        self.assertSavedRaises(get_saved, self.saved, "x", check="saved-query-missing")
        self.assertSavedRaises(list_saved, self.saved, check="saved-query-missing")

    def test_partial_store_fails_closed(self):
        # store file present, sidecar absent: NOT treated as an absent store
        os.makedirs(self.saved, exist_ok=True)
        with open(os.path.join(self.saved, SAVED_FILENAME), "w", encoding="utf-8") as handle:
            handle.write(canonical_json({"format": SAVED_FORMAT, "queries": {}}) + "\n")
        self.assertSavedRaises(list_saved, self.saved, check="saved-query-missing")

    def test_identifier_contract(self):
        for bad in ("UPPER", "-lead", "a" * 65, "", "dot.id", "space id", "tab\tid"):
            self.assertSavedRaises(
                create_saved, self.saved, bad, "Q8-data-quality", {}, check="saved-query-invalid"
            )
        # the contract boundary: 64 chars is legal
        ok = "a" * 64
        create_saved(self.saved, ok, "Q8-data-quality", {})
        self.assertIn(ok, load_saved(self.saved)["queries"])


class SavedPersistedStateFailClosedTests(SavedBase):
    """Corrupt / truncated / incompatible / non-contract persisted state."""

    def test_sidecar_mismatch_fails_closed(self):
        create_saved(self.saved, "a", "Q8-data-quality", {})
        path = os.path.join(self.saved, SAVED_FILENAME)
        with open(path, "rb") as handle:
            data = bytearray(handle.read())
        data[5] ^= 1  # flip one byte of the canonical document
        with open(path, "wb") as handle:
            handle.write(bytes(data))
        self.assertSavedRaises(list_saved, self.saved, check="saved-query-corrupt")

    def test_truncated_sidecar_fails_closed(self):
        create_saved(self.saved, "a", "Q8-data-quality", {})
        path = os.path.join(self.saved, SAVED_DIGEST_FILENAME)
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text[:5])
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-corrupt")

    def test_unparseable_json_fails_closed(self):
        os.makedirs(self.saved, exist_ok=True)
        with open(os.path.join(self.saved, SAVED_FILENAME), "w", encoding="utf-8") as handle:
            handle.write("{not json\n")
        with open(os.path.join(self.saved, SAVED_DIGEST_FILENAME), "w", encoding="utf-8") as handle:
            handle.write("0" * 64 + "  %s\n" % SAVED_FILENAME)
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-corrupt")

    def test_unknown_format_version_fails_closed(self):
        self.write_store_doc({"format": "serving-saved-queries/9.9", "queries": {}})
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-format")

    def test_non_object_document_fails_closed(self):
        os.makedirs(self.saved, exist_ok=True)
        text = canonical_json([1, 2, 3]) + "\n"
        digest = hashlib.sha256(text.encode()).hexdigest()
        with open(os.path.join(self.saved, SAVED_FILENAME), "w", encoding="utf-8") as handle:
            handle.write(text)
        with open(os.path.join(self.saved, SAVED_DIGEST_FILENAME), "w", encoding="utf-8") as handle:
            handle.write("%s  %s\n" % (digest, SAVED_FILENAME))
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-schema")

    def test_noncontract_top_level_keys_fail_closed(self):
        self.write_store_doc({"format": SAVED_FORMAT, "queries": {}, "extra": 1})
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-schema")

    def test_noncontract_record_keys_fail_closed(self):
        self.write_store_doc(
            {
                "format": SAVED_FORMAT,
                "queries": {
                    "a": {"id": "a", "mode": "Q8-data-quality", "params": {}, "description": "x"}
                },
            }
        )
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-schema")

    def test_id_key_mismatch_fails_closed(self):
        self.write_store_doc(
            {"format": SAVED_FORMAT, "queries": {"a": {"id": "b", "mode": "Q8-data-quality", "params": {}}}}
        )
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-schema")

    def test_noncontract_param_keys_fail_closed(self):
        self.write_store_doc(
            {
                "format": SAVED_FORMAT,
                "queries": {
                    "a": {"id": "a", "mode": "Q8-data-quality", "params": {"bogus": "x"}}
                },
            }
        )
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-invalid")

    def test_null_param_value_fails_closed(self):
        self.write_store_doc(
            {
                "format": SAVED_FORMAT,
                "queries": {
                    "a": {"id": "a", "mode": "Q3-instrument", "params": {"symbol": "X", "series": None}}
                },
            }
        )
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-invalid")

    def test_unknown_mode_in_stored_state_fails_closed(self):
        self.write_store_doc(
            {"format": SAVED_FORMAT, "queries": {"a": {"id": "a", "mode": "Q0-nope", "params": {}}}}
        )
        self.assertSavedRaises(load_saved, self.saved, check="saved-query-invalid")


class SavedDefinitionValidationTests(SavedBase):
    """The (mode, params) contract — fail closed on every violation."""

    def test_unknown_mode_rejected(self):
        self.assertSavedRaises(
            validate_saved_definition, "Q0-nope", {}, check="saved-query-invalid"
        )

    def test_param_not_in_mode_contract_rejected(self):
        self.assertSavedRaises(
            validate_saved_definition, "Q6-calendar", {"symbol": "X"}, check="saved-query-invalid"
        )

    def test_missing_required_param_rejected(self):
        self.assertSavedRaises(validate_saved_definition, "Q3-instrument", {"symbol": "X"}, check="saved-query-invalid")
        self.assertSavedRaises(validate_saved_definition, "Q2-date-range", {"date_from": "2016-01-04"}, check="saved-query-invalid")
        self.assertSavedRaises(validate_saved_definition, "Q7-record-detail", {"source_file": "f.csv"}, check="saved-query-invalid")

    def test_q6_one_sided_range_rejected(self):
        self.assertSavedRaises(
            validate_saved_definition, "Q6-calendar", {"date_from": "2016-01-04"}, check="saved-query-invalid"
        )

    def test_bad_date_values_rejected(self):
        for bad in ("2016-1-4", "2016-13-01", "not-a-date", 20160104, None):
            self.assertSavedRaises(
                validate_saved_definition,
                "Q2-date-range",
                {"date_from": bad, "date_to": "2016-01-05"},
                check="saved-query-invalid",
            )

    def test_q4_empty_or_blank_filters_rejected(self):
        self.assertSavedRaises(validate_saved_definition, "Q4-filter", {}, check="saved-query-invalid")
        self.assertSavedRaises(validate_saved_definition, "Q4-filter", {"filters": {}}, check="saved-query-invalid")
        self.assertSavedRaises(validate_saved_definition, "Q4-filter", {"filters": {"series": ""}}, check="saved-query-invalid")

    def test_q5_no_selector_rejected(self):
        self.assertSavedRaises(validate_saved_definition, "Q5-association", {}, check="saved-query-invalid")

    def test_int_params_reject_non_int(self):
        self.assertSavedRaises(
            validate_saved_definition, "Q3-instrument", {"symbol": "X", "series": "EQ", "year": "2016"},
            check="saved-query-invalid",
        )
        self.assertSavedRaises(
            validate_saved_definition, "Q3-instrument", {"symbol": "X", "series": "EQ", "year": True},
            check="saved-query-invalid",
        )
        self.assertSavedRaises(
            validate_saved_definition,
            "Q7-record-detail",
            {"source_file": "f.csv", "source_line_number": "1"},
            check="saved-query-invalid",
        )

    def test_blank_string_params_rejected(self):
        self.assertSavedRaises(
            validate_saved_definition, "Q3-instrument", {"symbol": "", "series": "EQ"}, check="saved-query-invalid"
        )

    def test_cli_blank_value_never_persisted(self):
        code, out = self.run_cli(
            "saved", "save", "--saved-state", self.saved, "--id", "b",
            "--mode", "Q3-instrument", "--symbol", "", "--series", "EQ",
        )
        self.assertEqual(code, 2)
        self.assertIn("saved-query-invalid", json.loads(out)["detail"])
        self.assertEqual(self.store_files(), {})


class SavedExecuteParityTests(SavedBase):
    """Load-and-execute == the corresponding existing query contract, exactly."""

    def _create(self, query_id, mode, params):
        create_saved(self.saved, query_id, mode, params)

    def test_q1_parity(self):
        partition = sorted(self.index["partitions"])[0]  # "LEGACY/2016"
        family = partition.split("/")[0]
        self._create("q1", "Q1-dataset", {"family": family, "year": int(partition.split("/")[1])})
        out = execute_saved(self.saved, "q1", self.handle, self.state)
        expected = query_dataset_summary(self.index, family=family, year=int(partition.split("/")[1]))
        self.assertEqual(out, expected)

    def test_q2_parity(self):
        self._create("q2", "Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"})
        out = execute_saved(self.saved, "q2", self.handle, self.state)
        rows = query_date_range(self.handle, self.index, "2016-01-04", "2016-01-05")
        self.assertEqual(
            out,
            {"query": "Q2-date-range", "date_from": "2016-01-04", "date_to": "2016-01-05",
             "result_count": len(rows), "rows": list(rows)},
        )
        self.assertGreater(len(rows), 0)

    def test_q3_parity_with_year(self):
        self._create("q3", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ", "year": 2016})
        out = execute_saved(self.saved, "q3", self.handle, self.state)
        rows = query_instrument(self.handle, self.index, "RELIANCE", "EQ", year=2016)
        self.assertEqual(out, {"query": "Q3-instrument", "result_count": len(rows), "rows": list(rows)})
        for row in out["rows"]:
            self.assertTrue(row["business_date"].startswith("2016-"))

    def test_q4_parity(self):
        self._create("q4", "Q4-filter", {"filters": {"series": "EQ"}})
        out = execute_saved(self.saved, "q4", self.handle, self.state)
        rows = query_filters(self.handle, self.index, {"series": "EQ"})
        self.assertEqual(
            out,
            {"query": "Q4-filter", "filters": {"series": "EQ"}, "result_count": len(rows), "rows": list(rows)},
        )

    def test_q5_parity_by_identity(self):
        self._create("q5i", "Q5-association", {"security_id": "INE002A01018"})
        out = execute_saved(self.saved, "q5i", self.handle, self.state)
        documents = parse_associations(self.handle)
        rows = query_associations(self.handle, self.index, security_id="INE002A01018", documents=documents)
        self.assertEqual(
            out,
            {"query": "Q5-association", "security_id": "INE002A01018", "series": None, "symbol": None,
             "associations_present": documents is not None, "record_count": len(rows), "records": list(rows)},
        )

    def test_q5_parity_by_symbol_series(self):
        self._create("q5s", "Q5-association", {"symbol": "RELIANCE", "series": "EQ"})
        out = execute_saved(self.saved, "q5s", self.handle, self.state)
        documents = parse_associations(self.handle)
        rows = query_associations(self.handle, self.index, symbol="RELIANCE", series="EQ", documents=documents)
        self.assertEqual(out["record_count"], len(rows))
        self.assertEqual(out["records"], list(rows))

    def test_q6_parity(self):
        # the base fixture carries NO calendar: the absent state is legitimate;
        # parity is asserted against the direct call either way.
        self._create("q6", "Q6-calendar", {})
        out = execute_saved(self.saved, "q6", self.handle, self.state)
        documents = parse_calendar(self.handle)
        rows = query_calendar(self.handle, self.index, documents=documents)
        self.assertEqual(
            out,
            {"query": "Q6-calendar", "date_from": None, "date_to": None,
             "calendar_present": documents is not None, "record_count": len(rows), "records": list(rows)},
        )

    def test_q7_parity(self):
        rows = query_date_range(self.handle, self.index, "2016-01-04", "2016-01-05")
        source_file = rows[0]["serving"]["source_file"]
        line = rows[0]["source_line_number"]
        self._create("q7", "Q7-record-detail", {"source_file": source_file, "source_line_number": line})
        out = execute_saved(self.saved, "q7", self.handle, self.state)
        self.assertEqual(out, query_record_detail(self.handle, self.index, source_file, line))

    def test_q8_parity(self):
        self._create("q8", "Q8-data-quality", {})
        out = execute_saved(self.saved, "q8", self.handle, self.state)
        self.assertEqual(out, query_data_quality(self.handle, self.index))

    def test_q9_parity(self):
        self._create("q9", "Q9-archive-inventory", {})
        out = execute_saved(self.saved, "q9", self.handle, self.state)
        self.assertEqual(out, query_archive_inventory(self.handle, d01=None))

    def test_q10_parity_without_repo(self):
        self._create("q10", "Q10-qualification", {})
        out = execute_saved(self.saved, "q10", self.handle, self.state)
        self.assertEqual(out, query_qualification(self.handle, repo_root=None))
        self.assertFalse(out["evidence"]["repo_root_provided"])

    def test_q10_parity_with_repo(self):
        repo = support.REPO_ROOT
        if not os.path.isdir(os.path.join(repo, "evidence")):
            self.skipTest("in-repository evidence records not present in this checkout")
        self._create("q10r", "Q10-qualification", {"repo": repo})
        out = execute_saved(self.saved, "q10r", self.handle, self.state)
        self.assertEqual(out, query_qualification(self.handle, repo_root=repo))
        self.assertTrue(out["evidence"]["repo_root_provided"])

    def test_run_unknown_identifier_fails_closed(self):
        self._create("q2", "Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"})
        before = self.store_files()
        self.assertSavedRaises(
            execute_saved, self.saved, "ghost", self.handle, self.state, check="saved-query-not-found"
        )
        self.assertEqual(self.store_files(), before)

    def test_execution_never_mutates_the_store(self):
        """C2(a): running a saved query writes nothing to the store (no history)."""
        self._create("q2", "Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"})
        self._create("q3", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        before = self.store_files()
        execute_saved(self.saved, "q2", self.handle, self.state)
        execute_saved(self.saved, "q3", self.handle, self.state)
        execute_saved(self.saved, "q2", self.handle, self.state)  # repeat: still read-only
        try:
            execute_saved(self.saved, "ghost", self.handle, self.state)
        except SavedQueryError:
            pass
        self.assertEqual(self.store_files(), before)

    def test_execution_uses_existing_query_semantics(self):
        """A definition is executed with the mode's EXISTING validation — an
        unknown Q4 field is stored (shape-valid) and fails closed at execution
        with the established Q4 check, never reinterpreted."""
        self._create("q4x", "Q4-filter", {"filters": {"bogus": "x"}})
        with self.assertRaises(QueryError) as ctx:
            execute_saved(self.saved, "q4x", self.handle, self.state)
        self.assertIn("unknown Q4 filter field", str(ctx.exception))


class RebuildIsolationTests(SavedBase):
    """C1(a): the derived-state rebuild never deletes or alters saved queries."""

    def test_rebuild_does_not_touch_saved_store(self):
        create_saved(self.saved, "a", "Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"})
        create_saved(self.saved, "b", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        before = self.store_files()
        report = rebuild_state(self.handle, self.state)
        self.assertEqual(report["identical"], True)
        self.assertEqual(self.store_files(), before)
        self.assertEqual([r["id"] for r in list_saved(self.saved)], ["a", "b"])

    def test_rebuild_known_state_files_unchanged(self):
        # the derived-state rebuild's scope is exactly the two derived files —
        # it cannot reach a distinct saved-store root, and its scope must not
        # grow (D37-DEC §6.4: derived-state behavior preserved).
        self.assertEqual(KNOWN_STATE_FILES, frozenset({"serving_index.json", "serving_index.sha256"}))

    def test_rebuild_still_refuses_unknown_files(self):
        with open(os.path.join(self.state, "foreign.txt"), "w", encoding="utf-8") as handle:
            handle.write("not serving state\n")
        with self.assertRaises(ServingIndexError) as ctx:
            rebuild_state(self.handle, self.state)
        self.assertEqual(ctx.exception.check, "rebuild-refuse")

    def test_same_root_execution_fails_closed(self):
        # Refuse creation in an existing index root as well as execution with
        # equal roots, before either operation can change state.
        from serving.paths import RootLayoutError
        with self.assertRaises(RootLayoutError):
            create_saved(self.state, "q3", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        self.assertSavedRaises(
            execute_saved, self.state, "q3", self.handle, self.state, check="saved-query-conflict"
        )

    def test_cli_run_same_root_exit_3(self):
        code, out = self.run_cli(
            "saved", "run", "--package", self.pkg, "--state", self.state,
            "--saved-state", self.state, "--id", "x",
        )
        self.assertEqual(code, 3)
        self.assertIn("saved-query-conflict", json.loads(out)["detail"])


class PackageImmutabilityTests(SavedBase):
    """The qualified package's bytes are unchanged by saved-query operations."""

    def test_package_bytes_unchanged_after_saved_operations(self):
        before = self.package_digests()
        create_saved(self.saved, "q2", "Q2-date-range", {"date_from": "2016-01-04", "date_to": "2016-01-05"})
        create_saved(self.saved, "q3", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
        get_saved(self.saved, "q2")
        list_saved(self.saved)
        update_saved(self.saved, "q2", "Q3-instrument", {"symbol": "TCS", "series": "EQ"})
        execute_saved(self.saved, "q3", self.handle, self.state)
        # failures: unknown id run, duplicate create, invalid definition
        for failing in (
            lambda: execute_saved(self.saved, "ghost", self.handle, self.state),
            lambda: create_saved(self.saved, "q3", "Q8-data-quality", {}),
            lambda: create_saved(self.saved, "x", "Q0-nope", {}),
        ):
            with self.assertRaises(SavedQueryError):
                failing()
        delete_saved(self.saved, "q2")
        self.assertEqual(self.package_digests(), before)


class SavedCliTests(SavedBase):
    """CLI surface: output parity with the query commands; exit codes; flow."""

    def test_cli_save_run_byte_parity_q3(self):
        self.run_cli(
            "saved", "save", "--saved-state", self.saved, "--id", "q3-rel",
            "--mode", "Q3-instrument", "--symbol", "RELIANCE", "--series", "EQ",
        )
        _c1, direct = self.run_cli("query", "--package", self.pkg, "--state", self.state, "RELIANCE", "EQ")
        code, via_saved = self.run_cli(
            "saved", "run", "--package", self.pkg, "--state", self.state,
            "--saved-state", self.saved, "--id", "q3-rel",
        )
        self.assertEqual(code, 0)
        self.assertEqual(via_saved, direct)  # byte-identical canonical output

    def test_cli_save_run_byte_parity_q2(self):
        self.run_cli(
            "saved", "save", "--saved-state", self.saved, "--id", "q2-r",
            "--mode", "Q2-date-range", "--from", "2016-01-04", "--to", "2016-01-05",
        )
        _c1, direct = self.run_cli(
            "query", "--package", self.pkg, "--state", self.state,
            "--from", "2016-01-04", "--to", "2016-01-05",
        )
        code, via_saved = self.run_cli(
            "saved", "run", "--package", self.pkg, "--state", self.state,
            "--saved-state", self.saved, "--id", "q2-r",
        )
        self.assertEqual(code, 0)
        self.assertEqual(via_saved, direct)

    def test_cli_list_show_sorted_and_exact(self):
        self.run_cli("saved", "save", "--saved-state", self.saved, "--id", "b", "--mode", "Q8-data-quality")
        self.run_cli("saved", "save", "--saved-state", self.saved, "--id", "a", "--mode", "Q9-archive-inventory")
        code, out = self.run_cli("saved", "list", "--saved-state", self.saved)
        self.assertEqual(code, 0)
        listing = json.loads(out)
        self.assertEqual(listing["count"], 2)
        self.assertEqual([q["id"] for q in listing["queries"]], ["a", "b"])
        code, out = self.run_cli("saved", "show", "--saved-state", self.saved, "--id", "a")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["query"], {"id": "a", "mode": "Q9-archive-inventory", "params": {}})

    def test_cli_update_delete_flow(self):
        self.run_cli("saved", "save", "--saved-state", self.saved, "--id", "u",
                     "--mode", "Q2-date-range", "--from", "2016-01-04", "--to", "2016-01-05")
        code, out = self.run_cli(
            "saved", "update", "--saved-state", self.saved, "--id", "u", "--mode", "Q8-data-quality"
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["query"]["mode"], "Q8-data-quality")
        self.assertEqual(json.loads(out)["query"]["params"], {})  # full replacement
        code, out = self.run_cli("saved", "delete", "--saved-state", self.saved, "--id", "u")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["id"], "u")
        code, out = self.run_cli("saved", "delete", "--saved-state", self.saved, "--id", "u")
        self.assertEqual(code, 2)  # second delete: not found
        self.assertIn("saved-query-not-found", json.loads(out)["detail"])

    def test_cli_exit_codes(self):
        # usage-level failures -> 2
        code, out = self.run_cli(
            "saved", "save", "--saved-state", self.saved, "--id", "x",
            "--mode", "Q0-nope",
        )
        self.assertEqual(code, 2)
        self.assertIn("saved-query-invalid", json.loads(out)["detail"])
        code, out = self.run_cli(
            "saved", "save", "--saved-state", self.saved, "--id", "x",
            "--mode", "Q9-archive-inventory", "--symbol", "X",
        )
        self.assertEqual(code, 2)
        self.assertIn("saved-query-invalid", json.loads(out)["detail"])
        code, out = self.run_cli("saved", "show", "--saved-state", os.path.join(self.root, "none"), "--id", "x")
        self.assertEqual(code, 3)  # state-level failure -> 3
        self.assertIn("saved-query-missing", json.loads(out)["detail"])
