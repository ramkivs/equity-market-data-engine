"""Serving slice — Q5 identity/association query (D16-10 Q5; D23 §18).

All cases run against the synthetic fixture package (tests/serving_fixtures.py)
— never against, and never represented as, the qualified M2 baseline. The
real-package leg is D24_M2_ROOT-gated in tests/test_serving_m2_integration.py.

Fixture Q5 facts (the engine's own W2 output over the fixture rows; D05
§3.2/§3.3): five identity documents, in sorted correlation-key order, six
dated-association intervals total:

* INE000000006 (line 1) — TCS legacy 2016-01-04 (invalid-check-digit ISIN kept
  as key; is_valid_isin_format: null), 1 interval TCS/EQ;
* INE002A01018 (line 2) — RELIANCE, 2 intervals: RELIANCE/EQ 2016-01-04…
  2017-02-06 then 500325/EQ 2024-03-05 (UDiff numeric listing symbol; the
  D05 §3.3 contiguous-run rule), is_valid_isin_format: true;
* INE009A01021 (line 3) — INFY, 1 interval INFY/EQ, true;
* INE123 (line 4) — TCS legacy 2016-01-05 (invalid-length ISIN kept as key;
  null validity), 1 interval TCS/EQ;
* INE467B01029 (line 5) — TCS UDiff 2024-03-05, 1 interval 500304/EQ, true;
* WIPRO rows (blank ISIN) — unkeyed, no document.
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
from dataclasses import replace

from tests import serving_fixtures
from serving import cli as serving_cli
from serving.archive import query_archive_inventory
from serving.baseline import open_baseline
from serving.detail import query_record_detail
from serving.index import build_index, write_index
from serving.quality import query_data_quality
from serving.query import (
    ASSOCIATIONS_FILE,
    ASSOCIATIONS_QUERY_ID,
    QueryError,
    parse_associations,
    query_associations,
    query_dataset_summary,
    query_date_range,
    query_filters,
    query_instrument,
)


class Q5Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d35-serving-association-")
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
        """Re-sign a variant package after a test-controlled file change."""
        manifest_path = os.path.join(variant, "PACKAGE_MANIFEST.sha256")
        marker_path = os.path.join(variant, "RUN_COMPLETE.json")

        def sha(path):
            with open(path, "rb") as handle:
                return hashlib.sha256(handle.read()).hexdigest()

        # re-sign the per-partition manifests (they pin the partition row files)
        # before the package manifest
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

    def assoc_variant(self, name, transform):
        """A variant package whose w2/associations.jsonl lines were replaced by
        ``transform(lines)`` (one document per line), re-signed and opened."""
        variant = self.copy_variant(name)
        path = os.path.join(variant, "w2", "associations.jsonl")
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        new_lines = transform(lines)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("".join(line + "\n" for line in new_lines))
        return self.resign_package(variant)

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = serving_cli.main(list(args))
        return code, buf.getvalue()


class Q5IdentityLookupTests(Q5Base):
    """(1) valid identity lookup; (4) unknown identity; (5) null validity;
    (6) absent file vs present-but-empty."""

    def test_valid_identity_lookup_serves_the_published_document(self):
        (doc,) = query_associations(self.handle, self.index, security_id="INE002A01018")
        self.assertEqual(doc["security_id"], "INE002A01018")
        self.assertEqual(doc["identity_basis"], "isin_correlation_key_upper_trim")
        self.assertEqual(doc["is_valid_isin_format"], True)
        self.assertEqual(doc["first_observed"], "2016-01-04")
        self.assertEqual(doc["last_observed"], "2024-03-05")
        self.assertEqual(doc["isin_list"], ["INE002A01018"])
        self.assertIn("non_promotion_note", doc)
        self.assertIn("correlation key", doc["non_promotion_note"])
        self.assertEqual(len(doc["associations"]), 2)
        self.assertEqual(len(doc["provenance"]), 4)  # four distinct members
        serving = doc["serving"]
        self.assertEqual(serving["query"], ASSOCIATIONS_QUERY_ID)
        self.assertEqual(serving["security_id"], "INE002A01018")
        self.assertEqual(serving["source_file"], ASSOCIATIONS_FILE)
        self.assertEqual(serving["source_line_number"], 2)  # second line, sorted keys

    def test_every_fixture_identity_lookup(self):
        for line_number, key, validity in (
            (1, "INE000000006", None),
            (2, "INE002A01018", True),
            (3, "INE009A01021", True),
            (4, "INE123", None),
            (5, "INE467B01029", True),
        ):
            (doc,) = query_associations(self.handle, self.index, security_id=key)
            self.assertEqual(doc["security_id"], key)
            self.assertEqual(doc["is_valid_isin_format"], validity)
            self.assertEqual(doc["serving"]["source_line_number"], line_number)

    def test_unknown_identity_is_empty_not_error(self):
        self.assertEqual(query_associations(self.handle, self.index, security_id="INE999999999"), ())
        # WIPRO never has an identity document (blank ISIN is unkeyed): a symbol
        # is not a selector and no identity is inferred from one
        self.assertEqual(query_associations(self.handle, self.index, security_id="WIPRO"), ())

    def test_no_normalisation_or_inference_of_the_key(self):
        # exact as-published equality only: the key is the normalized ISIN as
        # stored; lower-case / padded variants are different selectors
        self.assertEqual(query_associations(self.handle, self.index, security_id="ine002a01018"), ())
        self.assertEqual(query_associations(self.handle, self.index, security_id="INE002A01018 "), ())
        self.assertEqual(query_associations(self.handle, self.index, security_id="INE002A0101"), ())

    def test_missing_optional_identity_data_is_null_not_false(self):
        (doc,) = query_associations(self.handle, self.index, security_id="INE000000006")
        self.assertIsNone(doc["is_valid_isin_format"])  # UNDETERMINED, never coerced
        (doc,) = query_associations(self.handle, self.index, security_id="INE123")
        self.assertIsNone(doc["is_valid_isin_format"])

    def test_absent_file_is_a_legitimate_state(self):
        variant = self.copy_variant("pkg-no-w2")
        os.remove(os.path.join(variant, "w2", "associations.jsonl"))
        handle = self.resign_package(variant)
        self.assertIsNone(parse_associations(handle))
        self.assertEqual(query_associations(handle, self.index, security_id="INE002A01018"), ())
        self.assertEqual(query_associations(handle, self.index, symbol="TCS", series="EQ"), ())
        variant_state = os.path.join(self.root, "state-no-w2")
        write_index(variant_state, build_index(handle))
        code, out = self.run_cli("query", "--package", variant, "--state", variant_state, "--identity", "INE002A01018")
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertFalse(envelope["associations_present"])
        self.assertEqual(envelope["record_count"], 0)
        self.assertEqual(envelope["records"], [])

    def test_present_but_empty_file_is_distinguished_from_absent(self):
        handle = self.assoc_variant("pkg-empty-w2", lambda lines: [])
        self.assertEqual(parse_associations(handle), [])
        self.assertEqual(query_associations(handle, self.index, security_id="INE002A01018"), ())
        variant_state = os.path.join(self.root, "state-empty-w2")
        write_index(variant_state, build_index(handle))
        code, out = self.run_cli("query", "--package", os.path.join(self.root, "pkg-empty-w2"), "--state", variant_state, "--identity", "INE002A01018")
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertTrue(envelope["associations_present"])
        self.assertEqual(envelope["record_count"], 0)


class Q5InstrumentLookupTests(Q5Base):
    """(2) valid association lookup; (3) multiple records/relationships;
    (12) deterministic ordering."""

    def test_valid_instrument_lookup_returns_the_dated_intervals(self):
        intervals = query_associations(self.handle, self.index, symbol="RELIANCE", series="EQ")
        self.assertEqual([item["symbol"] for item in intervals], ["RELIANCE", "500325"])
        interval = intervals[0]
        self.assertEqual(interval["symbol"], "RELIANCE")
        self.assertEqual(interval["series"], "EQ")
        self.assertEqual(interval["security_id"], "INE002A01018")
        self.assertEqual(interval["observed_from"], "2016-01-04")
        self.assertEqual(interval["observed_to"], "2017-02-06")
        self.assertEqual(interval["interval_basis"], "observed-range")
        self.assertEqual(interval["association_type"], "corpus-observed")
        self.assertEqual(
            [row["business_date"] for row in interval["contributing_rows"]],
            ["2016-01-04", "2016-01-05", "2017-02-06"],
        )
        for row in interval["contributing_rows"]:
            self.assertIn("member_name", row)
            self.assertIsInstance(row["line_number"], int)
        self.assertEqual(interval["serving"]["query"], ASSOCIATIONS_QUERY_ID)
        self.assertEqual(interval["serving"]["symbol"], "RELIANCE")
        self.assertEqual(interval["serving"]["series"], "EQ")
        self.assertEqual(interval["serving"]["security_id"], "INE002A01018")
        self.assertEqual(interval["serving"]["source_file"], ASSOCIATIONS_FILE)
        self.assertEqual(interval["serving"]["source_line_number"], 2)

    def test_one_identity_many_intervals_run_rule(self):
        # the D05 §3.3 contiguous-run rule: RELIANCE's identity carries two
        # dated intervals because the (symbol, series) state changed
        # (RELIANCE/EQ -> 500325/EQ)
        (doc,) = query_associations(self.handle, self.index, security_id="INE002A01018")
        intervals = doc["associations"]
        self.assertEqual(len(intervals), 2)
        self.assertEqual(
            [(a["symbol"], a["series"], a["observed_from"], a["observed_to"]) for a in intervals],
            [
                ("RELIANCE", "EQ", "2016-01-04", "2017-02-06"),
                ("500325", "EQ", "2024-03-05", "2024-03-05"),
            ],
        )
        self.assertEqual(doc["observations"]["symbols_observed"], "2")

    def test_same_instrument_across_multiple_identities(self):
        # Invalid ISINs remain separate exact observations, never correlated.
        intervals = query_associations(self.handle, self.index, symbol="TCS", series="EQ")
        self.assertEqual([i["security_id"] for i in intervals], ["INE000000006", "INE123", "INE467B01029"])
        self.assertEqual([i["symbol"] for i in intervals], ["TCS", "TCS", "500304"])

    def test_combined_mode_restricts_the_identity_to_the_pair(self):
        combined = query_associations(
            self.handle, self.index, security_id="INE002A01018", symbol="RELIANCE", series="EQ"
        )
        self.assertEqual(len(combined), 2)
        self.assertEqual(combined[0]["serving"]["security_id"], "INE002A01018")
        self.assertEqual(query_associations(self.handle, self.index, security_id="INE002A01018", symbol="500325", series="EQ")[0]["observed_from"], "2024-03-05")
        # the pair exists, but not on this identity
        self.assertEqual(
            query_associations(self.handle, self.index, security_id="INE002A01018", symbol="TCS", series="EQ"), ()
        )
        # the pair + a different identity: still restricted to that identity
        self.assertEqual(
            query_associations(self.handle, self.index, security_id="INE999999999", symbol="TCS", series="EQ"), ()
        )

    def test_unknown_instrument_is_empty_not_error(self):
        self.assertEqual(query_associations(self.handle, self.index, symbol="SBI", series="EQ"), ())
        self.assertEqual(query_associations(self.handle, self.index, symbol="RELIANCE", series="BE"), ())
        self.assertEqual(query_associations(self.handle, self.index, symbol="reliance", series="EQ"), ())

    def test_exact_value_only_no_normalisation(self):
        self.assertEqual(query_associations(self.handle, self.index, symbol="tcs", series="EQ"), ())
        self.assertEqual(query_associations(self.handle, self.index, symbol="TCS ", series="EQ"), ())
        self.assertEqual(query_associations(self.handle, self.index, symbol="TCS", series="eq"), ())
        self.assertEqual(query_associations(self.handle, self.index, symbol="TCS", series=""), ())

    def test_no_overlay_series_is_served(self):
        # D05 §3.5: overlay rows are excluded at engine ingestion; no document
        # carries one, so no selector can surface one
        for series in ("BL", "BO", "T0", "IT", "IL"):
            self.assertEqual(query_associations(self.handle, self.index, symbol="TCS", series=series), ())

    def test_deterministic_file_ordering(self):
        first = query_associations(self.handle, self.index, symbol="TCS", series="EQ")
        second = query_associations(self.handle, self.index, symbol="TCS", series="EQ")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        # file order preserved: sorted identity keys, published interval order
        order = [(i["serving"]["source_line_number"], i["security_id"]) for i in first]
        self.assertEqual(order, sorted(order))
        identity_first = query_associations(self.handle, self.index, security_id="INE002A01018")
        self.assertEqual(json.dumps(identity_first, sort_keys=True), json.dumps(query_associations(self.handle, self.index, security_id="INE002A01018"), sort_keys=True))


class Q5FailClosedTests(Q5Base):
    """(9) malformed records; (10) invalid params; (11) no partial output."""

    def _expect_scan_error(self, handle, label):
        with self.assertRaises(QueryError) as ctx:
            query_associations(handle, self.index, security_id="INE002A01018")
        self.assertEqual(ctx.exception.check, "associations-scan")
        self.assertIn(label, str(ctx.exception))

    def test_non_object_line_fails_closed(self):
        handle = self.assoc_variant("pkg-nonobj", lambda lines: [lines[0], "[1, 2, 3]"] + lines[2:])
        self._expect_scan_error(handle, "line 2")

    def test_missing_top_level_key_fails_closed(self):
        def drop(lines):
            doc = json.loads(lines[1])
            del doc["non_promotion_note"]
            return [lines[0], json.dumps(doc, sort_keys=True)] + lines[2:]

        handle = self.assoc_variant("pkg-nokey", drop)
        self._expect_scan_error(handle, "non-contract key set")

    def test_unknown_association_type_fails_closed(self):
        def swap(lines):
            doc = json.loads(lines[3])
            doc["associations"][0]["association_type"] = "master-snapshot"
            return [lines[0], lines[1], lines[2], json.dumps(doc, sort_keys=True)] + lines[4:]

        handle = self.assoc_variant("pkg-apitype", swap)
        self._expect_scan_error(handle, "outside the present set")

    def test_foreign_interval_basis_fails_closed(self):
        def swap(lines):
            doc = json.loads(lines[4])
            doc["associations"][0]["interval_basis"] = "official-validity"
            return [lines[0], lines[1], lines[2], lines[3], json.dumps(doc, sort_keys=True)]

        handle = self.assoc_variant("pkg-basis", swap)
        self._expect_scan_error(handle, "interval_basis")

    def test_false_validity_flag_fails_closed(self):
        # the engine never asserts invalidity (true or null only)
        def swap(lines):
            doc = json.loads(lines[0])
            doc["is_valid_isin_format"] = False
            return [json.dumps(doc, sort_keys=True)] + lines[1:]

        handle = self.assoc_variant("pkg-false", swap)
        self._expect_scan_error(handle, "is_valid_isin_format")

    def test_malformed_interval_date_fails_closed(self):
        def swap(lines):
            doc = json.loads(lines[2])
            doc["associations"][0]["observed_from"] = "2017-13-01"
            return [lines[0], lines[1], json.dumps(doc, sort_keys=True)] + lines[3:]

        handle = self.assoc_variant("pkg-date", swap)
        self._expect_scan_error(handle, "not a valid calendar date")

    def test_association_of_another_identity_fails_closed(self):
        def swap(lines):
            doc = json.loads(lines[1])
            doc["associations"][0]["security_id"] = "INE467B01029"
            return [lines[0], json.dumps(doc, sort_keys=True)] + lines[2:]

        handle = self.assoc_variant("pkg-xidentity", swap)
        self._expect_scan_error(handle, "different identity")

    def test_duplicate_identity_document_fails_closed(self):
        handle = self.assoc_variant("pkg-dup", lambda lines: lines[:1] + lines[:1] + lines[1:])
        self._expect_scan_error(handle, "duplicate identity document")

    def test_no_partial_output_on_scan_failure(self):
        # a failure mid-file serves nothing, and the API is stateless: a valid
        # package queried after a failure still serves fully
        handle = self.assoc_variant("pkg-midfail", lambda lines: [lines[0], "not json at all", lines[2]])
        with self.assertRaises(QueryError):
            query_associations(handle, self.index, security_id="INE009A01021")
        self.assertEqual(len(query_associations(self.handle, self.index, security_id="INE009A01021")), 1)
        # instrument mode over the same failed package also fails closed
        with self.assertRaises(QueryError):
            query_associations(handle, self.index, symbol="TCS", series="EQ")

    def test_invalid_selectors_fail_closed(self):
        for kwargs in (
            {},  # no selector at all
            {"symbol": "TCS"},  # a single field is not an instrument selector
            {"series": "EQ"},
            {"security_id": 123},  # non-string key
            {"symbol": 500325, "series": "EQ"},  # non-string symbol
            {"series": "EQ", "symbol": "TCS", "security_id": 7},  # non-string key with a valid pair
        ):
            with self.assertRaises(QueryError) as ctx:
                query_associations(self.handle, self.index, **kwargs)
            self.assertEqual(ctx.exception.check, "query-input")

    def test_package_byte_identity_after_success_and_failure(self):
        before = self.package_digests()
        query_associations(self.handle, self.index, security_id="INE002A01018")
        query_associations(self.handle, self.index, symbol="TCS", series="EQ")
        handle = self.assoc_variant("pkg-fail-identity", lambda lines: [lines[0], "garbage"])
        with self.assertRaises(QueryError):
            query_associations(handle, self.index, security_id="INE002A01018")
        self.assertEqual(before, self.package_digests())


class Q5CliTests(Q5Base):
    """(13) canonical-JSON CLI; (10) CLI usage errors; (11) CLI failure
    envelope."""

    def _query_args(self, *mode):
        return ["query", "--package", self.pkg, "--state", self.state, *mode]

    def test_identity_lookup_cli_is_canonical_json(self):
        code, out = self.run_cli(*self._query_args("--identity", "INE002A01018"))
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertEqual(envelope["query"], ASSOCIATIONS_QUERY_ID)
        self.assertEqual(envelope["security_id"], "INE002A01018")
        self.assertIsNone(envelope["symbol"])
        self.assertIsNone(envelope["series"])
        self.assertTrue(envelope["associations_present"])
        self.assertEqual(envelope["record_count"], 1)
        self.assertEqual(envelope["records"][0]["security_id"], "INE002A01018")
        # canonical JSON: sorted keys, indent 2, deterministic byte-repeat
        self.assertEqual(out, json.dumps(envelope, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        code2, out2 = self.run_cli(*self._query_args("--identity", "INE002A01018"))
        self.assertEqual(code2, 0)
        self.assertEqual(out, out2)

    def test_instrument_lookup_cli(self):
        code, out = self.run_cli(*self._query_args("--instrument-symbol", "TCS", "--instrument-series", "EQ"))
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertEqual(envelope["record_count"], 3)
        self.assertEqual([r["security_id"] for r in envelope["records"]], ["INE000000006", "INE123", "INE467B01029"])
        self.assertEqual(envelope["symbol"], "TCS")
        self.assertEqual(envelope["series"], "EQ")
        self.assertIsNone(envelope["security_id"])
        self.assertTrue(envelope["associations_present"])

    def test_combined_mode_cli(self):
        code, out = self.run_cli(
            *self._query_args("--identity", "INE002A01018", "--instrument-symbol", "RELIANCE", "--instrument-series", "EQ")
        )
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertEqual(envelope["record_count"], 2)
        self.assertEqual(envelope["records"][0]["observed_from"], "2016-01-04")

    def test_unknown_key_cli_is_empty_success(self):
        code, out = self.run_cli(*self._query_args("--identity", "INE999999999"))
        self.assertEqual(code, 0)
        envelope = json.loads(out)
        self.assertEqual(envelope["record_count"], 0)
        self.assertEqual(envelope["records"], [])
        self.assertTrue(envelope["associations_present"])

    def test_half_instrument_pair_is_a_usage_error(self):
        for mode in (("--instrument-symbol", "TCS"), ("--instrument-series", "EQ")):
            code, out = self.run_cli(*self._query_args(*mode))
            self.assertEqual(code, 2)
            envelope = json.loads(out)
            self.assertEqual(envelope["result"], "fail")
            self.assertIn("both --instrument-symbol and --instrument-series", envelope["detail"])

    def test_modes_remain_mutually_exclusive(self):
        # Q5 + Q3 positional: two modes
        code, out = self.run_cli(*self._query_args("TCS", "EQ", "--identity", "INE002A01018"))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["result"], "fail")
        # Q5 + Q4: two modes
        code, out = self.run_cli(*self._query_args("--identity", "INE002A01018", "--field", "series=EQ"))
        self.assertEqual(code, 2)
        # no mode at all: unchanged behavior
        code, out = self.run_cli("query", "--package", self.pkg, "--state", self.state)
        self.assertEqual(code, 2)

    def test_malformed_package_cli_is_fail_closed_envelope(self):
        handle = self.assoc_variant("pkg-cli-fail", lambda lines: [lines[0], "garbage"])
        # the index build reads only the class-(1) row files (w2/ is outside
        # the index), so it succeeds even for the malformed W2 variant
        variant_state = os.path.join(self.root, "state-cli-fail")
        write_index(variant_state, build_index(handle))
        code, out = self.run_cli("query", "--package", os.path.join(self.root, "pkg-cli-fail"), "--state", variant_state, "--identity", "INE002A01018")
        self.assertEqual(code, 2)
        envelope = json.loads(out)
        self.assertEqual(envelope["result"], "fail")
        self.assertIn("associations-scan", envelope["detail"])
        self.assertNotIn("records", envelope)  # no partial results printed


class Q5RegressionTests(Q5Base):
    """(16) Q1–Q10 regression: the Q5 addition leaves every prior slice's
    behavior byte-identical (fixture now carries w2/ — class-(2) files do not
    enter the serving index, so the index document is unchanged too)."""

    def test_existing_query_contracts_unchanged(self):
        q1_before = query_dataset_summary(self.index)
        q2_before = query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06")
        q3_before = query_instrument(self.handle, self.index, "RELIANCE", "EQ")
        q4_before = query_filters(self.handle, self.index, {"series": "EQ"})
        q7_before = query_record_detail(
            self.handle, self.index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2
        )
        q8_before = query_data_quality(self.handle, self.index)
        q9_before = query_archive_inventory(self.handle)
        query_associations(self.handle, self.index, security_id="INE002A01018")
        query_associations(self.handle, self.index, symbol="TCS", series="EQ")
        self.assertEqual(json.dumps(q1_before, sort_keys=True), json.dumps(query_dataset_summary(self.index), sort_keys=True))
        self.assertEqual(json.dumps(q2_before, sort_keys=True), json.dumps(query_date_range(self.handle, self.index, "2016-01-04", "2017-02-06"), sort_keys=True))
        self.assertEqual(json.dumps(q3_before, sort_keys=True), json.dumps(query_instrument(self.handle, self.index, "RELIANCE", "EQ"), sort_keys=True))
        self.assertEqual(json.dumps(q4_before, sort_keys=True), json.dumps(query_filters(self.handle, self.index, {"series": "EQ"}), sort_keys=True))
        self.assertEqual(
            json.dumps(q7_before, sort_keys=True),
            json.dumps(query_record_detail(self.handle, self.index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2), sort_keys=True),
        )
        self.assertEqual(json.dumps(q8_before, sort_keys=True), json.dumps(query_data_quality(self.handle, self.index), sort_keys=True))
        self.assertEqual(json.dumps(q9_before, sort_keys=True), json.dumps(query_archive_inventory(self.handle), sort_keys=True))

    def test_index_is_unchanged_by_q5(self):
        # Q5 adds no class-(4) state and no index entry: an independent
        # rebuild is byte-identical to the state written in setUp
        document = build_index(self.handle)
        self.assertEqual(json.dumps(document, sort_keys=True), json.dumps(self.index, sort_keys=True))
        self.assertNotIn("w2/associations.jsonl", document.get("files", {}))


if __name__ == "__main__":
    unittest.main()
