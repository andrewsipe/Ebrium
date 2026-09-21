# Changelog

## [2.1.0] - 2026-09-21

### Changed (breaking)
- Folded `--force-baseline-main-cluster` into `--line-box` as a fourth
  choice, `force-baseline-main-cluster`. It never had a value of its own —
  it only ever narrowed which font `--force-baseline` uses as a reference
  — so it reads better as a mode than a sibling flag (same reasoning as
  folding `--safe-max` into `--grouping` in 2.0.0)
- `--line-box-from PATH_OR_GLOB` now implies `--line-box force-baseline`
  when `--line-box` is left at its default (`auto`), instead of silently
  doing nothing until both flags were passed together

### Added
- `--help` now prints the `--grouping modes` and `--line-box modes` tables
  immediately after their own argument group instead of only at the very
  end, via a new `inline` hook on `RichHelp` and a per-group
  `HelpFormatter` pass in `FontCore.core_cli_help`

## [2.0.0] - 2026-09-21

### Changed (breaking)
- Consolidated the grouping-mode flags into one choice argument:
  `--family`/`--superfamily`/`--individual`/`--safe-max` are gone; use
  `--grouping {family, family-safe-max, superfamily, individual}`
  (default unchanged: `family`)
- Consolidated the line-box flags into one choice argument:
  `--force-baseline`/`--safe-hhea` are gone; use
  `--line-box {auto, force-baseline, safe-hhea}` (default unchanged: `auto`).
  These were already mutually exclusive at runtime (`--safe-hhea` silently
  overrode `--force-baseline`); the parser now enforces that instead of
  hiding it.
- Renamed `--force-baseline-from` → `--line-box-from` and
  `--force-baseline-main-cluster` → `--line-box-main-cluster` to read as
  sub-options of `--line-box`
- `--help` gained `--grouping modes` and `--line-box modes` footer tables
  explaining each choice (via new `FontCore.core_cli_help.choices_section`)

## [1.0.1] - 2026-09-21

### Changed
- FontFixer-style `--help`: grouped options, safety panel, examples, notes, exit codes
- Shared `FontCore.core_cli_help`; parser lives in `ebrium.cli_parser`
- `--safe-max` is a real mutually exclusive grouping-mode flag
- One-line option help; interaction rules moved to notes footer
- Pinned `prog=ebrium`, hand-written usage, `--version`

## [1.0.0] - 2026-09-21

### Added
- Initial standalone ebrium package (from FontMetricsNormalizer)
- Vendored FontCore subset for GitHub-installable packaging
