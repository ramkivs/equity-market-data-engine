"""The I4 first-release UI serving adapter — the single data path.

Boundary (D16-11; D23 §18(8)/(9); the non-authoritative UI spec §10):

* The ONLY query operation the presentation layer can execute is
  ``serving.saved.execute_query_definition`` — the same single dispatch
  the CLI uses — addressed by its exact Q1–Q10 mode name, with parameters
  validated by the same ``serving.saved.validate_saved_definition``
  contract. No other query path exists: there is no route that bypasses
  this dispatch and no route that accepts query parameters outside a
  mode's exact parameter contract.
* Saved-query and query-history state is touched only through the D38
  (``serving.saved``) and D39 (``serving.history``) functions, at their
  own store roots (isolated from the derived-state root — C1(a)).
* This module never opens a baseline path and never reads durable data
  directly: every served value flows through an authorized serving
  operation. The baseline handle is opened once at server start by
  ``ui.serve`` (mirroring the CLI ``_open`` flow) — that is the serving
  boundary, not a UI data path.
* Every response body is canonical JSON (``serving.index.canonical_json``)
  — deterministic byte-for-byte for identical requests.
* No engine-log, raw-content, export, or processing endpoints exist
  (D16-12 first-release scope; D23 §19 withholdings); unknown routes fail
  closed with a canonical error document.
"""

from __future__ import annotations

import os
import re
import threading
from typing import Optional, Tuple

from serving.archive import D01InventoryError
from serving.baseline import Baseline, BaselineError
from serving.history import (
    HISTORY_DIGEST_FILENAME,
    HISTORY_FILENAME,
    HistoryError,
    delete_history,
    get_history,
    list_history,
    record_execution,
)
from serving.index import ServingIndexError, canonical_json
from serving.query import QueryError
from serving.paths import RootConfiguration, repository_root, resolved, RootLayoutError, validate_roots
from serving.saved import (
    SAVED_DIGEST_FILENAME,
    SAVED_FILENAME,
    SAVED_MODES,
    SavedQueryError,
    create_saved,
    delete_saved,
    execute_query_definition,
    execute_saved,
    get_saved,
    list_saved,
    update_saved,
    validate_saved_definition,
)

SERVICE = "i4-ui-serving-adapter/1.0"

#: The exact authorized query modes — nothing else is addressable.
QUERY_MODES = tuple(sorted(SAVED_MODES))

_SAVED_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: check id -> HTTP status. Anything unmapped is a server-side failure.
_CHECK_STATUS = {
    # request-input failures (400)
    "query-input": 400,
    "saved-query-invalid": 400,
    "history-invalid": 400,
    # not-found (404)
    "route-not-found": 404,
    "method-not-allowed": 404,
    "saved-query-not-found": 404,
    "history-not-found": 404,
    # conflicts (409)
    "saved-query-duplicate": 409,
    "saved-query-conflict": 409,
    "history-state-conflict": 409,
    # server-side store failures (500)
    "saved-query-missing": 500,
    "saved-query-corrupt": 500,
    "saved-query-format": 500,
    "saved-query-schema": 500,
    "history-missing": 500,
    "history-corrupt": 500,
    "history-format": 500,
    "history-schema": 500,
}


def _status_for_check(check: str) -> int:
    return _CHECK_STATUS.get(check, 500)


def _store_absent(root: str, filename: str, digest_filename: str) -> bool:
    """True iff NO part of the store exists at ``root`` (neither file).

    Presentation-level empty-state decision for the UI's own class-(4)
    user-state roots (never the baseline): a store that does not exist yet
    is presented as empty (list) or as not-found (single-item operations).
    A partially present store (either file) is NOT absent — it is loaded
    and fails closed through the serving contract if corrupt.
    """
    return not os.path.isfile(os.path.join(root, filename)) and not os.path.isfile(
        os.path.join(root, digest_filename)
    )


class RouteMethod(Exception):
    """Internal: the path exists but the method is not authorized for it."""


class UiApi:
    """The presentation layer's single data path over the serving boundary."""

    def __init__(
        self,
        baseline: Baseline,
        state_root: str,
        saved_root: str,
        history_root: str,
        m2: bool = False,
        repo_root: Optional[str] = None,
        root_config: Optional[RootConfiguration] = None,
        registry_root: Optional[str] = None,
    ) -> None:
        supplied = {"package": resolved(baseline.root), "state": resolved(state_root),
                    "saved": resolved(saved_root), "history": resolved(history_root)}
        self._root_config = root_config or RootConfiguration(baseline.root, state_root, saved_root, history_root)
        self._root_config.validate()
        if self._root_config.roots != supplied:
            raise RootLayoutError("root-layout: configuration does not match service roots")
        self._baseline = baseline
        self._state_root = resolved(state_root)
        self._saved_root = resolved(saved_root)
        self._history_root = resolved(history_root)
        self._m2 = m2
        self._registry_input = os.path.abspath(registry_root) if registry_root is not None else None
        self._registry_root = resolved(registry_root) if registry_root is not None else None
        self._repo_root = repository_root(repo_root) if repo_root is not None else None
        # serialize store mutations (saved/history) across handler threads
        self._lock = threading.Lock()
        self._validate_layout()
        if self._registry_root is not None:
            from serving.composite_binding import ensure_registry_binding
            ensure_registry_binding(self._baseline, self._state_root, self._registry_root)

    def _validate_layout(self):
        self._root_config.validate()
        if self._registry_root is not None:
            if resolved(self._registry_input) != self._registry_root:
                raise RootLayoutError("root-layout: configured registry path changed")
            validate_roots(package=self._baseline.root, state=self._state_root, saved=self._saved_root,
                           history=self._history_root, registry=self._registry_root)

    def _composite(self):
        from serving.composite_binding import read_binding, selected_snapshot
        configured = read_binding(self._baseline, self._state_root)
        if configured is not None:
            if self._registry_root is not None and configured != self._registry_root:
                raise QueryError('composite-unavailable', 'registry argument disagrees with durable binding')
            validate_roots(package=self._baseline.root, state=self._state_root, saved=self._saved_root,
                           history=self._history_root, registry=configured)
            return selected_snapshot(self._baseline, self._state_root)
        if self._registry_root is None:
            return None
        from serving.incremental_publication import active_snapshot
        try:
            return active_snapshot(self._baseline, self._registry_root, self._state_root)
        except Exception as exc:
            raise QueryError('composite-unavailable', 'composite selection failed: %s' % exc) from exc

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        """Server facts (all from the verified package record / CLI flags)."""
        self._validate_layout()
        run_record = self._baseline.run_record
        document = {
            "result": "pass",
            "service": SERVICE,
            "package_run_id": run_record.get("run_id") if isinstance(run_record, dict) else None,
            "m2": self._m2,
            "repo_root": self._repo_root,
            "query_modes": list(QUERY_MODES),
        }
        from serving.composite_binding import has_binding
        if self._registry_root is not None or has_binding(self._state_root):
            selected = self._composite()
            document['composite'] = {'generation': selected[0].manifest_digest if selected else None,
                                     'supported_query_modes': ['Q1-dataset', 'Q2-date-range', 'Q3-instrument', 'Q4-filter', 'Q5-association', 'Q7-record-detail', 'Q10-qualification'] if selected else list(QUERY_MODES)}
        return document

    # ------------------------------------------------------------------ query
    def query(self, body: Optional[dict]) -> dict:
        """POST /api/query — the single query path (mode + exact params).

        Validates the (mode, params) pair with the D38 definition contract,
        then executes it through the one shared dispatch the CLI uses.
        The result envelope is exactly the CLI envelope for the same
        parameters — no new query semantics (D23 §18(8)).
        """
        self._validate_layout()
        if not isinstance(body, dict):
            raise SavedQueryError("saved-query-invalid", "the request body must be a JSON object {mode, params}")
        mode = body.get("mode")
        params = body.get("params")
        if not isinstance(mode, str) or mode not in QUERY_MODES:
            raise SavedQueryError(
                "saved-query-invalid",
                "unknown query mode %r (supported: %s)" % (mode, ", ".join(QUERY_MODES)),
            )
        if not isinstance(params, dict):
            raise SavedQueryError("saved-query-invalid", "params must be a JSON object (the mode's exact parameter contract)")
        validated = validate_saved_definition(mode, params, "ui query")
        output = execute_query_definition(mode, validated, self._baseline, self._state_root, m2=self._m2, repo_root=self._repo_root, composite=self._composite())
        return {"result": "pass", "query": output}

    def _saved_fresh(self) -> bool:
        return _store_absent(self._saved_root, SAVED_FILENAME, SAVED_DIGEST_FILENAME)

    def _history_fresh(self) -> bool:
        return _store_absent(self._history_root, HISTORY_FILENAME, HISTORY_DIGEST_FILENAME)

    # ------------------------------------------------------------------ saved
    def saved_list(self) -> dict:
        self._validate_layout()
        if self._saved_fresh():
            return {"result": "pass", "count": 0, "entries": []}
        entries = list_saved(self._saved_root)
        return {"result": "pass", "count": len(entries), "entries": entries}

    def saved_show(self, query_id: str) -> dict:
        self._validate_layout()
        if self._saved_fresh():
            raise SavedQueryError("saved-query-not-found", "no saved query with identifier %r (store is empty)" % query_id)
        return {"result": "pass", "entry": get_saved(self._saved_root, query_id)}

    def saved_create(self, body: Optional[dict]) -> dict:
        self._validate_layout()
        query_id, mode, params = _saved_def_body(body)
        with self._lock:
            self._validate_layout()
            record, digest = create_saved(self._saved_root, query_id, mode, params)
        return {"result": "pass", "entry": record, "store_sha256": digest}

    def saved_update(self, query_id: str, body: Optional[dict]) -> dict:
        self._validate_layout()
        _query_id_or_raise(query_id)
        if self._saved_fresh():
            raise SavedQueryError("saved-query-not-found", "no saved query with identifier %r (store is empty)" % query_id)
        mode, params = _saved_mode_params(body)
        with self._lock:
            self._validate_layout()
            record, digest = update_saved(self._saved_root, query_id, mode, params)
        return {"result": "pass", "entry": record, "store_sha256": digest}

    def saved_delete(self, query_id: str) -> dict:
        self._validate_layout()
        _query_id_or_raise(query_id)
        if self._saved_fresh():
            raise SavedQueryError("saved-query-not-found", "no saved query with identifier %r (store is empty)" % query_id)
        with self._lock:
            self._validate_layout()
            digest = delete_saved(self._saved_root, query_id)
        return {"result": "pass", "query_id": query_id, "store_sha256": digest}

    def saved_run(self, query_id: str) -> dict:
        """Execute a saved definition — read-only on the store (C2(a))."""
        self._validate_layout()
        _query_id_or_raise(query_id)
        if self._saved_fresh():
            raise SavedQueryError("saved-query-not-found", "no saved query with identifier %r to run (store is empty)" % query_id)
        composite = self._composite()
        if composite is None:
            output = execute_saved(self._saved_root, query_id, self._baseline, self._state_root, m2=self._m2, repo_root=self._repo_root)
        else:
            record = get_saved(self._saved_root, query_id)
            output = execute_query_definition(record['mode'], record['params'], self._baseline, self._state_root, m2=self._m2, repo_root=self._repo_root, composite=composite)
        return {"result": "pass", "query_id": query_id, "query": output}

    # ------------------------------------------------------------------ history
    def history_list(self) -> dict:
        self._validate_layout()
        if self._history_fresh():
            return {"result": "pass", "count": 0, "entries": []}
        entries = list_history(self._history_root)
        return {"result": "pass", "count": len(entries), "entries": entries}

    def history_show(self, seq: str) -> dict:
        self._validate_layout()
        number = _seq_or_raise(seq)
        if self._history_fresh():
            raise HistoryError("history-not-found", "no history entry with seq %d (store is empty)" % number)
        return {"result": "pass", "entry": get_history(self._history_root, number)}

    def history_delete(self, seq: str) -> dict:
        self._validate_layout()
        number = _seq_or_raise(seq)
        if self._history_fresh():
            raise HistoryError("history-not-found", "no history entry with seq %d (store is empty)" % number)
        with self._lock:
            self._validate_layout()
            digest = delete_history(self._history_root, number)
        return {"result": "pass", "seq": number, "store_sha256": digest}

    def history_record(self, body: Optional[dict]) -> dict:
        """The ONLY explicit history-recording operation (D39; C2(a))."""
        self._validate_layout()
        if not isinstance(body, dict):
            raise HistoryError("history-invalid", "the request body must be a JSON object {mode, params}")
        mode = body.get("mode")
        params = body.get("params")
        if not isinstance(mode, str) or mode not in QUERY_MODES:
            raise HistoryError(
                "history-invalid", "unknown query mode %r (supported: %s)" % (mode, ", ".join(QUERY_MODES))
            )
        if not isinstance(params, dict):
            raise HistoryError("history-invalid", "params must be a JSON object (the mode's exact parameter contract)")
        with self._lock:
            self._validate_layout()
            entry, output, detail, digest = record_execution(
                self._history_root, mode, params, self._baseline, self._state_root, m2=self._m2, repo_root=self._repo_root
            )
        result: dict = {"result": "recorded", "outcome": entry["outcome"], "entry": entry, "store_sha256": digest}
        if entry["outcome"] == "success":
            result["query"] = output
        else:
            result["detail"] = detail
        return result

    # ------------------------------------------------------------------ routing
    def dispatch(self, method: str, path: str, body: Optional[dict] = None) -> Tuple[int, dict]:
        """Route one request -> (HTTP status, canonical-JSON document)."""
        try:
            self._validate_layout()
            status, document = self._route(method, path, body)
            return status, document
        except RootLayoutError as exc:
            return 400, {"result": "fail", "check": "root-layout", "detail": str(exc)}
        except RouteMethod:
            return 405, {"result": "fail", "check": "method-not-allowed", "detail": "method not allowed for this route"}
        except (SavedQueryError, HistoryError, QueryError) as exc:
            check = exc.check if isinstance(getattr(exc, "check", None), str) else "serving-error"
            return _status_for_check(check), {"result": "fail", "check": check, "detail": str(exc)}
        except (BaselineError, ServingIndexError, D01InventoryError) as exc:
            return 500, {"result": "fail", "check": "serving-state", "detail": str(exc)}
        except ValueError as exc:
            return 400, {"result": "fail", "check": "request-body", "detail": str(exc)}

    def _route(self, method: str, path: str, body: Optional[dict]) -> Tuple[int, dict]:
        segments = [segment for segment in path.split("/") if segment != ""]
        if segments == ["api", "status"]:
            if method != "GET":
                raise RouteMethod()
            return 200, self.status()
        if segments == ["api", "query"]:
            if method != "POST":
                raise RouteMethod()
            return 200, self.query(body)
        if segments == ["api", "saved"]:
            if method == "GET":
                return 200, self.saved_list()
            if method == "POST":
                return 201, self.saved_create(body)
            raise RouteMethod()
        if len(segments) == 3 and segments[0] == "api" and segments[1] == "saved":
            query_id = segments[2]
            _query_id_or_raise(query_id)
            if method == "GET":
                return 200, self.saved_show(query_id)
            if method == "PUT":
                return 200, self.saved_update(query_id, body)
            if method == "DELETE":
                return 200, self.saved_delete(query_id)
            raise RouteMethod()
        if len(segments) == 4 and segments[0] == "api" and segments[1] == "saved" and segments[3] == "run":
            if method != "POST":
                raise RouteMethod()
            return 200, self.saved_run(segments[2])
        if segments == ["api", "history"]:
            if method == "GET":
                return 200, self.history_list()
            if method == "POST":
                return 201, self.history_record(body)
            raise RouteMethod()
        if len(segments) == 3 and segments[0] == "api" and segments[1] == "history":
            if method == "GET":
                return 200, self.history_show(segments[2])
            if method == "DELETE":
                return 200, self.history_delete(segments[2])
            raise RouteMethod()
        return 404, {"result": "fail", "check": "route-not-found", "detail": "no authorized UI route at %r" % path}


def _query_id_or_raise(query_id: object) -> str:
    if not isinstance(query_id, str) or not _SAVED_ID_RE.match(query_id):
        raise SavedQueryError(
            "saved-query-invalid",
            "saved-query identifier must be 1-64 chars of [a-z0-9_-] starting with [a-z0-9], got %r" % (query_id,),
        )
    return query_id


def _seq_or_raise(seq: object) -> int:
    if not isinstance(seq, str) or not seq.isdigit():
        raise HistoryError("history-invalid", "history seq must be a positive integer, got %r" % (seq,))
    number = int(seq)
    if number < 1:
        raise HistoryError("history-invalid", "history seq must be a positive integer, got %r" % (seq,))
    return number


def _saved_def_body(body: Optional[dict]) -> Tuple[str, str, dict]:
    if not isinstance(body, dict):
        raise SavedQueryError("saved-query-invalid", "the request body must be a JSON object {id, mode, params}")
    mode, params = _saved_mode_params(body)
    query_id = body.get("id")
    _query_id_or_raise(query_id)
    return query_id, mode, params


def _saved_mode_params(body: Optional[dict]) -> Tuple[str, dict]:
    if not isinstance(body, dict):
        raise SavedQueryError("saved-query-invalid", "the request body must be a JSON object")
    mode = body.get("mode")
    params = body.get("params")
    if not isinstance(mode, str) or mode not in QUERY_MODES:
        raise SavedQueryError(
            "saved-query-invalid", "unknown query mode %r (supported: %s)" % (mode, ", ".join(QUERY_MODES))
        )
    if not isinstance(params, dict):
        raise SavedQueryError("saved-query-invalid", "params must be a JSON object (the mode's exact parameter contract)")
    return mode, params


def encode(document: dict) -> str:
    """Canonical-JSON body for one API response (deterministic bytes)."""
    return canonical_json(document) + "\n"
