"""Serving CLI — the read-only consumer boundary for the first vertical slice.

Single-user, personal-use (D23 §13; D16 §13 non-goals): a command-line consumer that
reads *only* through the serving/query layer over a verified qualified baseline. It
opens no network listener, selects no authentication, and introduces no
multi-user/enterprise architecture. Every subcommand is read-only with respect to the
baseline package; the only writes are to the caller-supplied ``--state`` directory
(durable state class (4)), which must live outside the package.

Commands:
  verify    verify a package against its manifests (and, with --m2, the pinned M2 pin)
  build     build the class-(4) index from the verified baseline into --state
  query     run the Q3 instrument query (symbol series), the Q2 date-range
            query (--from --to), the Q4 exact-value filter query
            (--field NAME=VALUE, repeatable), the Q5 identity/association
            query (--identity KEY and/or --instrument-symbol S
            --instrument-series SER), the Q6 calendar query (--calendar
            with optional --from --to inclusive range), or the Q7
            record-detail query (--file --line); exactly one mode per
            invocation
  dataset   run the Q1 dataset/partition selection and yearly summaries
  quality   run the Q8 data-quality view (flag census, quarantine count,
            unresolved-state records, reconciliation aggregates, D21 absence)
  qualification run the Q10 qualification/evidence view (run identity,
            fingerprints, manifests, R6/D11/D12/D14 evidence; optional --repo)
  inventory run the Q9 archive inventory (per-archive INPUT_MANIFEST + D01
            facts; no --state/index dependency)
  rebuild   delete and rebuild the class-(4) state (delegated operation (b))
  info      print a diagnostic summary of the serving state
  saved     manage the saved-query store (class-(4) user state in a DISTINCT
            root outside the derived-state rebuild scope — D37-DEC C1(a)):
            save / show / list / update / delete, and `saved run` (loads a saved
            definition and execute it through the existing query modes; a run
            never mutates the store — C2(a))
  history   query history — recorded ONLY through the explicit `history record`
            operation (executes the given mode + parameters and records the
            actual outcome; C2(a)). Ordinary query / saved-run execution never
            writes history. list / show / delete manage the entries (a DISTINCT
            root outside the derived-state rebuild scope)

Exit codes: 0 = ok (for `history record`: the entry is durably recorded — a
recorded query failure is data in the entry, not an operation failure);
2 = usage/verification/query failure (fail closed); 3 = index/stale/saved-store
state failure. No partial results are printed on failure.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import baseline as baseline_mod
from .paths import validate_roots, RootLayoutError, RootConfiguration, resolved
from .continuity_view import get_continuity
from .archive import D01InventoryError, load_d01_inventory, query_archive_inventory
from .detail import query_record_detail
from .index import index_state, load_index, write_index, build_index, ServingIndexError
from .qualification import query_qualification
from .quality import query_data_quality
from .query import (
    ASSOCIATIONS_QUERY_ID,
    CALENDAR_QUERY_ID,
    DATE_RANGE_QUERY_ID,
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
from .history import (
    HistoryError,
    delete_history,
    get_history,
    list_history,
    record_execution,
)
from .rebuild import rebuild_state
from .saved import (
    SavedQueryError,
    create_saved,
    delete_saved,
    execute_saved,
    get_saved,
    list_saved,
    update_saved,
    validate_saved_definition,
)


def _print_json(obj) -> None:
    sys.stdout.write(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )


def _open(args, verify_files=True):
    spec = baseline_mod.DEFAULT_M2_SPEC if getattr(args, "m2", False) else None
    return baseline_mod.open_baseline(args.package, spec=spec, verify_files=verify_files)


def cmd_verify(args) -> int:
    try:
        handle = _open(args, verify_files=not args.fast)
    except baseline_mod.BaselineError as exc:
        _print_json({"result": "fail", "check": exc.check, "detail": exc.detail})
        return 2
    _print_json(
        {
            "result": "pass",
            "checks_passed": list(handle.checks_passed),
            "verification": "metadata-and-on-access" if args.fast else "full",
            "manifest_sha256": handle.manifest_digest,
            "manifest_entries": len(handle.manifest_entries),
            "total_bytes": handle.total_bytes,
            "run_id": handle.marker.get("run_id"),
            "pinned": "m2" if args.m2 else "unpinned",
        }
    )
    return 0


def cmd_build(args) -> int:
    try:
        handle = _open(args)
        validate_roots(package=handle.root, state=args.state)
        document = build_index(handle)
        digest = write_index(args.state, document)
    except (baseline_mod.BaselineError, ServingIndexError) as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 3
    _print_json(
        {
            "result": "pass",
            "index_sha256": digest,
            "counts": document["counts"],
            "partitions": sorted(document["partitions"].keys()),
            "package_manifest_sha256": document["package"]["manifest_sha256"],
        }
    )
    return 0


def cmd_query(args) -> int:
    q2 = args.date_from is not None or args.date_to is not None
    q3 = args.symbol is not None or args.series is not None
    q7 = args.source_file is not None or args.source_line_number is not None
    q4 = bool(args.field)
    q5 = args.identity is not None or args.instrument_symbol is not None or args.instrument_series is not None
    q6 = bool(args.calendar)
    # with --calendar the --from/--to flags carry the Q6 range (not Q2)
    q2 = (not q6) and q2
    if sum(bool(mode) for mode in (q2, q3, q7, q4, q5, q6)) != 1:
        _print_json(
            {
                "result": "fail",
                "detail": "query requires exactly one of: symbol series (Q3), --from and --to (Q2), "
                "--field NAME=VALUE (Q4), --identity KEY / --instrument-symbol S --instrument-series SER (Q5), "
                "--calendar [with --from and --to] (Q6), or --file and --line (Q7)",
            }
        )
        return 2
    if q6 and (args.date_from is None) != (args.date_to is None):
        _print_json(
            {
                "result": "fail",
                "detail": "Q6 calendar range requires both --from and --to (inclusive ISO business dates)",
            }
        )
        return 2
    if q5 and (args.instrument_symbol is None) != (args.instrument_series is None):
        _print_json(
            {
                "result": "fail",
                "detail": "Q5 instrument selector requires both --instrument-symbol and --instrument-series "
                "(an ordered pair; a single field is not a selector)",
            }
        )
        return 2
    if q4:
        filters = {}
        for item in args.field:
            name, sep, value = item.partition("=")
            if not sep or not name:
                _print_json({"result": "fail", "detail": "Q4 --field requires NAME=VALUE, got %r" % item})
                return 2
            if name in filters:
                _print_json(
                    {"result": "fail", "detail": "Q4 allows exactly one value per field; duplicate filter for %r" % name}
                )
                return 2
            filters[name] = value
    if q7 and (args.source_file is None or args.source_line_number is None):
        _print_json({"result": "fail", "detail": "Q7 record detail requires both --file and --line"})
        return 2
    if q2 and (args.date_from is None or args.date_to is None):
        _print_json({"result": "fail", "detail": "Q2 date-range query requires both --from and --to"})
        return 2
    if q3 and (args.symbol is None or args.series is None):
        _print_json({"result": "fail", "detail": "Q3 instrument query requires both symbol and series"})
        return 2
    try:
        handle = _open(args)
        from .composite_binding import selected_snapshot
        composite = selected_snapshot(handle, args.state)
        if composite is None:
            document, _digest = load_index(args.state, handle)
        else:
            handle, document = composite
            if q6:
                raise QueryError('composite-unavailable', 'calendar unavailable for selected composite generation')
        if q2:
            rows = query_date_range(handle, document, args.date_from, args.date_to)
            output = {
                "query": DATE_RANGE_QUERY_ID,
                "date_from": args.date_from,
                "date_to": args.date_to,
                "result_count": len(rows),
                "rows": list(rows),
            }
        elif q6:
            documents = parse_calendar(handle)
            rows = query_calendar(
                handle,
                document,
                date_from=args.date_from,
                date_to=args.date_to,
                documents=documents,
            )
            output = {
                "query": CALENDAR_QUERY_ID,
                "date_from": args.date_from,
                "date_to": args.date_to,
                "calendar_present": documents is not None,
                "record_count": len(rows),
                "records": list(rows),
            }
        elif q4:
            rows = query_filters(handle, document, filters)
            output = {
                "query": FILTER_QUERY_ID,
                "filters": filters,
                "result_count": len(rows),
                "rows": list(rows),
            }
        elif q3:
            rows = query_instrument(handle, document, args.symbol, args.series, year=args.year)
            output = {"query": QUERY_ID, "result_count": len(rows), "rows": list(rows)}
        elif q5:
            documents = parse_associations(handle)
            rows = query_associations(
                handle,
                document,
                security_id=args.identity,
                symbol=args.instrument_symbol,
                series=args.instrument_series,
                documents=documents,
            )
            output = {
                "query": ASSOCIATIONS_QUERY_ID,
                "security_id": args.identity,
                "series": args.instrument_series,
                "symbol": args.instrument_symbol,
                "associations_present": documents is not None,
                "continuity": get_continuity(handle, document)[0],
                "record_count": len(rows),
                "records": list(rows),
            }
        else:
            output = query_record_detail(handle, document, args.source_file, args.source_line_number)
    except (baseline_mod.BaselineError, ServingIndexError) as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 3
    except QueryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 2
    _print_json(output)
    return 0


def _saved_exit_code(exc: SavedQueryError) -> int:
    """3 for store-state failures (missing/corrupt/format/schema/conflict);
    2 for usage-level failures (invalid definition, duplicate, not-found)."""
    state_checks = (
        "saved-query-missing",
        "saved-query-corrupt",
        "saved-query-format",
        "saved-query-schema",
        "saved-query-conflict",
    )
    return 3 if exc.check in state_checks else 2


def _saved_param_flags(args) -> dict:
    """Map the saved-query CLI flags to the mode's exact parameter names.

    Absent flags are simply not persisted (absent != null != blank — the
    contract rejects null/blank values). Q3 uses --symbol/--series; Q5 uses
    --instrument-symbol/--instrument-series; both cannot be given in one
    definition (the parameter name would be ambiguous).
    """
    if args.symbol is not None and args.instrument_symbol is not None:
        raise SavedQueryError(
            "saved-query-invalid",
            "--symbol (Q3) and --instrument-symbol (Q5) are mutually exclusive in one definition",
        )
    if args.series is not None and args.instrument_series is not None:
        raise SavedQueryError(
            "saved-query-invalid",
            "--series (Q3) and --instrument-series (Q5) are mutually exclusive in one definition",
        )
    params = {}
    if args.family is not None:
        params["family"] = args.family
    if args.date_from is not None:
        params["date_from"] = args.date_from
    if args.date_to is not None:
        params["date_to"] = args.date_to
    if args.symbol is not None:
        params["symbol"] = args.symbol
    if args.series is not None:
        params["series"] = args.series
    if args.year is not None:
        params["year"] = args.year
    if args.identity is not None:
        params["security_id"] = args.identity
    if args.instrument_symbol is not None:
        params["symbol"] = args.instrument_symbol
    if args.instrument_series is not None:
        params["series"] = args.instrument_series
    if args.source_file is not None:
        params["source_file"] = args.source_file
    if args.source_line_number is not None:
        params["source_line_number"] = args.source_line_number
    if args.repo is not None:
        params["repo"] = args.repo
    if args.field:
        filters = {}
        for item in args.field:
            name, sep, value = item.partition("=")
            if not sep or not name or not value:
                raise SavedQueryError("saved-query-invalid", "Q4 --field requires NAME=VALUE, got %r" % item)
            if name in filters:
                raise SavedQueryError(
                    "saved-query-invalid", "Q4 allows exactly one value per field; duplicate filter for %r" % name
                )
            filters[name] = value
        params["filters"] = filters
    return params


def cmd_saved_save(args) -> int:
    try:
        params = validate_saved_definition(args.mode, _saved_param_flags(args))
        record, digest = create_saved(args.saved_state, args.id, args.mode, params)
    except SavedQueryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _saved_exit_code(exc)
    _print_json({"result": "pass", "query": record, "store_sha256": digest})
    return 0


def cmd_saved_show(args) -> int:
    try:
        record = get_saved(args.saved_state, args.id)
    except SavedQueryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _saved_exit_code(exc)
    _print_json({"result": "pass", "query": record})
    return 0


def cmd_saved_list(args) -> int:
    try:
        records = list_saved(args.saved_state)
    except SavedQueryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _saved_exit_code(exc)
    _print_json({"result": "pass", "count": len(records), "queries": records})
    return 0


def cmd_saved_update(args) -> int:
    try:
        params = validate_saved_definition(args.mode, _saved_param_flags(args))
        record, digest = update_saved(args.saved_state, args.id, args.mode, params)
    except SavedQueryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _saved_exit_code(exc)
    _print_json({"result": "pass", "query": record, "store_sha256": digest})
    return 0


def cmd_saved_delete(args) -> int:
    try:
        digest = delete_saved(args.saved_state, args.id)
    except SavedQueryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _saved_exit_code(exc)
    _print_json({"result": "pass", "id": args.id, "store_sha256": digest})
    return 0


def cmd_saved_run(args) -> int:
    try:
        handle = _open(args)
        output = execute_saved(args.saved_state, args.id, handle, args.state, m2=args.m2, repo_root=args.repository_root)
    except SavedQueryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _saved_exit_code(exc)
    except (baseline_mod.BaselineError, ServingIndexError, D01InventoryError) as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 3
    except QueryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 2
    _print_json(output)
    return 0


def _history_exit_code(exc: HistoryError) -> int:
    """3 for store-state failures; 2 for usage-level failures (not-found)."""
    state_checks = (
        "history-missing",
        "history-corrupt",
        "history-format",
        "history-schema",
        "history-state-conflict",
    )
    return 3 if exc.check in state_checks else 2


def cmd_history_record(args) -> int:
    """The single explicit history-recording operation (C2(a)).

    Exit 0 = the entry is durably recorded (``outcome`` in the output says
    whether the explicitly requested execution succeeded or failed). Exit 2/3
    = the operation itself failed (invalid description, store-state failure,
    baseline/state failure) — in that case NO entry is published.
    """
    try:
        params = validate_saved_definition(args.mode, _saved_param_flags(args))
    except SavedQueryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 2
    try:
        handle = _open(args)
        entry, output, detail, digest = record_execution(
            args.history_state, args.mode, params, handle, args.state, m2=args.m2, repo_root=args.repository_root
        )
    except HistoryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _history_exit_code(exc)
    except (baseline_mod.BaselineError, ServingIndexError, D01InventoryError) as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 3
    result = {
        "result": "recorded",
        "outcome": entry["outcome"],
        "entry": entry,
        "store_sha256": digest,
    }
    if entry["outcome"] == "success":
        result["query"] = output
    else:
        result["detail"] = detail
    _print_json(result)
    return 0


def cmd_history_list(args) -> int:
    try:
        entries = list_history(args.history_state)
    except HistoryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _history_exit_code(exc)
    _print_json({"result": "pass", "count": len(entries), "entries": entries})
    return 0


def cmd_history_show(args) -> int:
    try:
        entry = get_history(args.history_state, args.seq)
    except HistoryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _history_exit_code(exc)
    _print_json({"result": "pass", "entry": entry})
    return 0


def cmd_history_delete(args) -> int:
    try:
        digest = delete_history(args.history_state, args.seq)
    except HistoryError as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return _history_exit_code(exc)
    _print_json({"result": "pass", "seq": args.seq, "store_sha256": digest})
    return 0


def cmd_dataset(args) -> int:
    try:
        handle = _open(args)
        from .composite_binding import selected_snapshot
        selected = selected_snapshot(handle, args.state)
        if selected is None:
            document, _digest = load_index(args.state, handle)
        else:
            _, document = selected
        output = query_dataset_summary(document, family=args.family, year=args.year)
    except (baseline_mod.BaselineError, ServingIndexError, QueryError) as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 3
    _print_json(output)
    return 0


def cmd_inventory(args) -> int:
    try:
        handle = _open(args)
        d01 = load_d01_inventory(repo_root=args.repo) if args.m2 else None
        output = query_archive_inventory(handle, d01=d01)
        output['subject_scope'] = 'original-baseline-only; does not include incremental registry or generation'
    except (baseline_mod.BaselineError, D01InventoryError, QueryError) as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 2
    _print_json(output)
    return 0


def cmd_qualification(args) -> int:
    try:
        handle = _open(args)
        output = query_qualification(handle, repo_root=args.repo)
        output['subject_scope'] = 'qualified-baseline-only; incremental generation is not independently qualified'
    except (baseline_mod.BaselineError, QueryError) as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 3
    _print_json(output)
    return 0


def cmd_quality(args) -> int:
    try:
        handle = _open(args)
        from .composite_binding import selected_snapshot
        if selected_snapshot(handle, args.state) is not None:
            raise QueryError('composite-unavailable', 'quality unavailable for selected composite generation')
        document, _digest = load_index(args.state, handle)
        output = query_data_quality(handle, document)
    except (baseline_mod.BaselineError, ServingIndexError, QueryError) as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 3
    _print_json(output)
    return 0


def cmd_rebuild(args) -> int:
    try:
        handle = _open(args)
        report = rebuild_state(handle, args.state)
    except (baseline_mod.BaselineError, ServingIndexError) as exc:
        _print_json({"result": "fail", "detail": str(exc)})
        return 3
    _print_json({"result": "pass", **report})
    return 0


def cmd_info(args) -> int:
    state = index_state(args.state)
    if state is None:
        _print_json({"result": "fail", "detail": "no serving state at %s" % args.state})
        return 3
    output = {"result": "pass", **state}
    if os.path.lexists(os.path.join(args.state, 'composite_registry.json')):
        output['scope'] = 'baseline index metadata only; a composite generation may be selected'
    _print_json(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serving", description=__doc__.splitlines()[0])
    for role in ("package", "state", "saved", "history"):
        parser.add_argument("--root-" + role, default=None,
                            help="complete four-root layout: " + role + " root (supply all four)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p, state=False):
        p.add_argument("--package", required=True, help="path to the qualified run package")
        p.add_argument("--m2", action="store_true", help="pin to the qualified M2 baseline identity")
        if state:
            p.add_argument("--state", required=True, help="serving state dir (OUTSIDE the package)")

    p_verify = sub.add_parser("verify", help="verify a package against its manifests")
    add_common(p_verify)
    p_verify.add_argument("--fast", action="store_true", help="skip per-file digest recompute")
    p_verify.set_defaults(func=cmd_verify)

    p_build = sub.add_parser("build", help="build the class-(4) index")
    add_common(p_build, state=True)
    p_build.set_defaults(func=cmd_build)

    p_query = sub.add_parser(
        "query",
        help="run the Q3 instrument query, the Q2 date-range query, the Q4 exact-value filter query, the Q5 identity/association query, or the Q7 record detail",
    )
    add_common(p_query, state=True)
    p_query.add_argument("symbol", nargs="?", default=None)
    p_query.add_argument("series", nargs="?", default=None)
    p_query.add_argument("--year", type=int, default=None)
    p_query.add_argument(
        "--field",
        dest="field",
        action="append",
        default=None,
        metavar="NAME=VALUE",
        help="Q4: exact-value filter on one of series/segment/source/instrument_type/symbol (repeatable; AND semantics)",
    )
    p_query.add_argument(
        "--from",
        dest="date_from",
        default=None,
        metavar="YYYY-MM-DD",
        help="Q2: inclusive range start; Q6: inclusive calendar range start (with --calendar; ISO business date, both bounds together)",
    )
    p_query.add_argument(
        "--to",
        dest="date_to",
        default=None,
        metavar="YYYY-MM-DD",
        help="Q2: inclusive range end; Q6: inclusive calendar range end (with --calendar; ISO business date, both bounds together)",
    )
    p_query.add_argument(
        "--calendar",
        dest="calendar",
        action="store_true",
        help="Q6: calendar query (trading days from file presence; sourced holiday labels; unexplained and not-retrieved states as published; optional --from/--to inclusive range)",
    )
    p_query.add_argument(
        "--file",
        dest="source_file",
        default=None,
        help="Q7: row file, exactly as served in a Q2/Q3 result (serving.source_file)",
    )
    p_query.add_argument(
        "--line",
        dest="source_line_number",
        type=int,
        default=None,
        help="Q7: the row's canonical source_line_number (D05 §8 field)",
    )
    p_query.add_argument(
        "--identity",
        dest="identity",
        default=None,
        metavar="KEY",
        help="Q5: identity lookup by exact as-published security_id (the D05 §6.1 normalized-ISIN correlation key; not exchange-authoritative identity)",
    )
    p_query.add_argument(
        "--instrument-symbol",
        dest="instrument_symbol",
        default=None,
        metavar="SYMBOL",
        help="Q5: the instrument trading symbol or exact as-published listing_symbol (with --instrument-series)",
    )
    p_query.add_argument(
        "--instrument-series",
        dest="instrument_series",
        default=None,
        metavar="SERIES",
        help="Q5: the instrument's exact as-published series (with --instrument-symbol)",
    )
    p_query.set_defaults(func=cmd_query)

    p_saved = sub.add_parser(
        "saved",
        help="manage the saved-query store (class-(4) user state; distinct root outside the "
        "derived-state rebuild scope, D37-DEC C1(a); a run never mutates the store, C2(a))",
    )
    saved_sub = p_saved.add_subparsers(dest="saved_command", required=True)

    def add_saved_def_flags(p):
        p.add_argument(
            "--mode",
            required=True,
            help="the exact query-id contract: Q1-dataset, Q2-date-range, Q3-instrument, "
            "Q4-filter, Q5-association, Q6-calendar, Q7-record-detail, Q8-data-quality, "
            "Q9-archive-inventory, Q10-qualification",
        )
        p.add_argument("--symbol", default=None, help="Q3: trading symbol or exact published listing_symbol")
        p.add_argument("--series", default=None, help="Q3: series (exact, as published)")
        p.add_argument("--year", type=int, default=None, help="Q1/Q3: restrict to one calendar-year partition")
        p.add_argument("--family", default=None, help="Q1: restrict to one format family (exact, as published)")
        p.add_argument(
            "--from",
            dest="date_from",
            default=None,
            metavar="YYYY-MM-DD",
            help="Q2/Q6: inclusive range start (ISO business date)",
        )
        p.add_argument(
            "--to",
            dest="date_to",
            default=None,
            metavar="YYYY-MM-DD",
            help="Q2/Q6: inclusive range end (ISO business date)",
        )
        p.add_argument(
            "--field",
            dest="field",
            action="append",
            default=None,
            metavar="NAME=VALUE",
            help="Q4: exact-value filter on series/segment/source/instrument_type/symbol (repeatable)",
        )
        p.add_argument(
            "--identity",
            dest="identity",
            default=None,
            metavar="KEY",
            help="Q5: identity lookup by exact as-published security_id",
        )
        p.add_argument(
            "--instrument-symbol",
            dest="instrument_symbol",
            default=None,
            metavar="SYMBOL",
            help="Q5: the instrument trading symbol or exact as-published listing_symbol",
        )
        p.add_argument(
            "--instrument-series",
            dest="instrument_series",
            default=None,
            metavar="SERIES",
            help="Q5: the instrument's exact as-published series",
        )
        p.add_argument(
            "--file",
            dest="source_file",
            default=None,
            help="Q7: row file, exactly as served in a Q2/Q3 result (serving.source_file)",
        )
        p.add_argument(
            "--line",
            dest="source_line_number",
            type=int,
            default=None,
            help="Q7: the row's canonical source_line_number (D05 §8 field)",
        )
        p.add_argument(
            "--repo",
            default=None,
            help="Q10: repository root holding the durable in-repository evidence records; omit for explicit absence",
        )

    p_saved_save = saved_sub.add_parser("save", help="create a saved query")
    p_saved_save.add_argument(
        "--saved-state",
        required=True,
        help="saved-query store dir (a DISTINCT dir from the derived --state dir; OUTSIDE the package)",
    )
    p_saved_save.add_argument(
        "--id",
        dest="id",
        required=True,
        help="stable saved-query identifier (1-64 chars of [a-z0-9_-], starting with [a-z0-9])",
    )
    add_saved_def_flags(p_saved_save)
    p_saved_save.set_defaults(func=cmd_saved_save)

    p_saved_show = saved_sub.add_parser("show", help="read one saved query by identifier")
    p_saved_show.add_argument("--saved-state", required=True, help="saved-query store dir")
    p_saved_show.add_argument("--id", dest="id", required=True, help="saved-query identifier")
    p_saved_show.set_defaults(func=cmd_saved_show)

    p_saved_list = saved_sub.add_parser("list", help="list saved queries (sorted by identifier)")
    p_saved_list.add_argument("--saved-state", required=True, help="saved-query store dir")
    p_saved_list.set_defaults(func=cmd_saved_list)

    p_saved_update = saved_sub.add_parser(
        "update", help="replace a saved query's definition exactly (full replacement, no merge)"
    )
    p_saved_update.add_argument("--saved-state", required=True, help="saved-query store dir")
    p_saved_update.add_argument("--id", dest="id", required=True, help="saved-query identifier")
    add_saved_def_flags(p_saved_update)
    p_saved_update.set_defaults(func=cmd_saved_update)

    p_saved_delete = saved_sub.add_parser("delete", help="explicitly delete one saved query")
    p_saved_delete.add_argument("--saved-state", required=True, help="saved-query store dir")
    p_saved_delete.add_argument("--id", dest="id", required=True, help="saved-query identifier")
    p_saved_delete.set_defaults(func=cmd_saved_delete)

    p_saved_run = saved_sub.add_parser(
        "run", help="load a saved definition and execute it through the existing query modes"
    )
    p_saved_run.add_argument("--saved-state", required=True, help="saved-query store dir")
    p_saved_run.add_argument("--id", dest="id", required=True, help="saved-query identifier")
    add_common(p_saved_run, state=True)
    p_saved_run.add_argument("--repository-root", default=None, help="repository root for D01 inventory")
    p_saved_run.set_defaults(func=cmd_saved_run)

    p_history = sub.add_parser(
        "history",
        help="query history (recorded ONLY via the explicit `history record` operation, "
        "C2(a); distinct root outside the derived-state rebuild scope)",
    )
    history_sub = p_history.add_subparsers(dest="history_command", required=True)

    p_history_record = history_sub.add_parser(
        "record",
        help="explicitly execute a mode + parameters and record the actual outcome "
        "(the ONLY path that writes history)",
    )
    p_history_record.add_argument(
        "--history-state",
        required=True,
        help="query-history store dir (a DISTINCT dir from the derived --state dir; OUTSIDE the package)",
    )
    add_saved_def_flags(p_history_record)
    add_common(p_history_record, state=True)
    p_history_record.add_argument("--repository-root", default=None, help="repository root for D01 inventory")
    p_history_record.set_defaults(func=cmd_history_record)

    p_history_list = history_sub.add_parser("list", help="list history entries (ascending seq)")
    p_history_list.add_argument("--history-state", required=True, help="query-history store dir")
    p_history_list.set_defaults(func=cmd_history_list)

    p_history_show = history_sub.add_parser("show", help="read one history entry by seq")
    p_history_show.add_argument("--history-state", required=True, help="query-history store dir")
    p_history_show.add_argument("--seq", type=int, required=True, help="the entry's stable seq")
    p_history_show.set_defaults(func=cmd_history_show)

    p_history_delete = history_sub.add_parser("delete", help="explicitly delete one history entry by seq")
    p_history_delete.add_argument("--history-state", required=True, help="query-history store dir")
    p_history_delete.add_argument("--seq", type=int, required=True, help="the entry's stable seq")
    p_history_delete.set_defaults(func=cmd_history_delete)

    p_dataset = sub.add_parser("dataset", help="Q1 dataset/partition selection and yearly summaries")
    add_common(p_dataset, state=True)
    p_dataset.add_argument("--family", default=None, help="restrict to one format family (exact, as-published)")
    p_dataset.add_argument("--year", type=int, default=None, help="restrict to one calendar-year partition")
    p_dataset.set_defaults(func=cmd_dataset)

    p_qualification = sub.add_parser(
        "qualification",
        help="Q10 qualification/evidence view (run identity, fingerprints, manifests, R6/D11/D12/D14 evidence)",
    )
    add_common(p_qualification)
    p_qualification.add_argument(
        "--repo",
        default=None,
        help="repository root holding the durable in-repository evidence records (R6/D11/D12/D14); omit for explicit absence",
    )
    p_qualification.set_defaults(func=cmd_qualification)

    p_quality = sub.add_parser(
        "quality",
        help="Q8 data-quality view (flag census, quarantine, unresolved, reconciliation, D21 absence)",
    )
    add_common(p_quality, state=True)
    p_quality.set_defaults(func=cmd_quality)

    p_inventory = sub.add_parser(
        "inventory",
        help="Q9 archive inventory (per-archive INPUT_MANIFEST + D01 facts; no index)",
    )
    add_common(p_inventory)
    p_inventory.add_argument("--repo", default=None, help="repository root holding D01 inventory")
    p_inventory.set_defaults(func=cmd_inventory)

    p_rebuild = sub.add_parser("rebuild", help="delete and rebuild class-(4) state (op b)")
    add_common(p_rebuild, state=True)
    p_rebuild.set_defaults(func=cmd_rebuild)

    p_info = sub.add_parser("info", help="summarise the serving state")
    p_info.add_argument("--state", required=True)
    p_info.set_defaults(func=cmd_info)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        values = {role: getattr(args, "root_" + role) for role in ("package", "state", "saved", "history")}
        roots = None
        if any(value is not None for value in values.values()):
            if any(value is None for value in values.values()):
                raise RootLayoutError("root-layout: supply all four --root-* options")
            roots = RootConfiguration(**values)
            for role, attribute in (("package", "package"), ("state", "state"),
                                    ("saved", "saved_state"), ("history", "history_state")):
                actual = getattr(args, attribute, None)
                if actual is not None and resolved(actual) != roots.roots[role]:
                    raise RootLayoutError("root-layout: --%s does not match configured %s root" % (attribute.replace("_", "-"), role))
            roots.validate()
        return args.func(args)
    except RootLayoutError as exc:
        _print_json({"result": "fail", "check": "root-layout", "detail": str(exc)})
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
