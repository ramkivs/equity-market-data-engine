"""Serving query-history store — class-(4) serving-owned user state (D37-DEC).

Governing decisions (docs/architecture/D37_SAVED_QUERY_HISTORY_DECISION.md):

* **C2(a)** — query history may be recorded **only through an explicit
  operation**. Executing an ordinary query (including a saved-query run) never
  implicitly mutates durable history. The single explicit operation is
  :func:`record_execution` (CLI ``history record``): it accepts a validated
  execution description (a supported Q1–Q10 mode + exact parameters), executes
  it through the existing query layer (the invocation IS the explicit execution
  request — no hidden side effects), and durably records the ACTUAL outcome.
  An execution that never happened is never recorded (no fabricated outcomes).
* **C1(a)** (still binding) — history is serving-owned user state in its own
  **distinct root** (``--history-state``), separate from the derived-state root
  and from the saved-query store root; derived-state rebuild never reaches it;
  deletion is explicit (``history delete``); there is no retention policy and
  no automatic pruning.

Authority: the standing D23 grant and the D37-DEC deferral clause ("its own
design record under the same standing authority"); technology selection
recorded in the D39 implementation record under the D23 §13 delegation with
the MD-10 grading. Design decisions (recording semantics, seq identity, no
timestamp, minimal entry content) are documented in the D39 record as the
narrowest decisions consistent with the governing records — proposals
elevated by that record, not new authority.

Entry contract (format ``serving-query-history/1.0``)::

    {
      "format": "serving-query-history/1.0",
      "next_seq": 3,
      "entries": [
        {"seq": 1, "mode": "<query-id>", "params": { ... }, "outcome": "success"},
        {"seq": 2, "mode": "<query-id>", "params": { ... }, "outcome": "error", "check": "<check>"}
      ]
    }

* ``mode``/``params`` — the exact execution description, validated by the SAME
  contract as saved-query definitions (the ten Q1–Q10 query ids; exact,
  as-published parameter values; nothing else).
* ``outcome`` — the actual outcome of the explicitly requested execution:
  ``"success"`` or ``"error"``.
* ``check`` — present iff outcome is ``"error"``: the fail-closed check id of
  the query failure. No result rows are ever stored, no result counts, no
  timestamps (the determinism contract admits no clock value into this
  durable state), and no provenance or qualification fields (never invented).
* ``seq`` — stable record identifier: a 1-based monotonically increasing
  integer, unique, **never reused** (even after deletion). The document's
  ``next_seq`` counter (the next seq a recording may use) is incremented on
  every recording and never decremented, so deletion cannot free a seq for
  reuse. Entry order is ascending ``seq`` = the order of the explicit
  recording operations. Repeated identical descriptions are NOT collapsed —
  every explicit recording produces a new entry.
* ``next_seq`` — integer >= 1; must be strictly greater than every stored
  entry seq (schema-validated on load; a violation is a fail-closed
  ``history-schema``).

Failure semantics (fail closed; no partial publication):

* ``history-missing``      — store file or sidecar absent where a store is required;
* ``history-corrupt``      — sidecar digest mismatch or unparseable JSON;
* ``history-format``       — unknown/unsupported store format version;
* ``history-schema``       — document/entry key-set violation or seq ordering
  violation (non-contract keys, seq not strictly ascending, ...);
* ``history-invalid``      — a stored entry's mode/params violates the
  definition contract (checked on load);
* ``history-not-found``    — read/delete of an unknown seq;
* ``history-state-conflict`` — the history root equals the derived-state root.

A *fresh* execution description violating the definition contract (in
``record_execution``) raises the shared ``SavedQueryError`` (check
``saved-query-invalid``) before anything is published — it is a fresh-input
validation error, not a store-state failure.

A baseline or derived-state failure during ``history record`` aborts the
operation with **no entry published** (there was no completed execution to
record). A query failure IS recorded (it is the actual outcome of the explicit
request) with its check id.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from typing import Dict, List, Optional, Tuple

from .paths import validate_roots, overlaps
from .baseline import Baseline
from .index import canonical_json
from .query import QueryError
from .saved import (
    SavedQueryError,
    execute_query_definition,
    validate_saved_definition,
)

HISTORY_FILENAME = "query_history.json"
HISTORY_DIGEST_FILENAME = "query_history.sha256"
HISTORY_FORMAT = "serving-query-history/1.0"

_HIST_ENTRY_KEYS = {"seq", "mode", "params", "outcome", "check"}
_HIST_OUTCOMES = ("success", "error")


class HistoryError(Exception):
    """Fail-closed query-history store failure (no partial state; nothing published)."""

    def __init__(self, check: str, detail: str) -> None:
        super().__init__("%s: %s" % (check, detail))
        self.check = check
        self.detail = detail


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write_text(path: str, text: str) -> None:
    """Write ``text`` via a temp file in the same directory + atomic replace.

    A crash mid-write can therefore never leave a partial history file or
    sidecar; the temp name is never persisted (renamed or unlinked), so the
    deterministic-output contract is unaffected. (Same convention as the
    saved-query store; per-module helper, as in the serving package.)
    """
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".%s." % os.path.basename(path), suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# validation (fail closed)
# ---------------------------------------------------------------------------


def _validate_entry(entry: object, context: str, previous_seq: Optional[int]) -> None:
    if not isinstance(entry, dict) or not set(entry) <= _HIST_ENTRY_KEYS:
        keys = sorted(entry) if isinstance(entry, dict) else type(entry).__name__
        raise HistoryError("history-schema", "%s: a history entry must have only the keys seq/mode/params/outcome/check, got %r" % (context, keys))
    if set(entry) != _HIST_ENTRY_KEYS - ({"check"} if entry.get("outcome") == "success" else set()):
        keys = sorted(entry)
        raise HistoryError("history-schema", "%s: a history entry must have exactly the keys seq/mode/params/outcome (+ check iff outcome is error), got %r" % (context, keys))
    seq = entry["seq"]
    if type(seq) is not int or seq < 1:
        raise HistoryError("history-schema", "%s: entry seq must be an integer >= 1, got %r" % (context, seq))
    if previous_seq is not None and seq <= previous_seq:
        raise HistoryError(
            "history-schema",
            "%s: entry seq %d is not strictly greater than the previous entry seq %d (ordering violation)" % (context, seq, previous_seq),
        )
    if entry["outcome"] not in _HIST_OUTCOMES:
        raise HistoryError("history-schema", "%s: entry outcome must be one of %s, got %r" % (context, list(_HIST_OUTCOMES), entry["outcome"]))
    if entry["outcome"] == "error":
        check = entry.get("check")
        if not isinstance(check, str) or check == "":
            raise HistoryError("history-schema", "%s: an error entry requires a non-empty check string, got %r" % (context, check))
    try:
        validate_saved_definition(entry["mode"], entry["params"], "%s entry seq %d" % (context, seq))
    except SavedQueryError as exc:
        # a STORED entry violating the definition contract is a history-store
        # state failure (fail closed), not a fresh-input validation error
        raise HistoryError("history-invalid", str(exc))


def _validate_document(document: object, context: str) -> dict:
    if not isinstance(document, dict) or set(document) != {"format", "entries", "next_seq"}:
        keys = sorted(document) if isinstance(document, dict) else type(document).__name__
        raise HistoryError(
            "history-schema",
            "%s: the history document must have exactly the keys format/entries/next_seq, got %r" % (context, keys),
        )
    if document["format"] != HISTORY_FORMAT:
        raise HistoryError(
            "history-format",
            "%s: unsupported history store format %r (supported: %s)" % (context, document["format"], HISTORY_FORMAT),
        )
    next_seq = document["next_seq"]
    if type(next_seq) is not int or next_seq < 1:
        raise HistoryError("history-schema", "%s: next_seq must be an integer >= 1, got %r" % (context, next_seq))
    entries = document["entries"]
    if not isinstance(entries, list):
        raise HistoryError("history-schema", "%s: entries must be an array, got %s" % (context, type(entries).__name__))
    previous: Optional[int] = None
    for i, entry in enumerate(entries):
        _validate_entry(entry, "%s entry index %d" % (context, i), previous)
        previous = entry["seq"]
    if entries and next_seq <= max(entry["seq"] for entry in entries):
        raise HistoryError(
            "history-schema",
            "%s: next_seq %d must be strictly greater than every stored entry seq (max %d)"
            % (context, next_seq, previous),
        )
    return document


# ---------------------------------------------------------------------------
# store I/O (fail closed)
# ---------------------------------------------------------------------------


def load_history(root: str) -> dict:
    """Load and validate the query-history store at ``root`` (fail closed)."""
    path = os.path.join(root, HISTORY_FILENAME)
    digest_path = os.path.join(root, HISTORY_DIGEST_FILENAME)
    if not (os.path.isfile(path) and os.path.isfile(digest_path)):
        raise HistoryError(
            "history-missing",
            "query-history state missing or incomplete at %s (create one with `history record`)" % root,
        )
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    digest = _sha256_text(text)
    with open(digest_path, "r", encoding="utf-8") as handle:
        sidecar = handle.read()
    if sidecar != "%s  %s\n" % (digest, HISTORY_FILENAME):
        raise HistoryError("history-corrupt", "query-history digest sidecar mismatch at %s" % root)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HistoryError("history-corrupt", "query-history store is not valid JSON: %s" % exc)
    return _validate_document(document, "query-history store at %s" % root)


def save_history_document(root: str, document: dict) -> str:
    """Validate and atomically persist ``document``; returns the store sha256."""
    _validate_document(document, "query-history store")
    validate_roots(state=root)
    os.makedirs(root, exist_ok=True)
    text = canonical_json(document) + "\n"
    digest = _sha256_text(text)
    _atomic_write_text(os.path.join(root, HISTORY_FILENAME), text)
    _atomic_write_text(os.path.join(root, HISTORY_DIGEST_FILENAME), "%s  %s\n" % (digest, HISTORY_FILENAME))
    return digest


def _load_or_empty(root: str) -> dict:
    """Load the store, or the empty document if no store exists yet.

    A *partially* present store (either file present) is loaded — and therefore
    fails closed if corrupt or incomplete — never treated as absent.
    """
    if os.path.isfile(os.path.join(root, HISTORY_FILENAME)) or os.path.isfile(
        os.path.join(root, HISTORY_DIGEST_FILENAME)
    ):
        return load_history(root)
    return {"format": HISTORY_FORMAT, "entries": [], "next_seq": 1}


def assert_separate_from_state(history_root: str, state_root: str) -> None:
    """Isolation (C1(a) discipline): the history root must be distinct from the
    derived-state root (the derived-state rebuild must never reach history)."""
    if overlaps(history_root, state_root):
        raise HistoryError(
            "history-state-conflict",
            "the query-history store root must be a distinct directory from the derived "
            "serving state root (D37-DEC: rebuilding derived state must not delete or "
            "modify user state)",
        )


# ---------------------------------------------------------------------------
# the explicit recording operation (C2(a)) and lifecycle
# ---------------------------------------------------------------------------


def record_execution(
    root: str,
    mode: str,
    params: dict,
    baseline: Baseline,
    state_root: str,
    m2: bool = False,
    repo_root: Optional[str] = None,
) -> Tuple[dict, Optional[dict], Optional[str], str]:
    """The single explicit history-recording operation (CLI ``history record``).

    Validates the execution description, executes it through the existing query
    layer, and durably records the ACTUAL outcome as the next entry. Returns
    ``(entry, query_output_or_None, error_detail_or_None, store_sha256)``.

    * A query failure is recorded (outcome ``"error"`` + its check id) — the
      failure IS the actual outcome of the explicit request.
    * A baseline or derived-state failure (``BaselineError``/
      ``ServingIndexError``/``D01InventoryError``) propagates with NO entry
      published (there was no completed execution to record).
    * This operation is the ONLY path that writes the history store (C2(a)).
    """
    assert_separate_from_state(root, state_root)
    validate_roots(package=baseline.root, history=root, state=state_root)
    params = validate_saved_definition(mode, params, "history execution description")
    document = _load_or_empty(root)
    entries: List[dict] = document["entries"]
    seq = document["next_seq"]
    try:
        output = execute_query_definition(mode, params, baseline, state_root, m2=m2, repo_root=repo_root)
        entry: Dict[str, object] = {"seq": seq, "mode": mode, "params": params, "outcome": "success"}
        detail: Optional[str] = None
    except QueryError as exc:
        entry = {"seq": seq, "mode": mode, "params": params, "outcome": "error", "check": exc.check}
        output = None
        detail = str(exc)
    document["entries"] = entries + [entry]
    document["next_seq"] = seq + 1
    digest = save_history_document(root, document)
    return entry, output, detail, digest


def list_history(root: str) -> List[dict]:
    """List all history entries, ascending seq (deterministic)."""
    return list(load_history(root)["entries"])


def get_history(root: str, seq: int) -> dict:
    """Read one history entry by exact seq (fail closed)."""
    if type(seq) is not int or seq < 1:
        raise HistoryError("history-not-found", "no history entry with seq %r" % (seq,))
    for entry in load_history(root)["entries"]:
        if entry["seq"] == seq:
            return entry
    raise HistoryError("history-not-found", "no history entry with seq %d" % seq)


def delete_history(root: str, seq: int) -> str:
    """Explicitly delete one history entry by exact seq; returns the store sha256.

    A deleted seq is never reused. There is no retention policy and no
    automatic pruning — explicit deletion is the only removal path.
    """
    if type(seq) is not int or seq < 1:
        raise HistoryError("history-not-found", "no history entry with seq %r" % (seq,))
    document = load_history(root)
    entries = document["entries"]
    remaining = [entry for entry in entries if entry["seq"] != seq]
    if len(remaining) == len(entries):
        raise HistoryError("history-not-found", "no history entry with seq %d to delete" % seq)
    document["entries"] = remaining
    return save_history_document(root, document)
