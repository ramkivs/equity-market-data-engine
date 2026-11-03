"""Serving slice — Q4 exact-value filter query (D16-10 Q4; D23 §18).

All cases run against the synthetic fixture package
(tests/serving_fixtures.py) — never against, and never represented as, the
qualified M2 baseline. The real-package leg is D24_M2_ROOT-gated in
tests/test_serving_m2_integration.py.

Fixture Q4 facts (as-published): all 9 rows carry series='EQ'; the 7 legacy
rows have segment/source/instrument_type ABSENT (None — legacy family); the
2 UDiff rows carry segment='CM', source='NSE', instrument_type='STK'.
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
from serving.baseline import Baseline, BaselineError, open_baseline
from serving.detail import query_record_detail
from serving.index import build_index, write_index
from serving.quality import query_data_quality
from serving.query import (
    FILTER_QUERY_ID,
    Q4_FILTER_FIELDS,
    QueryError,
    query_dataset_summary,
    query_date_range,
    query_filters,
    query_instrument,
)


class FilterBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d34-serving-filter-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]
        self.handle = open_baseline(self.pkg, spec=self.spec)
        self.index = build_index(self.handle)
        self.state = os.path.join(self.root, "state")
        write_index(self.state, self.index)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

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

        # re-sign the per-partition manifests (they pin the partition row
        # files, which the test may have modified) before the package manifest
        manifests_dir = os.path.join(variant, "manifests")
        if os.path.isdir(manifests_dir):
            for name in sorted(os.listdir(manifests_dir)):
                if not name.endswith(".sha256"):
                    continue
                full = os.path.join(manifests_dir, name)
                re_signed = []
                with open(full, "r", encoding="utf-8") as handle:
                    for line in handle:
                        digest, relative = line.rstrip("\n").split("  ", 1)
                        re_signed.append(
                            "%s  %s\n" % (sha(os.path.join(variant, relative.replace("/", os.sep))), relative)
                        )
                with open(full, "w", encoding="utf-8", newline="") as handle:
                    handle.write("".join(re_signed))

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
        spec = replace(
            self.spec,
            manifest_sha256=manifest_digest,
            total_bytes=total_bytes,
            file_count=file_count,
        )
        return open_baseline(variant, spec=spec)


class Q4ExactValueTests(FilterBase):
    def test_field_vocabulary_is_the_governed_one(self):
        self.assertEqual(Q4_FILTER_FIELDS, ("series", "segment", "source", "instrument_type", "symbol"))

    def test_exact_value_match(self):
        rows = query_filters(self.handle, self.index, {"series": "EQ"})
        self.assertEqual(len(rows), 9)
        for row in rows:
            self.assertEqual(row["source_values"]["series"], "EQ")
        self.assertEqual(rows[0]["serving"]["query"], FILTER_QUERY_ID)
        self.assertEqual(rows[0]["serving"]["filters"], {"series": "EQ"})
        for row in rows:
            self.assertNotIn("raw_line", row)

    def test_non_match_for_different_value(self):
        self.assertEqual(query_filters(self.handle, self.index, {"series": "BE"}), ())
        self.assertEqual(query_filters(self.handle, self.index, {"segment": "DM"}), ())
        self.assertEqual(query_filters(self.handle, self.index, {"source": "BSE"}), ())
        self.assertEqual(query_filters(self.handle, self.index, {"instrument_type": "BOND"}), ())

    def test_no_normalisation_or_inference(self):
        # exact as-published equality only: case, whitespace, and family
        # variants never fold together
        self.assertEqual(query_filters(self.handle, self.index, {"series": "eq"}), ())
        self.assertEqual(query_filters(self.handle, self.index, {"series": "EQ "}), ())
        self.assertEqual(query_filters(self.handle, self.index, {"segment": "cm"}), ())
        self.assertEqual(query_filters(self.handle, self.index, {"source": "nse"}), ())

    def test_missing_field_never_matches(self):
        # legacy rows have segment/source/instrument_type absent (None): they
        # can never match, for no requested value
        for value in ("CM", "DM", ""):
            rows = query_filters(self.handle, self.index, {"segment": value})
            for row in rows:
                self.assertEqual(row["format_family"], "udiff34")
        rows = query_filters(self.handle, self.index, {"source": "NSE"})
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["format_family"] == "udiff34" for row in rows))

    def test_absent_vs_blank_distinction(self):
        # a variant package where one UDiff row's segment is exactly blank:
        # blank matches the empty-string request (exact value), and the
        # blanked row no longer matches 'CM'; absent values still match nothing
        variant = self.copy_variant("pkg-blank")
        row_path = os.path.join(variant, "partitions", "udiff34", "2024", "rows", "fix-udf-2024-03-05.csv.rows.jsonl")
        lines = open(row_path, "r", encoding="utf-8").read().splitlines()
        row = json.loads(lines[0])
        self.assertEqual(row["source_values"]["segment"], "CM")
        row["source_values"]["segment"] = ""
        lines[0] = json.dumps(row, sort_keys=True, separators=(",", ":"))
        with open(row_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("\n".join(lines) + "\n")
        handle = self.resign_package(variant)
        index = build_index(handle)
        blank = query_filters(handle, index, {"segment": ""})
        self.assertEqual(len(blank), 1)
        self.assertEqual(blank[0]["source_values"]["segment"], "")
        cm = query_filters(handle, index, {"segment": "CM"})
        self.assertEqual(len(cm), 1)
        self.assertNotEqual(cm[0]["source_values"]["segment"], "")
        # absent (legacy) rows still never match the empty string
        self.assertTrue(all(r["format_family"] == "udiff34" for r in blank + cm))


class Q4FamilyAndCompositionTests(FilterBase):
    def test_format_family_specific_fields(self):
        # series applies to both families; the UDiFF-only fields match only
        # where the family stores them
        series_rows = query_filters(self.handle, self.index, {"series": "EQ"})
        self.assertEqual(len(series_rows), 9)
        self.assertEqual({r["format_family"] for r in series_rows}, {"legacy13", "udiff34"})
        for field in ("segment", "source", "instrument_type"):
            rows = query_filters(self.handle, self.index, {field: "CM" if field == "segment" else "NSE" if field == "source" else "STK"})
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r["format_family"] == "udiff34" for r in rows))

    def test_multiple_simultaneous_filters_and_semantics(self):
        rows = query_filters(
            self.handle,
            self.index,
            {"series": "EQ", "segment": "CM", "source": "NSE", "instrument_type": "STK"},
        )
        self.assertEqual(len(rows), 2)
        for row in rows:
            v = row["source_values"]
            self.assertEqual((v["series"], v["segment"], v["source"], v["instrument_type"]), ("EQ", "CM", "NSE", "STK"))
        # AND: one disagreeing field empties the result
        self.assertEqual(
            query_filters(self.handle, self.index, {"segment": "CM", "source": "BSE"}), ()
        )
        # same rows regardless of the (matching) series filter — compare the
        # row content and provenance, not the differing serving envelopes
        combined = query_filters(self.handle, self.index, {"series": "EQ", "segment": "CM"})
        single = query_filters(self.handle, self.index, {"segment": "CM"})
        strip = lambda rows: [
            {key: value for key, value in row.items() if key != "serving"} for row in rows
        ]
        self.assertEqual(strip(combined), strip(single))

    def test_deterministic_result_ordering(self):
        first = query_filters(self.handle, self.index, {"series": "EQ"})
        second = query_filters(self.handle, self.index, {"series": "EQ"})
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        keys = [
            (r.get("business_date") or "", r.get("format_family") or "", r["serving"]["source_file_year"] or "", r["serving"]["source_file"], r.get("source_line_number") or 0)
            for r in first
        ]
        self.assertEqual(keys, sorted(keys))


class Q4FailClosedTests(FilterBase):
    def test_unknown_field_fails_closed(self):
        for field in ("isin", "security_isin", "trading_status", "market_type"):
            with self.assertRaises(QueryError) as ctx:
                query_filters(self.handle, self.index, {field: "X"})
            self.assertEqual(ctx.exception.check, "query-input")
            self.assertIn("unknown Q4 filter field", str(ctx.exception))

    def test_empty_filter_set_fails_closed(self):
        with self.assertRaises(QueryError) as ctx:
            query_filters(self.handle, self.index, {})
        self.assertEqual(ctx.exception.check, "query-input")

    def test_non_string_value_fails_closed(self):
        for value in (1, None, ["EQ"], {"s": "EQ"}):
            with self.assertRaises(QueryError) as ctx:
                query_filters(self.handle, self.index, {"series": value})
            self.assertEqual(ctx.exception.check, "query-input")

    def test_non_dict_filters_fail_closed(self):
        with self.assertRaises(QueryError):
            query_filters(self.handle, self.index, [("series", "EQ")])

    def test_no_partial_output_on_failure(self):
        # the request is fully validated before any row is served
        with self.assertRaises(QueryError):
            query_filters(self.handle, self.index, {"series": "EQ", "bad_field": "X"})
        # a valid request over the same inputs still succeeds (no state change)
        self.assertEqual(len(query_filters(self.handle, self.index, {"series": "EQ"})), 9)

    def test_package_byte_identity(self):
        before = self.package_digests()
        query_filters(self.handle, self.index, {"series": "EQ"})
        try:
            query_filters(self.handle, self.index, {"unknown": "X"})
        except QueryError:
            pass
        self.assertEqual(before, self.package_digests())


class Q4RegressionTests(FilterBase):
    def test_existing_query_contracts_unchanged(self):
        q1_before = query_dataset_summary(self.index)
        q2_before = query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06")
        q3_before = query_instrument(self.handle, self.index, "RELIANCE", "EQ")
        q7_before = query_record_detail(self.handle, self.index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2)
        q8_before = query_data_quality(self.handle, self.index)
        q9_before = query_archive_inventory(self.handle)
        query_filters(self.handle, self.index, {"series": "EQ", "segment": "CM"})
        self.assertEqual(json.dumps(q1_before, sort_keys=True), json.dumps(query_dataset_summary(self.index), sort_keys=True))
        self.assertEqual(json.dumps(q2_before, sort_keys=True), json.dumps(query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06"), sort_keys=True))
        self.assertEqual(json.dumps(q3_before, sort_keys=True), json.dumps(query_instrument(self.handle, self.index, "RELIANCE", "EQ"), sort_keys=True))
        self.assertEqual(
            json.dumps(q7_before, sort_keys=True),
            json.dumps(query_record_detail(self.handle, self.index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2), sort_keys=True),
        )
        self.assertEqual(json.dumps(q8_before, sort_keys=True), json.dumps(query_data_quality(self.handle, self.index), sort_keys=True))
        self.assertEqual(json.dumps(q9_before, sort_keys=True), json.dumps(query_archive_inventory(self.handle), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
