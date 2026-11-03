"""Serving slice — qualified M2 baseline identity + real-package integration (D23 §18 #2).

Two distinct kinds of evidence, kept strictly separate (D24 record §13):

1. *Identity of the qualified baseline* (always executed): the pinned M2 spec
   (``serving.baseline.DEFAULT_M2_SPEC``) is verified against the repository-durable
   D11 transfer evidence (manifest digest, file count, total bytes, run/engine/runner
   identity, archive count). This is an identity check over recorded evidence — it
   does not touch the 21 GB package.

2. *Real-package integration* (executed only when the environment provides the
   qualified M2 package via ``D24_M2_ROOT``): full verification with the pinned spec,
   index build, Q1 dataset summaries, Q2 date-range query, Q3 query, rebuild.
   When the environment does not provide the package, this test is SKIPPED and
   reported as such — it is never represented as passed, and the fixture tests
   never stand in for it.
"""

from __future__ import annotations

import json
import os
import tarfile
import tempfile
import unittest

from tests import support
from serving.archive import load_d01_inventory, query_archive_inventory
from serving.baseline import DEFAULT_M2_SPEC, BaselineError, open_baseline
from serving.detail import query_record_detail
from serving.qualification import query_qualification
from serving.quality import query_data_quality
from serving.query import query_filters
from serving.index import build_index, load_index, write_index
from serving.query import (
    ASSOCIATIONS_FILE,
    DATE_RANGE_QUERY_ID,
    query_associations,
    query_calendar,
    query_date_range,
    query_dataset_summary,
    query_instrument,
)
from serving.rebuild import rebuild_state

TRANSFER = "evidence/D11_REPLAY_QUALIFICATION_20261009/D11_E1_E10_TRANSFER_20261009.tar.gz"


class M2BaselineIdentityTests(unittest.TestCase):
    """The pinned spec must agree with the repository-durable transfer evidence."""

    @classmethod
    def setUpClass(cls):
        transfer_path = os.path.join(support.REPO_ROOT, TRANSFER)
        with tarfile.open(transfer_path, "r:gz") as tar:
            cls.members = {
                m.name: tar.extractfile(m).read()
                for m in tar.getmembers()
                if m.isfile()
            }

    def _tsv(self):
        text = self.members["D11_E1_E10_TRANSFER_20261009/A.PACKAGE_FILES.tsv"].decode("utf-8")
        return [line.rsplit("\t", 2) for line in text.replace("\r", "").splitlines()[1:] if line]

    def test_pin_file_count_and_total_bytes(self):
        entries = self._tsv()
        self.assertEqual(len(entries), DEFAULT_M2_SPEC.file_count)
        self.assertEqual(sum(int(size) for _p, size, _s in entries), DEFAULT_M2_SPEC.total_bytes)

    def test_pin_manifest_digest(self):
        recorded = dict((path, sha.lower()) for path, _size, sha in self._tsv())
        self.assertEqual(DEFAULT_M2_SPEC.manifest_sha256, recorded["PACKAGE_MANIFEST.sha256"])
        import hashlib

        manifest_bytes = self.members["D11_E1_E10_TRANSFER_20261009/PACKAGE_MANIFEST.sha256"]
        self.assertEqual(DEFAULT_M2_SPEC.manifest_sha256, hashlib.sha256(manifest_bytes).hexdigest())

    def test_pin_run_and_tool_identity(self):
        import json

        record = json.loads(self.members["D11_E1_E10_TRANSFER_20261009/RUN_RECORD.json"].decode("utf-8"))
        self.assertEqual(DEFAULT_M2_SPEC.run_id, record["run_id"])
        self.assertEqual(DEFAULT_M2_SPEC.composite_run_identity, record["composite_run_identity"])
        self.assertEqual(
            DEFAULT_M2_SPEC.engine_tool_sha256,
            record["engine_identity"]["tool_sha256"],
        )
        self.assertEqual(DEFAULT_M2_SPEC.runner_sha256, record["runner_identity"]["runner_sha256"])
        self.assertEqual(DEFAULT_M2_SPEC.archive_count, record["corpus"]["archive_count"])

    def test_pin_row_count_matches_run_record(self):
        import json

        record = json.loads(self.members["D11_E1_E10_TRANSFER_20261009/RUN_RECORD.json"].decode("utf-8"))
        self.assertEqual(record["counts"]["rows"], 5689949)
        self.assertEqual(record["counts"]["members"], DEFAULT_M2_SPEC.archive_count)


@unittest.skipIf(
    not os.environ.get("D24_M2_ROOT"),
    "qualified M2 package not present in this environment (D24_M2_ROOT unset); "
    "real-package integration is PENDING baseline provisioning, not passed",
)
class M2RealPackageIntegrationTests(unittest.TestCase):
    """Runs only when the environment provides the qualified M2 package."""

    @classmethod
    def setUpClass(cls):
        cls.pkg_root = os.environ["D24_M2_ROOT"]
        cls.state = tempfile.mkdtemp(prefix="d24-m2-state-")
        cls.handle = open_baseline(cls.pkg_root, spec=DEFAULT_M2_SPEC)
        cls.index = build_index(cls.handle)
        cls.index_sha = write_index(cls.state, cls.index)

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls.state, ignore_errors=True)

    def test_full_verification_passes_with_pinned_spec(self):
        self.assertEqual(self.handle.manifest_digest, DEFAULT_M2_SPEC.manifest_sha256)
        self.assertEqual(self.handle.checks_passed[-1], "verify-07")
        self.assertEqual(self.handle.run_record["corpus"]["archive_count"], DEFAULT_M2_SPEC.archive_count)

    def test_q3_query_over_real_baseline(self):
        document, _digest = load_index(self.state, self.handle)
        rows = query_instrument(self.handle, document, "RELIANCE", "EQ")
        self.assertGreater(len(rows), 0)
        dates = [row["business_date"] for row in rows]
        self.assertEqual(dates, sorted(dates))
        for row in rows:
            self.assertIn("provenance", row)
            self.assertNotIn("raw_line", row)

    def test_q1_dataset_summary_over_real_baseline(self):
        document, _digest = load_index(self.state, self.handle)
        result = query_dataset_summary(document)
        self.assertEqual(len(result["partitions"]), 12)
        counts = document["counts"]
        self.assertEqual(result["summary"]["row_files"], counts["row_files"])
        self.assertEqual(result["summary"]["row_count"], counts["row_count"])
        self.assertEqual(result["summary"]["instrument_pairs"], counts["instrument_pairs"])
        selected = query_dataset_summary(document, family="legacy13", year=2024)
        self.assertEqual([p["family"] for p in selected["partitions"]], ["legacy13"])
        self.assertEqual(selected["summary"]["row_count"], selected["partitions"][0]["row_count"])
        self.assertEqual(
            query_dataset_summary(document, family="nosuchfamily"),
            {
                "query": "Q1-dataset",
                "selection": {"family": "nosuchfamily", "year": None},
                "partitions": [],
                "summary": {"row_files": 0, "row_count": 0, "instrument_pairs": 0},
            },
        )

    def test_q2_date_range_over_real_baseline(self):
        # 2024-06-21..2024-07-05 is a range with known real rows (D26 evidence
        # fragments: legacy13/2024 cmNN members, business dates within this span).
        document, _digest = load_index(self.state, self.handle)
        rows = query_date_range(self.handle, document, "2024-06-21", "2024-07-05")
        self.assertGreater(len(rows), 0)
        dates = [row["business_date"] for row in rows]
        self.assertEqual(dates, sorted(dates))
        for row in rows:
            self.assertGreaterEqual(row["business_date"], "2024-06-21")
            self.assertLessEqual(row["business_date"], "2024-07-05")
            self.assertEqual(row["serving"]["query"], DATE_RANGE_QUERY_ID)
            self.assertIn("provenance", row)
            self.assertNotIn("raw_line", row)
        # a range with no rows is empty, not an error
        self.assertEqual(query_date_range(self.handle, document, "1990-01-01", "1990-01-02"), ())

    def test_rebuild_reproducibility(self):
        report = rebuild_state(self.handle, self.state)
        self.assertTrue(report["identical"], "rebuild over an unchanged M2 baseline must be byte-identical")
        self.assertEqual(report["rows_scanned"], 5689949)

    def test_q9_archive_inventory_over_real_baseline(self):
        # Q9 over the actual qualified M2 baseline: 2,462 archives, a complete
        # D01 join (every archive_sha256_d01 equal to its D01 inventory sha256),
        # the explicit registry absence, and deterministic repeated output.
        d01 = load_d01_inventory()
        result = query_archive_inventory(self.handle, d01=d01)
        self.assertEqual(result["summary"]["archive_count"], 2462)
        self.assertEqual(len(result["archives"]), 2462)
        self.assertEqual(result["summary"]["d01_inventory"]["present"], True)
        self.assertEqual(result["summary"]["d01_inventory"]["record_count"], 2462)
        for archive in result["archives"]:
            self.assertIsNotNone(archive["d01"])
            self.assertEqual(archive["d01"]["sha256"], archive["archive_sha256_d01"])
            self.assertEqual(archive["registry"], {"present": False, "status": "absent-in-m2-only-release"})
        again = query_archive_inventory(self.handle, d01=d01)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(result, sort_keys=True))

    def test_q7_record_detail_over_real_baseline(self):
        # Q7 over the actual qualified M2 baseline: the row-to-archive join
        # succeeds on authoritative package data, the archive facts and the
        # member-scoped reconciliation records are attached as published,
        # raw_line stays excluded, and the output is deterministic.
        document, _digest = load_index(self.state, self.handle)
        rows = query_instrument(self.handle, document, "RELIANCE", "EQ")
        self.assertGreater(len(rows), 0)
        row = rows[0]
        source_file = row["serving"]["source_file"]
        line_number = row["source_line_number"]
        detail = query_record_detail(self.handle, document, source_file, line_number)
        self.assertEqual(detail["row"]["provenance"], row["provenance"])
        self.assertEqual(detail["row"]["source_line_number"], line_number)
        self.assertNotIn("raw_line", detail["row"])
        archive = detail["archive"]
        self.assertEqual(archive["member_name"], row["provenance"]["member_name"])
        self.assertEqual(archive["file_name"], row["provenance"]["source_archive"])
        self.assertEqual(archive["archive_sha256_d01"], row["provenance"]["archive_sha256"])
        self.assertEqual(archive["engine_family"], row["format_family"])
        self.assertGreater(len(detail["reconciliation"]), 0)
        for record in detail["reconciliation"]:
            self.assertEqual(record["input_identity"]["scope"], "member")
            self.assertEqual(record["input_identity"]["relative_path"], archive["relative_path"])
        again = query_record_detail(self.handle, document, source_file, line_number)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(detail, sort_keys=True))

    def test_q8_data_quality_over_real_baseline(self):
        # Q8 over the actual qualified M2 baseline: the flag census is a census
        # of governed names, the quarantine count is preserved as published
        # (zero stays zero), the reconciliation aggregates corroborate the
        # completion marker (39,402 records), the unresolved file is parsed as
        # published, and D21 CHANGED findings are explicitly absent.
        document, _digest = load_index(self.state, self.handle)
        result = query_data_quality(self.handle, document)
        self.assertEqual(result["query"], "Q8-data-quality")
        for count in result["flag_census"].values():
            self.assertIsInstance(count, int)
            self.assertGreaterEqual(count, 0)
        self.assertEqual(result["quarantine"]["count"], 0)
        self.assertEqual(self.handle.run_record["counts"]["quarantined"], 0)
        self.assertEqual(result["reconciliation"]["record_count"], 39402)
        self.assertEqual(
            result["reconciliation"]["by_result"], self.handle.marker["reconciliation"]["by_result"]
        )
        self.assertEqual(
            result["reconciliation"]["by_tier"], self.handle.marker["reconciliation"]["by_tier"]
        )
        self.assertTrue(result["unresolved"]["present"])
        self.assertGreater(result["unresolved"]["record_count"], 0)
        for record in result["unresolved"]["records"]:
            self.assertIsInstance(record.get("kind"), str)
            self.assertIsInstance(record.get("state"), str)
        self.assertEqual(result["changed"]["present"], False)
        self.assertEqual(result["changed"]["status"], "absent-in-m2-only-release")
        self.assertEqual(result["changed"]["findings"], [])
        again = query_data_quality(self.handle, document)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(result, sort_keys=True))

    def test_q10_qualification_over_real_baseline(self):
        # Q10 over the actual qualified M2 baseline: the run identity,
        # fingerprints, and manifest facts as published; the durable evidence
        # associates by verified identity when the repository root is provided
        # (D24_REPO_ROOT), and is reported explicitly absent otherwise.
        repo_root = os.environ.get("D24_REPO_ROOT") or None
        result = query_qualification(self.handle, repo_root=repo_root)
        package = result["package"]
        self.assertEqual(package["run_identity"]["run_id"], "i4-20261008-M2")
        self.assertEqual(
            package["run_identity"]["composite_run_identity"],
            "9609c7fccef1d2438810a564ef70aa8232d8ad1c69fded8702e488c13657802d",
        )
        self.assertEqual(package["engine_identity"]["tool_sha256"], "d3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9")
        self.assertEqual(package["runner_identity"]["runner_sha256"], "f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a")
        self.assertEqual(package["corpus"]["archive_count"], 2462)
        self.assertEqual(package["counts"]["quarantined"], 0)
        self.assertEqual(package["manifests"]["package_manifest_sha256"], self.handle.manifest_digest)
        self.assertEqual(package["manifests"]["file_count"], DEFAULT_M2_SPEC.file_count)
        self.assertTrue(result["pinned_identity"]["pinned"])
        self.assertEqual(package["governed_inputs"]["present"], True)
        evidence = result["evidence"]
        if repo_root is not None:
            self.assertEqual(evidence["d11"]["association"], "associated")
            self.assertTrue(evidence["d11"]["verified"]["tarball_sha256"]["match"])
            self.assertEqual(evidence["r6"]["association"], "associated")
            self.assertEqual(evidence["r6"]["result"], "pass")
            self.assertEqual(evidence["d12"]["association"], "associated")
            self.assertTrue(evidence["d12"]["r6_verdict_sha256_check"]["match"])
            self.assertEqual(evidence["d14"]["association"], "not-identity-bound")
        else:
            for key in ("r6", "d11", "d12", "d14"):
                self.assertEqual(evidence[key]["association"], "absent")
        again = query_qualification(self.handle, repo_root=repo_root)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(result, sort_keys=True))

    def test_q4_filters_over_real_baseline(self):
        # Q4 over the actual qualified M2 baseline: exact-value semantics
        # (every served row carries exactly the requested value), AND
        # semantics, absent-never-matches (legacy rows for UDiFF-only
        # fields), and determinism. No counts are asserted beyond the
        # corpus-proven facts (D05: Sgmt=CM/Src=NSE on UDiff rows).
        document, _digest = load_index(self.state, self.handle)
        cm = query_filters(self.handle, document, {"segment": "CM"})
        for row in cm:
            self.assertEqual(row["source_values"]["segment"], "CM")
            self.assertEqual(row["format_family"], "udiff34")
        nse = query_filters(self.handle, document, {"source": "NSE"})
        for row in nse:
            self.assertEqual(row["source_values"]["source"], "NSE")
            self.assertEqual(row["format_family"], "udiff34")
        # AND semantics: every combined row matches both requested values
        combined = query_filters(self.handle, document, {"segment": "CM", "source": "NSE"})
        for row in combined:
            self.assertEqual(row["source_values"]["segment"], "CM")
            self.assertEqual(row["source_values"]["source"], "NSE")
        self.assertEqual(query_filters(self.handle, document, {"segment": "__NONE__"}), ())
        again = query_filters(self.handle, document, {"segment": "CM"})
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(cm, sort_keys=True))

    def test_q5_associations_over_real_baseline(self):
        # Q5 over the actual qualified M2 baseline: the W2 associations file
        # is present, identity lookup by the first published correlation key
        # returns that key's document, instrument lookup by a published
        # (symbol, series) pair returns only matching intervals, no served
        # interval carries an overlay series (D05 §3.5), and results are
        # deterministic. Serving-behavior assertions only — no corpus counts
        # are assumed and the corpus is not re-qualified.
        document, _digest = load_index(self.state, self.handle)
        with open(self.handle.path(ASSOCIATIONS_FILE), "r", encoding="utf-8") as handle:
            first_key = json.loads(next(handle))["security_id"]
        identity = query_associations(self.handle, document, security_id=first_key)
        self.assertEqual(len(identity), 1)
        self.assertEqual(identity[0]["security_id"], first_key)
        self.assertEqual(identity[0]["identity_basis"], "isin_correlation_key_upper_trim")
        self.assertGreater(len(identity[0]["associations"]), 0)
        for association in identity[0]["associations"]:
            self.assertEqual(association["association_type"], "corpus-observed")
            self.assertEqual(association["interval_basis"], "observed-range")
            self.assertEqual(association["security_id"], first_key)
            self.assertNotIn(association["series"], ("BL", "BO", "T0", "IT", "IL"))
        first_association = identity[0]["associations"][0]
        intervals = query_associations(
            self.handle,
            document,
            symbol=first_association["symbol"],
            series=first_association["series"],
        )
        self.assertGreater(len(intervals), 0)
        for interval in intervals:
            self.assertEqual(interval["symbol"], first_association["symbol"])
            self.assertEqual(interval["series"], first_association["series"])
            self.assertNotIn(interval["series"], ("BL", "BO", "T0", "IT", "IL"))
        again = query_associations(self.handle, document, security_id=first_key)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(identity, sort_keys=True))

    def test_q6_calendar_over_real_baseline(self):
        # Q6 over the actual qualified M2 baseline: the W2 calendar is present
        # and strictly ascending; the served calendar arithmetic matches the
        # documented corpus facts (D03/D05 §3.4: 2,462 files + 147 missing
        # weekdays = 2,609 span weekdays); the three documented unresolved
        # dates are served unexplained (null label, cause never filled in);
        # legacy-era present days carry trad_dt_eq_biz_dt null; the documented
        # 2025-10-21 circular-holiday-with-file divergence is served as stored
        # (file present AND official-holiday); the inclusive single-day range
        # returns exactly that day; results are deterministic. Serving
        # behavior only — no re-qualification.
        document, _digest = load_index(self.state, self.handle)
        days = query_calendar(self.handle, document)
        self.assertGreater(len(days), 0)
        dates = [d["trade_date"] for d in days]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(set(dates)), len(dates))  # strictly ascending, no duplicates
        present = [d for d in days if d["file_present"]]
        missing = [d for d in days if not d["file_present"]]
        # D03 arithmetic as documented: 2,462 files + 147 gaps = 2,609 weekdays
        self.assertEqual(len(present), 2462)
        self.assertEqual(len(missing), 147)
        self.assertEqual(len(days), 2609)
        # the three documented unresolved dates (D05 §3.4 / D07-OPEN-8)
        unexplained = [d for d in days if d["label_status"] == "unexplained-by-obtained-circulars"]
        self.assertEqual([d["trade_date"] for d in unexplained], ["2024-11-20", "2025-10-20", "2026-01-15"])
        for day in unexplained:
            self.assertIsNone(day["official_holiday_label"])  # cause never filled in
        # the documented divergence: 2025-10-21 circular holiday WITH a file
        by_date = {d["trade_date"]: d for d in days}
        divergence = by_date["2025-10-21"]
        self.assertTrue(divergence["file_present"])
        self.assertEqual(divergence["label_status"], "official-holiday")
        # legacy-era present days are N/A for trad_dt_eq_biz_dt (never defaulted)
        legacy_present = [d for d in present if d["trad_dt_eq_biz_dt"] is None]
        self.assertGreater(len(legacy_present), 0)
        # inclusive single-day range
        single = query_calendar(self.handle, document, date_from="2024-11-20", date_to="2024-11-20")
        self.assertEqual([d["trade_date"] for d in single], ["2024-11-20"])
        again = query_calendar(self.handle, document)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(days, sort_keys=True))

    def test_saved_query_run_over_real_baseline(self):
        """D37-DEC C1(a)/C2(a) over the real qualified baseline: a saved
        definition executed through the existing query layer must be EXACTLY
        the corresponding direct-query result (no new semantics), and the
        execution must leave the saved store byte-identical (no history)."""
        import hashlib
        import shutil

        from serving.saved import SAVED_FILENAME, create_saved, execute_saved

        saved_root = tempfile.mkdtemp(prefix="d38-m2-saved-")
        try:
            create_saved(saved_root, "m2-rel", "Q3-instrument", {"symbol": "RELIANCE", "series": "EQ"})
            create_saved(saved_root, "m2-q2", "Q2-date-range", {"date_from": "2024-06-21", "date_to": "2024-07-05"})
            document, _digest = load_index(self.state, self.handle)

            out3 = execute_saved(saved_root, "m2-rel", self.handle, self.state)
            rows3 = query_instrument(self.handle, document, "RELIANCE", "EQ")
            self.assertEqual(out3, {"query": "Q3-instrument", "result_count": len(rows3), "rows": list(rows3)})
            self.assertGreater(len(rows3), 0)

            out2 = execute_saved(saved_root, "m2-q2", self.handle, self.state)
            rows2 = query_date_range(self.handle, document, "2024-06-21", "2024-07-05")
            self.assertEqual(
                out2,
                {
                    "query": DATE_RANGE_QUERY_ID,
                    "date_from": "2024-06-21",
                    "date_to": "2024-07-05",
                    "result_count": len(rows2),
                    "rows": list(rows2),
                },
            )
            self.assertGreater(len(rows2), 0)
        finally:
            shutil.rmtree(saved_root, ignore_errors=True)

    def test_history_record_over_real_baseline(self):
        """D37-DEC C2(a) over the real qualified baseline: the explicit
        recording operation records a real execution's outcome, and ordinary
        query execution leaves the history store untouched."""
        import hashlib
        import shutil

        from serving.history import HISTORY_FILENAME, list_history, record_execution

        hist_root = tempfile.mkdtemp(prefix="d39-m2-history-")
        try:
            entry, output, detail, digest = record_execution(
                hist_root, "Q2-date-range", {"date_from": "2024-06-21", "date_to": "2024-07-05"},
                self.handle, self.state,
            )
            self.assertEqual(entry["outcome"], "success")
            self.assertEqual(entry["seq"], 1)
            self.assertIsNone(detail)
            self.assertGreater(output["result_count"], 0)
            (stored,) = list_history(hist_root)
            self.assertEqual(stored, entry)
            with open(os.path.join(hist_root, HISTORY_FILENAME), "rb") as handle:
                self.assertEqual(hashlib.sha256(handle.read()).hexdigest(), digest)
            # ordinary query execution must not write history (C2(a))
            before = sorted(
                (name, hashlib.sha256(open(os.path.join(hist_root, name), "rb").read()).hexdigest())
                for name in os.listdir(hist_root) if os.path.isfile(os.path.join(hist_root, name))
            )
            query_date_range(self.handle, self.index, "2024-06-21", "2024-07-05")
            after = sorted(
                (name, hashlib.sha256(open(os.path.join(hist_root, name), "rb").read()).hexdigest())
                for name in os.listdir(hist_root) if os.path.isfile(os.path.join(hist_root, name))
            )
            self.assertEqual(after, before)
        finally:
            shutil.rmtree(hist_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
