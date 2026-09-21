"""ebrium argument parser (drop-in for the body of cli.parse_args()).

On top of the FontFixer-style presentation (grouped options, safety panel,
notes footer, hand-written usage, pinned prog), two flag families are
consolidated into single choice arguments:

  * --grouping {family, family-safe-max, superfamily, individual} replaces
    the four standalone flags --family/--superfamily/--individual/--safe-max.
    "safe-max" was never a fifth independent axis - grouping.py always runs
    it through group_by_family() - so it reads better as a family variant.
  * --line-box {auto, force-baseline, force-baseline-main-cluster, safe-hhea}
    replaces the two booleans --force-baseline/--safe-hhea plus the
    --force-baseline-main-cluster modifier. planning.py already treated
    force-baseline/safe-hhea as mutually exclusive at runtime (force_hhea
    short-circuits force_baseline inside maybe_apply_force_family_baseline());
    the parser now says so up front. --force-baseline-main-cluster never had
    a value of its own - like --safe-max, it only ever narrowed which
    reference force-baseline picks - so it folds in as a --line-box choice
    the same way --safe-max folded into --grouping.
  * --line-box-from keeps its own flag (it takes a path/glob, so it can't be
    a bare choice), but its mere presence now implies --line-box
    force-baseline when --line-box is left at its default, instead of doing
    nothing until you also pass --line-box force-baseline.

The --help footer also gets richer here: choices_section() renders a table
of {choice: meaning} and RichHelp's `inline` hook prints it immediately
after the argument group it belongs to (via a fresh HelpFormatter per group),
rather than only at the very end alongside examples/notes/exit codes.

finalize_args() maps the two new choice flags back onto the attribute names
the rest of the app already expects (grouping_mode, force_baseline,
force_baseline_main_cluster, safe_hhea), so validation.py / planning.py /
cli.py needed no changes beyond calling it once after parsing.

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

DESCRIPTION = (
    "Normalize vertical metrics across a font family without changing "
    "unitsPerEm or glyph outlines."
)

PANEL = safety_panel(
    message=(
        "Fonts are modified in place: no backup and no output directory. "
        "You are asked to confirm before anything is written."
    ),
    rows=[
        ("Preview only", "-n, --dry-run"),
        ("Family vs per-font analysis", "--report  (implies -n)"),
    ],
)

GROUPING_MODES = {
    "family": "group by family name; cluster within each family (default)",
    "family-safe-max": "group by family; bbox extremes for every font, no clustering (prevents clipping)",
    "superfamily": "merge families sharing a name prefix; cluster across the superfamily",
    "individual": "normalize each font on its own; no grouping or clustering",
}

LINE_BOX_MODES = {
    "auto": "each font keeps its own planned typo/hhea values (default)",
    "force-baseline": "unify typo/hhea across the family using its largest-span style "
    "(macOS/UI centering follows typo/hhea)",
    "force-baseline-main-cluster": "like force-baseline, but the reference is chosen "
    "only from the family's largest optical cluster",
    "safe-hhea": "average existing typo/hhea values across the family and apply them "
    "uniformly (Win uses max ranges)",
}

EXAMPLES = [
    ("ebrium fonts/ -r", "normalize a tree (asks before writing)"),
    ("ebrium fonts/ -r -n", "preview the changes"),
    ("ebrium fonts/ -r --report", "family vs per-font analysis (implies -n)"),
    ("ebrium fonts/ -r -y", "skip the confirmation prompt"),
    ("ebrium fonts/ --grouping family-safe-max", "no clustering; safest against clipping"),
    ("ebrium fonts/ --ignore-prefix Adobe", "ignore a vendor prefix when grouping"),
    (
        'ebrium fonts/ --combine "A,B" --line-box force-baseline',
        "merge two families, then unify the line box",
    ),
    (
        "ebrium fonts/ --line-box-from Bold.ttf",
        "pin the line-box reference font (implies --line-box force-baseline)",
    ),
    ("ebrium fonts/ --assume-script '*Swash*'", "override script detection by filename"),
]

NOTES = [
    "Every run, even with -n or --report, writes .metrics_checkpoint.json to the current "
    "directory. It caches measurements and clusters, and resets when the options or the "
    "font set change.",
    "--combine, --ignore-prefix and --exclude are ignored with --grouping individual; "
    "--exclude only applies to --grouping superfamily.",
    "--line-box-from pins an explicit reference font; it wins over "
    "--line-box force-baseline-main-cluster when both would pick one.",
    "--line-box force-baseline (and force-baseline-main-cluster) skip single-font "
    "families (e.g. a lone 'Name Variable'); pair them with --combine.",
    "--probe-variation-metrics ignores -n, --report and --line-box; "
    "add -v for per-pole deltas.",
]

EXIT_CODES = {
    "0": "done (including nothing to change, previews, reports and probes)",
    "1": "no font files found",
    "2": "no measurable fonts (also used for invalid arguments)",
    "3": "aborted at the confirmation prompt",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ebrium",
        usage="%(prog)s [options] [PATH ...]",
        description=DESCRIPTION,
        add_help=False,  # -h is registered below so it can live in "general"
    )

    # Groups display in creation order; create them in the order you want to read them.
    g_in = p.add_argument_group("input")
    g_run = p.add_argument_group("preview and confirmation")
    g_space = p.add_argument_group("vertical spacing (% of UPM)")
    g_mode = p.add_argument_group("grouping mode")
    g_mod = p.add_argument_group("grouping modifiers (repeatable)")
    g_box = p.add_argument_group("line box (typo / hhea)")
    g_det = p.add_argument_group("detection overrides (filename globs, repeatable)")
    g_gen = p.add_argument_group("general")

    # ---- general
    g_gen.add_argument(
        "-h", "--help", action=RichHelp, help="show this help message and exit",
        console=get_console(), panel=PANEL,
        inline={
            # Printed right after their own group, not just at the very end,
            # so the {choices} meanings sit next to the flag that offers them.
            "grouping mode": choices_section("--grouping modes", GROUPING_MODES),
            "line box (typo / hhea)": choices_section("--line-box modes", LINE_BOX_MODES),
        },
        footer=[
            examples_section(EXAMPLES),
            notes_section(NOTES),
            exit_status_section(EXIT_CODES),
            line_section("formats", "TTF, OTF, WOFF, WOFF2 (.ttx with --use-ttx)"),
            docs_section("https://github.com/andrewsipe/ebrium"),
        ],
    )
    g_gen.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    g_gen.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="verbose output; -vv for debug output",
    )

    # ---- input
    g_in.add_argument(
        "paths", nargs="*", metavar="PATH",
        help="font files or directories (default: current directory)",
    )
    g_in.add_argument("-r", "--recursive", action="store_true", help="recurse into directories")
    g_in.add_argument("--use-ttx", action="store_true", help="also process .ttx files")

    # ---- preview and confirmation
    g_run.add_argument("-n", "--dry-run", action="store_true", help="preview changes without writing")
    g_run.add_argument("-y", "--yes", action="store_true", help="skip the 'Proceed? [y/N]' prompt")
    g_run.add_argument(
        "--report", action="store_true",
        help="detailed family vs per-font analysis (implies --dry-run)",
    )
    g_run.add_argument(
        "--probe-variation-metrics", action="store_true",
        help="read-only MVAR/HVAR coverage report; does not measure or write fonts",
    )

    # ---- vertical spacing
    g_space.add_argument(
        "--letter-height", type=float, default=130, metavar="PERCENT",
        help="target height of the letter span (default: 130)",
    )
    g_space.add_argument(
        "--top-margin", type=float, default=25, metavar="PERCENT",
        help="extra space above capitals (default: 25)",
    )
    g_space.add_argument(
        "--max-adjustment", type=float, default=None, metavar="PERCENT",
        help="cap how far family extremes may pull a font (default: no cap); "
        "fonts over the cap are calculated individually",
    )
    g_space.add_argument(
        "--no-auto-adjust", action="store_true",
        help="use exactly --letter-height (skip the x-height adjustment)",
    )

    # ---- grouping mode: one flag, four choices (meanings printed right below)
    g_mode.add_argument(
        "--grouping", dest="grouping_mode", default="family",
        choices=["family", "family-safe-max", "superfamily", "individual"],
        metavar="MODE",
        help="how fonts are grouped and clustered (default: family; see modes below)",
    )

    # ---- grouping modifiers
    g_mod.add_argument(
        "--combine", action="append", metavar="GROUP",
        help='force-merge families, e.g. --combine "Font A,Font B"',
    )
    g_mod.add_argument(
        "--ignore-prefix", action="append", metavar="TOKEN",
        help="ignore a leading token when matching family names (e.g. Adobe, LT)",
    )
    g_mod.add_argument(
        "--exclude", action="append", metavar="FAMILY",
        help="keep FAMILY out of superfamily merges (--grouping superfamily only)",
    )

    # ---- line box: one flag, four choices (meanings printed right below),
    # plus --line-box-from since a reference path can't be a bare choice
    g_box.add_argument(
        "--line-box", dest="line_box", default="auto",
        choices=["auto", "force-baseline", "force-baseline-main-cluster", "safe-hhea"],
        metavar="MODE",
        help="how typo/hhea is set across a family (default: auto; see modes below)",
    )
    g_box.add_argument(
        "--line-box-from", dest="force_baseline_from", default=None, metavar="PATH_OR_GLOB",
        help="pin the force-baseline reference font (path, filename, or filename glob); "
        "implies --line-box force-baseline",
    )

    # ---- detection overrides
    g_det.add_argument(
        "--assume-script", action="append", metavar="PATTERN",
        help="treat matching fonts as script (e.g. '*Script*', '*Swash*')",
    )
    g_det.add_argument(
        "--assume-decorative", action="append", metavar="PATTERN",
        help="treat matching fonts as decorative (e.g. '*Rough*', '*Inline*')",
    )
    g_det.add_argument(
        "--assume-unicase", action="append", metavar="PATTERN",
        help="treat matching fonts as unicase (e.g. '*Unicase*')",
    )
    g_det.add_argument(
        "--assume-uniwidth", action="append", metavar="PATTERN",
        help="treat matching fonts as uniwidth; one match flags the whole family",
    )
    g_det.add_argument(
        "--exclude-measuring", action="append", metavar="PATTERN",
        help="measure matching fonts but leave them out of family calculations",
    )

    # ---- hidden expert thresholds (unchanged)
    p.add_argument("--decorative-threshold", type=float, default=1.4, help=argparse.SUPPRESS)
    p.add_argument("--unicase-threshold", type=float, default=0.05, help=argparse.SUPPRESS)
    p.add_argument("--max-span-ratio", type=float, default=1.5, help=argparse.SUPPRESS)
    return p


def finalize_args(args: argparse.Namespace) -> None:
    """Map the consolidated --grouping/--line-box choices onto the attribute
    names the rest of the app expects. Call this once, right after parse_args().

    --grouping family-safe-max        -> args.grouping_mode = "conservative"
    --line-box force-baseline         -> args.force_baseline = True
    --line-box force-baseline-main-cluster
                                       -> args.force_baseline = True
                                          args.force_baseline_main_cluster = True
    --line-box safe-hhea              -> args.safe_hhea = True
    --line-box-from PATH (no --line-box given) -> args.line_box promoted to
                                          "force-baseline" (see below)
    """
    if args.grouping_mode == "family-safe-max":
        args.grouping_mode = "conservative"

    args.force_baseline_main_cluster = args.line_box == "force-baseline-main-cluster"
    args.force_baseline = args.line_box in ("force-baseline", "force-baseline-main-cluster")
    args.safe_hhea = args.line_box == "safe-hhea"

    # --line-box-from only ever means something with force-baseline. If the
    # user pinned a reference file but left --line-box at its default, that
    # intent is unambiguous - treat it as --line-box force-baseline instead
    # of silently doing nothing until they also pass the mode flag. An
    # explicit --line-box safe-hhea is left alone; validate_args warns that
    # --line-box-from has no effect there.
    if args.force_baseline_from and args.line_box == "auto":
        args.line_box = "force-baseline"
        args.force_baseline = True
