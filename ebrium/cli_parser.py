"""ebrium argument parser: one subcommand per grouping strategy.

Earlier revisions put every flag at the top level and used runtime warnings
(validate_args) to say "this flag does nothing in that mode" -- e.g.
--exclude only works with superfamily, --merge/--line-box are no-ops with
individual, --probe-variation-metrics ignores most of the other flags. That
information already existed as branches in grouping.py/planning.py; the
parser just wasn't shaped the same way.

This version has one subcommand per branch:

  ebrium individual  [options] PATH...   -- each font normalized alone
  ebrium family      [options] PATH...   -- group by family, optional --no-cluster
  ebrium superfamily [options] PATH...   -- merge shared-prefix families
  ebrium probe       [options] PATH...   -- read-only line-box and clipping report
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
from typing import Any

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
DOCS_URL = "https://www.andrewsipe.com/Ebrium/"
FORMATS_LINE = "TTF, OTF, WOFF, WOFF2 (.ttx with --use-ttx)"

ASSUME_TYPES = {
    "script": "inherit the family's line box; clipping box grows around the swashes",
    "decorative": "effect cut (Shadow, Extrude, and similar): inherit the line box, don't set the floor",
    "unicase": "same line box, less headroom above the letters so it aligns with the text cut",
    "uniwidth": "label the family as fixed-width across weights (does not change the line box)",
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
    "probe": "read-only metrics; does not write fonts",
}

# Coupled to inline tables under "line box (typo / hhea)" and "detection
# overrides..." : help strings that say "see table below" / "see modes below"
# assume these print immediately after those groups. If a table moves to the
# footer, update the matching help.
LINE_BOX_MODES = {
    "auto": "shared line box from cap height, centered, at least the letter-height floor (default). "
    "Effect and script cuts inherit it. Mixed optical sizes each get their own box",
    "force-baseline": "after that plan, copy one style's line box onto the whole family "
    "(the largest span, unless --line-box-from names the file)",
    "force-baseline-main-cluster": "like force-baseline, but the copied style is chosen "
    "only from the core cluster, not from effect or script cuts",
    "safe-hhea": "ignore the measured plan and average the typo/hhea values already stored in the files",
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
    '--merge names one complete group per flag, e.g. --merge "A,B". Repeat '
    "--merge for further groups. A group must be complete inside a single flag: "
    "-m A -m B does not merge A with B — each is its own group of one and is "
    "skipped with a warning."
)

PANEL_ROWS_BASIC = [("Preview only", "-n, --dry-run")]
PANEL_ROWS_WITH_REPORT = [
    ("Preview only", "-n, --dry-run"),
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
# Group and subparser parameters are Any: argparse's group and subparser classes
# are private (_ArgumentGroup, _SubParsersAction).

def _add_input_args(g: Any) -> None:
    g.add_argument(
        "paths", nargs="*", metavar="PATH",
        help="font files or directories (default: current directory)",
    )
    g.add_argument("-r", "--recursive", action="store_true", help="recurse into directories")
    g.add_argument("--use-ttx", action="store_true", help="also process .ttx files")


def _add_preview_args(g: Any) -> None:
    g.add_argument("-n", "--dry-run", action="store_true", help="preview changes without writing")
    g.add_argument("-y", "--yes", action="store_true", help="skip the 'Proceed? [y/N]' prompt")


def _add_spacing_args(g: Any) -> None:
    g.add_argument(
        "-l", "--letter-height", type=float, default=130, metavar="PERCENT",
        help="minimum letter-span floor as %% of UPM (default: 130); measured "
        "accented-cap or descender clearance may raise the box above this",
    )
    g.add_argument(
        "-t", "--top-margin", type=float, default=25, metavar="PERCENT",
        help="extra space above capitals (default: 25); ignored for a font whose actual "
        "ascenders already clear it by a wide margin, which keeps its own ascender height",
    )


def _add_detection_args(p: argparse.ArgumentParser, g: Any) -> None:
    g.add_argument(
        "-a", "--assume", dest="assume", action="append", type=_assume_value,
        metavar="TYPE:PATTERN",
        help="override detection for matching filenames, repeatable "
        "(TYPE: script, decorative, unicase, uniwidth; see table below)",
    )
    g.add_argument(
        "--measure-only", action="append", dest="exclude_measuring", metavar="PATTERN",
        help="measure matching fonts, but leave them out of the shared plan",
    )
    # Hidden expert thresholds: added to the parser directly (not the visible
    # group) since help=SUPPRESS already keeps them out of --help either way.
    p.add_argument("--decorative-threshold", type=float, default=1.4, help=argparse.SUPPRESS)
    p.add_argument("--unicase-threshold", type=float, default=0.05, help=argparse.SUPPRESS)
    p.add_argument("--max-span-ratio", type=float, default=1.5, help=argparse.SUPPRESS)


def _add_grouping_mod_args(p: argparse.ArgumentParser, g: Any) -> None:
    g.add_argument(
        "-m", "--merge", action="append", dest="combine", metavar="GROUP",
        help='merge one group of families per flag, comma-separated inside the flag: '
        '--merge "Font A,Font B" (repeat --merge for further, separate groups — '
        "each flag is one group: -m A -m B does not merge A with B)",
    )
    # Old spelling. Same destination, hidden from help.
    p.add_argument(
        "-c", "--combine", action="append", dest="combine", help=argparse.SUPPRESS,
    )
    g.add_argument(
        "-i", "--ignore-term", action="append", metavar="TERM",
        help="drop a whole word from family names before grouping, case-sensitive, "
        "wherever it appears (e.g. Adobe, LT); repeatable, or comma-separated",
    )


def _add_line_box_args(g: Any) -> None:
    g.add_argument(
        "--line-box-from", dest="force_baseline_from", default=None, metavar="PATH_OR_GLOB",
        help="copy this file's line box onto the group (path, filename, or filename glob) "
        "instead of the measured plan",
    )
    g.add_argument(
        "--core-only", action="store_true",
        help="with --line-box-from, the named file must be a core style, not an effect or script cut",
    )


def _add_general_args(g: Any, verbose_help: str) -> None:
    g.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    g.add_argument("-v", "--verbose", action="count", default=0, help=verbose_help)


def _add_help(
    g: Any,
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

def build_probe_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ebrium probe",
        usage="%(prog)s [options] [PATH ...]",
        allow_abbrev=False,
        description="Read-only metrics for every font. Groups by family, shows the "
        "driver and each font's pull, and lists slider facts for variable fonts. "
        "Does not modify fonts.",
        add_help=False,
    )
    g_in = p.add_argument_group("input")
    g_out = p.add_argument_group("report")
    g_gen = p.add_argument_group("general")

    examples = [
        ("ebrium probe fonts/ -r", "metrics tables, grouped by family"),
        ("ebrium probe fonts/ -r -q -o probe.tsv", "write the same rows to a spreadsheet"),
    ]

    _add_help(
        g_gen,
        panel=False,  # fonts are not modified; no safety wording needed
        footer=[
            examples_section(examples),
            exit_status_section(PROBE_EXIT_CODES),
            line_section("formats", FORMATS_LINE),
            docs_section(DOCS_URL),
        ],
    )
    g_out.add_argument(
        "-o", "--output", metavar="FILE",
        help="write a tab-separated metrics sheet as the run goes (kept if you stop early). "
        "A relative FILE is saved at the top of the directory you probed, not the "
        "shell's current directory",
    )
    g_out.add_argument(
        "-q", "--quiet", action="store_true",
        help="terminal shows the current filename and a progress bar, then the tally; "
        "per-font lines go to --output only",
    )
    _add_general_args(
        g_gen, "-v adds the compact hhea, typo, and Win table; -vv uses one table with each value in its own column"
    )
    _add_input_args(g_in)
    return p

# ---------------------------------------------------------------- top level

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        usage="%(prog)s [options] [PATH ...]\n       %(prog)s probe [options] [PATH ...]",
        allow_abbrev=False,
        description=(
            "Give each family one centered line box. Outlines do not move. "
            "Effect cuts inherit that box. Optical sizes each keep their own. "
            "ebrium probe reads those metrics and does not write."
        ),
        add_help=False,
    )
    g_in = p.add_argument_group("input")
    g_run = p.add_argument_group("preview")
    g_plan = p.add_argument_group("plan")
    g_gen = p.add_argument_group("general")

    examples = [
        ("ebrium fonts/ -r -n", "preview"),
        ("ebrium fonts/ --span 120", "tighter line box"),
        ("ebrium fonts/ --line-gap 5", "a little space between lines"),
    ]
    notes = [
        "The plan is cap height, centered, at least 130% of the em. "
        "A taller accent or a deeper descender can raise one side.",
        "Shadow, Extrude, Fine, and similar effect cuts inherit the family's box. "
        "Caption, Display, Subhead, and Small Text each get their own.",
        "--no-cluster skips that plan. The family shares one box set to its outline extremes, so nothing clips.",
        "--span is the letter-span floor, as a percent of the em (default 130). "
        "120 is tighter, 150 is looser. A measured accent can still raise it.",
        "--line-gap adds space between lines, as a percent of the em (default 0). "
        "0 means the box itself is the line spacing. 5 is slightly looser.",
        CHECKPOINT_NOTE,
    ]
    _add_help(
        g_gen,
        panel=safety_panel(message=PANEL_MESSAGE, rows=PANEL_ROWS_BASIC),
        footer=[
            choices_section("commands", {
                PROG: "write the centered line box",
                f"{PROG} probe": "read metrics and write nothing",
            }),
            examples_section(examples),
            notes_section(notes),
            exit_status_section(EXIT_CODES),
            docs_section(DOCS_URL),
        ],
    )
    _add_input_args(g_in)
    _add_preview_args(g_run)
    g_plan.add_argument(
        "--span",
        type=float,
        default=130,
        metavar="PERCENT",
        help="letter-span floor as a percent of the em (default: 130). "
        "Tighter 120, looser 150. A measured accent may still raise it",
    )
    g_plan.add_argument(
        "--line-gap",
        type=float,
        default=0,
        metavar="PERCENT",
        help="extra space between lines as a percent of the em (default: 0). "
        "5 is slightly looser",
    )
    g_plan.add_argument(
        "--no-cluster",
        action="store_true",
        help="one shared box from the family's outline extremes, so nothing clips. "
        "Skips the centered plan. Formerly --safe-max",
    )
    _add_general_args(g_gen, "verbose output; -vv for debug output")
    return p


def finalize_args(args: argparse.Namespace) -> None:
    """Grouping is always by family. --no-cluster switches the plan to outline extremes."""
    if getattr(args, "mode", None) == "probe":
        args.plan_mode = None
        args.grouping_mode = "family"
    else:
        args.mode = None
        if getattr(args, "no_cluster", False):
            args.grouping_mode = "conservative"
            args.plan_mode = "conservative"
        else:
            args.grouping_mode = "family"
            args.plan_mode = "family"

    args.safe_hhea = False
    args.force_baseline = False
    args.force_baseline_main_cluster = False
    args.force_baseline_from = None
    args.combine = None
    args.ignore_term = None
    args.exclude = None
    args.report = False
    args.no_auto_adjust = False
    args.max_adjustment = None
    args.assume_script = None
    args.assume_decorative = None
    args.assume_unicase = None
    args.assume_uniwidth = None
    args.letter_height = getattr(args, "span", 130)
    args.top_margin = 25
    args.max_span_ratio = 1.5
    args.decorative_threshold = 1.4
    args.unicase_threshold = 0.05
