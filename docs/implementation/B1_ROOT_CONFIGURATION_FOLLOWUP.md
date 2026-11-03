# B1 root configuration follow-up

Starting point: `6f98a0e4fe5d18bbf94d7451e3dc6c5910c1cd37` on
`arena/215cb93c-nse-historical-data-engine`, matching its remote ref.

`RootConfiguration` checks all six root pairs, remembers resolved paths and the
identities of existing directories and their ancestors, and fails closed if a
configured alias is retargeted or a remembered directory is replaced/disappears.
The UI constructs it before opening the baseline and index initialization, and
reuses it before adapter reads and writes, including direct UiApi calls. This
check is repeated inside the UI mutation lock. A caller can pass the same
configuration explicitly to UiApi; mismatched arguments are refused.

CLI users may supply all four global options before the command:
`--root-package`, `--root-state`, `--root-saved`, and `--root-history`. The CLI
rejects partial configurations, overlapping roots, and operation flags that do
not match the configuration before invoking the command. Existing CLI command
forms remain usable for compatibility, but they cannot provide this four-root
assurance. The low-level direct serving functions likewise retain their original
root-only interfaces. Therefore **B1's requirement that all entry points use the
same four-root configuration is not closed**; making the configuration mandatory
across those interfaces, with an explicit compatibility transition and appropriate
regressions, remains necessary.

Identity and alias rechecks narrow accidental substitution risks, but are not
atomic with filesystem operations. They do not prevent a concurrent process from
swapping a directory after a check. File-handle-relative, no-follow operations or
another demonstrably safe cross-platform strategy would be needed to establish
that stronger guarantee. Windows junction, case and filesystem behavior remains
pending B6; Linux results do not establish it.

Validation in the Linux sandbox: targeted `unittest` execution of
`test_b1_root_configuration`, `test_b1_state_safety`, `test_ui_api`,
`test_ui_http`, `test_ui_boundary`, `test_serving_baseline`, `test_serving_query`,
`test_serving_saved`, `test_serving_history`, `test_serving_archive`, and
`test_serving_qualification`: **246 tests passed**. Tests used synthetic temporary
packages and state. The Windows M2 package was not accessed, modified or verified.
The persisted formats were not changed.
