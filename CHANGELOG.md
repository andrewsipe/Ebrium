# Changelog

## Unreleased

### Removed
- `ebrium springy` subcommand and `ebrium/springy.py`. The soft-span /
  x-height-attract path is gone; use `family` / `superfamily` / `individual`.

### Added
- Families that include a Face cut now treat effect styles (Shadow, Extrude,
  Outline, Fine, Inline, and similar) as decorative outliers: they inherit
  the Face typo box and do not set the floor. `--assume decorative` peels a
  style the same way even when the name has no Face token.
- A peer group that mixes optical-size names (Caption, Display, Subhead,
  Small Text, Text, and similar) is unpinned into one line box per size.
  A single size stays one pinned box. Effect cuts are not optical sizes.
- A multi-file layered or color set (every file has a color table, or every
  name is a layer) gets one shared typo box and one shared Win box from the
  union of the outlines.
- After planning, a Review block lists only the families that need a look:
  layered copy, missing accent samples, a span past the letter-height floor,
  cross-weight spread of cap, x-height, or accent height, and an
  x-height/cap-height ratio outside 0.65–0.78. Those notes do not change the plan.

### Changed
- Line box: capitals stay centered when growing to the letter-height floor
  (`asc − cap = |desc|`). The old 60/40 expand split is removed. Asymmetry
  comes only from measured floors (accented capitals, real descenders).
- X-height no longer raises the letter-height floor (that belongs in CSS
  leading, not font metrics).
- Accented-capital yMax is a hard typo-ascender floor. If no sample glyphs
  exist, the run flags a re-check (report-only).
- `--safe-max` is now `--no-cluster`. It skips clustering under `family`;
  the old flag still works and is hidden from `--help`.
- `--combine` / `-c` is now `--merge` / `-m`. Each flag is still one complete
  group (`--merge "A,B"`). `-m A -m B` does not merge A with B and warns.
  The old spelling still works and is hidden from `--help`.
- Parser helpers no longer annotate argparse's private `_ArgumentGroup` and
  `_SubParsersAction` types.
- `probe` now reports whether the typo line box already moves, and whether
  a flat Win clipping box is overflowed at an axis pole past the default
  ink. The run ends with a tally. HVAR is no longer part of the report.
- `probe` is the read-only metrics tool. It groups by family (or
  `--superfamily`), prints one table per group with the driver first and
  pull from least to most, and lists slider facts for variable fonts.
  `--report` is removed from `family` and `superfamily`.
- `probe -q` shows the current filename and a progress bar, then the tally.
  `probe -o FILE` writes a tab-separated row per font as the run goes.
  A relative file is saved at the top of the directory that was probed.

### Added
- Static docs site under `docs/` for GitHub Pages (concepts, how it thinks,
  flag reference, reading a run, `--report` lookup). README slimmed to install
  + quick start with a Docs link; `project.urls.Documentation` and CLI
  `DOCS_URL` point at https://www.andrewsipe.com/Ebrium/
- Docs now say that `family`, `individual`, and `superfamily` rewrite a
  variable font's default instance only and leave MVAR/HVAR alone. `probe`
  is the read-only coverage check.
- Fixture tests: one TTF through measure, plan, and write, plus a variable
  font whose MVAR/HVAR bytes stay put. Parser tests cover `--no-cluster` /
  `--merge` and the hidden old spellings.

## [3.2.2] - 2026-09-21

### Changed
- `--safe-max` help and its group title (`clustering override`) now make clear
  that clustering is the default under `family`, and `--safe-max` is an
  advanced opt-out for unpredictable or incorrectly detected metrics — not
  the primary clustering control.

## [3.2.1] - 2026-09-21

### Changed
- Reordered `--help` argument groups so non-metrics options come first
  (input → preview → grouping/clustering → detection) and metrics knobs
  last before `general` (vertical spacing → line box). Display-only;
  flag behavior unchanged. `probe` is unchanged (input → general).

## [3.2.0] - 2026-09-21

### Changed (breaking)
- Renamed `--ignore-prefix` to `--ignore-term` (`-i`). The old flag described
  stripping a "leading" token, but `FontSorter` drops a whole word
  case-sensitively wherever it appears in the family name. `grouping.py` and
  `validation.py` now read `args.ignore_term`.

### Changed
- `--combine` help and `family`/`superfamily` notes now state that each flag
  is one complete merge group: `--combine "A,B"` merges A and B, but
  `-c A -c B` creates two one-family groups (skipped with a warning), unlike
  `-i` / `--exclude` where repeats flatten the same way.
- `--letter-height` and `--top-margin` help document silent overrides:
  letter-height is a floor when auto-adjust is on (default); top-margin can
  be ignored when actual ascenders already exceed the requested margin.

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
