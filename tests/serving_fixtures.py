"""Test-only fixture package builder for the D24 serving slice.

Builds a small, layout-conformant run package using the repository's own engine
(``nse_engine.build_canonical``) so that fixture rows are byte-exact canonical rows
(D05 schema, real tool fingerprint, fixed run id — no clock, no randomness, no
environment value). The member bytes exist only in memory; the package retains the
same artifact classes the I4 runner retains (rows / evidence / metadata / manifest /
marker) and nothing else.

These packages are SYNTHETIC TEST DATA: they exercise the serving code paths (identity
verification, index determinism, query semantics, rebuild, fail-closed behaviour) and
are NEVER represented as the qualified M2 baseline or as evidence of integration with
it (D24 record, §13; D23 closure item 2 is met only by the real-package run).
"""

from __future__ import annotations

import hashlib
import os
from typing import Dict, List, Tuple

from tests import support  # noqa: E402  (adds SRC_DIR to sys.path)

from nse_engine import (  # noqa: E402
    DEFAULT_CONFIG,
    SourceDescriptor,
    build_canonical,
    canonical_json,
    contract,
    evidence_json,
    rows_jsonl,
    tool_fingerprint,
)
from nse_engine.identity import AssociationAccumulator  # noqa: E402
from nse_engine.provenance import sha256_bytes  # noqa: E402
from serving.baseline import BaselineSpec, PACKAGE_MANIFEST, COMPLETION_MARKER  # noqa: E402

FIXTURE_RUN_ID = "D24-FIXTURE-RUN"

LEGACY_HEADER = "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN"
UDIFF_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
    "FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,"
    "LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,"
    "TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4"
)

#: member_name -> (family, year, expected_source_date, body lines, expected canonical rows)
#
# ISIN policy: base rows carry ISO 6166 mod-10 VALID ISINs, so the only
# flagged rows in the fixture are the two deliberate data-quality rows
# (TCS 2016-01-04: failing check digit; TCS 2016-01-05: invalid length) and
# WIPRO's blank ISIN (validity BLANK — no flag, D05 §5).
MEMBERS: Dict[str, Tuple[str, str, str, List[str]]] = {
    "fix-leg-2016-01-04.csv": (
        contract.FAMILY_LEGACY,
        "2016",
        "2016-01-04",
        [
            "RELIANCE,EQ,1000.00,1050.00,990.00,1040.00,1039.50,1000.00,1200000,1250000000.00,04-JAN-2016,8500,INE002A01018",
            # TCS with a deliberately defective ISIN (fails the ISO 6166 mod-10
            # check digit) — exercises the governed isin_invalid_checkdigit flag
            # (D05 §5; informational, never gating) for the Q8 flag census.
            "TCS,EQ,3500.00,3560.00,3480.00,3545.00,3540.00,3500.00,450000,1596250000.00,04-JAN-2016,3200,INE000000006",
            "WIPRO,EQ,1200.00,1230.00,1195.00,1225.00,1220.00,1200.00,80000,98000000.00,04-JAN-2016,1500,",
        ],
        3,
    ),
    "fix-leg-2016-01-05.csv": (
        contract.FAMILY_LEGACY,
        "2016",
        "2016-01-05",
        [
            "RELIANCE,EQ,1040.00,1060.00,1030.00,1055.00,1050.00,1039.50,1300000,1371500000.00,05-JAN-2016,9100,INE002A01018",
            # TCS with a deliberately defective ISIN (invalid length after trim)
            # — exercises the governed isin_invalid_length flag (D05 §5) for the
            # Q8 flag census.
            "TCS,EQ,3545.00,3600.00,3530.00,3590.00,3585.00,3540.00,480000,1719600000.00,05-JAN-2016,3400,INE123",
        ],
        2,
    ),
    "fix-leg-2017-02-06.csv": (
        contract.FAMILY_LEGACY,
        "2017",
        "2017-02-06",
        [
            "RELIANCE,EQ,2500.00,2540.00,2480.00,2535.00,2530.00,2500.00,900000,2281500000.00,06-FEB-2017,7600,INE002A01018",
            "INFY,EQ,1100.00,1120.00,1090.00,1115.00,1110.00,1100.00,250000,278750000.00,06-FEB-2017,2100,INE009A01021",
        ],
        2,
    ),
    "fix-udf-2024-03-05.csv": (
        contract.FAMILY_UDIFF,
        "2024",
        "2024-03-05",
        [
            "2024-03-05,2024-03-05,CM,NSE,STK,500325,INE002A01018,RELIANCE,EQ,,,,,"
            "RELIANCE INDUSTRIES LTD,1010.00,1035.00,1005.00,1030.00,1028.50,1008.00,,"
            "1029.00,,,1500000,1543500000.00,11200,F1,2,,,,,",
            "2024-03-05,2024-03-05,CM,NSE,STK,500304,INE467B01029,TCS,EQ,,,,,"
            "TATA CONSULTANCY SERVICES LTD,3560.00,3610.00,3550.00,3600.00,3595.00,3555.00,,"
            "3605.00,,,470000,1693850000.00,3350,F1,10,,,,,",
        ],
        2,
    ),
}

EXPECTED_TOTAL_ROWS = 9
EXPECTED_MEMBERS = 4
EXPECTED_PARTITIONS = 3


def _member_bytes(member_name: str) -> bytes:
    family, _year, _date, lines, _expected_rows = MEMBERS[member_name]
    header = LEGACY_HEADER if family == contract.FAMILY_LEGACY else UDIFF_HEADER
    # CRLF endings, like the real bhavcopy members (raw bytes preserved; the engine
    # records both raw and LF-normalized hashes per D05 §9.2).
    text = "\r\n".join([header] + list(lines)) + "\r\n"
    return text.encode("utf-8")


def _write_text(root: str, relative: str, text: str) -> None:
    path = os.path.join(root, relative.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _module_sha256() -> str:
    path = os.path.abspath(__file__)
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _reconciliation_record(root: str, member_name: str, expected_date: str, check: str, expected, observed, note: str) -> dict:
    """One fixture reconciliation record in the runner's shared 14-field schema
    (tools/i4_runner/i4_reconcile.make_record is authoritative). Tier E:
    evidence-only, non-gating, member-scoped — the fixture has no governed
    counterpart, and the record says exactly that. The scope mirrors
    i4_reconcile.member_scope with the fixture's own identity values.
    """
    match = expected == observed
    return {
        "tier": "E",
        "tier_description": "evidence-only observation (non-gating; no governing counterpart)",
        "check": check,
        "input_identity": {
            "scope": "member",
            "root": root,
            "relative_path": member_name,
            "file_name": member_name,
            "member_name": member_name,
            "date_from_filename": expected_date,
        },
        "comparison_basis": "d24 synthetic fixture (never the M2 corpus)",
        "governing_definition": "fixture-declared expected value (synthetic; no governed counterpart)",
        "expected": expected,
        "observed": observed,
        "delta": (observed - expected) if match else None,
        "result": "match" if match else "divergence",
        "disposition": "non-gating",
        "unresolved_state": None,
        "note": note,
    }


def build_fixture_package(out_dir: str) -> dict:
    """Build the fixture package into ``out_dir`` (created if absent).

    Returns the pinned identity facts (a :class:`BaselineSpec` plus diagnostics).
    Deterministic: two builds yield byte-identical packages.
    """
    os.makedirs(out_dir, exist_ok=True)
    member_sha256 = {name: sha256_bytes(_member_bytes(name)) for name in MEMBERS}
    archive_set_digest = hashlib.sha256(
        b"".join(member_sha256[name].encode("ascii") for name in sorted(MEMBERS))
    ).hexdigest()

    input_manifest_lines = []
    input_manifest_records = []
    reconciliation_lines = []
    partition_files: Dict[str, List[str]] = {}
    rows_total = 0
    # Q5 source (w2/associations.jsonl): the engine's own W2 identity output over the
    # fixture's canonical rows — the same single accumulation the runner performs
    # (per member, in build order; D05 §3.2/§3.3). The engine computes every
    # document: no hand-crafted identity, no invented relationship (D23 §10).
    association_acc = AssociationAccumulator()
    for sequence, member_name in enumerate(sorted(MEMBERS), start=1):
        family, year, expected_date, lines, expected_rows = MEMBERS[member_name]
        data = _member_bytes(member_name)
        source = SourceDescriptor(
            source_archive=member_name,
            member_name=member_name,
            archive_sha256=member_sha256[member_name],
            archive_sha256_basis="computed-fixture-member-bytes",
            expected_source_date=expected_date,
            run_id=FIXTURE_RUN_ID,
        )
        build = build_canonical(data, source)
        if build.quarantined:
            raise AssertionError("fixture member produced quarantined rows: %s" % member_name)
        rows_total += len(build.rows)
        association_acc.add_security_rows(build.rows)
        partition = "%s/%s" % (family, year)
        rows_relative = "partitions/%s/rows/%s.rows.jsonl" % (partition, member_name)
        evidence_relative = "partitions/%s/evidence/%s.evidence.json" % (partition, member_name)
        _write_text(out_dir, rows_relative, rows_jsonl(build.rows))
        _write_text(out_dir, evidence_relative, evidence_json(build))
        partition_files.setdefault(partition, []).extend([rows_relative, evidence_relative])
        # Runner-schema INPUT_MANIFEST record (tools/i4_runner/i4_runner.py is the
        # package owner). Synthetic but honest: the archive digests are computed
        # from the fixture member bytes, and the basis says exactly that — never
        # "D01-inventory" (the fixture has no D01 inventory).
        report = build.parse.report
        root = "LEGACY" if family == contract.FAMILY_LEGACY else "UDIFF"
        manifest_record = {
            "sequence": sequence,
            "root": root,
            "relative_path": member_name,
            "file_name": member_name,
            "member_name": member_name,
            "date_from_filename": expected_date,
            "detected_format": root,
            "engine_family": report.format_family,
            "partition": partition,
            "archive_sha256_d01": member_sha256[member_name],
            "archive_sha256_basis": "computed-fixture-member-bytes",
            "archive_sha256_observed_raw_bytes": member_sha256[member_name],
            "member_sha256_raw_bytes": report.member_sha256_raw_bytes,
            "member_sha256_lf_text": report.member_sha256_lf_text,
            "member_size_bytes": report.member_size_bytes,
            "header_physical_width": report.header_physical_width,
            "header_tolerance_applied": report.header_tolerance_applied,
            "data_lines": report.data_lines,
            "rows": len(build.rows),
            "quarantined": report.quarantined,
        }
        input_manifest_records.append(manifest_record)
        input_manifest_lines.append(canonical_json(manifest_record) + "\n")
        # Runner-schema reconciliation records (see _reconciliation_record). The
        # fixture declares expected values (its own construction intent) and
        # corroborates them against the engine's observation — honest Tier E
        # evidence-only records, never a claim of governed checks. The udiff
        # member (sequence == EXPECTED_MEMBERS) deliberately carries NO
        # reconciliation records: an archive with none is a valid state.
        if len(build.rows) != expected_rows:
            raise AssertionError("fixture member row count diverged from its declaration: %s" % member_name)
        if sequence < EXPECTED_MEMBERS:
            reconciliation_records = [
                _reconciliation_record(
                    root,
                    member_name,
                    expected_date,
                    "fixture_row_count_corroboration",
                    expected_rows,
                    len(build.rows),
                    "d24 fixture: no divergence (synthetic)",
                )
            ]
            if sequence == 1:
                reconciliation_records.append(
                    _reconciliation_record(
                        root,
                        member_name,
                        expected_date,
                        "fixture_quarantine_census",
                        0,
                        len(build.quarantined),
                        "d24 fixture: no quarantined rows (synthetic)",
                    )
                )
            for record in reconciliation_records:
                reconciliation_lines.append(canonical_json(record) + "\n")

    # Class-(2) W2 output (the runner's own writer convention: canonical_json per
    # line): one SecurityIdentity document per line, in the engine's sorted
    # normalized-ISIN key order. The fixture has no overlay-series rows, so the
    # engine's observed-overlay exclusion excludes nothing here; WIPRO's blank-
    # ISIN rows are unkeyed and produce no document (D05 §3.2).
    associations_lines = []
    for identity_document in association_acc.identity_documents():
        associations_lines.append(canonical_json(identity_document.to_dict()) + "\n")
    _write_text(out_dir, "w2/associations.jsonl", "".join(associations_lines))

    _write_text(out_dir, "INPUT_MANIFEST.jsonl", "".join(input_manifest_lines))

    engine_sha = tool_fingerprint()
    runner_sha = _module_sha256()
    config_fp = DEFAULT_CONFIG.fingerprint()
    _write_text(
        out_dir,
        "GOVERNED_INPUTS.json",
        canonical_json(
            {
                "contract_version": "D24-fixture/1.0",
                "run_id": FIXTURE_RUN_ID,
                "files": sorted(
                    [
                        {
                            "role": "archive",
                            "path_label": record["relative_path"],
                            "sha256": record["archive_sha256_d01"],
                        }
                        for record in input_manifest_records
                    ],
                    key=lambda fact: (fact["role"], fact["path_label"]),
                ),
                "corpus": {
                    "root_labels": ["LEGACY", "UDIFF"],
                    "archive_count": EXPECTED_MEMBERS,
                    "archive_set_digest": archive_set_digest,
                    "hash_basis": "sha256 of member sha256 concatenation sorted by member_name (d24 fixture)",
                },
                "engine_identity": {
                    "spec_version": contract.SPEC_VERSION,
                    "tool_name": contract.TOOL_NAME,
                    "tool_sha256": engine_sha,
                    "tool_version": contract.TOOL_VERSION,
                },
                "runner_identity": {
                    "contract_version": "D24-fixture/1.0",
                    "runner_name": "d24-fixture-builder",
                    "runner_sha256": runner_sha,
                    "runner_version": "d24-fixture-1.0.0",
                },
                "governed_config": DEFAULT_CONFIG.to_dict(),
                "config_fingerprint": config_fp,
                "note": "d24 synthetic fixture (never the M2 corpus)",
            }
        )
        + "\n",
    )
    _write_text(
        out_dir,
        "PREFLIGHT.jsonl",
        canonical_json({"check_id": "PF-FIXTURE", "result": "pass", "detail": "d24 synthetic fixture"}) + "\n",
    )
    _write_text(out_dir, "RECONCILIATION.jsonl", "".join(reconciliation_lines))

    composite = hashlib.sha256(
        canonical_json(
            {
                "archive_set_digest": archive_set_digest,
                "config_fingerprint": config_fp,
                "engine_tool_sha256": engine_sha,
                "run_id": FIXTURE_RUN_ID,
                "runner_sha256": runner_sha,
            }
        ).encode("utf-8")
    ).hexdigest()
    _write_text(
        out_dir,
        "RUN_RECORD.json",
        canonical_json(
            {
                "authority": {"d24_fixture": "synthetic test package (never the M2 corpus)"},
                "boundary": {
                    "network_access": "none",
                    "production": False,
                    "storage_technology": "UNDECIDED (MD-12)",
                },
                "composite_run_identity": composite,
                "config": {"config_fingerprint": config_fp, "spec_version": contract.SPEC_VERSION},
                "contract_version": "D24-fixture/1.0",
                "corpus": {
                    "archive_count": EXPECTED_MEMBERS,
                    "archive_set_digest": archive_set_digest,
                    "partition_definition": {
                        "content_derived": True,
                        "key": "(format_family, calendar year of D01 date_from_filename)",
                    },
                },
                "counts": {"members": EXPECTED_MEMBERS, "quarantined": 0, "rows": rows_total},
                "engine_identity": {
                    "engine_module_count": len(contract.ENGINE_MODULES),
                    "spec_version": contract.SPEC_VERSION,
                    "tool_name": contract.TOOL_NAME,
                    "tool_sha256": engine_sha,
                    "tool_version": contract.TOOL_VERSION,
                },
                "run_id": FIXTURE_RUN_ID,
                "runner_identity": {
                    "contract_version": "D24-fixture/1.0",
                    "runner_name": "d24-fixture-builder",
                    "runner_sha256": runner_sha,
                    "runner_version": "d24-fixture-1.0.0",
                },
            }
        )
        + "\n",
    )

    for partition in sorted(partition_files):
        family, year = partition.split("/")
        lines = []
        for relative in sorted(partition_files[partition]):
            with open(os.path.join(out_dir, relative.replace("/", os.sep)), "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            lines.append("%s  %s\n" % (digest, relative))
        _write_text(out_dir, "manifests/%s_%s.sha256" % (family, year), "".join(lines))

    # package manifest: every retained file except the manifest and the marker
    retained = []
    for dirpath, dirnames, filenames in os.walk(out_dir):
        dirnames.sort()
        for name in sorted(filenames):
            relative = os.path.relpath(os.path.join(dirpath, name), out_dir).replace(os.sep, "/")
            if relative in (PACKAGE_MANIFEST, COMPLETION_MARKER):
                continue
            retained.append(relative)
    manifest_lines = []
    for relative in sorted(retained):
        with open(os.path.join(out_dir, relative.replace("/", os.sep)), "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        manifest_lines.append("%s  %s\n" % (digest, relative))
    manifest_text = "".join(manifest_lines)
    _write_text(out_dir, PACKAGE_MANIFEST, manifest_text)
    manifest_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()

    _write_text(
        out_dir,
        COMPLETION_MARKER,
        canonical_json(
            {
                "contract_version": "D24-fixture/1.0",
                "members": EXPECTED_MEMBERS,
                "note": "d24 synthetic fixture package (never the M2 corpus)",
                "package_manifest_sha256": manifest_digest,
                "partitions": EXPECTED_PARTITIONS,
                "quarantined": 0,
                "reconciliation": {"by_result": {"match": len(reconciliation_lines)}},
                "rows": rows_total,
                "run_id": FIXTURE_RUN_ID,
                "status": "complete",
            }
        )
        + "\n",
    )

    total_bytes = 0
    file_count = 0
    for dirpath, _dirnames, filenames in os.walk(out_dir):
        for name in filenames:
            total_bytes += os.path.getsize(os.path.join(dirpath, name))
            file_count += 1

    spec = BaselineSpec(
        package_name="d24-fixture",
        manifest_sha256=manifest_digest,
        file_count=file_count,
        total_bytes=total_bytes,
        run_id=FIXTURE_RUN_ID,
        composite_run_identity=composite,
        engine_tool_sha256=engine_sha,
        runner_sha256=runner_sha,
        archive_count=EXPECTED_MEMBERS,
    )
    return {
        "spec": spec,
        "manifest_sha256": manifest_digest,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "rows_total": rows_total,
        "engine_tool_sha256": engine_sha,
    }
