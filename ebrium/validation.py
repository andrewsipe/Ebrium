"""Validation and reporting functions."""

import sys
import argparse

import FontCore.core_console_styles as cs
from FontCore.core_console_styles import get_console

from . import planning

console = get_console()

analyze_family_impact = planning.analyze_family_impact


def validate_args(args: argparse.Namespace) -> None:
    """Nothing left to second-guess. The plan is fixed."""
    return


def confirm_or_exit(count: int) -> None:
    """Prompt for confirmation, looping until clear yes/no response."""
    while True:
        try:
            cs.emit("", console=console)
            response = (
                cs.prompt_input(
                    f"About to modify {cs.fmt_count(count)} file(s). Proceed? [y/N]: "
                )
                .strip()
                .lower()
            )

            if response in ["y", "yes"]:
                cs.emit("", console=console)
                return  # Proceed
            elif response in ["n", "no"]:
                cs.StatusIndicator("error").add_message("Aborted by user").emit(console)
                sys.exit(3)
            elif response == "":
                # Empty string - treat as mistake, re-prompt
                cs.StatusIndicator("warning").add_message(
                    "Please enter 'y' for yes or 'n' for no"
                ).emit(console)
                continue
            else:
                # Invalid input - re-prompt
                cs.StatusIndicator("warning").add_message(
                    f"Invalid input '{response}'. Please enter 'y' for yes or 'n' for no"
                ).emit(console)
                continue
        except (EOFError, KeyboardInterrupt):
            cs.StatusIndicator("error").add_message("Aborted by user").emit(console)
            sys.exit(3)


def report_changes(families, plans, args, forced_groups) -> bool:
    """Report planned changes per family."""
    any_changes_needed = False

    def get_impact_category(fam):
        group = families[fam]
        avg_typo, avg_span, num_fonts, has_changes = analyze_family_impact(group)
        if not has_changes or avg_typo < 0.1:
            return (0, fam)
        elif avg_typo < 2.0:
            return (1, fam)
        elif avg_typo < 8.0:
            return (2, fam)
        else:
            return (3, fam)

    sorted_families = sorted(plans.items(), key=lambda x: get_impact_category(x[0]))

    for fam, (fam_min, fam_max, fam_asc) in sorted_families:
        group = families[fam]
        avg_typo, avg_span, num_fonts, has_changes = analyze_family_impact(group)

        family_label = f"[bold]{fam}[/bold]"
        unique_names = set(fm.family_name for fm in group)
        if len(unique_names) > 1:
            if args.grouping_mode == "superfamily":
                family_label += " [darktext.dim](superfamily)[/darktext.dim]"
            elif forced_groups and any(fam in fg for fg in forced_groups):
                family_label += " [darktext.dim](forced group)[/darktext.dim]"

        if any(fm.is_uniwidth for fm in group):
            family_label += " [darktext.dim](uniwidth)[/darktext.dim]"

        # Adjust label for individual mode
        verbose = int(getattr(args, "verbose", 0) or 0)
        style_word = "style" if num_fonts == 1 else "styles"
        if verbose >= 1:
            upms = {fm.upm for fm in group}
            upm_note = str(next(iter(upms))) if len(upms) == 1 else "mixed"
            detail = f" (planned ascender {fam_asc:.3f} · UPM {upm_note})"
        else:
            detail = ""

        if not has_changes or avg_typo < 0.1:
            cs.StatusIndicator("info").add_message(
                f"{family_label} — {cs.fmt_count(num_fonts)} {style_word} already share a plan{detail}"
            ).emit(console)
            continue

        any_changes_needed = True

        if avg_typo < 2.0:
            impact_type = "minimal"
        elif avg_typo < 8.0:
            impact_type = "moderate"
        else:
            impact_type = "major"

        if abs(avg_span) < 1.0:
            span_info = "Line spacing stays about the same, gaps removed"
        elif avg_span > 0:
            span_info = f"Line spacing grows by ~[count]{avg_span:.0f}[/count]%, gaps removed"
        else:
            span_info = f"Line spacing shrinks by ~[count]{abs(avg_span):.0f}[/count]%, gaps removed"
        if verbose >= 1:
            span_info += f" (edges moved ~[count]{avg_typo:.0f}[/count]% of the em)"

        cs.StatusIndicator("info").add_message(
            f"{family_label} — {cs.fmt_count(num_fonts)} {style_word} matched, one shared plan{detail}"
        ).emit(console)
        cs.StatusIndicator(impact_type).add_message(span_info).emit(console)

    return any_changes_needed

