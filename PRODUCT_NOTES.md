# Product notes — ebrium

Standalone product tree for https://github.com/andrewsipe/ebrium

## Origin

Consolidated from monorepo `FontMetricsNormalizer/` (package was already named `ebrium`).
FontCore is vendored (console + collector + sorter + CLI help); no submodule.

## Done

- Standalone installable package with GitHub install paths
- Vendored FontCore subset
- FontFixer-style `--help` (`FontCore.core_cli_help` + `ebrium.cli_parser`)
- v3.2.1: `--help` group order is non-metrics first, metrics last before
  `general` (display-only)
- v3.2.0: `--ignore-prefix` → `--ignore-term` (accurate help + downstream
  rename); `--combine` trap documented; letter-height/top-margin override
  behavior in help
- v3.1.0: `-a/--assume TYPE:PATTERN` replaces the four `--assume-*` flags;
  short flags `-l`/`-t`/`-c`/`-i`/`-e`/`-b`/`-a` where letters don't collide
- v3.0.1 polish: `add_subparsers(prog=PROG)` so usage lines don't double on
  Python &lt; 3.14; dropped inert `--max-adjustment` from `individual`; probe
  `-v` help notes that repeating has no extra effect
- Subcommands replace the flat flag surface (v3.0.0, breaking):
  `ebrium {individual,family,superfamily,probe} [options] [PATH ...]`,
  subcommand required (no implicit default). Each subcommand's parser only
  defines the flags that do something for it — `grouping.py`/`planning.py`
  already branched on the grouping strategy as their first decision, so
  the parser now matches that shape instead of exposing every flag at the
  top level and warning at runtime when one didn't apply. Details:
  - `--grouping {family, family-safe-max, superfamily, individual}` split
    into the four subcommand names; `family-safe-max` became `--safe-max`,
    a plain boolean scoped to the `family` subcommand (it's unambiguous
    there — no other subcommand has a same-prefixed flag to confuse it
    with).
  - `--probe-variation-metrics` became the `probe` subcommand.
    `variation_probe.py` never touched grouping, measurement, or config —
    it was always a separate tool wearing a flag.
  - `--exclude` only exists under `superfamily` now (previously a runtime
    warning: "only applies to --grouping superfamily").
  - `--combine`/`--ignore-term`/`--line-box*`/`--report` only exist
    under `family`/`superfamily`; `individual`'s parser doesn't define
    them, so using them is an ordinary "unrecognized arguments" error
    instead of a silent no-op with a warning.
  - `validate_args()` lost ~5 branches that checked for now-impossible
    flag combinations (dead code once the parser itself enforces them).
  - `cli_parser.finalize_args()` still bridges the result back onto the
    attribute names the rest of the app expects (`grouping_mode`,
    `force_baseline`, `safe_hhea`, `combine`, `ignore_term`, `exclude`,
    `report`), defaulting the ones a given subcommand doesn't expose (e.g.
    `args.combine` is always present, `None` under `individual`/`probe`) so
    `grouping.py`/`planning.py`/`validation.py`/`cli.py` needed no other
    changes.
  - All 5 parsers (top-level + 4 subcommands) set `allow_abbrev=False`.
    Without it, `--exclude` under `individual` silently prefix-matched
    `--exclude-measuring` (the only flag there starting with `--exclude`)
    instead of erroring — argparse's default abbreviation matching doesn't
    care that the two flags mean completely different things.
  - `core_cli_help.py`'s shared `_grid()`/notes-grid columns gained
    `overflow="fold"` (was Rich's default `"ellipsis"`), fixing silent
    text truncation whenever a wrapped column's last word didn't fit —
    e.g. `--line-box-from`'s help text used to render as
    "...--line-box force-baselin…" with the rest dropped.
  - `RichHelp`'s `panel` param now also accepts `False` to omit the safety
    panel entirely (used by `probe`, which writes nothing).
- `--help` gained inline mode tables (v2.1.0): `choices_section()` results
  now print immediately after the argument group they explain (via a
  fresh `HelpFormatter` per group + `RichHelp`'s new `inline` hook),
  instead of only at the very end with everything else in `footer`
- Folded `--force-baseline-main-cluster` into `--line-box` as the
  `force-baseline-main-cluster` choice (v2.1.0, breaking) — it never had a
  value of its own, same reasoning as folding `--safe-max` into
  `--grouping`. `--line-box-from` stays a value-taking flag but now
  implies `--line-box force-baseline` when `--line-box` is left at
  `auto`, instead of doing nothing until both flags are given.
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
  (`probe` doesn't measure at all, so it never writes one)
- Exit code `2` is used both for “no measurable fonts” and by argparse for bad args

## Deferred

1. Optional: skip checkpoint writes in dry-run / report / probe modes
2. Tests / fixtures
3. Optional split of large `planning.py`
4. Archive or redirect old `FontMetricsNormalizer` GitHub remote when ready
5. Remove `FontMetricsNormalizer/` from monorepo + PushCore when leaving workspace
