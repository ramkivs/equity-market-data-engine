"""I4 first-release UI — the presentation layer (D16-11/D16-12; D23 §17(b)).

Scope (governing contracts prevail over every design reference):

* Presentation and navigation only: the shared shell, the Dashboard, the
  Data Explorer, record detail/provenance display, quality and yearly
  summaries, as-published charts, saved queries (D38) and query history
  (D39).
* Data flows ONLY through the authorized serving boundary: this package
  calls the existing ``serving`` operations (Q1–Q10 via the single
  ``execute_query_definition`` dispatch, D38 ``serving.saved``, D39
  ``serving.history``). It never opens baseline paths itself, never reads
  durable data directly, and introduces no alternate query path (D23
  §18(8)).
* No new processing or engine-control operations are exposed (the
  processing trigger is excluded from the first release; D23 §19 withholds
  raw-content serving, ingestion and DEC-1).
* Rebuildable, stdlib-only, single-user personal hosting (D23 §13/§14);
  deterministic UI-derived outputs (no clock, no randomness).

Non-authoritative design references (verified, byte-recorded; they grant
no authority): ``docs/design/I4_HISTORICAL_DATA_ENGINE_UI_SPEC.md`` and
the two original mockup PNGs under ``evidence/`` (see
``evidence/I4_UI_MOCKUP_REFERENCES.txt`` and the TASK62 implementation
record).
"""
