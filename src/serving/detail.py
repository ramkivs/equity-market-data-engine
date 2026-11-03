"""Q7 record detail (D16-10 Q7) — one canonical row plus its archive facts.

Contract (D16-10 Q7; D22 §6; D23 §§9-10):

* A Q7 result provides, for exactly one canonical row:
  1. the selected canonical row, served exactly as Q2/Q3 serve rows —
     as-published field values, the row's own D05 §8 provenance block, the
     serving envelope, and ``raw_line`` excluded (L1 retention is not part of
     the served view — D16-08 class-5 exclusions);
  2. the applicable archive facts from ``INPUT_MANIFEST.jsonl`` (as published,
     no invented defaults — the Q9 parser is reused, not duplicated);
  3. the reconciliation records applicable to that archive from
     ``RECONCILIATION.jsonl`` (as published, in file order; an archive with no
     applicable records yields an empty list — absence is a valid state, not
     an error).

Row identity (established; no new identifier introduced):

* A row is selected by ``(source_file, source_line_number)`` — ``source_file``
  is the row file exactly as served in the Q2/Q3 ``serving`` envelope
  (``serving.source_file``), and ``source_line_number`` is the row's canonical
  D05 §8 field (its line number within the source member, as stored on the
  row). Within one row file ``source_line_number`` is unique (each member data
  line produces at most one row), so the pair identifies exactly one row —
  stably, even where quarantined lines mean the row's position in the file
  differs from its member line number.

Row-to-archive join (schema-supported, digest-verified — no inference from
display symbols, dates, or file ordering):

* The runner (``tools/i4_runner/i4_inputs.build_source``) constructs the row's
  provenance strictly from the governed D01 inventory facts, and the
  ``INPUT_MANIFEST`` record (written by the same runner) carries those same
  facts. The join key is therefore the provenance triple
  ``(source_archive, member_name, archive_sha256)`` matched against the
  record's ``(file_name, member_name, archive_sha256_d01)`` — a digest-
  verified identity relationship, corroborated by ``row.format_family ==
  record.engine_family``. A missing, absent, or ambiguous match is an
  identity inconsistency: fail closed, never an arbitrary archive.

Reconciliation applicability:

* A ``RECONCILIATION.jsonl`` record applies to an archive exactly when its
  ``input_identity`` is a member scope (``scope == "member"``) whose
  ``(root, relative_path)`` equals the archive's. Corpus-scoped records apply
  to no single archive and are not served per-archive (they belong to the
  corpus-level quality/evidence views, Q8/Q10 — out of scope here).

Fail-closed: unknown row file, unknown row, malformed or contract-violating
INPUT_MANIFEST / RECONCILIATION records, or an identity inconsistency all
raise before any partial output is produced. Read-only: the query streams
class-(1) row files and opens the two package metadata documents; it writes
nothing and produces no serving state (the class-(4) index is read, never
rebuilt, by Q7).
"""

from __future__ import annotations

import json

from .archive import parse_input_manifest
from .symbols import observed_trading_symbol
from .baseline import Baseline
from .query import QueryError

RECORD_DETAIL_QUERY_ID = "Q7-record-detail"

RECONCILIATION = "RECONCILIATION.jsonl"

#: The runner's shared reconciliation record schema (tools/i4_runner/
#: i4_reconcile.make_record — the package owner writes exactly these 14 keys).
RECONCILIATION_CONTRACT_KEYS = (
    "tier",
    "tier_description",
    "check",
    "input_identity",
    "comparison_basis",
    "governing_definition",
    "expected",
    "observed",
    "delta",
    "result",
    "disposition",
    "unresolved_state",
    "note",
)


def parse_reconciliation(baseline: Baseline) -> list:
    """Parse the package's RECONCILIATION.jsonl (as-published; fail closed).

    Every record must be a JSON object carrying the runner's 14-key schema;
    ``input_identity`` must be a record (scope). Any violation raises
    :class:`QueryError` before any output is produced.
    """
    records = []
    with open(baseline.path(RECONCILIATION), "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise QueryError("reconciliation-scan", "unparseable RECONCILIATION line %d: %s" % (line_number, exc))
            if not isinstance(record, dict):
                raise QueryError("reconciliation-scan", "RECONCILIATION line %d is not a record" % line_number)
            missing = [key for key in RECONCILIATION_CONTRACT_KEYS if key not in record]
            if missing:
                raise QueryError("reconciliation-scan", "RECONCILIATION line %d missing contract keys: %s" % (line_number, missing))
            if not isinstance(record.get("input_identity"), dict):
                raise QueryError("reconciliation-scan", "RECONCILIATION line %d: input_identity is not a record" % line_number)
            records.append(record)
    return records


def _load_row(baseline: Baseline, index: dict, source_file: str, source_line_number: int) -> dict:
    """Stream one row file and return the row whose canonical
    ``source_line_number`` equals the requested value (fail closed)."""
    meta = index.get("files", {}).get(source_file)
    if not isinstance(meta, dict):
        raise QueryError("record-detail", "unknown row file %r (not a class-(1) row file of the verified baseline)" % source_file)
    with open(baseline.path(source_file), "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise QueryError("record-scan", "unparseable canonical row in %s: %s" % (source_file, exc))
            if not isinstance(row, dict) or not isinstance(row.get("source_values"), dict):
                raise QueryError("record-scan", "canonical row without contract keys in %s" % source_file)
            stored = row.get("source_line_number")
            if isinstance(stored, int) and not isinstance(stored, bool) and stored == source_line_number:
                return row
    raise QueryError("record-detail", "no row with source_line_number %d in %s" % (source_line_number, source_file))


def _archive_for_row(row: dict, manifest_records: list) -> dict:
    """Join the row's D05 §8 provenance triple to its INPUT_MANIFEST record.

    Fail closed on an absent provenance block, absent identity fields, no
    match, more than one match, or a format-family inconsistency.
    """
    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        raise QueryError("record-detail", "canonical row without a D05 §8 provenance block")
    key = (provenance.get("source_archive"), provenance.get("member_name"), provenance.get("archive_sha256"))
    if any(value is None for value in key):
        raise QueryError("record-detail", "row provenance lacks the archive identity fields (source_archive/member_name/archive_sha256)")
    matches = [
        record
        for record in manifest_records
        if (record.get("file_name"), record.get("member_name"), record.get("archive_sha256_d01")) == key
    ]
    if not matches:
        raise QueryError("record-detail", "row provenance does not identify a published INPUT_MANIFEST archive (identity inconsistency)")
    if len(matches) > 1:
        raise QueryError("record-detail", "row provenance is ambiguous: %d INPUT_MANIFEST records match %s" % (len(matches), key))
    record = matches[0]
    if record.get("engine_family") != row.get("format_family"):
        raise QueryError(
            "record-detail",
            "row format_family %r != INPUT_MANIFEST engine_family %r (inconsistent identity)"
            % (row.get("format_family"), record.get("engine_family")),
        )
    return record


def _reconciliation_for_archive(records: list, archive: dict) -> list:
    """The member-scoped reconciliation records applicable to one archive
    (as published, in file order; empty when none apply)."""
    applied = []
    for record in records:
        scope = record.get("input_identity")
        if not isinstance(scope, dict) or scope.get("scope") != "member":
            continue
        if scope.get("root") == archive.get("root") and scope.get("relative_path") == archive.get("relative_path"):
            applied.append(record)
    return applied


def query_record_detail(
    baseline: Baseline,
    index: dict,
    source_file: str,
    source_line_number: int,
) -> dict:
    """Q7 record detail (D16-10 Q7).

    ``source_file`` is the row file exactly as served in the Q2/Q3 ``serving``
    envelope; ``source_line_number`` is the row's canonical D05 §8 field.
    Returns a document shaped for canonical-JSON serving:

    * ``row`` — the selected canonical row exactly as Q2/Q3 serve rows
      (as-published values, D05 §8 provenance block, Q7 serving envelope,
      ``raw_line`` excluded);
    * ``archive`` — the applicable INPUT_MANIFEST record, as published;
    * ``reconciliation`` — the reconciliation records applicable to that
      archive (as published, in file order; ``[]`` when none apply).

    Read-only; deterministic; fail closed with no partial output.
    """
    if not isinstance(index, dict):
        raise QueryError("record-detail", "index must be a document")
    if not isinstance(source_file, str) or not source_file:
        raise QueryError("record-input", "source_file must be a non-empty string (serving.source_file)")
    if not isinstance(source_line_number, int) or isinstance(source_line_number, bool) or source_line_number < 1:
        raise QueryError("record-input", "source_line_number must be a positive integer (the row's canonical source_line_number)")

    row = _load_row(baseline, index, source_file, source_line_number)
    archive = _archive_for_row(row, parse_input_manifest(baseline))
    reconciliation = _reconciliation_for_archive(parse_reconciliation(baseline), archive)

    meta = index["files"][source_file]
    served = {key: value for key, value in row.items() if key != "raw_line"}
    served["serving"] = {
        "trading_symbol": observed_trading_symbol(row),
        "query": RECORD_DETAIL_QUERY_ID,
        "source_file": source_file,
        "source_file_family": meta.get("family"),
        "source_file_year": meta.get("year"),
        "source_line_number": source_line_number,
    }
    return {
        "query": RECORD_DETAIL_QUERY_ID,
        "row": served,
        "archive": archive,
        "reconciliation": reconciliation,
    }
