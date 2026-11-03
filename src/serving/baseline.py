"""Qualified-baseline access and identity verification (read-only).

The serving layer opens a run package (D16-07 durable state: the qualified baseline,
class (1)) read-only and verifies its identity before anything is served. The checks
mirror the I4 runner's offline package verification (``tools/i4_runner/i4_output.py``,
verify-01..verify-07), re-implemented at the serving boundary so that serving has no
runtime dependency on the engine's write-path tooling:

* verify-01  ``PACKAGE_MANIFEST.sha256`` present, well-formed, LF with final newline;
* verify-02  every manifest entry's file present with a matching sha256;
* verify-03  no unlisted file exists anywhere in the package (fail-closed);
* verify-04  ``RUN_COMPLETE.json`` present and its ``package_manifest_sha256`` matches
             the computed manifest digest (a package without it is incomplete by
             construction — RD-9);
* verify-05  partition manifests (``manifests/*.sha256``) consistent with file digests;
* verify-06  every artifact classifiable by exactly one MD-05 durability-class rule;
* verify-07  run-record identity (engine tool sha256, runner sha256, composite run
             identity, archive count) matches the pinned spec, when the spec pins it.

Nothing is ever written to the package directory. Any mismatch fails closed with the
exact check id and detail; no value is substituted, defaulted or normalised away.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Optional, Tuple

PACKAGE_MANIFEST = "PACKAGE_MANIFEST.sha256"
COMPLETION_MARKER = "RUN_COMPLETE.json"
RUN_RECORD = "RUN_RECORD.json"
UNMANIFESTED = (PACKAGE_MANIFEST, COMPLETION_MARKER)

#: MD-05 logical durability-class rules — transcribed verbatim from
#: ``tools/i4_runner/i4_output.py`` (the runner is the package's owner; serving
#: verifies against the same exhaustive rules and fails closed on 0 or >1 matches).
ARTIFACT_CLASS_RULES = (
    {"class": 1, "label": "authoritative engine output", "pattern": "partitions/*/*/rows/*.rows.jsonl"},
    {"class": 2, "label": "derived output (W2)", "pattern": "w2/calendar.jsonl"},
    {"class": 2, "label": "derived output (W2)", "pattern": "w2/associations.jsonl"},
    {"class": 2, "label": "derived output (W2)", "pattern": "w2/identity_summary.json"},
    {"class": 2, "label": "derived output (W2)", "pattern": "w2/metrics.json"},
    {"class": 3, "label": "provenance / evidence", "pattern": "partitions/*/*/evidence/*.evidence.json"},
    {"class": 3, "label": "provenance / evidence", "pattern": "w2/unresolved.jsonl"},
    {"class": 3, "label": "provenance / evidence", "pattern": "INPUT_MANIFEST.jsonl"},
    {"class": 3, "label": "provenance / evidence", "pattern": "PREFLIGHT.jsonl"},
    {"class": 3, "label": "provenance / evidence", "pattern": "RECONCILIATION.jsonl"},
    {"class": 3, "label": "provenance / evidence", "pattern": "GOVERNED_INPUTS.json"},
    {"class": 3, "label": "provenance / evidence", "pattern": RUN_RECORD},
    {"class": 3, "label": "provenance / evidence", "pattern": "manifests/*.sha256"},
    {"class": 3, "label": "provenance / evidence", "pattern": PACKAGE_MANIFEST},
    {"class": 3, "label": "provenance / evidence", "pattern": COMPLETION_MARKER},
)

#: Row files are the class-(1) canonical rows the slice serves.
ROW_FILE_PATTERN = "partitions/*/*/rows/*.rows.jsonl"


class BaselineError(Exception):
    """Fail-closed baseline access/verification failure (no partial serving)."""

    def __init__(self, check: str, detail: str) -> None:
        super().__init__("%s: %s" % (check, detail))
        self.check = check
        self.detail = detail


@dataclass(frozen=True)
class BaselineSpec:
    """Pinned identity of a qualified baseline.

    Every field, when not ``None``, is enforced before anything is served. The pin
    values come from the repository's durable evidence, never from the package being
    opened (an unpinned package cannot vouch for its own identity).
    """

    package_name: str
    manifest_sha256: str
    file_count: int
    total_bytes: int
    run_id: Optional[str] = None
    composite_run_identity: Optional[str] = None
    engine_tool_sha256: Optional[str] = None
    runner_sha256: Optional[str] = None
    archive_count: Optional[int] = None


#: The qualified M2 baseline (I4-qualified package ``i4-20261008-M2``).
#:
#: Pin values, all from repository-durable evidence:
#: * ``evidence/D11_REPLAY_QUALIFICATION_20261009/D11_E1_E10_TRANSFER_20261009.tar.gz``
#:   — ``A.PACKAGE_FILES.tsv`` (4,948 files; 21,119,807,344 bytes; the manifest's own
#:   digest ``e7c7e4c8…``), ``PACKAGE_MANIFEST.sha256``, ``RUN_RECORD.json``
#:   (run id, composite run identity, engine/runner identity, corpus),
#:   ``RUN_COMPLETE.json`` (completion marker);
#: * D12 (I4 closure) / D14 (I5 qualification) records of the same identifiers.
DEFAULT_M2_SPEC = BaselineSpec(
    package_name="i4-20261008-M2",
    manifest_sha256="e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc",
    file_count=4948,
    total_bytes=21119807344,
    run_id="i4-20261008-M2",
    composite_run_identity="9609c7fccef1d2438810a564ef70aa8232d8ad1c69fded8702e488c13657802d",
    engine_tool_sha256="d3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9",
    runner_sha256="f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a",
    archive_count=2462,
)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def classify_artifact(relative_path: str) -> dict:
    """The single matching MD-05 class rule; fail closed on 0 or >1 matches."""
    matches = [
        rule for rule in ARTIFACT_CLASS_RULES if fnmatch.fnmatch(relative_path, rule["pattern"])
    ]
    if len(matches) != 1:
        raise BaselineError(
            "verify-06",
            "artifact %r matches %d durability-class rules (exactly one required)"
            % (relative_path, len(matches)),
        )
    return matches[0]


@dataclass(frozen=True)
class Baseline:
    """A verified, read-only handle to a qualified run package."""

    root: str
    spec: BaselineSpec
    manifest_digest: str
    manifest_entries: Tuple[Tuple[str, str], ...]
    marker: dict
    run_record: dict
    total_bytes: int
    checks_passed: Tuple[str, ...]
    verify_on_access: bool = False

    def path(self, relative_path: str) -> str:
        path = os.path.join(self.root, relative_path.replace("/", os.sep))
        if self.verify_on_access:
            expected = next((digest for digest, name in self.manifest_entries if name == relative_path), None)
            if expected is not None:
                try:
                    valid = os.path.isfile(path) and sha256_file(path) == expected
                except OSError as exc:
                    raise BaselineError("verify-access", "cannot read qualified file %s: %s" % (relative_path, exc)) from exc
                if not valid:
                    raise BaselineError("verify-access", "qualified file missing or digest mismatch: %s" % relative_path)
            elif relative_path not in UNMANIFESTED and os.path.exists(path):
                raise BaselineError("verify-access", "file is not in the qualified manifest: %s" % relative_path)
        return path

    def row_files(self) -> Tuple[str, ...]:
        return tuple(
            relative
            for _digest, relative in self.manifest_entries
            if fnmatch.fnmatch(relative, ROW_FILE_PATTERN)
        )


def _parse_manifest(text: str, path_label: str) -> Tuple[Tuple[str, str], ...]:
    if not text or not text.endswith("\n"):
        raise BaselineError("verify-01", "manifest does not end with a final newline: %s" % path_label)
    if "\r" in text:
        raise BaselineError("verify-01", "manifest is not LF-canonical: %s" % path_label)
    entries = []
    for line in text.splitlines():
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise BaselineError("verify-01", "malformed manifest line: %r" % line)
        digest, relative = parts
        if len(digest) != 64:
            raise BaselineError("verify-01", "malformed digest in manifest line: %r" % line)
        entries.append((digest, relative))
    return tuple(entries)


def open_baseline(
    root: str,
    spec: Optional[BaselineSpec] = None,
    verify_files: bool = True,
) -> Baseline:
    """Open ``root`` read-only, verify it, and return a :class:`Baseline` handle.

    ``verify_files=False`` checks manifest and qualification metadata at open,
    and checks each manifested file's digest on access through ``path``. It
    does not claim that unaccessed files were checked. ``verify_files=True``
    remains the explicit full verification operation.

    ``spec`` pins the expected identity (required for the qualified M2 baseline).
    With ``spec=None`` only self-consistency is verified (structure, internal
    digests, completion marker) — the resulting handle is *not* pinned to any
    recorded qualified identity and must not be treated as the M2 baseline.
    """
    root = os.path.realpath(os.path.abspath(root))
    if not os.path.isdir(root):
        raise BaselineError("open", "package directory not found: %s" % root)
    manifest_path = os.path.join(root, PACKAGE_MANIFEST)
    if not os.path.isfile(manifest_path):
        raise BaselineError("verify-01", "package manifest missing")
    with open(manifest_path, "r", encoding="utf-8") as handle:
        entries = _parse_manifest(handle.read(), PACKAGE_MANIFEST)
    checks_passed = ["verify-01"]

    # verify-02: every entry present with matching digest (full pass only when requested)
    missing, mismatched = [], []
    for digest, relative in entries:
        path = os.path.join(root, relative.replace("/", os.sep))
        if not os.path.isfile(path):
            missing.append(relative)
            continue
        if verify_files and sha256_file(path) != digest:
            mismatched.append(relative)
    if missing or mismatched:
        raise BaselineError(
            "verify-02",
            "missing=%s hash_mismatch=%s"
            % (sorted(missing)[:10], sorted(mismatched)[:10]),
        )
    checks_passed.append("verify-02" if verify_files else "verify-02-presence-only")

    # verify-03: no unlisted file anywhere in the package
    listed = {relative for _digest, relative in entries}
    unlisted = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            relative = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            if relative in UNMANIFESTED:
                continue
            if relative not in listed:
                unlisted.append(relative)
    if unlisted:
        raise BaselineError("verify-03", "unlisted files present: %s" % sorted(unlisted)[:10])
    checks_passed.append("verify-03")

    # verify-04: completion marker binds the manifest
    marker_path = os.path.join(root, COMPLETION_MARKER)
    if not os.path.isfile(marker_path):
        raise BaselineError(
            "verify-04", "completion marker missing (an incomplete package must not be served)"
        )
    with open(marker_path, "r", encoding="utf-8") as handle:
        marker = json.load(handle)
    manifest_digest = sha256_file(manifest_path)
    if marker.get("package_manifest_sha256") != manifest_digest:
        raise BaselineError(
            "verify-04",
            "marker manifest digest %s != computed %s"
            % (marker.get("package_manifest_sha256"), manifest_digest),
        )
    checks_passed.append("verify-04")

    # verify-05: partition manifests consistent
    partition_bad = []
    manifest_pairs = set(entries)
    for _digest, relative in entries:
        if not (relative.startswith("manifests/") and relative.endswith(".sha256")):
            continue
        sub_path = os.path.join(root, relative.replace("/", os.sep))
        if not verify_files and sha256_file(sub_path) != _digest:
            raise BaselineError("verify-05", "partition manifest digest mismatch: %s" % relative)
        with open(sub_path, "r", encoding="utf-8") as handle:
            sub_entries = _parse_manifest(handle.read(), relative)
        for entry_digest, entry_relative in sub_entries:
            target = os.path.join(root, entry_relative.replace("/", os.sep))
            if not os.path.isfile(target) or (sha256_file(target) != entry_digest if verify_files else
                    (entry_digest, entry_relative) not in manifest_pairs):
                partition_bad.append("%s :: %s" % (relative, entry_relative))
    if partition_bad:
        raise BaselineError("verify-05", "partition manifest inconsistencies: %s" % partition_bad[:10])
    checks_passed.append("verify-05" if verify_files else "verify-05-manifest-consistency-only")

    # verify-06: every artifact classifiable by exactly one MD-05 rule
    class_bad = []
    for relative in sorted(listed):
        try:
            classify_artifact(relative)
        except BaselineError as exc:
            class_bad.append(exc.detail)
    if class_bad:
        raise BaselineError("verify-06", "unclassifiable artifacts: %s" % class_bad[:10])
    checks_passed.append("verify-06")

    # file count / total bytes (all files incl. manifest + marker)
    total_bytes = 0
    file_count = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            total_bytes += os.path.getsize(os.path.join(dirpath, name))
            file_count += 1

    # verify-07: run-record identity against the pin
    record_path = os.path.join(root, RUN_RECORD)
    if not os.path.isfile(record_path):
        raise BaselineError("verify-07", "run record missing")
    if not verify_files:
        record_digest = next((digest for digest, relative in entries if relative == RUN_RECORD), None)
        if record_digest is None or sha256_file(record_path) != record_digest:
            raise BaselineError("verify-07", "run record digest mismatch")
    with open(record_path, "r", encoding="utf-8") as handle:
        run_record = json.load(handle)
    if spec is not None:
        if spec.run_id is not None and marker.get("run_id") != spec.run_id:
            raise BaselineError("verify-07", "marker run_id %r != pinned %r" % (marker.get("run_id"), spec.run_id))
        if (
            spec.composite_run_identity is not None
            and run_record.get("composite_run_identity") != spec.composite_run_identity
        ):
            raise BaselineError(
                "verify-07",
                "composite_run_identity %r != pinned %r"
                % (run_record.get("composite_run_identity"), spec.composite_run_identity),
            )
        engine_recorded = run_record.get("engine_identity", {}).get("tool_sha256")
        if spec.engine_tool_sha256 is not None and engine_recorded != spec.engine_tool_sha256:
            raise BaselineError(
                "verify-07", "engine tool_sha256 %r != pinned %r" % (engine_recorded, spec.engine_tool_sha256)
            )
        runner_recorded = run_record.get("runner_identity", {}).get("runner_sha256")
        if spec.runner_sha256 is not None and runner_recorded != spec.runner_sha256:
            raise BaselineError(
                "verify-07", "runner_sha256 %r != pinned %r" % (runner_recorded, spec.runner_sha256)
            )
        archive_count = run_record.get("corpus", {}).get("archive_count")
        if spec.archive_count is not None and archive_count != spec.archive_count:
            raise BaselineError(
                "verify-07", "corpus.archive_count %r != pinned %r" % (archive_count, spec.archive_count)
            )
        if manifest_digest != spec.manifest_sha256:
            raise BaselineError(
                "verify-07", "manifest digest %s != pinned %s" % (manifest_digest, spec.manifest_sha256)
            )
        if file_count != spec.file_count:
            raise BaselineError(
                "verify-07", "file count %d != pinned %d" % (file_count, spec.file_count)
            )
        if total_bytes != spec.total_bytes:
            raise BaselineError(
                "verify-07", "total bytes %d != pinned %d" % (total_bytes, spec.total_bytes)
            )
    checks_passed.append("verify-07")

    return Baseline(
        root=root,
        spec=spec,
        manifest_digest=manifest_digest,
        manifest_entries=entries,
        marker=marker,
        run_record=run_record,
        total_bytes=total_bytes,
        checks_passed=tuple(checks_passed),
        verify_on_access=not verify_files,
    )
