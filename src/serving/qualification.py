"""Q10 qualification and evidence views (D16-10 Q10).

Contract (D16-10 Q10 "qualification/evidence views (run identity,
fingerprints, manifests, R6/D11/D12/D14 records)"; D16-07; D23 §§9-10/17(a);
D24 constraints; D30b Q10 contract assessment):

* **Package-provided data** — only fields actually present in the verified
  package records are exposed, as published: run identity (``run_id``,
  ``composite_run_identity``, ``contract_version``, ``config`` fingerprints),
  ``engine_identity`` and ``runner_identity`` (fingerprints as published),
  corpus / archive-set information, ``counts``, ``authority`` / ``boundary``,
  ``verification``, the ``RUN_COMPLETE`` marker, ``GOVERNED_INPUTS``, and the
  package manifest facts. Absent fields stay absent — never substituted with
  zero, empty string, or null.
* **Pinned identity** — the evidence-derived pin values enforced by
  ``open_baseline`` (verify-07) are composed, not recomputed: the same
  identity the ``verify`` command reports.
* **Durable in-repository evidence** — the R6 replay-qualification verdict
  (inside the D11 transfer tarball), the D11 replay-qualification evidence
  (transfer + publication pin), the D12 I4 closure decision, and the D14 I5
  authority decision are identified at their pinned in-repository locations
  and associated with the selected package/run **by verified identity**
  (run id, composite run identity, engine/runner fingerprints, corpus
  archive-set digest) — never inferred from filenames. A record whose
  identity cannot be parsed or bound is reported as not associated, and a
  record whose pinned digest disagrees with its bytes is reported as an
  integrity mismatch. The repository evidence is always kept distinct from
  the package's own files in the response schema; it is never claimed to be
  embedded in the package.
* **Fail closed** — contradictory run identities, manifest digests, or
  fingerprint bindings inside the package fail closed before any output;
  malformed present ``GOVERNED_INPUTS`` fails closed. No partial results.

Read-only: the query opens at most ``GOVERNED_INPUTS.json`` from the package
and the pinned in-repository evidence files; it writes nothing and produces
no serving state. Deterministic for a given package and repository state; no
clock, host, or randomness in the output.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tarfile
from typing import Optional, Tuple

from .baseline import Baseline, sha256_file
from .query import QueryError

QUALIFICATION_QUERY_ID = "Q10-qualification"

GOVERNED_INPUTS = "GOVERNED_INPUTS.json"

# Pinned in-repository evidence locations (repo-relative). These are the
# durable records named by D16-10 Q10; association is by their verified
# identity content, never by their names.
D11_DIR = "evidence/D11_REPLAY_QUALIFICATION_20261009"
D11_PUBLICATION = D11_DIR + "/D11_EVIDENCE_PUBLICATION.md"
D11_TARBALL = D11_DIR + "/D11_E1_E10_TRANSFER_20261009.tar.gz"
D11_R6_MEMBER = "D11_E1_E10_TRANSFER_20261009/D11_R6_REPLAY_QUALIFICATION_VERDICT.json"
D12_RECORD = "docs/investigations/D12_I4_CLOSURE_DECISION.md"
D14_RECORD = "docs/investigations/D14_I5_AUTHORITY_DECISION_10YEAR_FULL_QUALIFICATION.md"

# Association states (every state is derived from verified record content).
ASSOCIATED = "associated"
NOT_ASSOCIATED = "not-associated"
ABSENT = "absent"
INTEGRITY_MISMATCH = "integrity-mismatch"
UNREADABLE = "unreadable"
NOT_IDENTITY_BOUND = "not-identity-bound"

_EVIDENCE_BOUNDARY = (
    "durable in-repository evidence, distinct from the package's own files "
    "(never claimed to be embedded in the package); association is by "
    "verified identity, never inferred from filenames"
)

_D11_PINS = (
    ("tarball_sha256", re.compile(r"(?m)^SHA256:\n([0-9a-f]{64})")),
    ("engine_revision", re.compile(r"(?m)^Executed engine revision:\n([0-9a-f]{40})")),
    ("engine_fingerprint", re.compile(r"(?m)^Executed engine fingerprint:\n([0-9a-f]{64})")),
    ("runner_fingerprint", re.compile(r"(?m)^Executed runner fingerprint:\n([0-9a-f]{64})")),
    ("m2_run", re.compile(r"(?m)^M2 run:\n(\S+)")),
    ("replay_run", re.compile(r"(?m)^Replay run:\n(\S+)")),
)

_D12_COMPOSITE = re.compile(r"composite run identity `([0-9a-f]{64})`")
_D12_CORPUS = re.compile(r"corpus archive-set digest `([0-9a-f]{64})`")
_D12_R6_SHA = re.compile(
    r"D11_R6_REPLAY_QUALIFICATION_VERDICT\.json`, sha256\s*`([0-9a-f]{64})`", re.DOTALL
)


def _require_str(value, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise QueryError("run-identity", "RUN_RECORD without a usable %s" % label)
    return value


def _package_identity(run_record: dict, marker: dict) -> Tuple[str, str, dict]:
    """Run identity with the fail-closed record/marker agreement checks."""
    run_id = _require_str(run_record.get("run_id"), "run_id")
    composite = _require_str(run_record.get("composite_run_identity"), "composite_run_identity")
    marker_run_id = marker.get("run_id")
    if marker_run_id is not None and marker_run_id != run_id:
        raise QueryError(
            "run-identity", "RUN_COMPLETE run_id %r != RUN_RECORD run_id %r" % (marker_run_id, run_id)
        )
    marker_contract = marker.get("contract_version")
    record_contract = run_record.get("contract_version")
    if marker_contract is not None and record_contract is not None and marker_contract != record_contract:
        raise QueryError(
            "run-identity",
            "RUN_COMPLETE contract_version %r != RUN_RECORD contract_version %r"
            % (marker_contract, record_contract),
        )
    return run_id, composite, run_record


def _internal_consistency(baseline: Baseline, run_record: dict, marker: dict) -> None:
    """Presence-guarded cross-bindings between the package's own records."""
    marker_manifest = marker.get("package_manifest_sha256")
    if marker_manifest is not None and marker_manifest != baseline.manifest_digest:
        raise QueryError(
            "manifest-digest",
            "RUN_COMPLETE package_manifest_sha256 %r != verified manifest digest %r"
            % (marker_manifest, baseline.manifest_digest),
        )
    engine = run_record.get("engine_identity")
    if isinstance(engine, dict):
        modules = engine.get("engine_modules")
        count = engine.get("engine_module_count")
        if isinstance(modules, list) and isinstance(count, int) and not isinstance(count, bool):
            if count != len(modules):
                raise QueryError(
                    "identity-binding",
                    "engine_module_count %d != len(engine_modules) %d" % (count, len(modules)),
                )
    corpus = run_record.get("corpus")
    counts = run_record.get("counts")
    archive_count = corpus.get("archive_count") if isinstance(corpus, dict) else None
    if isinstance(counts, dict) and isinstance(archive_count, int) and not isinstance(archive_count, bool):
        members = counts.get("members")
        if isinstance(members, int) and not isinstance(members, bool) and members != archive_count:
            raise QueryError(
                "identity-binding", "corpus.archive_count %d != counts.members %d" % (archive_count, members)
            )
        partitions = corpus.get("partitions") if isinstance(corpus, dict) else None
        if isinstance(partitions, list) and partitions:
            partition_members = 0
            for entry in partitions:
                if not isinstance(entry, dict) or not isinstance(entry.get("members"), int) or isinstance(entry.get("members"), bool):
                    raise QueryError("identity-binding", "corpus.partitions entry without an integer members count")
                partition_members += entry["members"]
            if partition_members != archive_count:
                raise QueryError(
                    "identity-binding",
                    "sum(corpus.partitions.members) %d != corpus.archive_count %d"
                    % (partition_members, archive_count),
                )
    verification = run_record.get("verification")
    marker_recon = marker.get("reconciliation")
    if isinstance(verification, dict) and isinstance(marker_recon, dict):
        record_recon = verification.get("reconciliation")
        if isinstance(record_recon, dict):
            for key in ("by_result", "by_tier", "records"):
                if key in record_recon and key in marker_recon and record_recon[key] != marker_recon[key]:
                    raise QueryError(
                        "reconciliation-aggregate",
                        "RUN_RECORD verification.reconciliation[%s] %r != RUN_COMPLETE reconciliation[%s] %r"
                        % (key, record_recon[key], key, marker_recon[key]),
                    )


def _governed_inputs(baseline: Baseline, run_record: dict, run_id: str, composite: str) -> dict:
    """Parse GOVERNED_INPUTS when present (fail closed); bind its identity."""
    state = {"present": False}
    path = baseline.path(GOVERNED_INPUTS)
    if not os.path.isfile(path):
        return state
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except ValueError as exc:
        raise QueryError("governed-inputs", "unparseable GOVERNED_INPUTS.json: %s" % exc)
    if not isinstance(data, dict):
        raise QueryError("governed-inputs", "GOVERNED_INPUTS.json is not a record")
    state["present"] = True
    state["data"] = data
    corpus = run_record.get("corpus")
    engine = run_record.get("engine_identity")
    runner = run_record.get("runner_identity")
    config = run_record.get("config")
    for label, evidence_value, package_value in (
        ("run_id", data.get("run_id"), run_id),
        ("composite_run_identity", data.get("composite_run_identity"), composite),
        (
            "corpus.archive_set_digest",
            (data.get("corpus") or {}).get("archive_set_digest") if isinstance(data.get("corpus"), dict) else None,
            corpus.get("archive_set_digest") if isinstance(corpus, dict) else None,
        ),
        (
            "engine_identity.tool_sha256",
            (data.get("engine_identity") or {}).get("tool_sha256") if isinstance(data.get("engine_identity"), dict) else None,
            engine.get("tool_sha256") if isinstance(engine, dict) else None,
        ),
        (
            "runner_identity.runner_sha256",
            (data.get("runner_identity") or {}).get("runner_sha256") if isinstance(data.get("runner_identity"), dict) else None,
            runner.get("runner_sha256") if isinstance(runner, dict) else None,
        ),
        (
            "config_fingerprint",
            data.get("config_fingerprint"),
            config.get("config_fingerprint") if isinstance(config, dict) else None,
        ),
    ):
        if evidence_value is not None and package_value is not None and evidence_value != package_value:
            raise QueryError(
                "identity-binding", "GOVERNED_INPUTS %s %r != RUN_RECORD %r" % (label, evidence_value, package_value)
            )
    return state


def _package_section(baseline: Baseline, run_record: dict, marker: dict, governed_inputs: dict) -> dict:
    """Key-driven as-published projection of the verified package records."""
    package = {}
    run_identity = {
        "run_id": run_record["run_id"],
        "composite_run_identity": run_record["composite_run_identity"],
    }
    if run_record.get("contract_version") is not None:
        run_identity["contract_version"] = run_record["contract_version"]
    if isinstance(run_record.get("config"), dict):
        run_identity["config"] = run_record["config"]
    package["run_identity"] = run_identity
    for key in ("engine_identity", "runner_identity", "corpus", "counts", "authority", "boundary", "verification"):
        if isinstance(run_record.get(key), dict):
            package[key] = run_record[key]
    package["run_complete"] = marker
    package["governed_inputs"] = governed_inputs
    corpus = run_record.get("corpus")
    manifests = {"package_manifest_sha256": baseline.manifest_digest}
    if isinstance(corpus, dict) and corpus.get("archive_set_digest") is not None:
        manifests["archive_set_digest"] = corpus["archive_set_digest"]
    if baseline.spec is not None and baseline.spec.package_name is not None:
        manifests["package_name"] = baseline.spec.package_name
    # the verified file count: every manifest entry plus the manifest and the
    # completion marker (the two unmanifested package files)
    manifests["file_count"] = len(baseline.manifest_entries) + 2
    manifests["total_bytes"] = baseline.total_bytes
    package["manifests"] = manifests
    return package


def _pinned_section(baseline: Baseline) -> dict:
    """The evidence-derived pins enforced by open_baseline (verify-07)."""
    spec = baseline.spec
    if spec is None:
        return {
            "pinned": False,
            "note": (
                "opened without an identity pin: the handle is not pinned to any recorded "
                "qualified identity and must not be treated as the qualified M2 baseline"
            ),
        }
    pinned = {}
    for field in ("package_name", "manifest_sha256", "file_count", "total_bytes", "run_id", "composite_run_identity", "engine_tool_sha256", "runner_sha256", "archive_count"):
        value = getattr(spec, field)
        if value is not None:
            pinned[field] = value
    section = {"pinned": bool(pinned), "pinned_fields": pinned}
    if pinned:
        section["enforcement"] = "open_baseline verify-07 (before anything is served)"
    else:
        section["note"] = "no identity pins: the handle is not pinned to any recorded qualified identity"
    return section


def _associate(bindings: dict) -> Tuple[str, str]:
    """Association state from verified identity bindings only."""
    parsed = {label: values for label, values in bindings.items() if values[0] is not None}
    if not parsed:
        return NOT_ASSOCIATED, "no identity binding parseable in the record"
    mismatches = [label for label, (expected, actual) in parsed.items() if expected != actual]
    if mismatches:
        return NOT_ASSOCIATED, "identity binding mismatch: " + ", ".join(sorted(mismatches))
    return ASSOCIATED, "identity binding holds: " + ", ".join(sorted(parsed))


def _read_d11_publication(repo_root: str) -> Optional[dict]:
    path = os.path.join(repo_root, D11_PUBLICATION.replace("/", os.sep))
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    pin = {}
    for label, pattern in _D11_PINS:
        match = pattern.search(text)
        if match:
            pin[label] = match.group(1)
    return pin or None


def _read_r6_verdict(repo_root: str) -> Tuple[Optional[bytes], str]:
    """The R6 verdict bytes from the pinned D11 tarball member, or an error."""
    path = os.path.join(repo_root, D11_TARBALL.replace("/", os.sep))
    if not os.path.isfile(path):
        return None, ABSENT
    try:
        with tarfile.open(path, "r:gz") as tar:
            handle = tar.extractfile(D11_R6_MEMBER)
            if handle is None:
                return None, "unreadable (member missing from tarball)"
            return handle.read(), "ok"
    except (OSError, tarfile.TarError) as exc:
        return None, "unreadable (%s)" % exc.__class__.__name__
    except ValueError as exc:
        return None, "unreadable (%s)" % exc.__class__.__name__


def _evidence_r6(repo_root, run_id, composite, engine_sha, corpus_digest) -> dict:
    record = {
        "record": "R6 replay-qualification verdict",
        "location": "%s::%s" % (D11_TARBALL, D11_R6_MEMBER),
    }
    verdict_bytes, status = _read_r6_verdict(repo_root)
    if status == ABSENT:
        record.update({"present": False, "association": ABSENT, "association_basis": "D11 transfer tarball not found at the pinned location"})
        return record
    if verdict_bytes is None:
        record.update({"present": True, "association": UNREADABLE, "association_basis": status})
        return record
    try:
        verdict = json.loads(verdict_bytes)
    except ValueError:
        record.update({"present": True, "association": UNREADABLE, "association_basis": "verdict is not valid JSON"})
        return record
    if not isinstance(verdict, dict):
        record.update({"present": True, "association": UNREADABLE, "association_basis": "verdict is not a record"})
        return record
    packages_a = verdict.get("packages", {}).get("a", {}) if isinstance(verdict.get("packages"), dict) else {}
    revision = verdict.get("revision", {}) if isinstance(verdict.get("revision"), dict) else {}
    identity = {}
    if isinstance(packages_a, dict):
        if packages_a.get("completion_marker_run_id") is not None:
            identity["run_id"] = packages_a["completion_marker_run_id"]
        if packages_a.get("composite_run_identity") is not None:
            identity["composite_run_identity"] = packages_a["composite_run_identity"]
    if isinstance(revision, dict):
        if revision.get("engine_fingerprint") is not None:
            identity["engine_fingerprint"] = revision["engine_fingerprint"]
        if revision.get("corpus_archive_set_digest") is not None:
            identity["corpus_archive_set_digest"] = revision["corpus_archive_set_digest"]
        if revision.get("revision_commit") is not None:
            identity["revision_commit"] = revision["revision_commit"]
    if verdict.get("contract_version") is not None:
        identity["contract_version"] = verdict["contract_version"]
    record["present"] = True
    if identity:
        record["identity"] = identity
    if verdict.get("result") is not None:
        record["result"] = verdict["result"]
    if verdict.get("failures") is not None:
        record["failures"] = verdict["failures"]
    state, basis = _associate(
        {
            "run_id": (identity.get("run_id"), run_id),
            "composite_run_identity": (identity.get("composite_run_identity"), composite),
            "engine_fingerprint": (identity.get("engine_fingerprint"), engine_sha),
            "corpus_archive_set_digest": (identity.get("corpus_archive_set_digest"), corpus_digest),
        }
    )
    record.update({"association": state, "association_basis": basis})
    return record


def _evidence_d11(repo_root, run_id, engine_sha, runner_sha) -> dict:
    record = {
        "record": "D11 replay-qualification evidence (transfer + publication pin)",
        "location": D11_DIR,
    }
    publication = _read_d11_publication(repo_root)
    tarball_path = os.path.join(repo_root, D11_TARBALL.replace("/", os.sep))
    present = publication is not None or os.path.isfile(tarball_path)
    if not present:
        record.update({"present": False, "association": ABSENT, "association_basis": "D11 evidence not found at the pinned location"})
        return record
    record["present"] = True
    if publication:
        record["pin"] = publication
    integrity = None
    if publication and "tarball_sha256" in publication and os.path.isfile(tarball_path):
        computed = sha256_file(tarball_path)
        integrity = {
            "tarball_sha256": {
                "published": publication["tarball_sha256"],
                "computed": computed,
                "match": computed == publication["tarball_sha256"],
            }
        }
        record["verified"] = integrity
    if integrity and not integrity["tarball_sha256"]["match"]:
        record.update(
            {
                "association": INTEGRITY_MISMATCH,
                "association_basis": "tarball sha256 does not match the publication pin",
            }
        )
        return record
    state, basis = _associate(
        {
            "m2_run": ((publication or {}).get("m2_run"), run_id),
            "engine_fingerprint": ((publication or {}).get("engine_fingerprint"), engine_sha),
            "runner_fingerprint": ((publication or {}).get("runner_fingerprint"), runner_sha),
        }
    )
    record.update({"association": state, "association_basis": basis})
    return record


def _evidence_d12(repo_root, composite, corpus_digest, r6_verdict_bytes) -> dict:
    record = {"record": "D12 I4 closure decision (M2 execution + R6 replay qualification)", "location": D12_RECORD}
    path = os.path.join(repo_root, D12_RECORD.replace("/", os.sep))
    if not os.path.isfile(path):
        record.update({"present": False, "association": ABSENT, "association_basis": "record not found at the pinned location"})
        return record
    record["present"] = True
    identity = {}
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    match = _D12_COMPOSITE.search(text)
    if match:
        identity["composite_run_identity"] = match.group(1)
    match = _D12_CORPUS.search(text)
    if match:
        identity["corpus_archive_set_digest"] = match.group(1)
    r6_pinned = None
    match = _D12_R6_SHA.search(text)
    if match:
        r6_pinned = match.group(1)
        identity["r6_verdict_sha256"] = r6_pinned
    if identity:
        record["identity"] = identity
    if r6_pinned is not None and r6_verdict_bytes is not None:
        computed = hashlib.sha256(r6_verdict_bytes).hexdigest()
        record["r6_verdict_sha256_check"] = {
            "pinned": r6_pinned,
            "computed": computed,
            "match": computed == r6_pinned,
        }
    state, basis = _associate(
        {
            "composite_run_identity": (identity.get("composite_run_identity"), composite),
            "corpus_archive_set_digest": (identity.get("corpus_archive_set_digest"), corpus_digest),
        }
    )
    record.update({"association": state, "association_basis": basis})
    return record


def _evidence_d14(repo_root) -> dict:
    record = {
        "record": "D14 I5 authority decision (10-year full qualification)",
        "location": D14_RECORD,
        "kind": "authority-record",
    }
    path = os.path.join(repo_root, D14_RECORD.replace("/", os.sep))
    if not os.path.isfile(path):
        record.update({"present": False, "association": ABSENT, "association_basis": "record not found at the pinned location"})
        return record
    record["present"] = True
    record.update(
        {
            "association": NOT_IDENTITY_BOUND,
            "association_basis": (
                "authority record that governed the execution; it carries no run-identity "
                "binding, so applicability is by governance, never by identity"
            ),
        }
    )
    return record


def query_qualification(baseline: Baseline, repo_root: Optional[str] = None) -> dict:
    """Q10 qualification and evidence view (D16-10 Q10).

    ``baseline`` is an opened, verified baseline handle. ``repo_root`` is the
    root of the durable repository that holds the in-repository evidence
    records (R6/D11/D12/D14); when omitted, every evidence record is reported
    explicitly absent — never inferred. Returns a document shaped for
    canonical-JSON serving with the package's own data (``package``), the
    evidence-derived pinned identity (``pinned_identity``), and the durable
    in-repository evidence (``evidence``) kept in separate sections.

    Read-only; deterministic; fail closed with no partial output.
    """
    if not isinstance(baseline, Baseline):
        raise QueryError("qualification", "baseline must be an opened, verified baseline handle")
    if repo_root is not None and (not isinstance(repo_root, str) or not os.path.isdir(repo_root)):
        raise QueryError("qualification", "repo_root is not an existing directory: %r" % (repo_root,))
    run_record = baseline.run_record
    marker = baseline.marker
    run_id, composite, _record = _package_identity(run_record, marker)
    _internal_consistency(baseline, run_record, marker)
    governed_inputs = _governed_inputs(baseline, run_record, run_id, composite)
    corpus = run_record.get("corpus")
    corpus_digest = corpus.get("archive_set_digest") if isinstance(corpus, dict) else None
    engine = run_record.get("engine_identity")
    engine_sha = engine.get("tool_sha256") if isinstance(engine, dict) else None
    runner = run_record.get("runner_identity")
    runner_sha = runner.get("runner_sha256") if isinstance(runner, dict) else None
    package = _package_section(baseline, run_record, marker, governed_inputs)
    pinned = _pinned_section(baseline)
    if repo_root is not None:
        repo_root = os.path.realpath(os.path.abspath(repo_root))
    if repo_root is None:
        evidence = {"boundary": _EVIDENCE_BOUNDARY, "repo_root_provided": False}
        for key, builder in (
            ("r6", lambda: {"record": "R6 replay-qualification verdict", "location": "%s::%s" % (D11_TARBALL, D11_R6_MEMBER), "present": False, "association": ABSENT, "association_basis": "no repository root provided"}),
            ("d11", lambda: {"record": "D11 replay-qualification evidence (transfer + publication pin)", "location": D11_DIR, "present": False, "association": ABSENT, "association_basis": "no repository root provided"}),
            ("d12", lambda: {"record": "D12 I4 closure decision (M2 execution + R6 replay qualification)", "location": D12_RECORD, "present": False, "association": ABSENT, "association_basis": "no repository root provided"}),
            ("d14", lambda: {"record": "D14 I5 authority decision (10-year full qualification)", "location": D14_RECORD, "kind": "authority-record", "present": False, "association": ABSENT, "association_basis": "no repository root provided"}),
        ):
            evidence[key] = builder()
    else:
        r6_verdict_bytes, _status = _read_r6_verdict(repo_root)
        evidence = {
            "boundary": _EVIDENCE_BOUNDARY,
            "repo_root_provided": True,
            "r6": _evidence_r6(repo_root, run_id, composite, engine_sha, corpus_digest),
            "d11": _evidence_d11(repo_root, run_id, engine_sha, runner_sha),
            "d12": _evidence_d12(repo_root, composite, corpus_digest, r6_verdict_bytes),
            "d14": _evidence_d14(repo_root),
        }
    return {
        "query": QUALIFICATION_QUERY_ID,
        "package": package,
        "pinned_identity": pinned,
        "evidence": evidence,
    }
