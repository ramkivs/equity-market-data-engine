# B1 final closure — local single-owner scope

This record supersedes the open-status conclusion of the earlier B1 follow-up
for the proportional, personal-laptop scope. Existing implementation history
and evidence are retained.

## Safeguards

The UI validates the package, index, saved-query and history roots together
before startup and before operations. CLI commands can supply the four global
`--root-*` options to obtain the same pairwise checks. Standalone root-only
writers reject a package ancestor and reject another existing store at their
root or an ancestor. These checks do not guess unspecified root locations.
Callers using standalone APIs or CLI without a complete configuration are
responsible for selecting separate roots; a root-only call cannot detect every
unprovided, as-yet-empty or descendant root. Use the four-root configuration
when checking an entire layout.

On supported POSIX systems the common state publisher creates and replaces each
file relative to an open directory descriptor, and detects directory replacement
around publication. Other platforms retain same-directory temporary-file and
atomic replacement behavior. These checks are proportional safeguards, not a
transactional defense against a process deliberately modifying directories at
precisely the same time. Windows drive, case, junction and file-replacement
behavior remains for B6; no Windows result is claimed here.

Index, saved-query and history formats remain 1.2, 1.0 and 1.0. The document
and its digest are two separate atomic replacements, not a transaction. An
interrupted pair fails digest validation rather than being silently accepted.
The UI can rebuild derived index state from the baseline; it does not rebuild or
delete user-owned saved queries or history. If a user store pair is interrupted,
preserve both files and restore from a known-good backup or perform an explicit
user-directed recovery; no automatic recovery or guaranteed rollback is claimed.

## Validation

Linux sandbox, synthetic packages and disposable state:

* `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -t .`
  — 919 tests, OK, 14 real-M2 gated skips; existing ResourceWarnings were emitted.
* B1 targeted tests cover all root pairs, existing conflicting stores, aliases,
  directory replacement, POSIX descriptor-anchored publication, interrupted index
  and user-store writes, stale/corrupt index recovery and saved/history retention.
* A real UI subprocess started from a directory outside the repository using a
  synthetic package and existing index; its ready result was observed and the
  package, index and user stores remained byte-identical and state mtimes unchanged.

The Windows M2 package was not accessed, regenerated or modified by this work;
its current bytes were not independently reverified. No historical re-ingestion,
qualification, B2–B5 or B7 operation was performed.
