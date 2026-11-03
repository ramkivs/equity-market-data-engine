"""Serving slice — baseline identity verification and fail-closed behaviour (D23 §18 #2/#5/#6).

All cases run against the synthetic fixture package (tests/serving_fixtures.py) —
never against, or represented as, the qualified M2 baseline.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import unittest

from tests import serving_fixtures, support
from serving import baseline as baseline_mod
from serving.baseline import DEFAULT_M2_SPEC, BaselineError, open_baseline


class FixturePackageBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d24-serving-fixture-")
        self.pkg = os.path.join(self.root, "pkg")
        self.state = os.path.join(self.root, "state")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def package_digests(self) -> dict:
        digests = {}
        for dirpath, dirnames, filenames in os.walk(self.pkg):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, self.pkg).replace(os.sep, "/")
                digests[relative] = baseline_mod.sha256_file(full)
        return digests


class BaselineVerificationTests(FixturePackageBase):
    def test_verified_open_passes_all_checks(self):
        handle = open_baseline(self.pkg, spec=self.spec)
        self.assertEqual(
            handle.checks_passed,
            ("verify-01", "verify-02", "verify-03", "verify-04", "verify-05", "verify-06", "verify-07"),
        )
        self.assertEqual(handle.manifest_digest, self.spec.manifest_sha256)
        self.assertEqual(handle.marker["run_id"], serving_fixtures.FIXTURE_RUN_ID)
        self.assertEqual(len(handle.row_files()), 4)

    def test_unpinned_open_verifies_self_consistency_only(self):
        handle = open_baseline(self.pkg, spec=None)
        self.assertEqual(handle.manifest_digest, self.spec.manifest_sha256)
        self.assertIsNone(handle.spec)

    def test_tampered_row_file_fails_closed(self):
        target = os.path.join(self.pkg, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl")
        with open(target, "ab") as handle:
            handle.write(b"tampered\n")
        with self.assertRaises(BaselineError) as ctx:
            open_baseline(self.pkg, spec=self.spec)
        self.assertEqual(ctx.exception.check, "verify-02")

    def test_missing_completion_marker_fails_closed(self):
        os.remove(os.path.join(self.pkg, "RUN_COMPLETE.json"))
        with self.assertRaises(BaselineError) as ctx:
            open_baseline(self.pkg, spec=self.spec)
        self.assertEqual(ctx.exception.check, "verify-04")

    def test_unlisted_stray_file_fails_closed_and_serves_nothing(self):
        # D21 path prohibition at the slice level: unknown content inside the
        # package (e.g. a candidate that must never be canonical-serving-eligible)
        # makes the WHOLE package fail closed — nothing is served from it.
        stray = os.path.join(self.pkg, "partitions/legacy13/2016/rows", "candidate-unknown.csv.rows.jsonl")
        with open(stray, "w", encoding="utf-8") as handle:
            handle.write('{"source_values": {"listing_symbol": "EVT", "series": "EQ"}}\n')
        with self.assertRaises(BaselineError) as ctx:
            open_baseline(self.pkg, spec=self.spec)
        self.assertEqual(ctx.exception.check, "verify-03")

    def test_wrong_pin_fails_closed(self):
        bad_spec = baseline_mod.BaselineSpec(
            package_name="i4-20261008-M2",
            manifest_sha256="0" * 64,
            file_count=self.spec.file_count,
            total_bytes=self.spec.total_bytes,
            run_id=self.spec.run_id,
        )
        with self.assertRaises(BaselineError) as ctx:
            open_baseline(self.pkg, spec=bad_spec)
        self.assertEqual(ctx.exception.check, "verify-07")

    def test_wrong_run_identity_pin_fails_closed(self):
        # package files are intact (manifests match), but the spec pins a
        # composite run identity the package does not carry -> verify-07 only.
        from dataclasses import replace

        bad_spec = replace(self.spec, composite_run_identity="f" * 64)
        with self.assertRaises(BaselineError) as ctx:
            open_baseline(self.pkg, spec=bad_spec)
        self.assertEqual(ctx.exception.check, "verify-07")

    def test_tampered_run_record_fails_closed_at_digest(self):
        # altering RUN_RECORD bytes breaks its manifest digest -> fail closed
        # no later than verify-02 (identity can never be trusted on a tampered file)
        record_path = os.path.join(self.pkg, "RUN_RECORD.json")
        with open(record_path, "r", encoding="utf-8") as handle:
            record = handle.read()
        with open(record_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(record.replace(self.spec.composite_run_identity, "f" * 64))
        with self.assertRaises(BaselineError) as ctx:
            open_baseline(self.pkg, spec=self.spec)
        self.assertIn(ctx.exception.check, ("verify-02", "verify-04", "verify-07"))


class ReadOnlyDisciplineTests(FixturePackageBase):
    def test_every_serving_operation_leaves_the_package_byte_identical(self):
        before = self.package_digests()
        handle = open_baseline(self.pkg, spec=self.spec)
        from serving.index import build_index, write_index, load_index
        from serving.query import query_instrument
        from serving.rebuild import rebuild_state

        write_index(self.state, build_index(handle))
        rows = query_instrument(handle, load_index(self.state, handle)[0], "RELIANCE", "EQ")
        self.assertGreater(len(rows), 0)
        report = rebuild_state(handle, self.state)
        self.assertTrue(report["identical"])
        self.assertEqual(before, self.package_digests())

    def test_q1_q2_operations_leave_the_package_byte_identical(self):
        before = self.package_digests()
        handle = open_baseline(self.pkg, spec=self.spec)
        from serving.index import build_index, write_index, load_index
        from serving.query import query_date_range, query_dataset_summary

        write_index(self.state, build_index(handle))
        document = load_index(self.state, handle)[0]
        query_dataset_summary(document)
        query_dataset_summary(document, family="legacy13", year=2016)
        rows = query_date_range(handle, document, "2016-01-04", "2017-02-06")
        self.assertEqual(len(rows), 7)
        self.assertEqual(before, self.package_digests())


class M2PinIdentityTests(unittest.TestCase):
    """The pinned M2 spec (serving.baseline.DEFAULT_M2_SPEC) must be internally
    consistent with the repository-durable D11 transfer evidence."""

    def test_pin_matches_d11_transfer_evidence(self):
        import tarfile

        repo_root = support.REPO_ROOT
        transfer = os.path.join(
            repo_root,
            "evidence/D11_REPLAY_QUALIFICATION_20261009/D11_E1_E10_TRANSFER_20261009.tar.gz",
        )
        with tarfile.open(transfer, "r:gz") as tar:
            members = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
        tsv_text = members["D11_E1_E10_TRANSFER_20261009/A.PACKAGE_FILES.tsv"].decode("utf-8").replace("\r", "")
        entries = [line.rsplit("\t", 2) for line in tsv_text.splitlines()[1:] if line]
        file_count = len(entries)
        total_bytes = sum(int(size) for _path, size, _sha in entries)
        recorded_manifest_sha = dict(
            (path, sha.lower()) for path, _size, sha in entries
        )["PACKAGE_MANIFEST.sha256"]
        manifest_bytes = members["D11_E1_E10_TRANSFER_20261009/PACKAGE_MANIFEST.sha256"]
        computed_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        run_record = json_load(members["D11_E1_E10_TRANSFER_20261009/RUN_RECORD.json"])

        spec = DEFAULT_M2_SPEC
        self.assertEqual(file_count, 4948)
        self.assertEqual(total_bytes, 21119807344)
        self.assertEqual(spec.file_count, file_count)
        self.assertEqual(spec.total_bytes, total_bytes)
        self.assertEqual(spec.manifest_sha256, recorded_manifest_sha)
        self.assertEqual(spec.manifest_sha256, computed_manifest_sha)
        self.assertEqual(spec.run_id, "i4-20261008-M2")
        self.assertEqual(run_record["run_id"], spec.run_id)
        self.assertEqual(run_record["composite_run_identity"], spec.composite_run_identity)
        self.assertEqual(
            run_record["engine_identity"]["tool_sha256"], spec.engine_tool_sha256
        )
        self.assertEqual(run_record["runner_identity"]["runner_sha256"], spec.runner_sha256)
        self.assertEqual(run_record["corpus"]["archive_count"], spec.archive_count)


def json_load(data: bytes) -> dict:
    import json

    return json.loads(data.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
