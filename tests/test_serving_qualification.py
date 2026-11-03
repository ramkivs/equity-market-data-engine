"""Serving slice — Q10 qualification and evidence views (D16-10 Q10; D23 §18).

All package-side cases run against the synthetic fixture package
(tests/serving_fixtures.py) — never against, and never represented as, the
qualified M2 baseline. In-repository evidence cases use this checkout's
durable records (R6/D11/D12/D14) where present; the real-package leg is
D24_M2_ROOT-gated in tests/test_serving_m2_integration.py.
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
from serving.quality import query_data_quality
from serving.qualification import (
    QUALIFICATION_QUERY_ID,
    query_qualification,
)
from serving.query import QueryError, query_date_range, query_instrument

M2_RUN_ID = "i4-20261008-M2"
M2_COMPOSITE = "9609c7fccef1d2438810a564ef70aa8232d8ad1c69fded8702e488c13657802d"
M2_ENGINE = "d3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9"
M2_RUNNER = "f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a"
M2_CORPUS_DIGEST = "54d8150706ccf5d813a6f0af668e8230e147a7e370db20ea15dda1b72bf8b100"

REPO_EVIDENCE_MARKER = os.path.join(
    "evidence", "D11_REPLAY_QUALIFICATION_20261009", "D11_EVIDENCE_PUBLICATION.md"
)


def find_repo_root():
    path = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isfile(os.path.join(path, REPO_EVIDENCE_MARKER.replace("/", os.sep))):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


class QualificationBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d33-serving-qualification-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]
        self.handle = open_baseline(self.pkg, spec=self.spec)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # -- variant package helpers (test-only re-signing) ----------------------
    def copy_variant(self, name):
        variant = os.path.join(self.root, name)
        shutil.copytree(self.pkg, variant)
        return variant

    def resign_package(self, variant: str, spec=None):
        manifest_path = os.path.join(variant, "PACKAGE_MANIFEST.sha256")
        marker_path = os.path.join(variant, "RUN_COMPLETE.json")
        base = spec if spec is not None else self.spec

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
        spec = replace(
            base,
            manifest_sha256=manifest_digest,
            total_bytes=total_bytes,
            file_count=file_count,
        )
        return open_baseline(variant, spec=spec)

    def rewrite_json_file(self, variant, relative, mutate):
        path = os.path.join(variant, relative.replace("/", os.sep))
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        mutate(data)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")

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


class Q10PackageIdentityTests(QualificationBase):
    def test_package_identity_composition(self):
        result = query_qualification(self.handle)
        rr = self.handle.run_record
        self.assertEqual(result["query"], QUALIFICATION_QUERY_ID)
        self.assertEqual(result["package"]["run_identity"]["run_id"], rr["run_id"])
        self.assertEqual(result["package"]["run_identity"]["composite_run_identity"], rr["composite_run_identity"])
        self.assertEqual(result["package"]["run_identity"]["contract_version"], rr["contract_version"])
        self.assertEqual(result["package"]["run_identity"]["config"], rr["config"])
        self.assertEqual(result["package"]["engine_identity"], rr["engine_identity"])
        self.assertEqual(result["package"]["runner_identity"], rr["runner_identity"])
        self.assertEqual(result["package"]["corpus"], rr["corpus"])
        self.assertEqual(result["package"]["counts"], rr["counts"])
        self.assertEqual(result["package"]["authority"], rr["authority"])
        self.assertEqual(result["package"]["boundary"], rr["boundary"])
        self.assertEqual(result["package"]["run_complete"], self.handle.marker)

    def test_fingerprint_and_manifest_values(self):
        result = query_qualification(self.handle)
        package = result["package"]
        self.assertEqual(package["engine_identity"]["tool_sha256"], self.facts["engine_tool_sha256"])
        self.assertEqual(package["manifests"]["package_manifest_sha256"], self.handle.manifest_digest)
        self.assertEqual(
            package["manifests"]["archive_set_digest"], self.handle.run_record["corpus"]["archive_set_digest"]
        )
        self.assertEqual(package["manifests"]["file_count"], self.spec.file_count)
        self.assertEqual(package["manifests"]["total_bytes"], self.handle.total_bytes)
        self.assertEqual(package["manifests"]["package_name"], self.spec.package_name)

    def test_unpinned_handle_is_explicit(self):
        # an unpinned handle (opened without an identity spec) is served with an
        # explicit unpinned identity — never treated as the qualified M2 baseline
        handle = open_baseline(self.pkg)
        result = query_qualification(handle)
        self.assertEqual(result["pinned_identity"]["pinned"], False)
        self.assertIn("must not be treated as the qualified M2 baseline", result["pinned_identity"]["note"])
        self.assertNotIn("package_name", result["package"]["manifests"])
        self.assertEqual(result["package"]["manifests"]["file_count"], self.spec.file_count)
        self.assertEqual(result["package"]["manifests"]["total_bytes"], self.handle.total_bytes)

    def test_pinned_identity_composed_not_recomputed(self):
        result = query_qualification(self.handle)
        pinned = result["pinned_identity"]
        self.assertTrue(pinned["pinned"])
        self.assertEqual(pinned["pinned_fields"]["run_id"], self.spec.run_id)
        self.assertEqual(pinned["pinned_fields"]["composite_run_identity"], self.spec.composite_run_identity)
        self.assertEqual(pinned["pinned_fields"]["engine_tool_sha256"], self.spec.engine_tool_sha256)
        self.assertEqual(pinned["pinned_fields"]["runner_sha256"], self.spec.runner_sha256)
        self.assertIn("verify-07", pinned["enforcement"])

    def test_absent_fields_stay_absent_no_nulls(self):
        # the fixture RUN_RECORD publishes no `data_lines`/`observations` and no
        # `verification` block — absent values must stay absent, never zero/null
        result = query_qualification(self.handle)
        self.assertNotIn("data_lines", result["package"]["counts"])
        self.assertNotIn("observations", result["package"]["counts"])
        self.assertNotIn("verification", result["package"])
        self.assertNotIn("partitions", result["package"]["corpus"])
        self.assertNotIn(": null", json.dumps(result, sort_keys=True))

    def test_governed_inputs_present_and_bound(self):
        result = query_qualification(self.handle)
        governed = result["package"]["governed_inputs"]
        self.assertTrue(governed["present"])
        with open(os.path.join(self.pkg, "GOVERNED_INPUTS.json"), "r", encoding="utf-8") as handle:
            self.assertEqual(governed["data"], json.load(handle))

    def test_governed_inputs_absent_is_explicit(self):
        variant = self.copy_variant("pkg-no-gi")
        os.remove(os.path.join(variant, "GOVERNED_INPUTS.json"))
        handle = self.resign_package(variant)
        result = query_qualification(handle)
        self.assertEqual(result["package"]["governed_inputs"], {"present": False})


class Q10FailClosedTests(QualificationBase):
    def test_contradictory_run_record_run_id_fails_closed(self):
        variant = self.copy_variant("pkg-runid-mismatch")
        self.rewrite_json_file(
            variant, "RUN_RECORD.json", lambda rr: rr.__setitem__("run_id", "i4-20990101-OTHER")
        )
        handle = self.resign_package(variant)
        with self.assertRaises(QueryError) as ctx:
            query_qualification(handle)
        self.assertEqual(ctx.exception.check, "run-identity")

    def test_contradictory_fingerprint_binding_fails_closed(self):
        variant = self.copy_variant("pkg-fingerprint-mismatch")
        self.rewrite_json_file(
            variant,
            "GOVERNED_INPUTS.json",
            lambda gi: gi["engine_identity"].__setitem__("tool_sha256", "0" * 64),
        )
        handle = self.resign_package(variant)
        with self.assertRaises(QueryError) as ctx:
            query_qualification(handle)
        self.assertEqual(ctx.exception.check, "identity-binding")

    def test_engine_module_count_mismatch_fails_closed(self):
        variant = self.copy_variant("pkg-module-count")
        self.rewrite_json_file(
            variant, "RUN_RECORD.json", lambda rr: rr["engine_identity"].__setitem__("engine_modules", [])
        )
        handle = self.resign_package(variant)
        with self.assertRaises(QueryError) as ctx:
            query_qualification(handle)
        self.assertEqual(ctx.exception.check, "identity-binding")

    def test_malformed_governed_inputs_fails_closed(self):
        variant = self.copy_variant("pkg-gi-bad")
        with open(os.path.join(variant, "GOVERNED_INPUTS.json"), "w", encoding="utf-8", newline="") as handle:
            handle.write("{not-json\n")
        handle = self.resign_package(variant)
        with self.assertRaises(QueryError) as ctx:
            query_qualification(handle)
        self.assertEqual(ctx.exception.check, "governed-inputs")

    def test_manifest_digest_conflict_rejected_at_open(self):
        # a contradictory manifest digest is rejected before any Q10 output can
        # exist: the pin mismatch fails the baseline open (verify-07), fail closed
        variant = self.copy_variant("pkg-manifest-pin")
        wrong = replace(self.spec, manifest_sha256="f" * 64)
        with self.assertRaises(BaselineError) as ctx:
            open_baseline(variant, spec=wrong)
        self.assertEqual(ctx.exception.check, "verify-07")

    def test_no_partial_output_on_failure(self):
        variant = self.copy_variant("pkg-no-partial")
        self.rewrite_json_file(
            variant, "RUN_RECORD.json", lambda rr: rr.__setitem__("run_id", "i4-20990101-OTHER")
        )
        handle = self.resign_package(variant)
        try:
            query_qualification(handle)
        except QueryError:
            pass
        else:
            self.fail("expected QueryError")


class Q10EvidenceTests(QualificationBase):
    def setUp(self):
        super().setUp()
        self.repo = find_repo_root()
        if self.repo is None:
            self.skipTest("in-repository evidence records not present in this checkout")

    def test_evidence_absent_without_repo_root(self):
        result = query_qualification(self.handle)
        evidence = result["evidence"]
        self.assertFalse(evidence["repo_root_provided"])
        self.assertIn("distinct from the package", evidence["boundary"])
        for key in ("r6", "d11", "d12", "d14"):
            self.assertEqual(evidence[key]["present"], False)
            self.assertEqual(evidence[key]["association"], "absent")

    def test_synthetic_run_not_associated_with_real_evidence(self):
        # the fixture run (D24-FIXTURE-RUN) is synthetic: the durable records
        # exist, but their verified identities bind to the M2 run, not to this
        # synthetic run — association is by identity, never by filename
        result = query_qualification(self.handle, repo_root=self.repo)
        evidence = result["evidence"]
        self.assertTrue(evidence["repo_root_provided"])
        self.assertEqual(evidence["d11"]["present"], True)
        self.assertEqual(evidence["d11"]["association"], "not-associated")
        self.assertTrue(evidence["d11"]["verified"]["tarball_sha256"]["match"])
        self.assertEqual(evidence["r6"]["present"], True)
        self.assertEqual(evidence["r6"]["association"], "not-associated")
        self.assertEqual(evidence["r6"]["result"], "pass")  # as published, not inferred
        self.assertEqual(evidence["d12"]["present"], True)
        self.assertEqual(evidence["d12"]["association"], "not-associated")
        self.assertEqual(evidence["d14"]["present"], True)
        self.assertEqual(evidence["d14"]["association"], "not-identity-bound")
        # the synthetic package is never represented as qualified by the evidence
        self.assertNotIn("qualified", json.dumps(evidence, sort_keys=True))

    def test_m2_identity_package_associates_with_real_evidence(self):
        # a package carrying the M2 run identity (as published in the durable
        # records) associates to the real R6/D11/D12 records by verified
        # identity — the association mechanism itself, without any claim that
        # the synthetic package is the qualified M2 baseline
        variant = self.copy_variant("pkg-m2-identity")
        run_record_path = os.path.join(variant, "RUN_RECORD.json")
        with open(run_record_path, "r", encoding="utf-8") as handle:
            rr = json.load(handle)
        rr["run_id"] = M2_RUN_ID
        rr["composite_run_identity"] = M2_COMPOSITE
        rr["engine_identity"]["tool_sha256"] = M2_ENGINE
        rr["runner_identity"]["runner_sha256"] = M2_RUNNER
        rr["corpus"]["archive_set_digest"] = M2_CORPUS_DIGEST
        with open(run_record_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(rr, sort_keys=True, separators=(",", ":")) + "\n")
        gi_path = os.path.join(variant, "GOVERNED_INPUTS.json")
        with open(gi_path, "r", encoding="utf-8") as handle:
            gi = json.load(handle)
        gi["run_id"] = M2_RUN_ID
        gi["corpus"]["archive_set_digest"] = M2_CORPUS_DIGEST
        gi["engine_identity"]["tool_sha256"] = M2_ENGINE
        gi["runner_identity"]["runner_sha256"] = M2_RUNNER
        with open(gi_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(gi, sort_keys=True, separators=(",", ":")) + "\n")
        marker_path = os.path.join(variant, "RUN_COMPLETE.json")
        with open(marker_path, "r", encoding="utf-8") as handle:
            marker = json.load(handle)
        marker["run_id"] = M2_RUN_ID
        with open(marker_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n")
        spec = replace(
            self.spec,
            run_id=M2_RUN_ID,
            composite_run_identity=M2_COMPOSITE,
            engine_tool_sha256=M2_ENGINE,
            runner_sha256=M2_RUNNER,
        )
        handle = self.resign_package(variant, spec=spec)
        result = query_qualification(handle, repo_root=self.repo)
        evidence = result["evidence"]
        self.assertEqual(evidence["r6"]["association"], "associated")
        self.assertEqual(evidence["r6"]["identity"]["composite_run_identity"], M2_COMPOSITE)
        self.assertEqual(evidence["d11"]["association"], "associated")
        self.assertEqual(evidence["d11"]["pin"]["m2_run"], M2_RUN_ID)
        self.assertEqual(evidence["d12"]["association"], "associated")
        self.assertTrue(evidence["d12"]["r6_verdict_sha256_check"]["match"])
        self.assertEqual(evidence["d14"]["association"], "not-identity-bound")
        # the pinned package data is exposed as published, distinct from evidence
        self.assertEqual(result["package"]["run_identity"]["run_id"], M2_RUN_ID)

    def test_d11_integrity_mismatch_fail_closed(self):
        repo_variant = os.path.join(self.root, "repo-integrity")
        os.makedirs(repo_variant)
        for name in (
            os.path.join("evidence", "D11_REPLAY_QUALIFICATION_20261009", "D11_EVIDENCE_PUBLICATION.md"),
            os.path.join("evidence", "D11_REPLAY_QUALIFICATION_20261009", "D11_E1_E10_TRANSFER_20261009.tar.gz"),
        ):
            destination = os.path.join(repo_variant, name.replace("/", os.sep))
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copyfile(os.path.join(self.repo, name.replace("/", os.sep)), destination)
        # corrupt one byte of the tarball: the pinned digest can no longer bind
        tarball = os.path.join(repo_variant, "evidence", "D11_REPLAY_QUALIFICATION_20261009", "D11_E1_E10_TRANSFER_20261009.tar.gz")
        with open(tarball, "r+b") as handle:
            handle.seek(100)
            handle.write(b"\x00")
        result = query_qualification(self.handle, repo_root=repo_variant)
        self.assertEqual(result["evidence"]["d11"]["association"], "integrity-mismatch")
        self.assertFalse(result["evidence"]["d11"]["verified"]["tarball_sha256"]["match"])


class Q10DisciplineTests(QualificationBase):
    def test_deterministic_and_canonical_json(self):
        first = query_qualification(self.handle)
        second = query_qualification(self.handle)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(json.loads(json.dumps(first, sort_keys=True)), sort_keys=True))

    def test_package_byte_identity(self):
        before = self.package_digests()
        query_qualification(self.handle)
        variant = self.copy_variant("pkg-failing")
        self.rewrite_json_file(
            variant, "RUN_RECORD.json", lambda rr: rr.__setitem__("run_id", "i4-20990101-OTHER")
        )
        failing = self.resign_package(variant)
        try:
            query_qualification(failing)
        except QueryError:
            pass
        self.assertEqual(before, self.package_digests())

    def test_existing_query_contracts_unchanged(self):
        from serving.index import build_index

        index = build_index(self.handle)
        q3_before = query_instrument(self.handle, index, "RELIANCE", "EQ")
        q2_before = query_date_range(self.handle, index, "2016-01-04", "2017-02-06")
        q7_before = query_record_detail(
            self.handle, index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2
        )
        q8_before = query_data_quality(self.handle, index)
        q9_before = query_archive_inventory(self.handle)
        query_qualification(self.handle)
        self.assertEqual(json.dumps(q3_before, sort_keys=True), json.dumps(query_instrument(self.handle, index, "RELIANCE", "EQ"), sort_keys=True))
        self.assertEqual(json.dumps(q2_before, sort_keys=True), json.dumps(query_date_range(self.handle, index, "2016-01-04", "2017-02-06"), sort_keys=True))
        self.assertEqual(
            json.dumps(q7_before, sort_keys=True),
            json.dumps(query_record_detail(self.handle, index, "partitions/legacy13/2016/rows/fix-leg-2016-01-04.csv.rows.jsonl", 2), sort_keys=True),
        )
        self.assertEqual(json.dumps(q8_before, sort_keys=True), json.dumps(query_data_quality(self.handle, index), sort_keys=True))
        self.assertEqual(json.dumps(q9_before, sort_keys=True), json.dumps(query_archive_inventory(self.handle), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
