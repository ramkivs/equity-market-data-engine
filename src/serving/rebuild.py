"""Serving-state rebuild — delegated operation (b) (D16-09/D16-11; D22 §7).

User-initiated maintenance of the class-(4) serving state only. It never touches the
baseline package: it removes exactly the two known derived artifacts inside the
dedicated state directory (failing closed if anything else is present there) and
rebuilds the index from the verified baseline. Deleting class (4) is never a data
event (D16-07); the rebuild is a pure derivation of (1)+(2)+(3) — here, the
qualified baseline (class (1)).
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

from .baseline import Baseline
from .paths import validate_roots, validate_store_root
from .index import (
    INDEX_DIGEST_FILENAME,
    INDEX_FILENAME,
    ServingIndexError,
    build_index,
    write_index,
)

KNOWN_STATE_FILES = frozenset({INDEX_FILENAME, INDEX_DIGEST_FILENAME})


def rebuild_state(baseline: Baseline, state_dir: str, replace_only: bool = False) -> dict:
    """Delete and rebuild the serving state. Returns a deterministic report.

    ``identical`` is True when the rebuilt index is byte-identical to the previous
    one (the expected outcome for an unchanged baseline — the reproducibility
    proof), False when the baseline content changed (the baseline always wins).
    """
    validate_roots(package=baseline.root, state=state_dir)
    validate_store_root(state_dir, "state")
    before: Optional[str] = None
    if os.path.isdir(state_dir):
        present = set(os.listdir(state_dir))
        unknown = present - KNOWN_STATE_FILES
        if unknown and not replace_only:
            raise ServingIndexError(
                "rebuild-refuse",
                "state directory contains unknown files (refusing to delete): %s" % sorted(unknown)[:10],
            )
        index_path = os.path.join(state_dir, INDEX_FILENAME)
        if os.path.isfile(index_path):
            with open(index_path, "rb") as handle:
                before = _sha256_bytes(handle.read())
        if not replace_only:
            for name in sorted(present & KNOWN_STATE_FILES):
                os.remove(os.path.join(state_dir, name))
    document = build_index(baseline)
    after = write_index(state_dir, document)
    return {
        "before_sha256": before,
        "after_sha256": after,
        "identical": before == after,
        "files_scanned": document["counts"]["row_files"],
        "rows_scanned": document["counts"]["row_count"],
        "instrument_pairs": document["counts"]["instrument_pairs"],
        "package_manifest_sha256": document["package"]["manifest_sha256"],
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
