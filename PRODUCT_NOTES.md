# Product notes — ebrium

Standalone product tree for https://github.com/andrewsipe/ebrium

## Origin

Consolidated from monorepo `FontMetricsNormalizer/` (package was already named `ebrium`).
FontCore is vendored (console + collector + sorter + CLI help); no submodule.

## Done

- Standalone installable package with GitHub install paths
- Vendored FontCore subset
- FontFixer-style `--help` (`FontCore.core_cli_help` + `ebrium.cli_parser`)
- Consolidated argument surface (v2.0.0, breaking):
  - `--family`/`--superfamily`/`--individual`/`--safe-max` → single
    `--grouping {family, family-safe-max, superfamily, individual}`.
    `--safe-max` was always routed through `group_by_family()` in
    `grouping.py`, never a true fifth axis, so it's now a named family
    variant instead of a sibling flag.
  - `--force-baseline`/`--safe-hhea` → single
    `--line-box {auto, force-baseline, safe-hhea}`. `planning.py` already
    made these mutually exclusive at runtime (`force_hhea` short-circuits
    `maybe_apply_force_family_baseline`); the parser now enforces it
    instead of silently overriding.
  - `--force-baseline-from`/`--force-baseline-main-cluster` renamed to
    `--line-box-from`/`--line-box-main-cluster` (read as belonging to
    `--line-box`).
  - `cli_parser.finalize_args()` maps the new choice values back onto the
    original attribute names (`grouping_mode`, `force_baseline`,
    `safe_hhea`), so `validation.py`/`planning.py`/`cli.py` needed no
    other changes.

## Known behavior (documented in `--help` notes)

- Even `-n` / `--report` write `.metrics_checkpoint.json` in the **current** directory
- `--combine` is ignored with `--grouping individual` (`validate_args` warns)
- Exit code `2` is used both for “no measurable fonts” and by argparse for bad args

## Deferred

1. Optional: skip checkpoint writes in dry-run / report / probe modes
2. Tests / fixtures
3. Optional split of large `planning.py`
4. Archive or redirect old `FontMetricsNormalizer` GitHub remote when ready
5. Remove `FontMetricsNormalizer/` from monorepo + PushCore when leaving workspace
