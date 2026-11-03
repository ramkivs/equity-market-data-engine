"""Q8 data-quality views (D16-10 Q8) — flag censuses, quarantine, unresolved
state, reconciliation aggregates, and the explicit D21 CHANGED absence.

Contract (D16-10 Q8; D16-07; D21 §14; D22 §§5A/6; D23 §§9-10/17(a)):

* **Flag census** — derived in the class-(4) index build pass (format
  ``serving-index/1.2``) from the canonical rows' governed ``flags[].name``
  fields (D05 §5; no flag gates anything — ``GATING_FLAG_NAMES`` is
  deliberately empty). The census counts what the rows publish; it stores no
  row values and no raw text.
* **Quarantine count** — the authoritative ``RUN_RECORD`` ``counts.quarantined``
  (runner-written run record), corroborated by the ``RUN_COMPLETE`` marker's
  ``quarantined``. A missing or non-integer value, or a disagreement between
  the two governed records, fails closed — zero is preserved as zero and a
  missing value is never substituted with zero.
* **Unresolved-state records** — ``w2/unresolved.jsonl`` (runner-written,
  class-(3) provenance/evidence, "never resolved") is parsed **only when
  present and valid**. An absent file is a legitimate state meaning no
  unresolved records (served as ``present: false`` with an empty list — never
  an error, never fabricated). A present file with an unparseable line, a
  line that is not a record, or a record lacking its ``kind`` field fails
  closed. The runner revision that writes the file (fingerprint-pinned in the
  package ``RUN_RECORD``) publishes exactly one stateless record kind — the
  terminal ``cross-era-boundary-residual`` record (see
  ``tools/i4_runner/i4_runner.py``, ``_unresolved_records``); its stateless
  form is the published schema and is served as published. Every other
  record carries a ``state`` field, which must be a string when present.
  Records are served as published, in file order.
* **Reconciliation aggregates** — the package's ``RECONCILIATION.jsonl`` is
  parsed with the shared D31 parser (runner's 14-field schema, as published)
  and aggregated by ``result`` and by ``tier`` (the governed
  match/divergence/not-comparable/observed and A/G/C/E semantics). When the
  ``RUN_COMPLETE`` marker carries its own ``reconciliation`` block (the runner
  writes one), the re-computed aggregates must agree with it — disagreement
  is a package inconsistency and fails closed. Historical findings are never
  reinterpreted or rewritten.
* **D21 CHANGED findings** — the class-(3) registry does not exist in the
  M2-only first release (D21; D22 §6). CHANGED findings are represented as
  explicitly absent with the same ``absent-in-m2-only-release`` status the Q9
  registry representation uses, and an empty findings list. No CHANGED finding
  is ever fabricated and no D21 resolution machinery is implemented.

Fail-closed: every contract violation above raises before any partial output
is produced. Read-only: the query opens at most ``w2/unresolved.jsonl`` and
``RECONCILIATION.jsonl`` (the row files are read only by the index build); it
writes nothing and produces no serving state.
"""

from __future__ import annotations

import json
import os
from typing import Tuple

from .archive import REGISTRY_ABSENT
from .baseline import Baseline
from .detail import parse_reconciliation
from .query import QueryError

DATA_QUALITY_QUERY_ID = "Q8-data-quality"

UNRESOLVED = "w2/unresolved.jsonl"

# The runner-published record kind that carries no ``state`` field: the
# terminal cross-era-boundary-residual record appended last by
# ``_unresolved_records`` (tools/i4_runner/i4_runner.py). Its stateless form
# is the published schema of the qualified package (canonical data, never
# reinterpreted); every other published kind carries a string state.
CROSS_ERA_RESIDUAL = "cross-era-boundary-residual"


def _flag_census(index: dict) -> dict:
    census = index.get("flag_census")
    if not isinstance(census, dict):
        raise QueryError("data-quality", "index without a flag_census block (build an index of the supported format)")
    for name, count in census.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise QueryError("data-quality", "index flag_census holds a non-count value for %r" % name)
    return census


def _quarantine_count(baseline: Baseline) -> int:
    """The governed quarantined-row count, cross-checked between the two
    authoritative package records (fail closed; zero preserved as zero)."""
    run_record = baseline.run_record if isinstance(baseline.run_record, dict) else {}
    counts = run_record.get("counts")
    if not isinstance(counts, dict):
        raise QueryError("quarantine-count", "RUN_RECORD without a counts block")
    quarantined = counts.get("quarantined")
    if not isinstance(quarantined, int) or isinstance(quarantined, bool):
        raise QueryError("quarantine-count", "RUN_RECORD counts.quarantined missing or not an integer")
    marker = baseline.marker if isinstance(baseline.marker, dict) else {}
    marker_quarantined = marker.get("quarantined")
    if not isinstance(marker_quarantined, int) or isinstance(marker_quarantined, bool):
        raise QueryError("quarantine-count", "RUN_COMPLETE marker without an integer quarantined count")
    if marker_quarantined != quarantined:
        raise QueryError(
            "quarantine-count",
            "RUN_COMPLETE quarantined %d != RUN_RECORD counts.quarantined %d (inconsistent package records)"
            % (marker_quarantined, quarantined),
        )
    return quarantined


def parse_unresolved(baseline: Baseline) -> list:
    """Parse ``w2/unresolved.jsonl`` when present; absence is a legitimate
    no-records state. Present-but-malformed data fails closed.

    Validation matches the runner-published schema (the package is canonical
    and never reinterpreted): every line must be a JSON record with a
    non-empty string ``kind``; records of the published kinds that carry a
    ``state`` must carry a string ``state``; the terminal
    ``cross-era-boundary-residual`` record is published without a ``state``
    (a non-string state on it is still malformed and fails closed)."""
    path = baseline.path(UNRESOLVED)
    if not os.path.isfile(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise QueryError("unresolved-scan", "unparseable w2/unresolved.jsonl line %d: %s" % (line_number, exc))
            if not isinstance(record, dict):
                raise QueryError("unresolved-scan", "w2/unresolved.jsonl line %d is not a record" % line_number)
            kind = record.get("kind")
            if not isinstance(kind, str) or not kind:
                raise QueryError("unresolved-scan", "w2/unresolved.jsonl line %d without a kind" % line_number)
            if kind == CROSS_ERA_RESIDUAL:
                # published stateless form; a present-but-non-string state is malformed
                # (an explicit JSON null counts as present)
                if "state" in record and not isinstance(record["state"], str):
                    raise QueryError("unresolved-scan", "w2/unresolved.jsonl line %d with a non-string state" % line_number)
            state = record.get("state")
            if kind != CROSS_ERA_RESIDUAL and not isinstance(state, str):
                raise QueryError("unresolved-scan", "w2/unresolved.jsonl line %d without a state" % line_number)
            records.append(record)
    return records


def _reconciliation_aggregates(baseline: Baseline) -> Tuple[int, dict, dict]:
    """Re-compute the reconciliation aggregates from the as-published records
    (D31 parser) and corroborate them against the completion marker when the
    marker carries its own block (fail closed on disagreement)."""
    records = parse_reconciliation(baseline)
    by_result = {}
    by_tier = {}
    for record in records:
        result = record.get("result")
        tier = record.get("tier")
        by_result[result] = by_result.get(result, 0) + 1
        by_tier[tier] = by_tier.get(tier, 0) + 1
    marker = baseline.marker if isinstance(baseline.marker, dict) else {}
    marker_recon = marker.get("reconciliation")
    if isinstance(marker_recon, dict):
        marker_by_result = marker_recon.get("by_result")
        if marker_by_result is not None and marker_by_result != by_result:
            raise QueryError(
                "reconciliation-aggregate",
                "re-computed by_result %r != RUN_COMPLETE marker by_result %r (inconsistent package records)"
                % (by_result, marker_by_result),
            )
        marker_by_tier = marker_recon.get("by_tier")
        if marker_by_tier is not None and marker_by_tier != by_tier:
            raise QueryError(
                "reconciliation-aggregate",
                "re-computed by_tier %r != RUN_COMPLETE marker by_tier %r (inconsistent package records)"
                % (by_tier, marker_by_tier),
            )
        marker_records = marker_recon.get("records")
        if marker_records is not None and marker_records != len(records):
            raise QueryError(
                "reconciliation-aggregate",
                "parsed record count %d != RUN_COMPLETE marker records %r (inconsistent package records)"
                % (len(records), marker_records),
            )
    return len(records), by_result, by_tier


def query_data_quality(baseline: Baseline, index: dict) -> dict:
    """Q8 data-quality view (D16-10 Q8).

    ``index`` is the class-(4) index document (serving-index/1.2, which
    carries the flag census from the deterministic build pass). Returns a
    document shaped for canonical-JSON serving:

    * ``flag_census`` — governed flag name -> number of rows carrying it
      (deterministic; ``{}`` when no row carries a flag);
    * ``quarantine`` — the governed quarantined-row count (cross-checked);
    * ``unresolved`` — the ``w2/unresolved.jsonl`` state: ``present``,
      ``record_count``, and the as-published ``records`` (``[]`` when the file
      is absent — a legitimate no-records state);
    * ``reconciliation`` — ``record_count`` plus aggregates ``by_result`` and
      ``by_tier`` (as-published values; corroborated against the marker);
    * ``changed`` — the explicit D21 CHANGED-findings absence (the class-(3)
      registry is absent in the M2-only release; findings are never
      fabricated).

    Read-only; deterministic; fail closed with no partial output.
    """
    if not isinstance(baseline, Baseline):
        raise QueryError("data-quality", "baseline must be an opened, verified baseline handle")
    if not isinstance(index, dict):
        raise QueryError("data-quality", "index must be a document")
    census = _flag_census(index)
    quarantined = _quarantine_count(baseline)
    unresolved = parse_unresolved(baseline)
    record_count, by_result, by_tier = _reconciliation_aggregates(baseline)
    changed = dict(REGISTRY_ABSENT)
    changed["findings"] = []
    changed["note"] = (
        "D21 CHANGED findings require the class-(3) registry, which does not exist in the "
        "M2-only release (D21; D22 §6); they are explicitly absent and never fabricated"
    )
    return {
        "query": DATA_QUALITY_QUERY_ID,
        "flag_census": census,
        "quarantine": {"count": quarantined},
        "unresolved": {
            "present": bool(unresolved),
            "record_count": len(unresolved),
            "records": unresolved,
        },
        "reconciliation": {
            "record_count": record_count,
            "by_result": by_result,
            "by_tier": by_tier,
        },
        "changed": changed,
    }
