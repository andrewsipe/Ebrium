# Changelog

## [3.1.0] - 2026-09-21

### Changed (breaking)
- Consolidated `--assume-script` / `--assume-decorative` / `--assume-unicase` /
  `--assume-uniwidth` into one repeatable flag:
  `-a, --assume TYPE:PATTERN` (e.g. `-a script:'*Swash*'`). A font can still
  match more than one type (script and decorative aren't exclusive), so this
  stays append-style rather than a single-choice flag. Bad types are argparse
  errors. `--exclude-measuring` stays separate — it excludes from calculations
  rather than classifying. `finalize_args` splits `--assume` back into the
  four list attributes `measurements.py` already expects.
- Added short flags where a letter means the same thing in every subcommand
  that exposes it: `-l`/`-t`/`-c`/`-i`/`-e`/`-b`/`-a` for `--letter-height`,
  `--top-margin`, `--combine`, `--ignore-prefix`, `--exclude`, `--line-box`,
  `--assume`. Left long-only: `--max-adjustment`, `--safe-max`,
  `--no-auto-adjust`, `--use-ttx`, `--line-box-from`.

## [3.0.1] - 2026-09-21

### Fixed
- Subcommand usage lines doubled on Python &lt; 3.14
  (`usage: ebrium {individual,...} [options] [PATH ...] individual [options]...`)
  because `add_subparsers()` built each subparser's `prog` from the parent's
  custom `usage=` string. Pass `prog=PROG` so each expands to
  `ebrium individual` / `ebrium family` / etc. (3.14 already ignored the
  custom usage when building the prefix; this matches that on older
  versions.)

### Changed
- Dropped `--max-adjustment` from `ebrium individual`. The pull check in
  `plan_identical_metrics` only fires when `len(main_cluster) > 1`, and
  individual mode always plans one font at a time, so the flag was a
  silent no-op — the same class of problem the subcommand split was meant
  to turn into an argparse error. Still present under `family` /
  `superfamily`.
- `ebrium probe -v` help now notes that repeating (`-vv`) has no extra
  effect (`cli.py` only checks `verbose >= 1` for probe).

## [3.0.0] - 2026-09-21

### Changed (breaking)
- Replaced the flat flag surface with required subcommands:
  `ebrium {individual,family,superfamily,probe} [options] [PATH ...]`.
  There's no default subcommand — `ebrium fonts/ -r` (implicit `family`)
  no longer works; use `ebrium family fonts/ -r`.
- `--grouping {family, family-safe-max, superfamily, individual}` is gone.
  `family`/`superfamily`/`individual` are now subcommand names;
  `family-safe-max` is `--safe-max`, a plain boolean scoped to the
  `family` subcommand.
- `--probe-variation-metrics` is gone; use the `probe` subcommand
  (`ebrium probe fonts/ -r`). It never touched grouping, measurement, or
  config, so it was always a separate tool wearing a flag.
- `--exclude` only exists under `superfamily` now (previously accepted
  everywhere with a runtime warning that it "only applies to
  `--grouping superfamily`").
- `--combine`, `--ignore-prefix`, `--line-box`, `--line-box-from`, and
  `--report` only exist under `family`/`superfamily`. Using them under
  `individual` or `probe` is now an "unrecognized arguments" error instead
  of a silent no-op with a runtime warning.
- All parsers set `allow_abbrev=False`. Previously, `--exclude` typed under
  `individual` silently prefix-matched `--exclude-measuring` (the only
  flag there starting with `--exclude`) instead of erroring, since
  argparse's default abbreviation matching doesn't check whether the two
  flags mean the same thing.

### Fixed
- `--help` sections built from `FontCore.core_cli_help`'s shared grid
  (examples, notes) could silently drop text: Rich's default column
  `overflow="ellipsis"` truncated an over-long final word instead of
  wrapping it (e.g. `--line-box-from`'s help used to end
  "...--line-box force-baselin…" with `e)` dropped). Grids now use
  `overflow="fold"`.

### Added
- `RichHelp`'s `panel` parameter accepts `False` to omit the safety panel
  entirely; used by `probe`, which never writes anything.

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
