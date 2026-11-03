"""The I4 first-release UI host — a local, single-user, read-only server.

This is a presentation-layer host (D16-11/D16-12; D23 §17(b)): it binds a
local HTTP port and serves

* the static application (``ui/static`` — no build step, no third-party
  runtime dependencies, stdlib-only like the rest of the repository), and
* the JSON serving adapter (``ui.api.UiApi``) — the single data path over
  the authorized serving boundary.

Hosting model (D23 §13/§14): personal, single-user, local. The server
binds to loopback by default; ``--bind 0.0.0.0`` is available only for a
supervised environment and is NOT a network product. No authentication
exists by contract (single user, personal) — the loopback bind is the
hosting control.

Startup mirrors the established CLI verify → build → query flow:

1. ``serving.baseline.open_baseline`` — the manifest and qualification
   metadata are checked at startup; manifested files are digest-verified on
   access. Use ``serving verify`` for explicit full package verification;
2. the class-(4) index is loaded from the derived-state root; when it is
   missing it is built, and when it is stale it is rebuilt — the delegated
   rebuild operation (D16-11 item (b); deterministic, rebuildable state);
3. the HTTP server starts.

Usage (from the repository root, with PYTHONPATH=src):

    python3 -m ui.serve --package <pkg> [--m2] --state <dir> \
        --saved-state <dir> --history-state <dir> [--repo <dir>] \
        [--bind 127.0.0.1] [--port 8613]

    then open http://127.0.0.1:8613 in a browser on the same machine.

The derived-state root must live OUTSIDE the package; the saved-query and
query-history store roots are distinct class-(4) user-state roots outside
the derived-state rebuild scope (C1(a)).
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from serving.baseline import DEFAULT_M2_SPEC, open_baseline
from serving.index import (
    ServingIndexError,
    build_index,
    load_index,
    write_index,
)
from serving.paths import RootConfiguration
from serving.rebuild import rebuild_state

from .api import UiApi, encode

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
#: The complete static file table — an exact path -> filename map. Nothing
#: else is served; there is no directory traversal surface.
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.css": "app.css",
    "/app.js": "app.js",
}
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def _ensure_index(baseline, state_root: str) -> dict:
    """Load the class-(4) index, building or rebuilding it when required."""
    try:
        document, _digest = load_index(state_root, baseline)
        return document
    except ServingIndexError as exc:
        # Recovery leaves unknown files (including interrupted temp files) alone.
        if exc.check == "index-stale":
            rebuild_state(baseline, state_root, replace_only=True)
        else:
            document = build_index(baseline)
            write_index(state_root, document)
        document, _digest = load_index(state_root, baseline)
        return document


class _Handler(BaseHTTPRequestHandler):
    """One request: static files or the UI serving adapter."""

    #: deterministic headers (no wall-clock Date; fixed server identity)
    def date_time_string(self, timestamp=None):  # noqa: N802 (stdlib signature)
        import time

        return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(0))

    def version_string(self):  # noqa: N802 (stdlib signature)
        return "i4-ui"

    # -- routing ---------------------------------------------------------
    def do_GET(self):  # noqa: N802 (stdlib signature)
        self._handle("GET")

    def do_POST(self):  # noqa: N802 (stdlib signature)
        self._handle("POST")

    def do_PUT(self):  # noqa: N802 (stdlib signature)
        self._handle("PUT")

    def do_DELETE(self):  # noqa: N802 (stdlib signature)
        self._handle("DELETE")

    def _body(self):
        length = self.headers.get("Content-Length")
        if length is None or length == "":
            return None
        raw = self.rfile.read(int(length))
        if not raw:
            return None
        try:
            document = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("the request body must be a UTF-8 JSON object")
        return document

    def _handle(self, method: str):
        path = self.path.split("?", 1)[0]
        try:
            if path in STATIC_FILES:
                if method != "GET":
                    self._send_json(405, {"result": "fail", "check": "method-not-allowed", "detail": "static assets are GET-only"})
                    return
                self._send_static(path)
                return
            body = self._body() if method in ("POST", "PUT") else None
            status, document = self.server.ui_api.dispatch(method, path, body)
        except ValueError as exc:
            status, document = 400, {"result": "fail", "check": "request-body", "detail": str(exc)}
        self._send_json(status, document)

    def _send_static(self, path: str):
        filename = STATIC_FILES[path]
        full = os.path.join(STATIC_DIR, filename)
        if os.path.dirname(os.path.abspath(full)) != STATIC_DIR or not os.path.isfile(full):
            self._send_json(404, {"result": "fail", "check": "route-not-found", "detail": "static file not found"})
            return
        with open(full, "rb") as handle:
            payload = handle.read()
        self.send_response(200)
        self.send_header("Content-Type", STATIC_TYPES[os.path.splitext(filename)[1]])
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, status: int, document: dict):
        payload = (encode(document) if isinstance(document, dict) else json.dumps(document) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002 (stdlib signature)
        # deterministic, quiet: no per-request logging (no clock, no noise)
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ui", description=__doc__.splitlines()[0])
    parser.add_argument("--package", required=True, help="path to the qualified run package")
    parser.add_argument("--m2", action="store_true", help="pin to the qualified M2 baseline identity (joins the in-repo D01 inventory for Q9)")
    parser.add_argument("--state", required=True, help="serving state dir (OUTSIDE the package)")
    parser.add_argument("--saved-state", required=True, help="saved-query store dir (distinct from --state)")
    parser.add_argument("--history-state", required=True, help="query-history store dir (distinct from --state)")
    parser.add_argument("--registry", default=None, help="optional bounded composite registry root")
    parser.add_argument("--repo", default=None, help="repository root holding the durable in-repository evidence records (Q10); omit for explicit absence")
    parser.add_argument("--bind", default="127.0.0.1", help="interface to bind (default loopback — single-user personal hosting)")
    parser.add_argument("--port", type=int, default=8613, help="port to bind (default 8613)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        roots = RootConfiguration(args.package, args.state, args.saved_state, args.history_state)
        baseline = open_baseline(args.package, spec=DEFAULT_M2_SPEC if args.m2 else None, verify_files=False)
    except Exception as exc:  # fail closed before binding anything
        print(json.dumps({"result": "fail", "stage": "baseline", "detail": str(exc)}, sort_keys=True), flush=True)
        return 3
    try:
        roots.validate()
        _ensure_index(baseline, roots.roots["state"])
        roots.validate()
    except Exception as exc:
        print(json.dumps({"result": "fail", "stage": "index", "detail": str(exc)}, sort_keys=True), flush=True)
        return 3
    try:
        api = UiApi(
            baseline,
            args.state,
            args.saved_state,
            args.history_state,
            m2=args.m2,
            repo_root=args.repo,
            root_config=roots,
            registry_root=args.registry,
        )
    except Exception as exc:
        print(json.dumps({"result": "fail", "stage": "layout", "detail": str(exc)}, sort_keys=True), flush=True)
        return 3
    server = ThreadingHTTPServer((args.bind, args.port), _Handler)
    server.daemon_threads = True
    server.ui_api = api  # type: ignore[attr-defined]
    run_record = baseline.run_record
    print(
        json.dumps(
            {
                "result": "ready",
                "service": "i4-ui/1.0",
                "bind": args.bind,
                "port": args.port,
                "package_run_id": run_record.get("run_id") if isinstance(run_record, dict) else None,
                "m2": args.m2,
                "url": "http://%s:%d/" % (args.bind if args.bind != "0.0.0.0" else "127.0.0.1", args.port),
            },
            sort_keys=True,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
