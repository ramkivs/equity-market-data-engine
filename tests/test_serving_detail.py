"""Serving slice — Q7 record detail (D16-10 Q7; D23 §18 items 4/8/10).

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
from serving.archive import parse_input_manifest
from serving.baseline import Baseline, open_baseline
from serving.detail import (
    RECORD_DETAIL_QUERY_ID,
    parse_reconciliation,
    query_record_detail,
)
from serving.index import build_index
from serving.query import QueryError, query_date_range, query_instrument


def _stored_lines(package: str, relative: str):
    with open(os.path.join(package, relative.replace("/", os.sep)), "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class DetailBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d31-serving-detail-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]
        self.handle = open_baseline(self.pkg, spec=self.spec)
        self.index = build_index(self.handle)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # -- ground-truth accessors (as-published package content) --------------
    def stored_row(self, source_file, line_number):
        for row in _stored_lines(self.pkg, source_file):
            if row.get("source_line_number") == line_number:
                return row
        raise AssertionError("stored row not found: %s:%s" % (source_file, line_number))

    def stored_manifest(self):
        return _stored_lines(self.pkg, "INPUT_MANIFEST.jsonl")

    def stored_reconciliation(self):
        return _stored_lines(self.pkg, "RECONCILIATION.jsonl")

    def row_by(self, **envelope):
        """One Q3 result row selected by its envelope fields (test-only)."""
        rows = query_instrument(
            self.handle, self.index, envelope["symbol"], envelope["series"], year=envelope.get("year")
        )
        matches = [row for row in rows if all(row["serving"].get(key) == value for key, value in envelope.items() if key in row["serving"])]
        self.assertEqual(len(matches), 1, "expected exactly one row for %s" % envelope)
        return matches[0]

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
        for dirpath, dirnames, filenames in os.walk(variant):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, variant).replace(os.sep, "/")
                if relative in ("PACKAGE_MANIFEST.sha256", "RUN_COMPLETE.json"):
                    continue
                total_bytes += os.path.getsize(full)
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
        return replace(self.spec, manifest_sha256=manifest_digest, total_bytes=total_bytes)

    def open_variant(self, variant, spec):
        return open_baseline(variant, spec=spec)

    def variant_index(self, variant, handle):
        return build_index(handle)

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


class Q7RecordDetailTests(DetailBase):
    def test_row_selection_and_detail_response(self):
        row = self.row_by(symbol="RELIANCE", series="EQ", year=2016, source_file="partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl")
        detail = query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        self.assertEqual(detail["query"], RECORD_DETAIL_QUERY_ID)
        stored = self.stored_row(row["serving"]["source_file"], row["source_line_number"])
        for key, value in stored.items():
            if key == "raw_line":
                continue
            self.assertEqual(detail["row"][key], value)
        self.assertEqual(detail["row"]["business_date"], "2016-01-04")

    def test_provenance_and_envelope_preserved(self):
        row = self.row_by(symbol="RELIANCE", series="EQ", year=2016, source_file="partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl")
        detail = query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        stored = self.stored_row(row["serving"]["source_file"], row["source_line_number"])
        self.assertEqual(detail["row"]["provenance"], stored["provenance"])
        envelope = detail["row"]["serving"]
        self.assertEqual(envelope["query"], RECORD_DETAIL_QUERY_ID)
        self.assertEqual(envelope["source_file"], row["serving"]["source_file"])
        self.assertEqual(envelope["source_file_family"], "legacy13")
        self.assertEqual(envelope["source_file_year"], "2016")
        self.assertEqual(envelope["source_line_number"], row["source_line_number"])

    def test_archive_join_correct(self):
        row = self.row_by(symbol="RELIANCE", series="EQ", year=2016, source_file="partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl")
        detail = query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        stored_records = self.stored_manifest()
        self.assertEqual(detail["archive"], stored_records[0])  # as published, verbatim
        prov = row["provenance"]
        archive = detail["archive"]
        self.assertEqual(archive["file_name"], prov["source_archive"])
        self.assertEqual(archive["member_name"], prov["member_name"])
        self.assertEqual(archive["archive_sha256_d01"], prov["archive_sha256"])

    def test_reconciliation_association(self):
        row = self.row_by(symbol="RELIANCE", series="EQ", year=2016, source_file="partitions/legacy13/2016/rows/fix-leg-2016-01-05.csv.rows.jsonl")
        detail = query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        expected = [
            record
            for record in self.stored_reconciliation()
            if record["input_identity"]["scope"] == "member"
            and record["input_identity"]["relative_path"] == "fix-leg-2016-01-05.csv"
        ]
        self.assertEqual(len(expected), 1)
        self.assertEqual(detail["reconciliation"], expected)
        for record in detail["reconciliation"]:
            for key in ("tier", "tier_description", "check", "input_identity", "comparison_basis",
                        "governing_definition", "expected", "observed", "delta", "result",
                        "disposition", "unresolved_state", "note"):
                self.assertIn(key, record)

    def test_multiple_reconciliation_records_for_one_archive(self):
        row = self.row_by(symbol="RELIANCE", series="EQ", year=2016, source_file="partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl")
        detail = query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        expected = [
            record
            for record in self.stored_reconciliation()
            if record["input_identity"]["scope"] == "member"
            and record["input_identity"]["relative_path"] == "fix-leg-2016-01-04.csv"
        ]
        self.assertEqual(len(expected), 2)
        self.assertEqual(detail["reconciliation"], expected)  # order preserved, as published

    def test_archive_without_reconciliation_records(self):
        source_file = "partitions/udiff34/2024/rows/fix-udf-2024-03-05.csv.rows.jsonl"
        first = self.stored_row(source_file, 2)
        detail = query_record_detail(self.handle, self.index, source_file, first["source_line_number"])
        self.assertEqual(detail["reconciliation"], [])
        # and the join still succeeds for that archive
        self.assertEqual(detail["archive"]["member_name"], "fix-udf-2024-03-05.csv")

    def test_unknown_row_identity(self):
        with self.assertRaises(QueryError) as ctx:
            query_record_detail(self.handle, self.index, "partitions/legacy13/2016/rows/nope.csv.rows.jsonl", 1)
        self.assertEqual(ctx.exception.check, "record-detail")
        source_file = "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl"
        with self.assertRaises(QueryError) as ctx:
            query_record_detail(self.handle, self.index, source_file, 99999)
        self.assertEqual(ctx.exception.check, "record-detail")

    def test_input_validation_fails_closed(self):
        source_file = "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl"
        for bad_file, bad_line in (("", 1), (source_file, 0), (source_file, True), (None, 1)):
            with self.assertRaises(QueryError) as ctx:
                query_record_detail(self.handle, self.index, bad_file, bad_line)
            self.assertEqual(ctx.exception.check, "record-input")

    def test_ambiguous_identity_fails_closed(self):
        variant = self.copy_variant("pkg-ambiguous")
        manifest_path = os.path.join(variant, "INPUT_MANIFEST.jsonl")
        with open(manifest_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        duplicate = json.loads(lines[0])  # same (file_name, member_name, archive_sha256_d01) triple
        with open(manifest_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("\n".join([lines[0], json.dumps(duplicate)] + lines[1:]) + "\n")
        handle = self.open_variant(variant, self.resign_package(variant))
        index = self.variant_index(variant, handle)
        with self.assertRaises(QueryError) as ctx:
            query_record_detail(handle, index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2)
        self.assertEqual(ctx.exception.check, "record-detail")
        self.assertIn("ambiguous", ctx.exception.detail)

    def test_inconsistent_family_fails_closed(self):
        variant = self.copy_variant("pkg-family-mismatch")
        manifest_path = os.path.join(variant, "INPUT_MANIFEST.jsonl")
        with open(manifest_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        record = json.loads(lines[0])
        record["engine_family"] = "udiff34"
        with open(manifest_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(record) + "\n" + "\n".join(lines[1:]) + "\n")
        handle = self.open_variant(variant, self.resign_package(variant))
        index = self.variant_index(variant, handle)
        with self.assertRaises(QueryError) as ctx:
            query_record_detail(handle, index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2)
        self.assertEqual(ctx.exception.check, "record-detail")
        self.assertIn("inconsistent", ctx.exception.detail)

    def test_malformed_reconciliation_fails_closed(self):
        # case 1: unparseable line
        bad1 = self.copy_variant("pkg-recon-bad1")
        path = os.path.join(bad1, "RECONCILIATION.jsonl")
        with open(path, "r", encoding="utf-8") as handle:
            first_line = handle.readline()
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(first_line + "{not-json\n")
        handle = self.open_variant(bad1, self.resign_package(bad1))
        with self.assertRaises(QueryError) as ctx:
            query_record_detail(handle, self.variant_index(bad1, handle), "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2)
        self.assertEqual(ctx.exception.check, "reconciliation-scan")
        # case 2: missing contract key
        bad2 = self.copy_variant("pkg-recon-bad2")
        path = os.path.join(bad2, "RECONCILIATION.jsonl")
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        record = json.loads(lines[0])
        record.pop("check", None)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(record) + "\n" + "\n".join(lines[1:]) + "\n")
        handle = self.open_variant(bad2, self.resign_package(bad2))
        with self.assertRaises(QueryError) as ctx:
            query_record_detail(handle, self.variant_index(bad2, handle), "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2)
        self.assertEqual(ctx.exception.check, "reconciliation-scan")
        # case 3: input_identity not a record
        bad3 = self.copy_variant("pkg-recon-bad3")
        path = os.path.join(bad3, "RECONCILIATION.jsonl")
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        record = json.loads(lines[0])
        record["input_identity"] = "not-a-scope"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(record) + "\n" + "\n".join(lines[1:]) + "\n")
        handle = self.open_variant(bad3, self.resign_package(bad3))
        with self.assertRaises(QueryError) as ctx:
            query_record_detail(handle, self.variant_index(bad3, handle), "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2)
        self.assertEqual(ctx.exception.check, "reconciliation-scan")

    def test_malformed_manifest_fails_closed_via_reused_q9_parser(self):
        variant = self.copy_variant("pkg-manifest-bad")
        path = os.path.join(variant, "INPUT_MANIFEST.jsonl")
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        record = json.loads(lines[0])
        record.pop("rows", None)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(record) + "\n" + "\n".join(lines[1:]) + "\n")
        handle = self.open_variant(variant, self.resign_package(variant))
        with self.assertRaises(QueryError) as ctx:
            query_record_detail(handle, self.variant_index(variant, handle), "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2)
        self.assertEqual(ctx.exception.check, "input-manifest-scan")
        # the same check is exercised by the shared parser itself
        with self.assertRaises(QueryError):
            parse_input_manifest(handle)

    def test_null_and_as_published_values_preserved(self):
        # the WIPRO row (source_line_number 4) has a blank ISIN column, a
        # as-published empty normalisation, and many null fields — all must
        # pass through untouched (neither defaulted, normalised, nor dropped)
        source_file = "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl"
        stored = self.stored_row(source_file, 4)
        detail = query_record_detail(self.handle, self.index, source_file, 4)
        self.assertEqual(detail["row"]["source_values"], stored["source_values"])
        self.assertEqual(detail["row"]["source_values"]["security_isin"], "")
        self.assertIsNone(detail["row"]["source_values"]["instrument_type"])  # null preserved
        self.assertEqual(detail["row"]["isin_normalized"], stored["isin_normalized"])
        self.assertEqual(detail["row"]["raw_biz_dt"], stored["raw_biz_dt"])

    def test_raw_line_excluded(self):
        row = self.row_by(symbol="RELIANCE", series="EQ", year=2016, source_file="partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl")
        stored = self.stored_row(row["serving"]["source_file"], row["source_line_number"])
        self.assertIn("raw_line", stored)
        detail = query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        self.assertNotIn("raw_line", detail["row"])
        self.assertNotIn(stored["raw_line"], json.dumps(detail, sort_keys=True))

    def test_deterministic_output(self):
        row = self.row_by(
            symbol="TCS",
            series="EQ",
            year=2016,
            source_file="partitions/legacy13/2016/rows/fix-leg-2016-01-05.csv.rows.jsonl",
        )
        first = query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        second = query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_q2_q3_unchanged_after_detail(self):
        q3_before = query_instrument(self.handle, self.index, "RELIANCE", "EQ")
        q2_before = query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06")
        row = q3_before[0]
        query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        self.assertEqual(json.dumps(q3_before, sort_keys=True), json.dumps(query_instrument(self.handle, self.index, "RELIANCE", "EQ"), sort_keys=True))
        self.assertEqual(json.dumps(q2_before, sort_keys=True), json.dumps(query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06"), sort_keys=True))

    def test_package_byte_identity(self):
        before = self.package_digests()
        row = self.row_by(
            symbol="RELIANCE",
            series="EQ",
            year=2016,
            source_file="partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl",
        )
        query_record_detail(self.handle, self.index, row["serving"]["source_file"], row["source_line_number"])
        with self.assertRaises(QueryError):
            query_record_detail(self.handle, self.index, row["serving"]["source_file"], 99999)
        self.assertEqual(before, self.package_digests())


class Q7ReconciliationFixtureTests(DetailBase):
    """The fixture RECONCILIATION records must follow the runner's schema."""

    def test_fixture_reconciliation_schema(self):
        records = self.stored_reconciliation()
        self.assertEqual(len(records), 4)  # 2 + 1 + 1 + 0 across the four members
        for record in records:
            for key in ("tier", "tier_description", "check", "input_identity", "comparison_basis",
                        "governing_definition", "expected", "observed", "delta", "result",
                        "disposition", "unresolved_state", "note"):
                self.assertIn(key, record)
            self.assertEqual(record["input_identity"]["scope"], "member")
            self.assertEqual(record["input_identity"]["member_name"], record["input_identity"]["relative_path"])
        by_member = {}
        for record in records:
            by_member[record["input_identity"]["relative_path"]] = by_member.get(record["input_identity"]["relative_path"], 0) + 1
        self.assertEqual(by_member.get("fix-udf-2024-03-05.csv", 0), 0)  # no-record member
        self.assertEqual(by_member.get("fix-leg-2016-01-04.csv"), 2)  # multi-record member


class Q7MetadataParsersTests(DetailBase):
    def test_parse_reconciliation_empty_is_valid(self):
        variant = self.copy_variant("pkg-recon-empty")
        path = os.path.join(variant, "RECONCILIATION.jsonl")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("")
        handle = self.open_variant(variant, self.resign_package(variant))
        self.assertEqual(parse_reconciliation(handle), [])
        # and Q7 serves an empty reconciliation list for every archive
        source_file = "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl"
        detail = query_record_detail(handle, self.variant_index(variant, handle), source_file, 2)
        self.assertEqual(detail["reconciliation"], [])


if __name__ == "__main__":
    unittest.main()
