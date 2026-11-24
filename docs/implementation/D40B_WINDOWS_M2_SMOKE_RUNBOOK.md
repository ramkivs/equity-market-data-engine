# D40B — Windows M2 Smoke Verification Runbook (owner execution; Arena handoff)

**Purpose.** Execute the A9 smoke and the M2-dependent legs of A2, A5, A7 and EC-AC-05 against the
physical, I5-qualified package `i4-20261008-M2` on the Windows custody host, and capture the exact
evidence Arena needs to update the acceptance matrix in the Phase B implementation record.

**Status of this document.** Prepared 2026-11-24 (PR #8). Nothing in this runbook proves anything by
itself; acceptance requires the owner to execute it and supply the captured outputs. Until then:
**A9 and the M2 legs of A2/A5/A7/EC-AC-05 = `PENDING OWNER WINDOWS VERIFICATION`.**

**Honesty and custody rules.**

- The M2 package stays on the Windows host; nothing here copies package files anywhere.
- Raw row-level payloads are personal-use NSE data. **Do not commit them to this public repository.**
  The evidence to return to Arena is JSON responses, logs and digests only (list in §12). If you
  explicitly decide to publish an evidence bundle under `evidence/`, that is your decision — record
  it as such; it is not required by this runbook.
- Single-user, personal use only (D40 §1.1). Bind stays `127.0.0.1`; never `0.0.0.0`.
- PowerShell examples assume `C:\M2\i4-20261008-M2` as the package path and `C:\M2state` as the
  state root — **substitute your actual custody paths** everywhere. `python` = the same Python 3 used
  for the I5 qualification on this host; if the `py` launcher is what the host uses, substitute
  `py -3` for `python`.

## 0. Checkout prerequisites

```powershell
cd C:\work\equity-market-data-engine        # your checkout of ramkivs/equity-market-data-engine
git fetch origin
git checkout arena/ddcaa938-equity-market-data-engine   # or main after PR #8 merges
git log --oneline -1
```

- **Expected:** the HEAD line shows the branch tip (`182db91…` or a successor; if PR #8 merged to
  `main`, `origin/main`'s merge commit). Record `git rev-parse HEAD` into `evidence\head.txt`.
- **Failure:** checkout conflict → stop; resolve manually; do not force.

## 1. M2 package and manifest verification (A1/A2)

```powershell
$env:PYTHONPATH = "src"
python -m serving verify --package C:\M2\i4-20261008-M2 --m2 | Tee-Object -FilePath .\verify-pre.txt
"verify exit code: $LASTEXITCODE" | Tee-Object -FilePath .\verify-pre-exitcode.txt
```

- **Expected success:** JSON with `"result": "pass"`, `"verification": "full"`, `"manifest_sha256":
  "e7c7e4c8271f3a1c8ef42d76b926fe048a8997a342c92d89819eecd79e73b9dc"`, `"manifest_entries": 4946`,
  `"total_bytes": 21119807344`, `"run_id": "i4-20261008-M2"`, exit code `0`. (4,946 manifest entries +
  manifest + marker = 4,948 files.)
- **Failure interpretation:** `"result": "fail"` with `verify-07`/`verify-01`/… or exit `2` → the
  package is not the pinned M2 or a file drifted. **Stop. Nothing else in this runbook may run.**
  Capture the JSON; AARENA must see it; no workarounds; do not edit the package.

## 2. Engine and runner revision verification (A1)

```powershell
# 2a. executed revision and tree (commit that produced/qualified the M2 package)
git rev-parse 8ade8372e150e541a52206baa377a02249a308f4^{tree} | Tee-Object -FilePath .\rev-tree.txt
# expect: 8e1557de766d4c952be7261c4f72aa743f81de0b
git cat-file -t 8ade8372e150e541a52206baa377a02249a308f4 | Tee-Object -FilePath .\rev-type.txt   # expect: commit

# 2b. module fingerprints recomputed from this checkout's module bytes (same construction the runner uses)
python -c "import sys; sys.path.insert(0,'.'); import tools.i4_runner.i4_identity as m; print('engine', m.engine_fingerprint()); print('runner', m.runner_fingerprint())" | Tee-Object -FilePath .\rev-fingerprints.txt
```

- **Expected success:** `engine d3269b731008a0d544eaa7e96d6c6b75cf94dfd6ce31d8fb5e1f23fdf10a80e9`
  and `runner f3ebf62488716ea3f4fff76b104760dfee7df45c81af253a4faf352beb624c4a`. (17 engine modules —
  nse-engine w2-1.0.0; 6 runner modules — i4-runner-1.0.0; single executed revision `8ade8372…`,
  tree `8e1557de…`, both fingerprints re-derived and verified from that tree in the Arena session on
  2026-11-24 and recorded in the implementation record.)
- **Note (carried transparently, per D11/D12):** the Windows worktree's recorded `repo_head` for the
  M2 run was `6a60583f…` with the M2 payload applied over the worktree (`repo_status_entries: 65`);
  identity is enforced from the **executed bytes** (the fingerprints above), which `2b` recomputes.
  A CRLF checkout fails this fingerprint check — use an LF checkout (`git config core.autocrlf false`
  or the committed `.gitattributes`).
- **Failure interpretation:** any mismatch → stop; the serving boundary may not be opened against a
  non-M2 identity. Capture outputs; do not patch.

## 3. Class-(4) index build (A5)

```powershell
python -m serving.isin_index build --package C:\M2\i4-20261008-M2 --state C:\M2state | Tee-Object -FilePath .\index-build-a.txt
python -m serving.isin_index info  --package C:\M2\i4-20261008-M2 --state C:\M2state | Tee-Object -FilePath .\index-info-a.txt
Get-Content C:\M2state\serving_isin_index.sha256 | Tee-Object -FilePath .\index-sha-a.txt
```

- **Expected success:** `build` prints `{"built": true, "digest": "<d1>", "counts": {...}}`; `info`
  prints the same `digest` plus `"format": "serving-isin-index/1.0"`, the package identity block
  (manifest `e7c7e4c8…`, `file_count`, `total_bytes`, `run_id "i4-20261008-M2"`) and
  `counts.rows_scanned = 5689949`. `serving_isin_index.sha256` contains `<d1>  serving_isin_index.json`.
  On 5.69M rows this may take a while and must show **zero** warnings about VALID-marked rows
  missing `isin_normalized` (none exist by construction; the builder fails closed if they did).
- **Failure interpretation:** any `IsinIndexError` line, or `rows_scanned != 5689949` → stop;
  capture; do not bypass.

## 4. Independent rebuild and digest comparison (A5)

```powershell
Remove-Item C:\M2state\serving_isin_index.json, C:\M2state\serving_isin_index.sha256
python -m serving.isin_index build --package C:\M2\i4-20261008-M2 --state C:\M2state | Tee-Object -FilePath .\index-build-b.txt
Get-Content C:\M2state\serving_isin_index.sha256 | Tee-Object -FilePath .\index-sha-b.txt
if ((Get-Content .\index-sha-a.txt) -eq (Get-Content .\index-sha-b.txt)) { "INDEX DIGEST MATCH d1==d2" } else { "INDEX DIGEST MISMATCH — STOP" } | Tee-Object .\index-compare.txt
```

- **Expected success:** `digest` identical in `index-build-a.txt` / `index-build-b.txt`;
  `index-sha-a.txt` == `index-sha-b.txt`; `INDEX DIGEST MATCH`.
- **Failure interpretation:** mismatch → A5 fails; the index is not deterministic on your host;
  stop and capture both artifacts.

## 5. Server startup on 127.0.0.1:8614 (EC-AC-01)

```powershell
$env:IIPS_EQUICORE_TRANSPORT_TOKEN = "<one-time token you choose>"
python -m serving.iips_serve --package C:\M2\i4-20261008-M2 --state C:\M2state --port 8614 *>&1 | Tee-Object -FilePath .\server.log
```

- **Expected success:** stderr line `serving iips-equicore-historical/v1 on http://127.0.0.1:8614
  (package i4-20261008-M2, manifest e7c7e4c8…, pid <n>)`; the process keeps running.
- **Failure interpretation:** exit code 2 with `REFUSING TO START: --bind …` → non-loopback bind
  attempted (never expected with these commands). `REFUSING TO START: … verify-07 …` → wrong package
  (see Step 1). `REFUSING TO START: a bearer token is mandatory` → `IIPS_EQUICORE_TRANSPORT_TOKEN`
  not set. Note the env var is **`IIPS_EQUICORE_TRANSPORT_TOKEN`** (this is the approved contract name;
  the retired `IIPS_EQUI_CORE_TOKEN` is not read anywhere).

Leave this process running; open a second PowerShell for steps 6–10.

## 6. Authentication and host enforcement (EC-AC-01)

```powershell
curl.exe -s -o .\health-noauth.json -w "HTTP %{http_code}`n" http://127.0.0.1:8614/v1/health
curl.exe -s -o .\health-wrong.json  -w "HTTP %{http_code}`n" -H "Authorization: Bearer definitely-wrong" http://127.0.0.1:8614/v1/health
curl.exe -s -i -H "Host: 192.0.2.5" -H "Authorization: Bearer $env:IIPS_EQUICORE_TRANSPORT_TOKEN" http://127.0.0.1:8614/v1/health > .\health-badhost.txt
curl.exe -s -D .\health-headers.txt -o .\health-ok.json -w "HTTP %{http_code}`n" -H "Authorization: Bearer $env:IIPS_EQUICORE_TRANSPORT_TOKEN" http://127.0.0.1:8614/v1/health
```

- **Expected success:** `health-noauth.json` and `health-wrong.json` are HTTP `401` bodies
  (`{"contract": "iips-equicore-historical/v1", "error": {"code": "UNAUTHORIZED", …"responseDigest": "…"}}`);
  `health-badhost.txt` shows `403` + `HOST_FORBIDDEN`; `health-headers.txt` shows `Content-Type`,
  `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `X-Response-Digest`, and **no
  `Access-Control-*` header anywhere**; `health-ok.json` HTTP `200`, with `"contract":
  "iips-equicore-historical/v1"`, `"service": "iips-equicore-historical"`, `"package":
  { "manifest_sha256": "e7c7e4c8…", "run_id": "i4-20261008-M2", "archive_count": 2462 }`,
  `"state": { "serving_index": …, "isin_index": … }`, and `"auth": "bearer"`.
- **Failure interpretation:** any other status → record verbatim; EC-AC-01 fails.

## 7. Specimen discovery and flagged-row retrieval (A4/A9) — CORRECTED 2026-11-24

**Why this section was corrected.** The D05 §5 parenthetical "Legacy era: 215,393 rows ≈5.4%"
was produced by the D03 evidence tool's check-digit routine (`tools/d03_fixture_scan/d03_fixtures.py:82-118`),
which evaluates Luhn over `v[1:11]` (dropping the leading country-code character) — not the
governed ISO 6166 check. W1 (the engine that qualified M2, `d3269b73…`) implements ISO 6166 and
finds **zero** invalid check digits on the published 3,554-row sample (W1-DIV-1,
`src/nse_engine/contract.py` `KNOWN_EVIDENCE_DIVERGENCES[0]`; rows.py docstring). The canonical
M2 therefore very likely contains **zero** `INVALID_CHECKDIGIT` rows — which is exactly why the
literal search below returns zero matches. That is the expected package content, not a search
failure and not package corruption. The Q8 census (one pass, engine-computed) decides what the
real flagged population is.

### 7a. Whole-package verdict sweep (one pass, all five literals, no row content printed)

```powershell
@'
import json, os, sys
counts = {k: 0 for k in ("VALID", "BLANK", "INVALID_LEN", "INVALID_PREFIX", "INVALID_CHARSET", "INVALID_CHECKDIGIT")}
flags = 0
for dirpath, _dirnames, filenames in os.walk(r"C:\M2\i4-20261008-M2\partitions"):
    for f in filenames:
        if not f.endswith(".rows.jsonl"):
            continue
        with open(os.path.join(dirpath, f), encoding="utf-8") as h:
            for line in h:
                line = line.strip()
                if not line:
                    continue
                o = json.loads(line)
                v = o.get("isin_validity")
                if v in counts:
                    counts[v] += 1
                flags += sum(1 for fl in (o.get("flags") or []))
print("validity_counts", json.dumps(counts, sort_keys=True))
print("total_flag_entries", flags)
'@ | Set-Content -Encoding utf8 C:\M2state\verdict_census.py
python C:\M2state\verdict_census.py | Tee-Object .\verdict-counts.txt
```

Expected (evidence-informed, not assumed): `VALID ≈ 5,689,948`, `INVALID_LEN = 1`, all other
categories `0`, `total_flag_entries = 1`. **Record the printed counts verbatim — do not edit them.**
If `INVALID_CHECKDIGIT` is anything other than `0`, note it and proceed with 7c using that literal.

### 7b. Authoritative engine-side census (Q8)

```powershell
python -m serving build --package C:\M2\i4-20261008-M2 --state C:\M2state | Tee-Object .\serving-index-build.txt
python -m serving quality --package C:\M2\i4-20261008-M2 --m2 --state C:\M2state | Tee-Object .\q8-quality.json
```

Expected: `q8-quality.json` carries `"flag_census"` with the **engine-computed** counts (likely
`{"isin_invalid_length": 1}` or `{}`), `"quarantine"` with `"count": 0`. Record verbatim. (The
serving index is class-(4) like the ISIN index; both stay outside the package.)

### 7c. Locate the flagged specimen (works for whichever flagged population exists)

```powershell
Get-ChildItem -Recurse -Filter *.rows.jsonl -Path C:\M2\i4-20261008-M2\partitions |
  Select-String -SimpleMatch '"isin_validity":"INVALID_LEN"' | Select-Object -First 3 |
  ForEach-Object { $_.Line } | Tee-Object .\specimen-lines-private.txt
```

From the printed line(s), note exactly: `source_values.listing_symbol`, `source_values.series`,
`business_date`, `isin_normalized`, `flags[].name` (for the INVALID_LEN row: `isin_invalid_length`).
(`Select-String -SimpleMatch` avoids regex escaping issues; if 7a found a nonzero
`INVALID_CHECKDIGIT`, substitute that literal.)

### 7d. Corrected retrieval request (same A4/A9 objective; real flagged population)

```powershell
$spec = @{ symbol = "<listing_symbol from 7c>"; series = "<series from 7c>"; date = "<business_date from 7c>" }
$body = @{ exchange="NSE_EQ"; frequency="1D"; adjustmentMode="RAW_UNADJUSTED"; series=$spec.series; symbol=$spec.symbol; from=$spec.date; to=$spec.date } | ConvertTo-Json -Compress
$body | Set-Content -NoNewline .\bars-body.json
curl.exe -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer $env:IIPS_EQUICORE_TRANSPORT_TOKEN" --data-binary "@.\bars-body.json" -D .\bars-headers.txt -o .\bars-specimen.json -w "HTTP %{http_code}`n" http://127.0.0.1:8614/v1/historical/bars
python -c "import json; m=json.load(open('.\bars-specimen.json',encoding='utf-8')); rows=[r for r in m['rows'] if r['business_date']=='$($spec.date)']; print('rows_on_date', len(rows), 'total', m['total']); [print(json.dumps({k: r.get(k) for k in ('isin_normalized','isin_validity','flags','raw_line')}, ensure_ascii=False)) for r in rows]" | Tee-Object .\specimen-check.txt
```

- **Expected success (A4 objective; honestly scoped to what M2 contains):** HTTP `200`; the
  specimen row is present in `.\bars-specimen.json` **with** `isin_validity` equal to whatever 7a
  reported (`INVALID_LEN` most likely), `flags[]` containing the matching governed name
  (`isin_invalid_length`), `isin_normalized` verbatim, and **no** `raw_line` key. Zero rows
  dropped/de-ranked.
- **A9 as originally worded ("at least one Legacy instrument known to carry an invalid check
  digit") is expected NOT to be satisfiable on this M2** — the governed-ISO-6166 qualification found
  no invalid check digits (W1-DIV-1). If 7a/7b confirm zero `INVALID_CHECKDIGIT`, record Step 7 as
  **A9-UNMET-ON-QUALIFIED-PACKAGE (evidence attached)** or ask Ramki to direct an A9 disposition —
  either way, do **not** report A9 as passed, and do not touch the package or the serving code to
  manufacture a specimen. The fidelity leg (flagged rows served verbatim with flags) is still
  verified end-to-end on the real M2 flagged population, and the automated suite covers
  INVALID_CHECKDIGIT/INVALID_LEN/BLANK fixtures (`test_invalid_checkdigit_and_len_rows_are_served_verbatim`).
- **Failure interpretation:** specimen row missing, flags stripped, or row de-ranked → stop; capture;
  A4 fails. HTTP `400/422` → body fields must be exactly `exchange: NSE_EQ`, `frequency: 1D`,
  `adjustmentMode: RAW_UNADJUSTED`.


## 8. Count parity against the package (A3)

For the same scope as Step 7, also run a wider window that stays inside the corpus and record counts
two ways — the API and a direct package count. Example window (corpus starts 2016-09-20):

```powershell
$wide = @{ exchange="NSE_EQ"; frequency="1D"; adjustmentMode="RAW_UNADJUSTED"; series="EQ"; symbol="<SYMBOL>"; from="2016-09-20"; to="2016-12-31" } | ConvertTo-Json -Compress
curl.exe -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer $env:IIPS_EQUICORE_TRANSPORT_TOKEN" --data-binary $wide -o .\bars-wide.json -w "HTTP %{http_code}`n" http://127.0.0.1:8614/v1/historical/bars
python -c "import json; m=json.load(open('.\\bars-wide.json',encoding='utf-8')); print('total', m['total'], 'returned', m['returnedBarCount'])"
```

Direct package census (keeps custody local). Write a small helper once, then run it:

```powershell
@'
import json, os, sys

sym, date_from, date_to = sys.argv[1], sys.argv[2], sys.argv[3]
n = 0
for dirpath, _dirnames, filenames in os.walk(r"C:\M2\i4-20261008-M2\partitions"):
    for f in filenames:
        if not f.endswith(".rows.jsonl"):
            continue
        for line in open(os.path.join(dirpath, f), encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            v = o.get("source_values") or {}
            family = o.get("format_family")
            symbol = v.get("listing_symbol") if family == "legacy13" else v.get("underlying_symbol")
            day = o.get("business_date") or ""
            if v.get("series") == "EQ" and symbol == sym and date_from <= day <= date_to:
                n += 1
print("package rows", n)
'@ | Set-Content -Encoding utf8 C:\M2state\census.py
python C:\M2state\census.py <SYMBOL> 2016-09-20 2016-12-31
```

- **Expected success:** API `total` equals the package census for the same symbol/series/window
  (or the difference is exactly explained by window bounds — record verbatim). Flags verbatim.
- **Failure:** parity broken → stop; capture.

## 9. Digest and completeness verification (A8/EC-AC-04/EC-AC-05)

```powershell
curl.exe -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer $env:IIPS_EQUICORE_TRANSPORT_TOKEN" --data-binary "@.\bars-body.json" -o .\bars-specimen-2.json -w "HTTP %{http_code}`n" http://127.0.0.1:8614/v1/historical/bars
curl.exe -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer $env:IIPS_EQUICORE_TRANSPORT_TOKEN" --data-binary "@.\bars-body.json" -D .\bars-headers-2.txt -o .\eod-observation.json -w "HTTP %{http_code}`n" http://127.0.0.1:8614/v1/historical/eod-observation
Copy-Item .\bars-specimen.json .\bars-1.json; Copy-Item .\bars-specimen-2.json .\bars-2.json
if (Compare-Object (Get-Content .\bars-1.json) (Get-Content .\bars-2.json)) { "BARS BODY DIFFER — STOP" } else { "bars bodies byte-identical" } | Tee-Object .\bars-identity.txt
curl.exe -s "http://127.0.0.1:8614/v1/calendar?from=2024-11-15&to=2024-11-30" -H "Authorization: Bearer $env:IIPS_EQUICORE_TRANSPORT_TOKEN" -o .\calendar-window.json -w "HTTP %{http_code}`n"
```

- **Expected success:** `BARS bodies byte-identical`; headers on both runs show equal
  `X-Response-Digest`; bodies carry equal `responseDigest`. `eod-observation.json` carries
  `"pinnedGeneration": "PINNED_GENERATION_EOD_SNAPSHOT"` and `"bitemporalKnowledgeAsOf": false`.
  `calendar-window.json` `unexplainedCalendarDates` contains exactly `2024-11-20` for that window
  (the three known M2 unexplained dates are 2024-11-20, 2025-10-20, 2026-01-15 — see D36).

Independent digest recompute (proves `responseDigest`, not just self-consistency):

```powershell
python -c "import json,hashlib; b=json.load(open('.\\eod-observation.json',encoding='utf-8')); d=b.get('responseDigest'); b.pop('responseDigest'); print('responseDigest', d); print('recomputed   ', hashlib.sha256(json.dumps(b,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest())"
```

- **Expected:** the two digests are equal.
- **Completeness (EC-AC-04):** in the chosen window check
  `completeness.tradingDaysWithArchive === completeness.returnedBarCount + completeness.securityAbsentOnTradingDaysCount`
  when `completeness.status == "exact"`; record `unexplainedCalendarDates` / `notRetrievedCalendarDates`
  verbatim from the response. (M2 carries the class-(2) `w2/calendar.jsonl` + `w2/metrics.json`, so
  `exact` is expected; if the response instead reports `calendar-unavailable`, record that verbatim —
  do not treat it as a pass.)

## 10. Final provenance and acceptance evidence capture (A1/A2 close-out)

```powershell
python -m serving verify --package C:\M2\i4-20261008-M2 --m2 | Tee-Object .\verify-post.txt
"exit $LASTEXITCODE" | Tee-Object -FilePath .\verify-post-exitcode.txt
Stop-Process -Id <pid from server.log> -Force   # or Ctrl+C in the server console
Get-ChildItem .\verify-*.txt,.\rev-*.txt,.\index-*.txt,.\bars-*.json,.\eod-observation.json,.\calendar-window.json,.\health-*.json,.\health-headers.txt,.\bars-*.txt | ForEach-Object {
  "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower(), $_.Name
} | Set-Content .\SHA256SUMS.txt
```

- **Expected success:** `verify-post.txt` shows the same `manifest_sha256` (`e7c7e4c8…`) and exit 0 —
  the package is byte-identical before and after serving (A2). `SHA256SUMS.txt` lists every captured
  file.

## 11. Failure-interpretation quick table

| Symptom | Meaning | Disposition |
|---|---|---|
| `verify` → `verify-07` / exit 2 | package not the pinned M2 / identity drift | stop; no serving |
| `verify` passes but fingerprints differ | host checkout not the executed revision (CRLF? wrong tree) | stop; LF checkout |
| index build → `index-scan` | corrupt VALID row marker (defect) | stop; capture; do not patch index |
| rebuilt digest ≠ first digest | nondeterminism | stop; A5 fails |
| 401 without token / 401 with wrong token is **expected** | contract working (EC-AC-01) | record as pass |
| 403 on `Host: 192.0.2.5` is **expected** | loopback-Host contract | record as pass |
| `verdict-counts.txt` shows `INVALID_CHECKDIGIT > 0` | engine census contradicts W1-DIV-1 expectation | unprecedented — stop; capture; report to Arena |
| `verdict-counts.txt` all zero except VALID/INVALID_LEN | expected M2 content (W1-DIV-1) | proceed with INVALID_LEN specimen; A9 as worded UNMET (not passed) |
| `bars` missing the flagged specimen row | A4 failure | stop; capture |
| `calendar-unavailable` | class-(2) calendar pair absent in this M2 | record verbatim; EC-AC-04 not met by this run |
| any `Access-Control-*` header | EC-AC-01 failure | stop |

## 12. Files/outputs the owner must return to Arena

Return (attach to the Arena conversation or the owner-chosen channel — **not** a public commit of raw
row payloads):

1. `head.txt`, `verify-pre.txt`, `verify-pre-exitcode.txt`, `verify-post.txt`, `verify-post-exitcode.txt`
2. `rev-tree.txt`, `rev-type.txt`, `rev-fingerprints.txt`
3. `index-build-a.txt`, `index-info-a.txt`, `index-sha-a.txt`, `index-build-b.txt`, `index-sha-b.txt`, `index-compare.txt`
4. `health-noauth.json`, `health-wrong.json`, `health-badhost.txt`, `health-headers.txt`, `health-ok.json`, `server.log`
5. `verdict-counts.txt`, `serving-index-build.txt`, `q8-quality.json`, `specimen-lines-private.txt` (or redacted), `bars-body.json`, `bars-specimen.json`, `specimen-check.txt`, `bars-specimen-2.json`, `bars-1.json`, `bars-2.json`, `bars-identity.txt`, `bars-wide.json`, `bars-counts.txt`
6. `eod-observation.json`, `bars-headers-2.txt`, `calendar-window.json`, digest-recompute output
7. `SHA256SUMS.txt`

Acceptance is declared only after Arena verifies these against A1–A10 / EC-AC-01..05 and the owner
merges/accepts the updated record on PR #8. Until then: **PENDING OWNER WINDOWS VERIFICATION.**
