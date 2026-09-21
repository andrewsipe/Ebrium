# Product notes — ebrium

Standalone product tree for https://github.com/andrewsipe/ebrium

## Origin

Consolidated from monorepo `FontMetricsNormalizer/` (package was already named `ebrium`).
FontCore is vendored (console + collector + sorter + CLI help); no submodule.

## Done

- Standalone installable package with GitHub install paths
- Vendored FontCore subset
- FontFixer-style `--help` (`FontCore.core_cli_help` + `ebrium.cli_parser`)

## Known behavior (documented in `--help` notes)

- Even `-n` / `--report` write `.metrics_checkpoint.json` in the **current** directory
- `--combine` is ignored with `--individual` (`validate_args` warns)
- Exit code `2` is used both for “no measurable fonts” and by argparse for bad args

## Deferred

1. Optional: skip checkpoint writes in dry-run / report / probe modes
2. Tests / fixtures
3. Optional split of large `planning.py`
4. Archive or redirect old `FontMetricsNormalizer` GitHub remote when ready
5. Remove `FontMetricsNormalizer/` from monorepo + PushCore when leaving workspace
