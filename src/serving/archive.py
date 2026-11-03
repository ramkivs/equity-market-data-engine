"""Q9 archive inventory query (D16-10 Q9) — per-archive D01 + INPUT_MANIFEST facts.

Contract (D16-10 Q9; D22 §6; D23 §§9-10):

* The archive inventory is derived from the verified baseline's package
  metadata only: ``INPUT_MANIFEST.jsonl`` (per-archive records, the runner's
  record schema as written by ``tools/i4_runner/i4_runner.py``, the package
  owner) and ``GOVERNED_INPUTS.json`` (published corpus facts). Canonical row
  files and source archive bytes are never opened.
* Every archive result preserves the as-published INPUT_MANIFEST fields
  (absent fields are never defaulted) and is extended with:
  - ``d01`` — the joined per-archive D01 inventory facts, or ``null`` when the
    authoritative D01 inventory does not apply to this baseline;
  - ``registry`` — the explicit M2-only absence representation: the class-(3)
    registry does not exist in the M2-only first release and is never
    fabricated (D22 §6 Q9; D16-02).
* The D01 inventory is committed in-repository evidence (``evidence/
  inventory/file_inventory.json``), digest-pinned here. It is not package
  data. For the pinned M2 baseline it is REQUIRED, and any join miss or
  ``archive_sha256_d01`` mismatch is an identity inconsistency that fails
  closed. For synthetic/unpinned packages it is represented as absent
  (``d01: null``, status ``"absent"``) — never mispresented as package-
  embedded data.
* Fail-closed: unparseable or contract-violating INPUT_MANIFEST records,
  missing/misshaped GOVERNED_INPUTS, D01 inventory identity failures, or a
  mismatch between the INPUT_MANIFEST record count and the published corpus
  ``archive_count`` all raise before any partial output is produced.
* Deterministic: archives are ordered by (sequence, relative_path); the CLI
  emits canonical JSON.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

from .baseline import DEFAULT_M2_SPEC, Baseline
from .paths import repository_root
from .query import QueryError

ARCHIVE_QUERY_ID = "Q9-archive-inventory"

INPUT_MANIFEST = "INPUT_MANIFEST.jsonl"
GOVERNED_INPUTS = "GOVERNED_INPUTS.json"

#: The runner's INPUT_MANIFEST record schema (tools/i4_runner/i4_runner.py —
#: the package owner writes exactly these 20 fields per archive). A record
#: missing any of them is a contract violation (fail closed).
INPUT_MANIFEST_CONTRACT_KEYS = (
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

#: Per-archive D01 facts exposed in the ``d01`` block (a projection of the
#: in-repo D01 inventory record; the inventory is the authority and is never
#: modified or reinterpreted).
D01_FACT_KEYS = (
    "sha256",
    "size_bytes",
    "date_from_filename",
    "row_count",
    "bad_rows",
    "series_counts",
    "symbol_count",
    "isin_count",
    "header_signature",
)

#: Committed in-repository D01 inventory (durable evidence — never package-
#: embedded data). Pinned identity verified before the file is trusted.
D01_INVENTORY_PATH = "evidence/inventory/file_inventory.json"
D01_INVENTORY_SHA256 = "336b9531cd34f48e9a2e7e7593cc4e9c2736b3864d8213bc65d6ab8b488729d2"
D01_INVENTORY_RECORD_COUNT = 2462

#: Explicit M2-only registry-absence representation (D22 §6 Q9; D16-02).
REGISTRY_ABSENT = {"present": False, "status": "absent-in-m2-only-release"}


class D01InventoryError(Exception):
    """Fail-closed in-repo D01 inventory load/identity failure."""

    def __init__(self, check: str, detail: str) -> None:
        super().__init__("%s: %s" % (check, detail))
        self.check = check
        self.detail = detail


def parse_input_manifest(baseline: Baseline) -> list:
    """Parse the package's INPUT_MANIFEST.jsonl (as-published; fail closed).

    Public (not Q9-private): the Q7 record-detail slice reuses this parser and
    its contract checks — there is one INPUT_MANIFEST parser in the serving
    layer, not one per query.
    """
    records = []
    with open(baseline.path(INPUT_MANIFEST), "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise QueryError("input-manifest-scan", "unparseable INPUT_MANIFEST line %d: %s" % (line_number, exc))
            if not isinstance(record, dict):
                raise QueryError("input-manifest-scan", "INPUT_MANIFEST line %d is not a record" % line_number)
            missing = [key for key in INPUT_MANIFEST_CONTRACT_KEYS if key not in record]
            if missing:
                raise QueryError("input-manifest-scan", "INPUT_MANIFEST line %d missing contract keys: %s" % (line_number, missing))
            records.append(record)
    if not records:
        raise QueryError("input-manifest-scan", "INPUT_MANIFEST contains no records")
    return records


def _parse_governed_inputs(baseline: Baseline) -> dict:
    """Parse the package's GOVERNED_INPUTS.json (as-published; fail closed)."""
    with open(baseline.path(GOVERNED_INPUTS), "r", encoding="utf-8") as handle:
        try:
            document = json.load(handle)
        except ValueError as exc:
            raise QueryError("governed-inputs", "unparseable GOVERNED_INPUTS: %s" % exc)
    if not isinstance(document, dict):
        raise QueryError("governed-inputs", "GOVERNED_INPUTS is not a document")
    corpus = document.get("corpus")
    count = corpus.get("archive_count") if isinstance(corpus, dict) else None
    if not isinstance(count, int) or isinstance(count, bool):
        raise QueryError("governed-inputs", "GOVERNED_INPUTS.corpus.archive_count missing or not an integer")
    return document


def load_d01_inventory(path: Optional[str] = None, repo_root: Optional[str] = None) -> dict:
    """Load and verify the committed in-repo D01 inventory.

    Returns a mapping keyed by (root, relative_path). The file's sha256 must
    match the pinned ``D01_INVENTORY_SHA256`` (and its record count the pinned
    ``D01_INVENTORY_RECORD_COUNT``) before it is trusted; any identity failure
    raises :class:`D01InventoryError` (fail closed — no fallback, no repair).
    """
    inventory_path = path if path is not None else os.path.join(repository_root(repo_root), D01_INVENTORY_PATH)
    if not os.path.isfile(inventory_path):
        raise D01InventoryError("d01-load", "in-repo D01 inventory missing: %s" % inventory_path)
    with open(inventory_path, "rb") as handle:
        data = handle.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != D01_INVENTORY_SHA256:
        raise D01InventoryError("d01-load", "D01 inventory digest %s != pinned %s" % (digest, D01_INVENTORY_SHA256))
    try:
        records = json.loads(data.decode("utf-8"))
    except ValueError as exc:
        raise D01InventoryError("d01-load", "D01 inventory unparseable: %s" % exc)
    if not isinstance(records, list):
        raise D01InventoryError("d01-load", "D01 inventory is not a record list")
    if len(records) != D01_INVENTORY_RECORD_COUNT:
        raise D01InventoryError("d01-load", "D01 inventory record count %d != pinned %d" % (len(records), D01_INVENTORY_RECORD_COUNT))
    inventory = {}
    for record in records:
        if not isinstance(record, dict):
            raise D01InventoryError("d01-load", "D01 inventory contains a non-record entry")
        key = (record.get("root"), record.get("relative_path"))
        if key in inventory:
            raise D01InventoryError("d01-load", "duplicate D01 inventory key %s" % (key,))
        inventory[key] = record
    return inventory


def _is_pinned_m2(baseline: Baseline) -> bool:
    return baseline.spec is not None and baseline.spec == DEFAULT_M2_SPEC


def query_archive_inventory(baseline: Baseline, d01: Optional[dict] = None) -> dict:
    """Q9 archive inventory query (D16-10 Q9).

    ``d01`` is the mapping returned by :func:`load_d01_inventory`. For the
    pinned M2 baseline it is required (join miss / identity mismatch fail
    closed); for any other baseline it must not be supplied (the D01 facts are
    represented as absent, never fabricated).

    Returns a document shaped for canonical-JSON serving:

    * ``archives`` — one entry per INPUT_MANIFEST record, ordered by
      (sequence, relative_path): the as-published record fields, plus
      ``d01`` (the joined D01 facts or ``null``) and ``registry`` (the explicit
      M2-only absence representation);
    * ``summary`` — ``archive_count`` (cross-checked against the published
      corpus ``archive_count``), ``archive_set_digest`` (as published),
      ``d01_inventory`` (presence + path + record count + verified digest, or
      absence), and ``registry`` (the same explicit absence representation).

    Read-only with respect to the package: only the two metadata files are
    opened; no canonical row file or source archive byte is read.
    """
    records = parse_input_manifest(baseline)
    governed = _parse_governed_inputs(baseline)
    published_count = governed["corpus"]["archive_count"]
    if len(records) != published_count:
        raise QueryError(
            "inventory-count",
            "INPUT_MANIFEST record count %d != GOVERNED_INPUTS corpus.archive_count %d" % (len(records), published_count),
        )

    pinned = _is_pinned_m2(baseline)
    if pinned and d01 is None:
        raise QueryError("d01-required", "the pinned M2 baseline requires the in-repo D01 inventory (load_d01_inventory)")
    if not pinned and d01 is not None:
        raise QueryError("d01-mismatch", "a D01 inventory was supplied for a baseline that is not the pinned M2 baseline")

    archives = []
    for record in records:
        served = dict(record)
        d01_facts = None
        if pinned:
            key = (record.get("root"), record.get("relative_path"))
            d01_record = d01.get(key)
            if d01_record is None:
                raise QueryError("d01-join-miss", "archive %s absent from the pinned D01 inventory" % (key,))
            if d01_record.get("sha256") != record.get("archive_sha256_d01"):
                raise QueryError(
                    "d01-identity-mismatch",
                    "archive %s: D01 sha256 %r != INPUT_MANIFEST archive_sha256_d01 %r"
                    % (key, d01_record.get("sha256"), record.get("archive_sha256_d01")),
                )
            d01_facts = {key: d01_record.get(key) for key in D01_FACT_KEYS}
        served["d01"] = d01_facts
        served["registry"] = dict(REGISTRY_ABSENT)
        archives.append(served)

    archives.sort(
        key=lambda record: (
            record.get("sequence") if isinstance(record.get("sequence"), int) else 0,
            record.get("relative_path") or "",
        )
    )

    if pinned:
        d01_status = {
            "present": True,
            "path": D01_INVENTORY_PATH,
            "record_count": D01_INVENTORY_RECORD_COUNT,
            "sha256": D01_INVENTORY_SHA256,
        }
    else:
        d01_status = {"present": False, "status": "absent"}
    return {
        "query": ARCHIVE_QUERY_ID,
        "archives": archives,
        "summary": {
            "archive_count": len(archives),
            "archive_set_digest": governed["corpus"].get("archive_set_digest"),
            "d01_inventory": d01_status,
            "registry": dict(REGISTRY_ABSENT),
        },
    }
