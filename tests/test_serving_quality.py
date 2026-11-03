"""Serving slice — Q8 data-quality views (D16-10 Q8; D23 §18 items 4/8/10).

All cases run against the synthetic fixture package (tests/serving_fixtures.py)
— never against, and never represented as, the qualified M2 baseline. The
real-package leg is D24_M2_ROOT-gated in tests/test_serving_m2_integration.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from dataclasses import replace

from tests import serving_fixtures
from serving.archive import query_archive_inventory
from serving.baseline import Baseline, open_baseline
from serving.detail import query_record_detail
from serving.index import (
    INDEX_DIGEST_FILENAME,
    INDEX_FILENAME,
    INDEX_FORMAT,
    ServingIndexError,
    build_index,
    canonical_json,
    load_index,
    write_index,
)
from serving.quality import DATA_QUALITY_QUERY_ID, parse_unresolved, query_data_quality
from serving.query import QueryError, query_date_range, query_instrument

GOVERNED_FLAG_NAMES = (
    "isin_invalid_checkdigit",
    "isin_invalid_length",
    "row_fieldcount_mismatch",
    "date_source_conflict",
    "bizdt_ne_traddt",
    "orphan_no_base_row",
    "overlay_qty_gt_base",
)


def _stored_lines(package: str, relative: str):
    with open(os.path.join(package, relative.replace("/", os.sep)), "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class QualityBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d32-serving-quality-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]
        self.handle = open_baseline(self.pkg, spec=self.spec)
        self.index = build_index(self.handle)
        self.state = os.path.join(self.root, "state")
        write_index(self.state, self.index)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # -- variant package helpers (test-only re-signing) ----------------------
    def copy_variant(self, name):
        variant = os.path.join(self.root, name)
        shutil.copytree(self.pkg, variant)
        return variant

    def resign_package(self, variant: str):
        manifest_path = os.path.join(variant, "PACKAGE_MANIFEST.sha256")
        marker_path = os.path.join(variant, "RUN_COMPLETE.json")

        def sha(path):
            with open(path, "rb") as handle:
                return hashlib.sha256(handle.read()).hexdigest()

        entries = []
        total_bytes = 0
        file_count = 0
        for dirpath, dirnames, filenames in os.walk(variant):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, variant).replace(os.sep, "/")
                if relative in ("PACKAGE_MANIFEST.sha256", "RUN_COMPLETE.json"):
                    continue
                total_bytes += os.path.getsize(full)
                file_count += 1
                entries.append("%s  %s" % (sha(full), relative))
        manifest_text = "".join(line + "\n" for line in sorted(entries))
        with open(manifest_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(manifest_text)
        manifest_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
        with open(marker_path, "r", encoding="utf-8") as handle:
            marker = json.load(handle)
        marker["package_manifest_sha256"] = manifest_digest
        marker_text = json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n"
        with open(marker_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(marker_text)
        total_bytes += len(manifest_text.encode("utf-8")) + len(marker_text.encode("utf-8"))
        file_count += 2  # manifest + marker (the pinned count includes both)
        return replace(
            self.spec,
            manifest_sha256=manifest_digest,
            total_bytes=total_bytes,
            file_count=file_count,
        )

    def open_variant(self, variant, spec):
        return open_baseline(variant, spec=spec)

    def package_digests(self):
        digests = {}
        for dirpath, dirnames, filenames in os.walk(self.pkg):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, self.pkg).replace(os.sep, "/")
                with open(full, "rb") as handle:
                    digests[relative] = hashlib.sha256(handle.read()).hexdigest()
        return digests


class Q8FlagCensusTests(QualityBase):
    def test_flag_census_counts_governed_flags(self):
        # the fixture carries two deliberate data-quality rows: TCS 2016-01-04
        # (ISIN fails the mod-10 check digit) and TCS 2016-01-05 (ISIN invalid
        # length) — every other row is flag-free
        self.assertEqual(self.index["flag_census"], {"isin_invalid_checkdigit": 1, "isin_invalid_length": 1})
        result = query_data_quality(self.handle, self.index)
        self.assertEqual(result["query"], DATA_QUALITY_QUERY_ID)
        self.assertEqual(result["flag_census"], {"isin_invalid_checkdigit": 1, "isin_invalid_length": 1})
        for name in result["flag_census"]:
            self.assertIn(name, GOVERNED_FLAG_NAMES)

    def test_census_rows_match_canonical_rows(self):
        # cross-check the census against the stored rows' flag fields directly
        flagged = 0
        for relative in self.handle.row_files():
            for row in _stored_lines(self.pkg, relative):
                flagged += len(row.get("flags", []))
        self.assertEqual(sum(self.index["flag_census"].values()), flagged)
        self.assertEqual(flagged, 2)

    def test_deterministic_census_and_rebuild(self):
        rebuilt = build_index(self.handle)
        self.assertEqual(rebuilt, self.index)
        self.assertEqual(write_index(self.state, rebuilt), write_index(self.state, self.index))
        first = query_data_quality(self.handle, self.index)
        second = query_data_quality(self.handle, self.index)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_index_format_and_old_format_refusal(self):
        document, _digest = load_index(self.state, self.handle)
        self.assertEqual(document["format"], INDEX_FORMAT)
        self.assertEqual(INDEX_FORMAT, "serving-index/1.2")
        self.assertIn("flag_census", document)
        # a 1.1 document (no flag census) must be refused, fail closed
        old = json.loads(json.dumps(document))
        old["format"] = "serving-index/1.1"
        old.pop("flag_census", None)
        text = canonical_json(old) + "\n"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with open(os.path.join(self.state, INDEX_FILENAME), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        with open(os.path.join(self.state, INDEX_DIGEST_FILENAME), "w", encoding="utf-8", newline="") as handle:
            handle.write("%s  %s\n" % (digest, INDEX_FILENAME))
        with self.assertRaises(ServingIndexError) as ctx:
            load_index(self.state, self.handle)
        self.assertEqual(ctx.exception.check, "index-load")

    def test_stale_index_still_refused(self):
        variant = self.copy_variant("pkg-stale")
        path = os.path.join(variant, "RECONCILIATION.jsonl")
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write("{}\n")  # breaks the 14-key contract; content change only
        handle = self.open_variant(variant, self.resign_package(variant))
        with self.assertRaises(ServingIndexError) as ctx:
            load_index(self.state, handle)
        self.assertEqual(ctx.exception.check, "index-stale")


class Q8QuarantineTests(QualityBase):
    def test_quarantine_zero_preserved(self):
        result = query_data_quality(self.handle, self.index)
        self.assertEqual(result["quarantine"], {"count": 0})
        self.assertEqual(self.handle.run_record["counts"]["quarantined"], 0)
        self.assertEqual(self.handle.marker["quarantined"], 0)

    def test_inconsistent_quarantine_counts_fail_closed(self):
        variant = self.copy_variant("pkg-quar-mismatch")
        marker_path = os.path.join(variant, "RUN_COMPLETE.json")
        with open(marker_path, "r", encoding="utf-8") as handle:
            marker = json.load(handle)
        marker["quarantined"] = 3
        with open(marker_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n")
        handle = self.open_variant(variant, self.resign_package(variant))
        with self.assertRaises(QueryError) as ctx:
            query_data_quality(handle, build_index(handle))
        self.assertEqual(ctx.exception.check, "quarantine-count")

    def test_missing_run_record_quarantine_fails_closed(self):
        variant = self.copy_variant("pkg-quar-missing")
        run_record_path = os.path.join(variant, "RUN_RECORD.json")
        with open(run_record_path, "r", encoding="utf-8") as handle:
            run_record = json.load(handle)
        run_record["counts"].pop("quarantined", None)
        with open(run_record_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(run_record, sort_keys=True, separators=(",", ":")) + "\n")
        handle = self.open_variant(variant, self.resign_package(variant))
        with self.assertRaises(QueryError) as ctx:
            query_data_quality(handle, build_index(handle))
        self.assertEqual(ctx.exception.check, "quarantine-count")


class Q8UnresolvedTests(QualityBase):
    def test_absent_unresolved_file_is_a_valid_empty_state(self):
        self.assertFalse(os.path.isfile(os.path.join(self.pkg, "w2", "unresolved.jsonl")))
        self.assertEqual(parse_unresolved(self.handle), [])
        result = query_data_quality(self.handle, self.index)
        self.assertEqual(result["unresolved"], {"present": False, "record_count": 0, "records": []})

    def test_populated_unresolved_served_as_published(self):
        variant = self.copy_variant("pkg-unresolved")
        w2_dir = os.path.join(variant, "w2")
        os.makedirs(w2_dir, exist_ok=True)
        records = [
            {
                "kind": "governance-dependency",
                "dependency_id": "GOV-FIXTURE-1",
                "label": "fixture declared dependency (synthetic)",
                "row_count": 2,
                "state": "unresolved (carried; never resolved by the runner)",
            },
            {
                "kind": "identity-non-promotion",
                "identities": 6,
                "note": "d24 synthetic fixture (never the M2 corpus)",
                "state": "correlation key is not promoted to exchange-authoritative identity",
            },
        ]
        with open(os.path.join(w2_dir, "unresolved.jsonl"), "w", encoding="utf-8", newline="") as handle:
            handle.write("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
        handle = self.open_variant(variant, self.resign_package(variant))
        parsed = parse_unresolved(handle)
        self.assertEqual(parsed, records)
        result = query_data_quality(handle, build_index(handle))
        self.assertEqual(result["unresolved"], {"present": True, "record_count": 2, "records": records})

    def test_malformed_unresolved_fails_closed(self):
        # case 1: unparseable line
        bad1 = self.copy_variant("pkg-unres-bad1")
        os.makedirs(os.path.join(bad1, "w2"), exist_ok=True)
        path = os.path.join(bad1, "w2", "unresolved.jsonl")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write('{not-json\n')
        handle = self.open_variant(bad1, self.resign_package(bad1))
        with self.assertRaises(QueryError) as ctx:
            query_data_quality(handle, build_index(handle))
        self.assertEqual(ctx.exception.check, "unresolved-scan")
        # case 2: record without a kind
        bad2 = self.copy_variant("pkg-unres-bad2")
        os.makedirs(os.path.join(bad2, "w2"), exist_ok=True)
        path = os.path.join(bad2, "w2", "unresolved.jsonl")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write('{"state": "some state"}\n')
        handle = self.open_variant(bad2, self.resign_package(bad2))
        with self.assertRaises(QueryError) as ctx:
            query_data_quality(handle, build_index(handle))
        self.assertEqual(ctx.exception.check, "unresolved-scan")
        # case 3: non-string state
        bad3 = self.copy_variant("pkg-unres-bad3")
        os.makedirs(os.path.join(bad3, "w2"), exist_ok=True)
        path = os.path.join(bad3, "w2", "unresolved.jsonl")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write('{"kind": "governance-dependency", "state": null}\n')
        handle = self.open_variant(bad3, self.resign_package(bad3))
        with self.assertRaises(QueryError) as ctx:
            query_data_quality(handle, build_index(handle))
        self.assertEqual(ctx.exception.check, "unresolved-scan")


class Q8RunnerProducedFileTests(QualityBase):
    """Regression for the TASK64 finding: the D32 Q8 parser was written
    against serving fixtures that never contain ``w2/unresolved.jsonl``, so it
    was never checked against the runner's actual published record set — whose
    terminal ``cross-era-boundary-residual`` record carries no ``state``. This
    test runs the real runner over the authorized fixture corpus and passes
    its output through the Q8 serving parser (fixture only — never the
    qualified M2 baseline)."""

    def test_runner_produced_unresolved_file_passes_the_q8_parser(self):
        from tests.test_i4_runner import RunPackageTests

        tc = RunPackageTests("test_w2_outputs_and_unresolved_state_are_present")
        tc.setUp()
        try:
            corpus = tc.make_corpus()
            out = tc.out_dir()
            code = tc.invoke(corpus.run_args(out))
            self.assertEqual(code, 0, tc.last_stderr)
            self.assertTrue(os.path.isfile(os.path.join(out, "w2", "unresolved.jsonl")))
            baseline = open_baseline(out)  # self-consistency verification
            parsed = parse_unresolved(baseline)
            self.assertTrue(parsed)
            kinds = [record["kind"] for record in parsed]
            # the runner publishes the stateless terminal record last
            self.assertEqual(kinds[-1], "cross-era-boundary-residual")
            self.assertNotIn("state", parsed[-1])
            # every other published record in the file carries a string state
            for record in parsed[:-1]:
                self.assertIsInstance(record.get("state"), str)
            # and the full Q8 view serves the file as published, in file order
            result = query_data_quality(baseline, build_index(baseline))
            self.assertEqual(result["unresolved"], {"present": True, "record_count": len(parsed), "records": parsed})
        finally:
            tc.doCleanups()

    def test_stateless_form_of_other_published_kinds_still_fails_closed(self):
        # the stateless form is authorized ONLY for cross-era-boundary-residual;
        # the same file shape with a different kind must still fail closed
        variant = self.copy_variant("pkg-unres-stateless-other")
        os.makedirs(os.path.join(variant, "w2"), exist_ok=True)
        with open(os.path.join(variant, "w2", "unresolved.jsonl"), "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps({"kind": "governance-dependency", "dependency_id": "X", "row_count": 1}, sort_keys=True) + "\n")
        baseline = self.open_variant(variant, self.resign_package(variant))
        with self.assertRaises(QueryError) as ctx:
            parse_unresolved(baseline)
        self.assertEqual(ctx.exception.check, "unresolved-scan")
        self.assertIn("without a state", str(ctx.exception))

    def test_cross_era_residual_with_non_string_state_fails_closed(self):
        variant = self.copy_variant("pkg-unres-nonstring-state")
        os.makedirs(os.path.join(variant, "w2"), exist_ok=True)
        with open(os.path.join(variant, "w2", "unresolved.jsonl"), "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps({"kind": "cross-era-boundary-residual", "first_date": "2016-01-01", "last_date": "2026-09-18", "note": "n", "state": None}, sort_keys=True) + "\n")
        baseline = self.open_variant(variant, self.resign_package(variant))
        with self.assertRaises(QueryError) as ctx:
            parse_unresolved(baseline)
        self.assertEqual(ctx.exception.check, "unresolved-scan")
        self.assertIn("non-string state", str(ctx.exception))


class Q8ReconciliationTests(QualityBase):
    def test_aggregates_by_result_and_tier(self):
        result = query_data_quality(self.handle, self.index)
        # fixture: 4 records, all tier E, all match
        self.assertEqual(result["reconciliation"], {"record_count": 4, "by_result": {"match": 4}, "by_tier": {"E": 4}})

    def test_aggregates_match_as_published_records(self):
        result = query_data_quality(self.handle, self.index)
        stored = _stored_lines(self.pkg, "RECONCILIATION.jsonl")
        self.assertEqual(result["reconciliation"]["record_count"], len(stored))
        by_result = {}
        by_tier = {}
        for record in stored:
            by_result[record["result"]] = by_result.get(record["result"], 0) + 1
            by_tier[record["tier"]] = by_tier.get(record["tier"], 0) + 1
        self.assertEqual(result["reconciliation"]["by_result"], by_result)
        self.assertEqual(result["reconciliation"]["by_tier"], by_tier)

    def test_empty_reconciliation_is_a_valid_state(self):
        variant = self.copy_variant("pkg-recon-empty")
        with open(os.path.join(variant, "RECONCILIATION.jsonl"), "w", encoding="utf-8", newline="") as handle:
            handle.write("")
        marker_path = os.path.join(variant, "RUN_COMPLETE.json")
        with open(marker_path, "r", encoding="utf-8") as handle:
            marker = json.load(handle)
        marker["reconciliation"] = {"by_result": {}}
        with open(marker_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n")
        handle = self.open_variant(variant, self.resign_package(variant))
        result = query_data_quality(handle, build_index(handle))
        self.assertEqual(result["reconciliation"], {"record_count": 0, "by_result": {}, "by_tier": {}})

    def test_marker_agreement_mismatch_fails_closed(self):
        variant = self.copy_variant("pkg-recon-marker-mismatch")
        marker_path = os.path.join(variant, "RUN_COMPLETE.json")
        with open(marker_path, "r", encoding="utf-8") as handle:
            marker = json.load(handle)
        marker["reconciliation"]["by_result"] = {"match": 99}
        with open(marker_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n")
        handle = self.open_variant(variant, self.resign_package(variant))
        with self.assertRaises(QueryError) as ctx:
            query_data_quality(handle, build_index(handle))
        self.assertEqual(ctx.exception.check, "reconciliation-aggregate")


class Q8ChangedAbsenceTests(QualityBase):
    def test_changed_findings_explicitly_absent(self):
        result = query_data_quality(self.handle, self.index)
        self.assertEqual(
            result["changed"],
            {
                "present": False,
                "status": "absent-in-m2-only-release",
                "findings": [],
                "note": (
                    "D21 CHANGED findings require the class-(3) registry, which does not exist in the "
                    "M2-only release (D21; D22 §6); they are explicitly absent and never fabricated"
                ),
            },
        )


class Q8DisciplineTests(QualityBase):
    def test_canonical_json_deterministic_ordering(self):
        result = query_data_quality(self.handle, self.index)
        text = json.dumps(result, sort_keys=True)
        self.assertEqual(json.dumps(result, sort_keys=True), text)
        self.assertEqual(list(result["flag_census"]), sorted(result["flag_census"]))

    def test_package_byte_identity(self):
        before = self.package_digests()
        query_data_quality(self.handle, self.index)
        with self.assertRaises(QueryError):
            query_data_quality(self.handle, {})
        self.assertEqual(before, self.package_digests())

    def test_existing_query_contracts_unchanged(self):
        q3_before = query_instrument(self.handle, self.index, "RELIANCE", "EQ")
        q2_before = query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06")
        q7_before = query_record_detail(self.handle, self.index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2)
        q9_before = query_archive_inventory(self.handle)
        query_data_quality(self.handle, self.index)
        self.assertEqual(json.dumps(q3_before, sort_keys=True), json.dumps(query_instrument(self.handle, self.index, "RELIANCE", "EQ"), sort_keys=True))
        self.assertEqual(json.dumps(q2_before, sort_keys=True), json.dumps(query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06"), sort_keys=True))
        self.assertEqual(json.dumps(q7_before, sort_keys=True), json.dumps(query_record_detail(self.handle, self.index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2), sort_keys=True))
        self.assertEqual(json.dumps(q9_before, sort_keys=True), json.dumps(query_archive_inventory(self.handle), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
