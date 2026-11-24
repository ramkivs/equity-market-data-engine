"""Class-(4) ISIN/series/date correlation index (D40 EC-DEC-02 / Addendum C-1 §5.2, §5.4, §5.5).

This module builds, verifies and loads the **derived** Class-(4) correlation
index the owner approved on 2026-11-24 for the IIPS–EquiCore personal-use
integration:

    key = (isin_normalized, series, business_date)

It is **Class-(4) serving state (D16-07)**: a pure derivation of the qualified
class-(1) package plus class-(2) publications, rebuildable at any time, stored
at a caller-chosen ``--state`` root OUTSIDE the package; deleting it is never a
data event, and on any disagreement the baseline wins and the index is rebuilt.

**Eligibility is exclusive and absolute** (D40 §5.4-2): a row enters the index
iff its stored ``isin_validity`` equals ``'VALID'`` — the classification the
engine computes (``src/nse_engine/rows.py``) and stores on the canonical row.
No other predicate is applied here, and **none of this module may ever be used
to filter, gate, or suppress canonical rows anywhere else**: observation
retrieval is validity-agnostic (D40 §5.4-4) and this module is never imported
on an observation-retrieval path for that purpose.

The index stores no prices and no canonical values beyond what is required for
correlation evidence: per key the count and the sorted set of as-published
observed symbols (used for rename/ambiguity semantics per A6). Values, flags
and provenance are served from the package, never from this index.

Determinism: identical baseline bytes yield identical index bytes (canonical
JSON, sorted keys, LF text, D05 §9 conventions), and the digest sidecar is
verified on load. A stale index (different package identity) is refused.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Optional, Tuple

from .atomic import atomic_write_text
from .baseline import Baseline
from .index import _package_identity, canonical_json
from .paths import validate_roots
from .symbols import observed_trading_symbol

ISIN_INDEX_FILENAME = "serving_isin_index.json"
ISIN_INDEX_DIGEST_FILENAME = "serving_isin_index.sha256"
ISIN_INDEX_FORMAT = "serving-isin-index/1.0"


class IsinIndexError(Exception):
    """Fail-closed index build/load failure (no serving on a bad read model)."""

    def __init__(self, check: str, detail: str) -> None:
        super().__init__("%s: %s" % (check, detail))
        self.check = check
        self.detail = detail


def canonical_index_bytes(document: dict) -> bytes:
    return (canonical_json(document) + "\n").encode("utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_isin_index(baseline: Baseline) -> dict:
    """One linear, read-only pass over the class-(1) row files.

    Membership (D40 §5.4-2, exclusive): the row's stored ``isin_validity``
    must equal ``'VALID'`` and ``isin_normalized`` must be non-empty. BLANK,
    INVALID_LEN, INVALID_PREFIX, INVALID_CHARSET and INVALID_CHECKDIGIT rows
    are never indexed — and are equally never removed, de-ranked or
    distinguished anywhere else by this module.
    """
    entries: dict = {}
    rows_total = 0
    rows_indexed = 0
    for relative in baseline.row_files():
        with open(baseline.path(relative), "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise IsinIndexError(
                        "index-scan", "unparseable canonical row in %s line %d: %s" % (relative, line_number, exc)
                    )
                rows_total += 1
                if obj.get("isin_validity") != "VALID":
                    continue
                isin = obj.get("isin_normalized")
                if not isinstance(isin, str) or not isin:
                    # A stored-VALID row without a normalized key is a package
                    # inconsistency — fail closed, never silently skip.
                    raise IsinIndexError(
                        "index-scan",
                        "canonical row marked VALID without isin_normalized in %s line %d" % (relative, line_number),
                    )
                values = obj.get("source_values")
                if not isinstance(values, dict):
                    raise IsinIndexError(
                        "index-scan",
                        "canonical row without contract keys in %s line %d" % (relative, line_number),
                    )
                series = values.get("series")
                date = obj.get("business_date")
                if not isinstance(series, str) or not series:
                    raise IsinIndexError(
                        "index-scan",
                        "VALID canonical row without series in %s line %d" % (relative, line_number),
                    )
                if not isinstance(date, str) or len(date) != 10:
                    raise IsinIndexError(
                        "index-scan",
                        "VALID canonical row without ISO business_date in %s line %d" % (relative, line_number),
                    )
                observed = observed_trading_symbol(obj)["observed_symbol"]
                cell = entries.setdefault(isin, {}).setdefault(series, {}).setdefault(
                    date, {"count": 0, "symbols": []}
                )
                cell["count"] += 1
                if observed and observed not in cell["symbols"]:
                    cell["symbols"].append(observed)
                rows_indexed += 1

    for isin, series_map in entries.items():
        for series, days in series_map.items():
            for date, cell in days.items():
                cell["symbols"] = sorted(cell["symbols"])

    keys = sum(len(days) for series_map in entries.values() for days in series_map.values())
    return {
        "format": ISIN_INDEX_FORMAT,
        "package": _package_identity(baseline),
        "dimensions": ["isin_normalized", "series", "business_date"],
        "eligibility": (
            "isin_validity == 'VALID' only (D40 EC-DEC-02 / Addendum C-1 §5.4-2); "
            "stored classification; BLANK/invalid rows never indexed, never deleted"
        ),
        "counts": {
            "rows_scanned": rows_total,
            "rows_indexed": rows_indexed,
            "isins": len(entries),
            "keys": keys,
        },
        "entries": entries,
    }


def write_isin_index(state_dir: str, package_root: str, document: dict) -> str:
    """Persist the index (class-4 state) as a canonical file + digest sidecar."""
    validate_roots(package=package_root, state=state_dir)
    os.makedirs(state_dir, exist_ok=True)
    text = canonical_json(document) + "\n"
    digest = sha256_text(text)
    atomic_write_text(os.path.join(state_dir, ISIN_INDEX_FILENAME), text, sync=True)
    atomic_write_text(
        os.path.join(state_dir, ISIN_INDEX_DIGEST_FILENAME),
        "%s  %s\n" % (digest, ISIN_INDEX_FILENAME),
        sync=True,
    )
    return digest


def load_isin_index(state_dir: str, package_root: str, baseline: Baseline) -> Tuple[dict, str]:
    """Load the index, verify digest and package identity (stale refusal)."""
    validate_roots(package=package_root, state=state_dir)
    index_path = os.path.join(state_dir, ISIN_INDEX_FILENAME)
    digest_path = os.path.join(state_dir, ISIN_INDEX_DIGEST_FILENAME)
    if not (os.path.isfile(index_path) and os.path.isfile(digest_path)):
        raise IsinIndexError("index-load", "ISIN index missing or incomplete (run: python -m serving.isin_index build)")
    with open(index_path, "r", encoding="utf-8") as handle:
        text = handle.read()
    digest = sha256_text(text)
    with open(digest_path, "r", encoding="utf-8") as handle:
        sidecar = handle.read()
    if sidecar != "%s  %s\n" % (digest, ISIN_INDEX_FILENAME):
        raise IsinIndexError("index-load", "ISIN index digest sidecar mismatch")
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise IsinIndexError("index-load", "invalid ISIN index JSON: %s" % exc)
    if not isinstance(document, dict) or document.get("format") != ISIN_INDEX_FORMAT:
        raise IsinIndexError("index-load", "unknown ISIN index format %r" % (document or {}).get("format"))
    identity = document.get("package", {})
    current = _package_identity(baseline)
    for key in ("manifest_sha256", "file_count", "total_bytes", "run_id"):
        if identity.get(key) != current.get(key):
            raise IsinIndexError(
                "index-stale",
                "ISIN index package identity %s=%r != baseline %r — rebuild required"
                % (key, identity.get(key), current.get(key)),
            )
    return document, digest


def main(argv: Optional[list] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="D40 EC-DEC-02 — class-(4) ISIN/series/date index build/info")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "info"):
        sub_p = sub.add_parser(name)
        sub_p.add_argument("--package", required=True, help="path to the qualified baseline package (read-only)")
        sub_p.add_argument("--state", required=True, help="state root for the derived index (outside the package)")
    args = parser.parse_args(argv)

    from .baseline import DEFAULT_M2_SPEC, BaselineError, open_baseline

    try:
        baseline = open_baseline(args.package, spec=DEFAULT_M2_SPEC)
    except BaselineError as exc:
        print("FAIL %s: %s" % (exc.check, exc), file=sys.stderr)
        return 2

    if args.command == "build":
        document = build_isin_index(baseline)
        digest = write_isin_index(args.state, args.package, document)
        print(canonical_json({"built": True, "digest": digest, "counts": document["counts"]}))
        return 0
    if args.command == "info":
        document, digest = load_isin_index(args.state, args.package, baseline)
        print(canonical_json({"format": document["format"], "digest": digest, "package": document["package"],
                              "counts": document["counts"]}))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
