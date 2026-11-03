"""Serving read model — durable state class (4) of D16-07.

The index is a pure derivation of the verified baseline: one linear pass over every
class-(1) row file collecting, per row file, the set of (listing_symbol, series)
instrument pairs present, the row count, the minimum/maximum as-published
``business_date`` (format serving-index/1.1), and — in serving-index/1.2 — the
global flag census: per governed flag ``name`` (the D05 §5 ``flags[].name``
field on canonical rows), the number of rows carrying that flag. It stores no row
values, no raw line text, and no clock/host/path value; identical baseline bytes
yield a byte-identical index (D05 §9 conventions; MD-10 criteria 1/4).

Deleting the index is never a data event (D16-07): it is always rebuildable from the
baseline, and when it ever disagrees with the baseline the baseline wins and the
index is rebuilt (D16-07 conflict rule). A stale index (built over a different
package identity) is detected on load and refused.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import contextlib
from typing import Optional, Tuple

from .baseline import Baseline
from .paths import validate_roots

INDEX_FILENAME = "serving_index.json"
INDEX_DIGEST_FILENAME = "serving_index.sha256"
INDEX_FORMAT = "serving-index/1.2"


class ServingIndexError(Exception):
    """Fail-closed index build/load failure (no serving on a bad read model)."""

    def __init__(self, check: str, detail: str) -> None:
        super().__init__("%s: %s" % (check, detail))
        self.check = check
        self.detail = detail


def canonical_json(obj) -> str:
    """Canonical document form (D05 §9): sorted keys, compact, LF text."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _write_text(path: str, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix="." + os.path.basename(path) + ".", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _package_identity(baseline: Baseline) -> dict:
    spec = baseline.spec
    return {
        "package_name": spec.package_name if spec is not None else "unpinned",
        "manifest_sha256": baseline.manifest_digest,
        "file_count": len(baseline.manifest_entries) + 2,
        "total_bytes": baseline.total_bytes,
        "run_id": baseline.marker.get("run_id"),
        "composite_run_identity": baseline.run_record.get("composite_run_identity"),
        "engine_tool_sha256": baseline.run_record.get("engine_identity", {}).get("tool_sha256"),
        "runner_sha256": baseline.run_record.get("runner_identity", {}).get("runner_sha256"),
        "archive_count": baseline.run_record.get("corpus", {}).get("archive_count"),
    }


def build_index(baseline: Baseline) -> dict:
    """One linear, read-only pass over the class-(1) row files.

    Deterministic: files are scanned in manifest order (already sorted), pair lists
    are sorted, per-file date bounds are order-independent min/max over the
    as-published ``business_date`` values (files without a dated row carry null
    bounds), documents are canonically keyed, and no clock/host/path value is
    embedded. A row that fails to parse or lacks the contract keys is a package
    integrity failure (fail closed), never a silently skipped record.
    """
    files = {}
    partitions = {}
    global_pairs = set()
    rows_total = 0
    flag_census = {}
    for relative in baseline.row_files():
        parts = relative.split("/")
        family, year = parts[1], parts[2]
        stem = parts[4][: -len(".rows.jsonl")]
        pairs = set()
        count = 0
        date_min: Optional[str] = None
        date_max: Optional[str] = None
        with open(baseline.path(relative), "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise ServingIndexError("index-scan", "unparseable canonical row in %s: %s" % (relative, exc))
                values = obj.get("source_values")
                if not isinstance(values, dict) or "listing_symbol" not in values or "series" not in values:
                    raise ServingIndexError(
                        "index-scan", "canonical row without contract keys in %s" % relative
                    )
                symbol = values.get("listing_symbol") or ""
                series = values.get("series") or ""
                pairs.add((symbol, series))
                count += 1
                business_date = obj.get("business_date")
                if isinstance(business_date, str) and business_date:
                    if date_min is None or business_date < date_min:
                        date_min = business_date
                    if date_max is None or business_date > date_max:
                        date_max = business_date
                # serving-index/1.2: global flag census (D05 §5; never gating).
                # The census counts what the canonical rows publish, per flag
                # ``name``; a row without a ``flags`` list carries none. A flag
                # entry that is not a record with a string ``name`` is a package
                # integrity failure (fail closed), never a silently skipped flag.
                flags = obj.get("flags", [])
                if not isinstance(flags, list):
                    raise ServingIndexError("index-scan", "canonical row with a non-list flags field in %s" % relative)
                for flag in flags:
                    if not isinstance(flag, dict) or not isinstance(flag.get("name"), str) or not flag.get("name"):
                        raise ServingIndexError("index-scan", "canonical row with a malformed flag entry in %s" % relative)
                    name = flag["name"]
                    flag_census[name] = flag_census.get(name, 0) + 1
        rows_total += count
        pairs_list = sorted([list(pair) for pair in pairs])
        files[relative] = {
            "family": family,
            "year": year,
            "member_stem": stem,
            "row_count": count,
            "instruments": pairs_list,
            "business_date_min": date_min,
            "business_date_max": date_max,
        }
        for pair in pairs:
            global_pairs.add(pair)
        partition_key = "%s/%s" % (family, year)
        partition = partitions.setdefault(
            partition_key,
            {"family": family, "year": year, "row_files": 0, "row_count": 0},
        )
        partition["row_files"] += 1
        partition["row_count"] += count
    return {
        "format": INDEX_FORMAT,
        "package": _package_identity(baseline),
        "partitions": partitions,
        "files": files,
        "flag_census": flag_census,
        "counts": {
            "row_files": len(files),
            "row_count": rows_total,
            "instrument_pairs": len(global_pairs),
        },
    }


def write_index(state_dir: str, document: dict) -> str:
    """Persist the index (class-4 state) as a canonical file + digest sidecar.

    Returns the index file's sha256. The state directory is created if absent and
    must live OUTSIDE the baseline package (never inside it).
    """
    validate_roots(state=state_dir)
    os.makedirs(state_dir, exist_ok=True)
    text = canonical_json(document) + "\n"
    digest = _sha256_text(text)
    _write_text(os.path.join(state_dir, INDEX_FILENAME), text)
    _write_text(os.path.join(state_dir, INDEX_DIGEST_FILENAME), "%s  %s\n" % (digest, INDEX_FILENAME))
    return digest


def load_index(state_dir: str, baseline: Baseline) -> Tuple[dict, str]:
    """Load the index, verifying its digest and its package identity against ``baseline``.

    The conflict rule (D16-07): the baseline is the source of truth. An index whose
    embedded package identity differs from the verified baseline is stale and is
    refused (``ServingIndexError``) — the remedy is a rebuild, never a silent serve.
    """
    validate_roots(package=baseline.root, state=state_dir)
    index_path = os.path.join(state_dir, INDEX_FILENAME)
    digest_path = os.path.join(state_dir, INDEX_DIGEST_FILENAME)
    if not (os.path.isfile(index_path) and os.path.isfile(digest_path)):
        raise ServingIndexError("index-load", "serving state missing or incomplete (run a build)")
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            text = handle.read()
        digest = _sha256_text(text)
        with open(digest_path, "r", encoding="utf-8") as handle:
            sidecar = handle.read()
    except (UnicodeError, OSError) as exc:
        raise ServingIndexError("index-load", "cannot read serving state: %s" % exc)
    if sidecar != "%s  %s\n" % (digest, INDEX_FILENAME):
        raise ServingIndexError("index-load", "index digest sidecar mismatch")
    try:
        document = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ServingIndexError("index-load", "invalid index JSON: %s" % exc)
    if not isinstance(document, dict):
        raise ServingIndexError("index-load", "index is not an object")
    if document.get("format") != INDEX_FORMAT:
        raise ServingIndexError("index-load", "unknown index format %r" % document.get("format"))
    identity = document.get("package", {})
    current = _package_identity(baseline)
    for key in ("manifest_sha256", "file_count", "total_bytes", "run_id"):
        if identity.get(key) != current.get(key):
            raise ServingIndexError(
                "index-stale",
                "index package identity %s=%r != baseline %r — rebuild required" % (key, identity.get(key), current.get(key)),
            )
    return document, digest


def index_state(state_dir: str) -> Optional[dict]:
    """Diagnostic summary of the serving state without requiring a baseline."""
    index_path = os.path.join(state_dir, INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return None
    with open(index_path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    return {
        "format": document.get("format"),
        "package": document.get("package"),
        "counts": document.get("counts"),
        "partitions": document.get("partitions"),
    }
