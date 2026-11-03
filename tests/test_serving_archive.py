"""Serving slice — Q9 archive inventory (D16-10 Q9; D23 §18 items 4/8/10).

All cases run against the synthetic fixture package (tests/serving_fixtures.py)
and the committed in-repo D01 inventory — never against, and never represented
as, the qualified M2 baseline. The real-package leg (2,462 archives, complete
D01 join, registry absence over the actual baseline) is D24_M2_ROOT-gated in
tests/test_serving_m2_integration.py.
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
from serving.archive import (
    D01_INVENTORY_PATH,
    D01_INVENTORY_RECORD_COUNT,
    D01_INVENTORY_SHA256,
    D01InventoryError,
    ARCHIVE_QUERY_ID,
    load_d01_inventory,
    query_archive_inventory,
)
from serving.baseline import DEFAULT_M2_SPEC, Baseline, open_baseline
from serving.query import QueryError

REGISTRY_ABSENT = {"present": False, "status": "absent-in-m2-only-release"}

CONTRACT_KEYS = (
    "sequence",
    "root",
    "relative_path",
    "file_name",
    "member_name",
    "date_from_filename",
    "detected_format",
    "engine_family",
    "partition",
    "archive_sha256_d01",
    "archive_sha256_basis",
    "archive_sha256_observed_raw_bytes",
    "member_sha256_raw_bytes",
    "member_sha256_lf_text",
    "member_size_bytes",
    "header_physical_width",
    "header_tolerance_applied",
    "data_lines",
    "rows",
    "quarantined",
)


class ArchiveBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d30b-serving-archive-")
        self.pkg = os.path.join(self.root, "pkg")
        self.facts = serving_fixtures.build_fixture_package(self.pkg)
        self.spec = self.facts["spec"]

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def open_handle(self):
        return open_baseline(self.pkg, spec=self.spec)

    def pinned_handle(self, handle):
        """The same verified package pinned to the M2 baseline identity (test-only:
        exercises the pinned-M2 gates without the real package)."""
        return Baseline(
            root=handle.root,
            spec=DEFAULT_M2_SPEC,
            manifest_digest=handle.manifest_digest,
            manifest_entries=handle.manifest_entries,
            marker=handle.marker,
            run_record=handle.run_record,
            total_bytes=handle.total_bytes,
            checks_passed=handle.checks_passed,
        )

    def copy_variant(self, name):
        variant = os.path.join(self.root, name)
        shutil.copytree(self.pkg, variant)
        return variant

    def resign_package(self, variant: str):
        """Re-sign a copied package's manifest + completion marker after an
        in-place metadata edit (test-only). Returns the matching spec."""
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


class Q9ArchiveInventoryTests(ArchiveBase):
    def test_per_archive_schema_and_as_published_fields(self):
        handle = self.open_handle()
        result = query_archive_inventory(handle)
        self.assertEqual(result["query"], ARCHIVE_QUERY_ID)
        self.assertEqual(len(result["archives"]), 4)
        for archive in result["archives"]:
            for key in CONTRACT_KEYS:
                self.assertIn(key, archive)
            self.assertIsNone(archive["d01"])
            self.assertEqual(archive["registry"], REGISTRY_ABSENT)
        # as-published pass-through: the first archive must equal the stored record
        with open(os.path.join(self.pkg, "INPUT_MANIFEST.jsonl"), "r", encoding="utf-8") as handle:
            stored = json.loads(handle.readline())
        first = result["archives"][0]
        for key, value in stored.items():
            self.assertEqual(first[key], value)

    def test_deterministic_ordering_and_identical_output(self):
        handle = self.open_handle()
        first = query_archive_inventory(handle)
        second = query_archive_inventory(handle)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        sequences = [archive["sequence"] for archive in first["archives"]]
        self.assertEqual(sequences, sorted(sequences))

    def test_summary_count_and_digest(self):
        handle = self.open_handle()
        result = query_archive_inventory(handle)
        summary = result["summary"]
        self.assertEqual(summary["archive_count"], 4)
        with open(os.path.join(self.pkg, "GOVERNED_INPUTS.json"), "r", encoding="utf-8") as handle:
            governed = json.load(handle)
        self.assertEqual(summary["archive_set_digest"], governed["corpus"]["archive_set_digest"])
        self.assertEqual(summary["d01_inventory"], {"present": False, "status": "absent"})
        self.assertEqual(summary["registry"], REGISTRY_ABSENT)

    def test_count_mismatch_fails_closed(self):
        variant = self.copy_variant("pkg-count-mismatch")
        governed_path = os.path.join(variant, "GOVERNED_INPUTS.json")
        with open(governed_path, "r", encoding="utf-8") as handle:
            governed = json.load(handle)
        governed["corpus"]["archive_count"] = 5
        with open(governed_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(governed, sort_keys=True, separators=(",", ":")) + "\n")
        spec = self.resign_package(variant)
        with self.assertRaises(QueryError) as ctx:
            query_archive_inventory(self.open_variant(variant, spec))
        self.assertEqual(ctx.exception.check, "inventory-count")

    def test_registry_absent_representation_exact(self):
        handle = self.open_handle()
        result = query_archive_inventory(handle)
        for archive in result["archives"]:
            self.assertEqual(archive["registry"], REGISTRY_ABSENT)
        self.assertEqual(result["summary"]["registry"], REGISTRY_ABSENT)

    def test_synthetic_package_d01_absent(self):
        handle = self.open_handle()
        result = query_archive_inventory(handle)
        for archive in result["archives"]:
            self.assertIsNone(archive["d01"])
        self.assertEqual(result["summary"]["d01_inventory"], {"present": False, "status": "absent"})

    def test_pinned_m2_requires_d01_inventory(self):
        handle = self.open_handle()
        with self.assertRaises(QueryError) as ctx:
            query_archive_inventory(self.pinned_handle(handle))
        self.assertEqual(ctx.exception.check, "d01-required")

    def test_pinned_m2_d01_join_miss_and_identity_mismatch_fail_closed(self):
        handle = self.open_handle()
        pinned = self.pinned_handle(handle)
        with open(os.path.join(self.pkg, "INPUT_MANIFEST.jsonl"), "r", encoding="utf-8") as fh:
            record = json.loads(fh.readline())
        key = (record["root"], record["relative_path"])
        # join miss: the archive is absent from the supplied inventory
        with self.assertRaises(QueryError) as ctx:
            query_archive_inventory(pinned, d01={("OTHER", "other.csv"): {"sha256": "0" * 64}})
        self.assertEqual(ctx.exception.check, "d01-join-miss")
        # identity mismatch: the archive is present but its sha256 disagrees
        with self.assertRaises(QueryError) as ctx:
            query_archive_inventory(pinned, d01={key: {"sha256": "0" * 64}})
        self.assertEqual(ctx.exception.check, "d01-identity-mismatch")

    def test_d01_supplied_for_non_m2_baseline_fails_closed(self):
        handle = self.open_handle()
        with self.assertRaises(QueryError) as ctx:
            query_archive_inventory(handle, d01={})
        self.assertEqual(ctx.exception.check, "d01-mismatch")

    def test_malformed_input_manifest_fails_closed(self):
        # case 1: unparseable line
        bad1 = self.copy_variant("pkg-bad1")
        with open(os.path.join(bad1, "INPUT_MANIFEST.jsonl"), "r", encoding="utf-8") as handle:
            first_line = handle.readline()
        with open(os.path.join(bad1, "INPUT_MANIFEST.jsonl"), "w", encoding="utf-8", newline="") as handle:
            handle.write(first_line + "{not-json\n")
        with self.assertRaises(QueryError) as ctx:
            query_archive_inventory(self.open_variant(bad1, self.resign_package(bad1)))
        self.assertEqual(ctx.exception.check, "input-manifest-scan")
        # case 2: missing contract key
        bad2 = self.copy_variant("pkg-bad2")
        with open(os.path.join(bad2, "INPUT_MANIFEST.jsonl"), "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        record = json.loads(lines[0])
        record.pop("rows", None)
        with open(os.path.join(bad2, "INPUT_MANIFEST.jsonl"), "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n" + "\n".join(lines[1:]) + "\n")
        with self.assertRaises(QueryError) as ctx:
            query_archive_inventory(self.open_variant(bad2, self.resign_package(bad2)))
        self.assertEqual(ctx.exception.check, "input-manifest-scan")

    def test_metadata_only_access_no_row_bytes_opened(self):
        # a handle whose manifest lists no partition (row/evidence) files at all:
        # Q9 must still succeed, proving it never opens canonical row files or
        # source archive bytes — only the two package metadata documents.
        handle = self.open_handle()
        metadata_entries = tuple(
            entry for entry in handle.manifest_entries if not entry[1].startswith("partitions/")
        )
        meta_only = Baseline(
            root=handle.root,
            spec=handle.spec,
            manifest_digest=handle.manifest_digest,
            manifest_entries=metadata_entries,
            marker=handle.marker,
            run_record=handle.run_record,
            total_bytes=handle.total_bytes,
            checks_passed=handle.checks_passed,
        )
        result = query_archive_inventory(meta_only)
        self.assertEqual(len(result["archives"]), 4)


class Q9ReadOnlyDisciplineTests(ArchiveBase):
    def test_inventory_leaves_the_package_byte_identical(self):
        before = self.package_digests()
        handle = self.open_handle()
        query_archive_inventory(handle)
        with self.assertRaises(QueryError):
            query_archive_inventory(handle, d01={})
        self.assertEqual(before, self.package_digests())


class D01InventoryIdentityTests(unittest.TestCase):
    """The committed in-repo D01 inventory must match its pinned identity."""

    def test_in_repo_d01_inventory_identity(self):
        self.assertTrue(os.path.isfile(D01_INVENTORY_PATH), D01_INVENTORY_PATH)
        with open(D01_INVENTORY_PATH, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(digest, D01_INVENTORY_SHA256)
        inventory = load_d01_inventory()
        self.assertEqual(len(inventory), D01_INVENTORY_RECORD_COUNT)
        by_root = {}
        for root, _relative_path in inventory:
            by_root[root] = by_root.get(root, 0) + 1
        self.assertEqual(by_root, {"LEGACY": 1919, "UDIFF": 543})


class D01InventoryLoadFailClosedTests(ArchiveBase):
    def test_pinned_digest_mismatch_fails_closed(self):
        wrong = os.path.join(self.root, "wrong-inventory.json")
        with open(wrong, "w", encoding="utf-8", newline="") as handle:
            handle.write("[]\n")
        with self.assertRaises(D01InventoryError) as ctx:
            load_d01_inventory(path=wrong)
        self.assertEqual(ctx.exception.check, "d01-load")

    def test_missing_path_fails_closed(self):
        with self.assertRaises(D01InventoryError) as ctx:
            load_d01_inventory(path=os.path.join(self.root, "absent.json"))
        self.assertEqual(ctx.exception.check, "d01-load")


if __name__ == "__main__":
    unittest.main()
