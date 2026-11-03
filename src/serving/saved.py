"""Serving saved-query store — class-(4) serving-owned user state (D37-DEC).

Governing decisions (docs/architecture/D37_SAVED_QUERY_HISTORY_DECISION.md):

* **C1(a)** — saved queries are serving-owned *user* state, not a derivation of the
  qualified baseline. The store lives in a **distinct root outside the derived-state
  rebuild operation's scope**; rebuilding derived state never deletes or modifies it;
  deleting a saved query is an explicit user-visible operation; the derived-state
  rebuild behavior and package-immutability guarantees are preserved unchanged.
* **C2(a)** — query history may be recorded only through an explicit operation.
  Executing a saved query (or any query) **never mutates this store**. History itself
  is deferred (D37-DEC §8) and has no surface here.

Authority: the standing D23 grant (§17(c) "serving state class (4) (indexes/rollups/
saved-query store)"); technology selection recorded in the D38 implementation record
under the D23 §13 delegation with the MD-10 grading.

Persistence technology (recorded selection): one canonical-JSON document + a sha256
sidecar on local disk, Python 3 standard library only, deterministic serialization,
atomic write/replace (temp file in the same directory + ``os.replace``). Single user,
local, no authentication, no multi-user architecture (D16 §13; D23 §13 constraints 1–2).

Document schema (format ``serving-saved-queries/1.0``)::

    {
      "format": "serving-saved-queries/1.0",
      "queries": {
        "<id>": {"id": "<id>", "mode": "<query-id>", "params": { ... }}
      }
    }

* ``<id>`` — the stable saved-query identifier (see the contract below).
* ``mode`` — exactly one of the ten currently implemented Q1–Q10 query ids
  (``Q1-dataset``, ``Q2-date-range``, ``Q3-instrument``, ``Q4-filter``,
  ``Q5-association``, ``Q6-calendar``, ``Q7-record-detail``, ``Q8-data-quality``,
  ``Q9-archive-inventory``, ``Q10-qualification``). No other query path exists
  (D23 §18(8)); loading an unknown mode fails closed.
* ``params`` — exactly the parameters required to reproduce the definition for that
  mode, with the exact, as-published values the corresponding query contract accepts.
  Only mode-relevant parameters are persisted; an absent parameter is a *missing key*
  (never null, never blank — a blank or null value is an invalid definition). No
  normalization, no field aliases, no full result rows are persisted.

Identifier contract (stable, deterministic, documented):

* 1–64 characters of ``[a-z0-9_-]`` starting with ``[a-z0-9]`` (case-sensitive, exact;
  no normalization of any kind);
* unique within the store (a duplicate create fails closed);
* chosen by the user at create; update/delete reference it by exact value.

Lifecycle (explicit, testable):

* **create** — add a definition; the first create bootstraps an empty store;
* **read** — one record by id; **list** — all records, sorted by id;
* **update** — *full replacement*: the new (mode, params) pair exactly replaces the
  previous definition (parameters not supplied are removed, not merged);
* **delete** — remove one definition; there is no retention policy and no automatic
  cleanup — deletion is the only removal path (D37-DEC §6.3).

Failure semantics (fail closed; no partial state, nothing served):

* ``saved-query-missing``   — store file or sidecar absent where a store is required;
* ``saved-query-corrupt``   — sidecar digest mismatch or unparseable JSON;
* ``saved-query-format``    — unknown/unsupported store format version;
* ``saved-query-schema``    — document/record key-set violation (non-contract keys);
* ``saved-query-invalid``   — unknown mode, missing required parameter, or a value
  that violates the mode's parameter contract (wrong type, blank/null, bad date);
* ``saved-query-duplicate`` — create with an identifier already in the store;
* ``saved-query-not-found`` — read/update/delete/execute of an unknown identifier;
* ``saved-query-conflict``  — the saved store root is the same directory as the
  derived-state root (C1(a) isolation violation).

A saved-store failure never affects the baseline (D16-09), and executing a saved
query never writes to the store (C2(a)).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
from typing import Dict, List, Optional, Tuple

from .archive import ARCHIVE_QUERY_ID, load_d01_inventory, query_archive_inventory
from .paths import validate_roots, overlaps, validate_store_root
from .atomic import atomic_write_text
from .baseline import Baseline
from .detail import RECORD_DETAIL_QUERY_ID, query_record_detail
from .index import canonical_json, load_index
from .qualification import QUALIFICATION_QUERY_ID, query_qualification
from .quality import DATA_QUALITY_QUERY_ID, query_data_quality
from .query import (
    ASSOCIATIONS_QUERY_ID,
    CALENDAR_QUERY_ID,
    DATE_RANGE_QUERY_ID,
    DATASET_QUERY_ID,
    FILTER_QUERY_ID,
    QUERY_ID,
    QueryError,
    parse_associations,
    parse_calendar,
    query_associations,
    query_calendar,
    query_date_range,
    query_dataset_summary,
    query_filters,
    query_instrument,
)

SAVED_FILENAME = "saved_queries.json"
SAVED_DIGEST_FILENAME = "saved_queries.sha256"
SAVED_FORMAT = "serving-saved-queries/1.0"

#: Stable identifier contract: 1-64 chars of [a-z0-9_-], starting with [a-z0-9].
SAVED_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: The ten currently implemented and supported Q1–Q10 query contracts, by their
#: exact query-id names. This set is the only savable vocabulary (D23 §18(8)).
DATASET_MODE = DATASET_QUERY_ID          # Q1
DATE_RANGE_MODE = DATE_RANGE_QUERY_ID    # Q2
INSTRUMENT_MODE = QUERY_ID               # Q3
FILTER_MODE = FILTER_QUERY_ID            # Q4
ASSOCIATIONS_MODE = ASSOCIATIONS_QUERY_ID  # Q5
CALENDAR_MODE = CALENDAR_QUERY_ID        # Q6
RECORD_DETAIL_MODE = RECORD_DETAIL_QUERY_ID    # Q7
DATA_QUALITY_MODE = DATA_QUALITY_QUERY_ID      # Q8
ARCHIVE_MODE = ARCHIVE_QUERY_ID              # Q9
QUALIFICATION_MODE = QUALIFICATION_QUERY_ID  # Q10
SAVED_MODES = frozenset(
    (
        DATASET_MODE,
        DATE_RANGE_MODE,
        INSTRUMENT_MODE,
        FILTER_MODE,
        ASSOCIATIONS_MODE,
        CALENDAR_MODE,
        RECORD_DETAIL_MODE,
        DATA_QUALITY_MODE,
        ARCHIVE_MODE,
        QUALIFICATION_MODE,
    )
)

#: mode -> {param: (kind, required)}; kind in {"str", "date", "int", "filters"}.
#: The exact parameter surface of each query contract, nothing else.
_MODE_PARAM_SPECS: Dict[str, Dict[str, Tuple[str, bool]]] = {
    DATASET_MODE: {"family": ("str", False), "year": ("int", False)},
    DATE_RANGE_MODE: {"date_from": ("date", True), "date_to": ("date", True)},
    INSTRUMENT_MODE: {"symbol": ("str", True), "series": ("str", True), "year": ("int", False)},
    FILTER_MODE: {"filters": ("filters", True)},
    ASSOCIATIONS_MODE: {"security_id": ("str", False), "symbol": ("str", False), "series": ("str", False)},
    CALENDAR_MODE: {"date_from": ("date", False), "date_to": ("date", False)},
    RECORD_DETAIL_MODE: {"source_file": ("str", True), "source_line_number": ("int", True)},
    DATA_QUALITY_MODE: {},
    ARCHIVE_MODE: {},
    QUALIFICATION_MODE: {"repo": ("str", False)},
}


class SavedQueryError(Exception):
    """Fail-closed saved-query store failure (no partial state; nothing served)."""

    def __init__(self, check: str, detail: str) -> None:
        super().__init__("%s: %s" % (check, detail))
        self.check = check
        self.detail = detail


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write_text(path: str, text: str) -> None:
    atomic_write_text(path, text)


# ---------------------------------------------------------------------------
# validation (fail closed)
# ---------------------------------------------------------------------------


def validate_saved_definition(mode: str, params: dict, context: str = "saved-query definition") -> dict:
    """Validate a (mode, params) pair against the saved-definition contract.

    Returns a canonically (by key) ordered params dict. Raises
    :class:`SavedQueryError` fail-closed on any contract violation — unknown mode,
    parameter not part of the mode's contract, missing required parameter, or a
    value that is not exactly the type/shape the query contract accepts.
    """
    if not isinstance(mode, str) or mode not in SAVED_MODES:
        raise SavedQueryError(
            "saved-query-invalid",
            "%s: unknown query mode %r (supported: %s)" % (context, mode, ", ".join(sorted(SAVED_MODES))),
        )
    if not isinstance(params, dict):
        raise SavedQueryError(
            "saved-query-invalid",
            "%s: parameters must be an object, got %s" % (context, type(params).__name__),
        )
    spec = _MODE_PARAM_SPECS[mode]
    for name in sorted(params):
        if name not in spec:
            allowed = ", ".join(sorted(spec)) if spec else "none"
            raise SavedQueryError(
                "saved-query-invalid",
                "%s: parameter %r is not part of the %s contract (allowed: %s)" % (context, name, mode, allowed),
            )
    for name in sorted(spec):
        kind, required = spec[name]
        if name not in params:
            if required:
                raise SavedQueryError(
                    "saved-query-invalid",
                    "%s: the %s definition is missing required parameter %r" % (context, mode, name),
                )
            continue
        value = params[name]
        if kind == "str":
            if not isinstance(value, str) or value == "":
                raise SavedQueryError(
                    "saved-query-invalid",
                    "%s: %s parameter %r must be a non-empty string exactly as published "
                    "(absent means unspecified; null and blank are never persisted)" % (context, mode, name),
                )
        elif kind == "date":
            if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
                raise SavedQueryError(
                    "saved-query-invalid",
                    "%s: %s parameter %r must be an ISO date (YYYY-MM-DD), got %r" % (context, mode, name, value),
                )
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                raise SavedQueryError(
                    "saved-query-invalid",
                    "%s: %s parameter %r is not a valid calendar date: %r" % (context, mode, name, value),
                )
        elif kind == "int":
            if type(value) is not int:
                raise SavedQueryError(
                    "saved-query-invalid",
                    "%s: %s parameter %r must be an integer, got %r" % (context, mode, name, value),
                )
        elif kind == "filters":
            if not isinstance(value, dict) or not value:
                raise SavedQueryError(
                    "saved-query-invalid",
                    "%s: the %s definition requires a non-empty filters object" % (context, mode),
                )
            for field in sorted(value):
                if not isinstance(field, str) or field == "":
                    raise SavedQueryError(
                        "saved-query-invalid",
                        "%s: Q4 filter names must be non-empty strings, got %r" % (context, field),
                    )
                if not isinstance(value[field], str) or value[field] == "":
                    raise SavedQueryError(
                        "saved-query-invalid",
                        "%s: Q4 filter value for %r must be a non-empty string, got %r" % (context, field, value[field]),
                    )
    if mode == ASSOCIATIONS_MODE and not (
        params.get("security_id") or params.get("symbol") or params.get("series")
    ):
        raise SavedQueryError(
            "saved-query-invalid",
            "%s: the Q5 definition requires at least one selector (security_id / symbol / series)" % context,
        )
    if mode == CALENDAR_MODE and ("date_from" in params) != ("date_to" in params):
        raise SavedQueryError(
            "saved-query-invalid",
            "%s: the Q6 range requires both date_from and date_to (inclusive ISO business dates, both-or-neither)"
            % context,
        )
    return {name: params[name] for name in sorted(params)}


def _validate_saved_id(query_id: object, context: str) -> None:
    if not isinstance(query_id, str) or not SAVED_ID_RE.match(query_id):
        raise SavedQueryError(
            "saved-query-invalid",
            "%s: saved-query identifier %r violates the identifier contract "
            "(1-64 chars of [a-z0-9_-], starting with [a-z0-9])" % (context, query_id),
        )


def _validate_record(record: object, context: str, key: Optional[str] = None) -> dict:
    if not isinstance(record, dict) or set(record) != {"id", "mode", "params"}:
        keys = sorted(record) if isinstance(record, dict) else type(record).__name__
        raise SavedQueryError(
            "saved-query-schema",
            "%s: a saved-query record must have exactly the keys id/mode/params, got %r" % (context, keys),
        )
    _validate_saved_id(record["id"], context)
    if key is not None and record["id"] != key:
        raise SavedQueryError(
            "saved-query-schema",
            "%s: stored identifier %r does not match its key %r" % (context, record["id"], key),
        )
    validate_saved_definition(record["mode"], record["params"], context)
    return record


def _validate_document(document: object, context: str) -> dict:
    if not isinstance(document, dict) or set(document) != {"format", "queries"}:
        keys = sorted(document) if isinstance(document, dict) else type(document).__name__
        raise SavedQueryError(
            "saved-query-schema",
            "%s: the store document must have exactly the keys format/queries, got %r" % (context, keys),
        )
    if document["format"] != SAVED_FORMAT:
        raise SavedQueryError(
            "saved-query-format",
            "%s: unsupported saved-query store format %r (supported: %s)" % (context, document["format"], SAVED_FORMAT),
        )
    queries = document["queries"]
    if not isinstance(queries, dict):
        raise SavedQueryError(
            "saved-query-schema",
            "%s: the queries member must be an object, got %s" % (context, type(queries).__name__),
        )
    for key in sorted(queries):
        _validate_record(queries[key], "%s saved query %r" % (context, key), key=key)
    return document


# ---------------------------------------------------------------------------
# store I/O (fail closed)
# ---------------------------------------------------------------------------


def load_saved(root: str) -> dict:
    """Load and validate the saved-query store at ``root`` (fail closed).

    Mirrors the established class-(4) discipline: the store is the single
    canonical-JSON file + sha256 sidecar; missing/incomplete state, a sidecar
    mismatch, unparseable JSON, an unknown format version, or any schema/contract
    violation is refused — never silently repaired.
    """
    path = os.path.join(root, SAVED_FILENAME)
    digest_path = os.path.join(root, SAVED_DIGEST_FILENAME)
    if not (os.path.isfile(path) and os.path.isfile(digest_path)):
        raise SavedQueryError(
            "saved-query-missing",
            "saved-query state missing or incomplete at %s (create one with `saved save`)" % root,
        )
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    digest = _sha256_text(text)
    with open(digest_path, "r", encoding="utf-8") as handle:
        sidecar = handle.read()
    if sidecar != "%s  %s\n" % (digest, SAVED_FILENAME):
        raise SavedQueryError("saved-query-corrupt", "saved-query digest sidecar mismatch at %s" % root)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SavedQueryError("saved-query-corrupt", "saved-query store is not valid JSON: %s" % exc)
    return _validate_document(document, "saved-query store at %s" % root)


def save_document(root: str, document: dict) -> str:
    """Validate and atomically persist ``document``; returns the store sha256."""
    _validate_document(document, "saved-query store")
    validate_store_root(root, "saved")
    os.makedirs(root, exist_ok=True)
    text = canonical_json(document) + "\n"
    digest = _sha256_text(text)
    _atomic_write_text(os.path.join(root, SAVED_FILENAME), text)
    _atomic_write_text(os.path.join(root, SAVED_DIGEST_FILENAME), "%s  %s\n" % (digest, SAVED_FILENAME))
    return digest


def _load_or_empty(root: str) -> dict:
    """Load the store, or the empty document if no store exists yet.

    A *partially* present store (either file present) is loaded — and therefore
    fails closed if corrupt or incomplete — never treated as absent.
    """
    if os.path.isfile(os.path.join(root, SAVED_FILENAME)) or os.path.isfile(
        os.path.join(root, SAVED_DIGEST_FILENAME)
    ):
        return load_saved(root)
    return {"format": SAVED_FORMAT, "queries": {}}


def assert_separate_roots(saved_root: str, state_root: str) -> None:
    """C1(a) isolation: the saved store root must be distinct from the
    derived-state root (the derived-state rebuild must never reach the store)."""
    if overlaps(saved_root, state_root):
        raise SavedQueryError(
            "saved-query-conflict",
            "the saved-query store root must be a distinct directory from the derived "
            "serving state root (D37-DEC C1(a): rebuilding derived state must not "
            "delete or modify saved queries)",
        )


# ---------------------------------------------------------------------------
# CRUD (explicit operations only — D37-DEC §6)
# ---------------------------------------------------------------------------


def create_saved(root: str, query_id: str, mode: str, params: dict) -> Tuple[dict, str]:
    """Create a saved query; returns (record, store sha256).

    Fails closed on an invalid identifier/mode/params, a duplicate identifier, or
    a corrupt existing store.
    """
    _validate_saved_id(query_id, "saved-query definition")
    params = validate_saved_definition(mode, params, "saved-query definition")
    document = _load_or_empty(root)
    if query_id in document["queries"]:
        raise SavedQueryError(
            "saved-query-duplicate",
            "a saved query with identifier %r already exists (use `saved update` to replace it)" % query_id,
        )
    record = {"id": query_id, "mode": mode, "params": params}
    document["queries"][query_id] = record
    digest = save_document(root, document)
    return record, digest


def get_saved(root: str, query_id: str) -> dict:
    """Read one saved query by exact identifier (fail closed)."""
    document = load_saved(root)
    record = document["queries"].get(query_id)
    if record is None:
        raise SavedQueryError("saved-query-not-found", "no saved query with identifier %r" % query_id)
    return record


def list_saved(root: str) -> List[dict]:
    """List all saved queries, sorted by identifier (deterministic)."""
    document = load_saved(root)
    return [document["queries"][key] for key in sorted(document["queries"])]


def update_saved(root: str, query_id: str, mode: str, params: dict) -> Tuple[dict, str]:
    """Update a saved query — **full replacement** semantics.

    The new (mode, params) pair exactly replaces the previous definition;
    parameters not supplied are removed, not merged. Returns (record, store sha256).
    Fails closed on an unknown identifier, an invalid new definition, or a corrupt
    store.
    """
    _validate_saved_id(query_id, "saved-query definition")
    params = validate_saved_definition(mode, params, "saved-query definition")
    document = load_saved(root)
    if query_id not in document["queries"]:
        raise SavedQueryError("saved-query-not-found", "no saved query with identifier %r to update" % query_id)
    record = {"id": query_id, "mode": mode, "params": params}
    document["queries"][query_id] = record
    digest = save_document(root, document)
    return record, digest


def delete_saved(root: str, query_id: str) -> str:
    """Explicitly delete one saved query; returns the store sha256.

    Fails closed on an unknown identifier or a corrupt store. There is no other
    removal path (no retention policy, no automatic cleanup — D37-DEC §6.3).
    """
    _validate_saved_id(query_id, "saved-query definition")
    document = load_saved(root)
    if query_id not in document["queries"]:
        raise SavedQueryError("saved-query-not-found", "no saved query with identifier %r to delete" % query_id)
    del document["queries"][query_id]
    return save_document(root, document)


# ---------------------------------------------------------------------------
# load-and-execute (C2(a): never mutates the store)
# ---------------------------------------------------------------------------


def execute_query_definition(
    mode: str, params: dict, baseline: Baseline, state_root: str, m2: bool = False, repo_root: Optional[str] = None
) -> dict:
    """Execute one supported Q1–Q10 query contract by its query-id mode name,
    with an exact (already validated) params dict.

    Single implementation of the per-mode execution and result envelope, shared
    by the saved-query load-and-execute path and the explicit history-recording
    operation. The result envelope is exactly the one the corresponding CLI
    query/view command produces for the same parameters (no new query semantics —
    D23 §18(8)). ``state_root`` is the derived-state directory (required for
    every mode; the index is loaded even by the two modes that do not consume it,
    mirroring the established verify → build → query flow). ``m2`` pins the D01
    inventory for the Q9 view exactly as the CLI does.
    """
    index_document, _digest = load_index(state_root, baseline)
    if mode == DATASET_MODE:
        return query_dataset_summary(index_document, family=params.get("family"), year=params.get("year"))
    if mode == DATE_RANGE_MODE:
        rows = query_date_range(baseline, index_document, params["date_from"], params["date_to"])
        return {
            "query": DATE_RANGE_QUERY_ID,
            "date_from": params["date_from"],
            "date_to": params["date_to"],
            "result_count": len(rows),
            "rows": list(rows),
        }
    if mode == INSTRUMENT_MODE:
        rows = query_instrument(
            baseline, index_document, params["symbol"], params["series"], year=params.get("year")
        )
        return {"query": QUERY_ID, "result_count": len(rows), "rows": list(rows)}
    if mode == FILTER_MODE:
        rows = query_filters(baseline, index_document, params["filters"])
        return {"query": FILTER_QUERY_ID, "filters": params["filters"], "result_count": len(rows), "rows": list(rows)}
    if mode == ASSOCIATIONS_MODE:
        documents = parse_associations(baseline)
        rows = query_associations(
            baseline,
            index_document,
            security_id=params.get("security_id"),
            symbol=params.get("symbol"),
            series=params.get("series"),
            documents=documents,
        )
        return {
            "query": ASSOCIATIONS_QUERY_ID,
            "security_id": params.get("security_id"),
            "series": params.get("series"),
            "symbol": params.get("symbol"),
            "associations_present": documents is not None,
            "record_count": len(rows),
            "records": list(rows),
        }
    if mode == CALENDAR_MODE:
        documents = parse_calendar(baseline)
        rows = query_calendar(
            baseline,
            index_document,
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
            documents=documents,
        )
        return {
            "query": CALENDAR_QUERY_ID,
            "date_from": params.get("date_from"),
            "date_to": params.get("date_to"),
            "calendar_present": documents is not None,
            "record_count": len(rows),
            "records": list(rows),
        }
    if mode == RECORD_DETAIL_MODE:
        return query_record_detail(baseline, index_document, params["source_file"], params["source_line_number"])
    if mode == DATA_QUALITY_MODE:
        return query_data_quality(baseline, index_document)
    if mode == ARCHIVE_MODE:
        return query_archive_inventory(baseline, d01=(load_d01_inventory(repo_root=repo_root) if m2 else None))
    if mode == QUALIFICATION_MODE:
        return query_qualification(baseline, repo_root=params.get("repo", repo_root))
    raise SavedQueryError(
        "saved-query-invalid",
        "no execution path for query mode %r (supported: %s)" % (mode, ", ".join(sorted(SAVED_MODES))),
    )


def execute_saved(root: str, query_id: str, baseline: Baseline, state_root: str, m2: bool = False, repo_root: Optional[str] = None) -> dict:
    """Load a saved definition and execute it through the existing query layer.

    The result envelope is exactly the one the corresponding CLI query/view
    command produces for the same parameters (no new query semantics — D23
    §18(8)). The call is read-only against the store: it never writes the store
    (C2(a)), and a query failure never affects it or the baseline (D16-09).
    """
    assert_separate_roots(root, state_root)
    validate_roots(package=baseline.root, saved=root, state=state_root)
    document = load_saved(root)
    record = document["queries"].get(query_id)
    if record is None:
        raise SavedQueryError("saved-query-not-found", "no saved query with identifier %r to run" % query_id)
    return execute_query_definition(record["mode"], record["params"], baseline, state_root, m2=m2, repo_root=repo_root)
