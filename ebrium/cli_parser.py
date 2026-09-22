"""ebrium argument parser: one subcommand per grouping strategy.

Earlier revisions put every flag at the top level and used runtime warnings
(validate_args) to say "this flag does nothing in that mode" -- e.g.
--exclude only works with superfamily, --combine/--line-box are no-ops with
individual, --probe-variation-metrics ignores most of the other flags. That
information already existed as branches in grouping.py/planning.py; the
parser just wasn't shaped the same way.

This version has one subcommand per branch:

  ebrium individual  [options] PATH...   -- each font normalized alone
  ebrium family      [options] PATH...   -- group by family, optional --safe-max
  ebrium superfamily [options] PATH...   -- merge shared-prefix families
  ebrium probe       [options] PATH...   -- read-only MVAR/HVAR report
                                             (was --probe-variation-metrics;
                                             it never touched grouping,
                                             measurement, or config at all --
                                             variation_probe.py is fully
                                             self-contained, so it was always
                                             a separate tool wearing a flag)

Each subcommand's parser only defines the flags that do something for it, so
invalid combinations (e.g. `ebrium individual ... --exclude X`) are ordinary
argparse "unrecognized arguments" errors instead of silent runtime warnings.
The subcommand is required; there's no implicit default mode.

finalize_args() still bridges the result back onto the attribute names
grouping.py/planning.py/validation.py/cli.py/measurements.py already expect
(grouping_mode, force_baseline, force_baseline_main_cluster, safe_hhea,
combine, ignore_term, exclude, report, assume_script/decorative/unicase/
uniwidth), defaulting the ones a given subcommand doesn't expose (e.g.
args.combine is always present, None under `individual`/`probe`) so the
rest of the app never needs to branch on args.mode itself.

In cli.py:

    from .cli_parser import build_parser, finalize_args

    def parse_args() -> argparse.Namespace:
        args = build_parser().parse_args()
        finalize_args(args)
        return args
"""

from __future__ import annotations

import argparse

from FontCore.core_cli_help import (
    RichHelp,
    choices_section,
    docs_section,
    examples_section,
    exit_status_section,
    line_section,
    notes_section,
    safety_panel,
)
from FontCore.core_console_styles import get_console

from . import __version__

PROG = "ebrium"
DOCS_URL = "https://andrewsipe.github.io/ebrium/"
FORMATS_LINE = "TTF, OTF, WOFF, WOFF2 (.ttx with --use-ttx)"

ASSUME_TYPES = {
    "script": "treat as a script/handwriting face",
    "decorative": "treat as a decorative/display face",
    "unicase": "treat as unicase (no separate cap-height row)",
    "uniwidth": "treat as fixed-advance-width across the family (one match flags the whole family)",
}


def _assume_value(raw: str) -> tuple[str, str]:
    """argparse `type=` for `--assume TYPE:PATTERN`. Raising ArgumentTypeError
    here gives a normal argparse usage error instead of a silent no-op --
    same reasoning as splitting the flags into subcommands in the first place."""
    type_, sep, pattern = raw.partition(":")
    if not sep or not pattern:
        raise argparse.ArgumentTypeError(
            f"expected TYPE:PATTERN, e.g. script:*Swash* (got {raw!r})"
        )
    if type_ not in ASSUME_TYPES:
        choices = ", ".join(ASSUME_TYPES)
        raise argparse.ArgumentTypeError(f"unknown type {type_!r} (choose from {choices})")
    return type_, pattern


MODE_SUMMARY = {
    "individual": "normalize each font on its own; no grouping or clustering",
    "family": "group by family name; cluster within each family (add --safe-max to skip clustering)",
    "superfamily": "merge families sharing a name prefix; cluster across the superfamily",
    "probe": "read-only MVAR/HVAR coverage report; no grouping, measuring, or writing",
}

# Coupled to inline tables under "line box (typo / hhea)" and "detection
# overrides..." : help strings that say "see table below" / "see modes below"
# assume these print immediately after those groups. If a table moves to the
# footer, update the matching help.
LINE_BOX_MODES = {
    "auto": "each font keeps its own planned typo/hhea values (default)",
    "force-baseline": "unify typo/hhea across the family using its largest-span style "
    "(macOS/UI centering follows typo/hhea)",
    "force-baseline-main-cluster": "like force-baseline, but the reference is chosen "
    "only from the family's largest optical cluster",
    "safe-hhea": "average existing typo/hhea values across the family and apply them "
    "uniformly (Win uses max ranges)",
}

EXIT_CODES = {
    "0": "done (including nothing to change, previews and reports)",
    "1": "no font files found",
    "2": "no measurable fonts (also used for invalid arguments)",
    "3": "aborted at the confirmation prompt",
}

PROBE_EXIT_CODES = {
    "0": "done",
    "1": "no font files found",
    "2": "invalid arguments",
}

CHECKPOINT_NOTE = (
    "Every run, even with -n, writes .metrics_checkpoint.json to the current "
    "directory. It caches measurements and clusters, and resets when the options "
    "or the font set change."
)

COMBINE_NOTE = (
    '--combine merges the families named in ONE flag, e.g. --combine "A,B". Repeat '
    "--combine for further groups, but a group must be complete in a single flag: "
    "-c A -c B does not merge A with B -- each is its own group of one and gets "
    "skipped with a warning."
)

PANEL_ROWS_BASIC = [("Preview only", "-n, --dry-run")]
PANEL_ROWS_WITH_REPORT = [
    ("Preview only", "-n, --dry-run"),
    ("Family vs per-font analysis", "--report  (implies -n)"),
]
PANEL_MESSAGE = (
    "Fonts are modified in place: no backup and no output directory. "
    "You are asked to confirm before anything is written."
)


# ---------------------------------------------------------------- shared flag builders
# Each subcommand is a plain ArgumentParser (from subparsers.add_parser()); these
# helpers add the same flag to whichever subcommands actually use it, instead of
# every subcommand redefining it (and instead of one subcommand exposing a flag
# that does nothing for it).

def _add_input_args(g: argparse._ArgumentGroup) -> None:
    g.add_argument(
        "paths", nargs="*", metavar="PATH",
        help="font files or directories (default: current directory)",
    )
    g.add_argument("-r", "--recursive", action="store_true", help="recurse into directories")
    g.add_argument("--use-ttx", action="store_true", help="also process .ttx files")


def _add_preview_args(g: argparse._ArgumentGroup) -> None:
    g.add_argument("-n", "--dry-run", action="store_true", help="preview changes without writing")
    g.add_argument("-y", "--yes", action="store_true", help="skip the 'Proceed? [y/N]' prompt")


def _add_report_arg(g: argparse._ArgumentGroup) -> None:
    g.add_argument(
        "--report", action="store_true",
        help="detailed family vs per-font analysis (implies --dry-run)",
    )


def _add_spacing_args(g: argparse._ArgumentGroup, *, include_max_adjustment: bool = True) -> None:
    g.add_argument(
        "-l", "--letter-height", type=float, default=130, metavar="PERCENT",
        help="target height of the letter span (default: 130); a floor, not a fixed "
        "value -- auto-adjust may raise it for large x-heights, see --no-auto-adjust",
    )
    g.add_argument(
        "-t", "--top-margin", type=float, default=25, metavar="PERCENT",
        help="extra space above capitals (default: 25); ignored for a font whose actual "
        "ascenders already clear it by a wide margin, which keeps its own ascender height",
    )
    if include_max_adjustment:
        # Meaningless under `individual`: the "pull toward family extremes" it
        # caps never happens when every font is its own group of one, so this
        # subcommand's callers pass include_max_adjustment=False rather than
        # exposing a flag that silently does nothing.
        g.add_argument(
            "--max-adjustment", type=float, default=None, metavar="PERCENT",
            help="cap how far family extremes may pull a font (default: no cap); "
            "fonts over the cap are calculated individually",
        )
    g.add_argument(
        "--no-auto-adjust", action="store_true",
        help="use exactly --letter-height (skip the x-height adjustment)",
    )


def _add_detection_args(p: argparse.ArgumentParser, g: argparse._ArgumentGroup) -> None:
    g.add_argument(
        "-a", "--assume", dest="assume", action="append", type=_assume_value,
        metavar="TYPE:PATTERN",
        help="override detection for matching filenames, repeatable "
        "(TYPE: script, decorative, unicase, uniwidth; see table below)",
    )
    g.add_argument(
        "--exclude-measuring", action="append", metavar="PATTERN",
        help="measure matching fonts but leave them out of family calculations",
    )
    # Hidden expert thresholds: added to the parser directly (not the visible
    # group) since help=SUPPRESS already keeps them out of --help either way.
    p.add_argument("--decorative-threshold", type=float, default=1.4, help=argparse.SUPPRESS)
    p.add_argument("--unicase-threshold", type=float, default=0.05, help=argparse.SUPPRESS)
    p.add_argument("--max-span-ratio", type=float, default=1.5, help=argparse.SUPPRESS)


def _add_grouping_mod_args(g: argparse._ArgumentGroup) -> None:
    g.add_argument(
        "-c", "--combine", action="append", metavar="GROUP",
        help='merge one group of families per flag, comma-separated inside the flag: '
        '--combine "Font A,Font B" (repeat --combine for further, separate groups -- '
        "don't split one group across repeats, e.g. -c A -c B merges nothing)",
    )
    g.add_argument(
        "-i", "--ignore-term", action="append", metavar="TERM",
        help="drop a whole word from family names before grouping, case-sensitive, "
        "wherever it appears (e.g. Adobe, LT); repeatable, or comma-separated",
    )


def _add_line_box_args(g: argparse._ArgumentGroup) -> None:
    g.add_argument(
        "-b", "--line-box", dest="line_box", default="auto",
        choices=["auto", "force-baseline", "force-baseline-main-cluster", "safe-hhea"],
        metavar="MODE",
        help="how typo/hhea is set across the group (default: auto; see modes below)",
    )
    g.add_argument(
        "--line-box-from", dest="force_baseline_from", default=None, metavar="PATH_OR_GLOB",
        help="pin the force-baseline reference font (path, filename, or filename glob); "
        "implies --line-box force-baseline",
    )


def _add_general_args(g: argparse._ArgumentGroup, verbose_help: str) -> None:
    g.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    g.add_argument("-v", "--verbose", action="count", default=0, help=verbose_help)


def _add_help(
    g: argparse._ArgumentGroup,
    *,
    panel,
    footer,
    inline=None,
) -> None:
    g.add_argument(
        "-h", "--help", action=RichHelp, help="show this help message and exit",
        console=get_console(), panel=panel, inline=inline or {}, footer=footer,
    )


# ---------------------------------------------------------------- subcommands

def _build_individual(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "individual",
        usage="%(prog)s [options] [PATH ...]",
        allow_abbrev=False,
        description="Normalize each font's own vertical metrics -- no grouping, no clustering.",
        add_help=False,
    )
    # Group *creation* order is display order (argparse), independent of when
    # arguments are added to each group below. Non-metrics groups (which fonts
    # get picked up, previewed, classified) come first; the one metrics group
    # -- the actual normalization knobs -- comes last, before "general".
    g_in = p.add_argument_group("input")
    g_run = p.add_argument_group("preview and confirmation")
    g_det = p.add_argument_group("detection overrides (filename globs, repeatable)")
    g_space = p.add_argument_group("vertical spacing (% of UPM)")
    g_gen = p.add_argument_group("general")

    examples = [
        ("ebrium individual fonts/ -r", "normalize each font on its own (asks before writing)"),
        ("ebrium individual fonts/ -r -n", "preview the changes"),
        ("ebrium individual fonts/ -r -y", "skip the confirmation prompt"),
        ("ebrium individual fonts/ -a script:'*Swash*'", "override script detection by filename"),
    ]
    notes = [CHECKPOINT_NOTE]

    _add_help(
        g_gen,
        panel=safety_panel(message=PANEL_MESSAGE, rows=PANEL_ROWS_BASIC),
        inline={"detection overrides (filename globs, repeatable)": choices_section("--assume types", ASSUME_TYPES)},
        footer=[
            examples_section(examples),
            notes_section(notes),
            exit_status_section(EXIT_CODES),
            line_section("formats", FORMATS_LINE),
            docs_section(DOCS_URL),
        ],
    )
    _add_input_args(g_in)
    _add_preview_args(g_run)
    _add_detection_args(p, g_det)
    _add_spacing_args(g_space, include_max_adjustment=False)
    _add_general_args(g_gen, "verbose output; -vv for debug output")


def _build_family(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "family",
        usage="%(prog)s [options] [PATH ...]",
        allow_abbrev=False,
        description="Normalize vertical metrics within families, clustering optically similar styles together.",
        add_help=False,
    )
    # Non-metrics groups (sorting/analysis) first, ordered by how often they
    # come up; the two metrics groups -- the actual normalization knobs --
    # come last, before "general". See _build_individual for the same logic.
    g_in = p.add_argument_group("input")
    g_run = p.add_argument_group("preview and confirmation")
    g_mod = p.add_argument_group("grouping modifiers (repeatable)")
    g_cluster = p.add_argument_group("clustering override")
    g_det = p.add_argument_group("detection overrides (filename globs, repeatable)")
    g_space = p.add_argument_group("vertical spacing (% of UPM)")
    g_box = p.add_argument_group("line box (typo / hhea)")
    g_gen = p.add_argument_group("general")

    examples = [
        ("ebrium family fonts/ -r", "normalize a tree by family (asks before writing)"),
        ("ebrium family fonts/ -r -n", "preview the changes"),
        ("ebrium family fonts/ -r --report", "family vs per-font analysis (implies -n)"),
        ("ebrium family fonts/ -r -y", "skip the confirmation prompt"),
        ("ebrium family fonts/ --safe-max", "skip clustering (unpredictable / mis-detected metrics)"),
        ("ebrium family fonts/ --ignore-term Adobe", "drop a shared word before grouping"),
        ('ebrium family fonts/ --combine "A,B"', "force-merge two families before clustering"),
        ("ebrium family fonts/ --line-box force-baseline", "unify the typo/hhea line box"),
        ("ebrium family fonts/ --line-box-from Bold.ttf", "pin the line-box reference font"),
    ]
    notes = [
        CHECKPOINT_NOTE,
        COMBINE_NOTE,
        "--combine and --ignore-term still apply with --safe-max; clustering is what's skipped.",
        "--line-box-from pins an explicit reference font; it wins over "
        "--line-box force-baseline-main-cluster when both would pick one.",
        "--line-box force-baseline (and force-baseline-main-cluster) skip single-font "
        "families (e.g. a lone 'Name Variable'); pair them with --combine.",
    ]

    _add_help(
        g_gen,
        panel=safety_panel(message=PANEL_MESSAGE, rows=PANEL_ROWS_WITH_REPORT),
        inline={
            "line box (typo / hhea)": choices_section("--line-box modes", LINE_BOX_MODES),
            "detection overrides (filename globs, repeatable)": choices_section(
                "--assume types", ASSUME_TYPES
            ),
        },
        footer=[
            examples_section(examples),
            notes_section(notes),
            exit_status_section(EXIT_CODES),
            line_section("formats", FORMATS_LINE),
            docs_section(DOCS_URL),
        ],
    )
    _add_input_args(g_in)
    _add_preview_args(g_run)
    _add_report_arg(g_run)
    _add_grouping_mod_args(g_mod)
    g_cluster.add_argument(
        "--safe-max", action="store_true",
        help="skip clustering; use bbox extremes for every font in the family "
        "(default is to cluster; advanced — for unpredictable metrics that get "
        "incorrectly detected)",
    )
    _add_detection_args(p, g_det)
    _add_spacing_args(g_space)
    _add_line_box_args(g_box)
    _add_general_args(g_gen, "verbose output; -vv for debug output")


def _build_superfamily(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "superfamily",
        usage="%(prog)s [options] [PATH ...]",
        allow_abbrev=False,
        description="Merge families sharing a name prefix and cluster optically similar styles across the merge.",
        add_help=False,
    )
    # Same ordering logic as _build_family: non-metrics (sorting/analysis)
    # groups first, then the metrics groups, then "general" last.
    g_in = p.add_argument_group("input")
    g_run = p.add_argument_group("preview and confirmation")
    g_mod = p.add_argument_group("grouping modifiers (repeatable)")
    g_det = p.add_argument_group("detection overrides (filename globs, repeatable)")
    g_space = p.add_argument_group("vertical spacing (% of UPM)")
    g_box = p.add_argument_group("line box (typo / hhea)")
    g_gen = p.add_argument_group("general")

    examples = [
        ("ebrium superfamily fonts/ -r", "merge shared-prefix families into one group"),
        ("ebrium superfamily fonts/ -r --report", "family vs per-font analysis (implies -n)"),
        ("ebrium superfamily fonts/ --exclude Mono", "keep a family out of the merge"),
        ("ebrium superfamily fonts/ --ignore-term Adobe", "drop a shared word before grouping"),
        ('ebrium superfamily fonts/ --combine "A,B"', "force-merge two families before the prefix merge"),
        ("ebrium superfamily fonts/ --line-box force-baseline", "unify the typo/hhea line box"),
    ]
    notes = [
        CHECKPOINT_NOTE,
        COMBINE_NOTE,
        "--exclude keeps a family out of the superfamily merge; --combine still "
        "force-merges named families first.",
        "--line-box-from pins an explicit reference font; it wins over "
        "--line-box force-baseline-main-cluster when both would pick one.",
        "--line-box force-baseline (and force-baseline-main-cluster) skip single-font "
        "families (e.g. a lone 'Name Variable'); pair them with --combine.",
    ]

    _add_help(
        g_gen,
        panel=safety_panel(message=PANEL_MESSAGE, rows=PANEL_ROWS_WITH_REPORT),
        inline={
            "line box (typo / hhea)": choices_section("--line-box modes", LINE_BOX_MODES),
            "detection overrides (filename globs, repeatable)": choices_section(
                "--assume types", ASSUME_TYPES
            ),
        },
        footer=[
            examples_section(examples),
            notes_section(notes),
            exit_status_section(EXIT_CODES),
            line_section("formats", FORMATS_LINE),
            docs_section(DOCS_URL),
        ],
    )
    _add_input_args(g_in)
    _add_preview_args(g_run)
    _add_report_arg(g_run)
    _add_grouping_mod_args(g_mod)
    g_mod.add_argument(
        "-e", "--exclude", action="append", metavar="FAMILY",
        help="keep FAMILY out of the superfamily merge",
    )
    _add_detection_args(p, g_det)
    _add_spacing_args(g_space)
    _add_line_box_args(g_box)
    _add_general_args(g_gen, "verbose output; -vv for debug output")


def _build_probe(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "probe",
        usage="%(prog)s [options] [PATH ...]",
        allow_abbrev=False,
        description="Read-only MVAR/HVAR coverage report for variable fonts -- "
        "no grouping, measuring, or writing.",
        add_help=False,
    )
    g_in = p.add_argument_group("input")
    g_gen = p.add_argument_group("general")

    examples = [
        ("ebrium probe fonts/ -r", "read-only MVAR/HVAR coverage report"),
        ("ebrium probe fonts/ -r -v", "same, with per-pole deltas"),
    ]

    _add_help(
        g_gen,
        panel=False,  # nothing is written; no safety wording needed
        footer=[
            examples_section(examples),
            exit_status_section(PROBE_EXIT_CODES),
            line_section("formats", FORMATS_LINE),
            docs_section(DOCS_URL),
        ],
    )
    _add_general_args(
        g_gen, "verbose output (per-pole deltas); repeating has no extra effect"
    )
    _add_input_args(g_in)


# ---------------------------------------------------------------- top level

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        usage="%(prog)s {individual,family,superfamily,probe} [options] [PATH ...]",
        allow_abbrev=False,
        description=(
            "Normalize vertical metrics across fonts without changing unitsPerEm "
            "or glyph outlines. Pick how fonts are grouped first -- that choice "
            "determines which other options apply."
        ),
        add_help=False,
    )
    g_gen = p.add_argument_group("general")
    _add_help(
        g_gen,
        panel=False,
        footer=[
            choices_section("subcommands", MODE_SUMMARY),
            line_section("see also", f"{PROG} <subcommand> --help for that subcommand's options"),
            docs_section(DOCS_URL),
        ],
    )
    g_gen.add_argument("--version", action="version", version=f"{PROG} {__version__}")

    subparsers = p.add_subparsers(
        dest="mode", metavar="MODE", required=True,
        prog=PROG,  # otherwise each subparser's prog becomes this parser's whole
                    # custom usage= string, doubling the usage line under -h
        help="grouping subcommand; see 'subcommands' below",
    )
    _build_individual(subparsers)
    _build_family(subparsers)
    _build_superfamily(subparsers)
    _build_probe(subparsers)
    return p


def finalize_args(args: argparse.Namespace) -> None:
    """Map the subcommand + its choice flags onto the attribute names the
    rest of the app already expects. Call this once, right after parse_args().

    Every attribute set here is guaranteed to exist afterward regardless of
    which subcommand was used, even ones that subcommand's parser never
    defines (e.g. args.combine is always present, None under individual/probe).
    """
    mode = args.mode

    if mode == "individual":
        args.grouping_mode = "individual"
    elif mode == "family":
        args.grouping_mode = "conservative" if getattr(args, "safe_max", False) else "family"
    elif mode == "superfamily":
        args.grouping_mode = "superfamily"
    # probe: grouping_mode is unused downstream (variation_probe.py doesn't group)

    line_box = getattr(args, "line_box", "auto")
    args.force_baseline_main_cluster = line_box == "force-baseline-main-cluster"
    args.force_baseline = line_box in ("force-baseline", "force-baseline-main-cluster")
    args.safe_hhea = line_box == "safe-hhea"
    args.force_baseline_from = getattr(args, "force_baseline_from", None)

    # --line-box-from only ever means something with force-baseline. If the
    # user pinned a reference file but left --line-box at its default, that
    # intent is unambiguous - treat it as --line-box force-baseline instead
    # of silently doing nothing. An explicit --line-box safe-hhea is left
    # alone; validate_args warns that --line-box-from has no effect there.
    if args.force_baseline_from and line_box == "auto":
        line_box = "force-baseline"
        args.force_baseline = True
    args.line_box = line_box

    args.combine = getattr(args, "combine", None)
    args.ignore_term = getattr(args, "ignore_term", None)
    args.exclude = getattr(args, "exclude", None)
    args.report = getattr(args, "report", False)
    # individual omits --max-adjustment (silent no-op there); default it so
    # cli.py's MetricsConfig construction never AttributeErrors.
    if not hasattr(args, "max_adjustment"):
        args.max_adjustment = None

    # --assume TYPE:PATTERN (repeatable) replaces the four --assume-* flags;
    # split it back into the per-type lists measurements.py already expects,
    # so nothing downstream of finalize_args needs to know --assume exists.
    buckets: dict[str, list[str]] = {t: [] for t in ASSUME_TYPES}
    for type_, pattern in getattr(args, "assume", None) or []:
        buckets[type_].append(pattern)
    args.assume_script = buckets["script"] or None
    args.assume_decorative = buckets["decorative"] or None
    args.assume_unicase = buckets["unicase"] or None
    args.assume_uniwidth = buckets["uniwidth"] or None
