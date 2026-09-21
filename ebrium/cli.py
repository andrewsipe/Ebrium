"""CLI parsing and main orchestration."""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# Checkout fallback: product root (sibling FontCore/) on path when not installed
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import FontCore.core_console_styles as cs
from FontCore.core_console_styles import get_console
from FontCore.core_file_collector import collect_font_files
from FontCore.core_logging_config import Verbosity

from . import application
from . import checkpoints
from . import config
from . import grouping
from . import measurements
from . import models
from . import planning
from . import validation

console = get_console()
MetricsConfig = config.MetricsConfig
FontMeasures = models.FontMeasures

# Import functions from modules
measure_fonts = measurements.measure_fonts
save_measurements_checkpoint = checkpoints.save_measurements_checkpoint
load_measurements_checkpoint = checkpoints.load_measurements_checkpoint
group_families = grouping.group_families
build_plans = planning.build_plans
report_changes = validation.report_changes
generate_family_report = validation.generate_family_report
process_all = application.process_all
confirm_or_exit = validation.confirm_or_exit
validate_args = validation.validate_args


def scan_fonts(paths: Iterable[str], recursive: bool, include_ttx: bool) -> List[str]:
    files = collect_font_files(paths, recursive)
    if include_ttx:
        return files
    return [f for f in files if Path(f).suffix.lower() != ".ttx"]


def parse_args() -> argparse.Namespace:
    from .cli_parser import build_parser

    return build_parser().parse_args()



def main() -> None:
    start_time = time.time()
    args = parse_args()
    validate_args(args)

    # --report implies --dry-run
    if args.report:
        args.dry_run = True

    if getattr(args, "probe_variation_metrics", False):
        files_probe = scan_fonts(args.paths or ["."], args.recursive, args.use_ttx)
        if not files_probe:
            cs.StatusIndicator("error").add_message("No font files found").emit(console)
            sys.exit(1)
        from . import variation_probe

        variation_probe.run_probe(files_probe, verbose=args.verbose >= 1)
        elapsed = time.time() - start_time
        cs.emit(
            f"{cs.INDENT}[darktext.dim]Total time: [bold]{elapsed:.1f}[/bold]s[/darktext.dim]",
            console=console,
        )
        sys.exit(0)

    # Convert percentage inputs to internal fraction representation
    config = MetricsConfig(
        target_span=(args.letter_height / 100.0) if args.letter_height > 0 else 1.3,
        win_buffer=0.02,
        xheight_softener=0.6,
        adapt_for_xheight=True,
        optical_threshold=0.025,  # Validated optimal threshold (2.5% UPM)
        top_margin=(args.top_margin / 100.0) if args.top_margin >= 0 else 0.25,
        max_adjustment=(args.max_adjustment / 100.0) if args.max_adjustment else None,
        max_span_ratio=args.max_span_ratio,
        decorative_span_threshold=args.decorative_threshold,
        unicase_threshold=args.unicase_threshold,
        auto_adjust_target=not args.no_auto_adjust,
        force_baseline=getattr(args, "force_baseline", False),
        force_baseline_main_cluster_only=getattr(
            args, "force_baseline_main_cluster", False
        ),
        force_baseline_from_pattern=(
            (getattr(args, "force_baseline_from", None) or "").strip() or None
        ),
    )

    files = scan_fonts(args.paths or ["."], args.recursive, args.use_ttx)
    if not files:
        cs.StatusIndicator("error").add_message("No font files found").emit(console)
        sys.exit(1)

    # Determine checkpoint path
    checkpoint_path = Path(".metrics_checkpoint.json")

    # Try to load checkpoint
    loaded_measures: List[FontMeasures] = []
    checkpoint_files: List[str] = []
    cached_clusters: Optional[Dict[str, Dict[str, List[str]]]] = None
    if checkpoint_path.exists():
        try:
            loaded_measures, missing_files, cached_clusters = (
                load_measurements_checkpoint(
                    checkpoint_path, expected_files=files, config=config
                )
            )
            checkpoint_files = [fm.path for fm in loaded_measures]

            if loaded_measures:
                # Check if checkpoint matches current file set
                checkpoint_set = set(checkpoint_files)
                files_set = set(files)
                overlap = len(checkpoint_set & files_set)
                new_files = len(files_set - checkpoint_set)
                removed_files = len(checkpoint_set - files_set)

                # If no overlap, checkpoint is useless - skip it
                if overlap == 0:
                    cs.StatusIndicator("info").add_message(
                        "Checkpoint found but contains no matching fonts (skipping)"
                    ).emit(console)
                    measures = []
                else:
                    # Display checkpoint status with StatusIndicator
                    cs.emit("", console=console)
                    if checkpoint_set == files_set:
                        # Perfect match
                        cs.StatusIndicator("info").add_message(
                            f"Checkpoint found with measurements for all {cs.fmt_count(len(loaded_measures))} fonts"
                        ).add_item(
                            "Using checkpoint would skip all measurement",
                            indent_level=1,
                        ).emit(console)
                        prompt_msg = "Use checkpoint?"
                    elif new_files > 0 and removed_files == 0:
                        # Only new files added
                        cs.StatusIndicator("info").add_message(
                            f"Checkpoint found with measurements for {cs.fmt_count(overlap)} fonts"
                        ).add_item(
                            f"{cs.fmt_count(new_files)} new file(s) would still need measurement",
                            indent_level=1,
                        ).emit(console)
                        prompt_msg = "Use checkpoint for existing measurements?"
                    elif removed_files > 0 and new_files == 0:
                        # Some files removed
                        cs.StatusIndicator("info").add_message(
                            f"Checkpoint found with measurements for {cs.fmt_count(overlap)} fonts"
                        ).add_item(
                            f"({cs.fmt_count(removed_files)} files from checkpoint no longer in current set)",
                            indent_level=1,
                        ).emit(console)
                        prompt_msg = "Use checkpoint? (skips all measurement)"
                    else:
                        # Mixed changes
                        cs.StatusIndicator("info").add_message(
                            f"Checkpoint found: {cs.fmt_count(overlap)} matching fonts"
                        ).add_item(
                            f"{cs.fmt_count(new_files)} new file(s) would need measurement",
                            indent_level=1,
                        ).add_item(
                            f"{cs.fmt_count(removed_files)} file(s) removed from current set",
                            indent_level=1,
                        ).emit(console)
                        prompt_msg = "Use checkpoint for matching fonts?"

                    # Prompt user for checkpoint usage
                    cs.emit("", console=console)
                    resp = cs.prompt_confirm(prompt_msg, default=True)

                    if resp:
                        # Use checkpoint for matching files
                        measures = [
                            fm for fm in loaded_measures if fm.path in files_set
                        ]
                        # Apply exclusion patterns to checkpoint-loaded fonts
                        if args.exclude_measuring:
                            import fnmatch

                            for fm in measures:
                                filename = Path(fm.path).name
                                for pattern in args.exclude_measuring:
                                    if fnmatch.fnmatch(filename, pattern):
                                        fm.is_excluded_from_calculations = True
                                        break
                        # Update files list to only measure missing ones
                        files = [f for f in files if f not in checkpoint_files]

                        if new_files > 0:
                            cs.StatusIndicator("info").add_message(
                                f"Reusing {cs.fmt_count(overlap)} measurements, will measure {cs.fmt_count(new_files)} new file(s)"
                            ).emit(console)
                        else:
                            cs.StatusIndicator("info").add_message(
                                f"Reusing all {cs.fmt_count(len(measures))} measurements from checkpoint"
                            ).emit(console)
                    else:
                        # User wants fresh measurement
                        measures = []
                        cs.StatusIndicator("info").add_message(
                            f"Remeasuring all {cs.fmt_count(len(files))} fonts"
                        ).emit(console)
            else:
                measures = []
        except Exception as e:
            cs.StatusIndicator("warning").add_message(
                f"Error processing checkpoint: {e}. Proceeding with fresh measurement."
            ).emit(console)
            measures = []
    else:
        measures = []

    # Measure fonts (only those not in checkpoint)
    if files:
        cs.StatusIndicator("info").add_message(
            f"Measuring {cs.fmt_count(len(files))} file(s) for bounds and metrics"
        ).emit(console)

        try:
            measures = measure_fonts(
                files,
                existing_measures=measures,
                unicase_threshold=config.unicase_threshold,
                script_span_threshold=config.script_span_threshold,
                script_asymmetry_ratio=config.script_asymmetry_ratio,
                decorative_span_threshold=config.decorative_span_threshold,
                assume_script=args.assume_script,
                assume_decorative=args.assume_decorative,
                assume_unicase=args.assume_unicase,
                assume_uniwidth=args.assume_uniwidth,
                exclude_measuring=args.exclude_measuring,
            )
        except KeyboardInterrupt:
            cs.emit("", console=console)
            cs.StatusIndicator("warning").add_message(
                "Measurement interrupted. Saving partial checkpoint..."
            ).emit(console)
            # Save partial checkpoint before exiting
            if measures:
                save_measurements_checkpoint(measures, checkpoint_path, config=config)
            cs.StatusIndicator("info").add_message(
                f"Partial checkpoint saved to {checkpoint_path}"
            ).emit(console)
            sys.exit(0)

    if not measures:
        cs.StatusIndicator("error").add_message("No measurable fonts found").emit(
            console
        )
        sys.exit(2)

    # Save checkpoint after successful measurement (clusters will be saved after build_plans)
    save_measurements_checkpoint(measures, checkpoint_path, config=config)

    cs.emit("", console=console)
    # Collect forced groups from --combine argument
    forced_groups = []
    if args.combine:
        for group_str in args.combine:
            families = [name.strip() for name in group_str.split(",")]
            if len(families) < 2:
                cs.StatusIndicator("warning").add_message(
                    f"--combine requires at least 2 families, skipping: {group_str}"
                ).emit(console)
                continue
            forced_groups.append(families)
    families = group_families(args, measures, forced_groups)
    cs.emit("", console=console)

    # Map verbose count to Verbosity enum: 0=BRIEF, 1=VERBOSE, 2+=DEBUG
    verbosity = (
        Verbosity.DEBUG
        if args.verbose >= 2
        else (Verbosity.VERBOSE if args.verbose >= 1 else Verbosity.BRIEF)
    )
    family_plans, clusters_cache = build_plans(
        families,
        config,
        verbosity=verbosity,
        cached_clusters=cached_clusters,
        grouping_mode=args.grouping_mode,
        force_hhea=args.safe_hhea,
    )

    # Save checkpoint with cluster information
    save_measurements_checkpoint(
        measures, checkpoint_path, config=config, clusters=clusters_cache
    )

    if args.report:
        # Generate detailed impact report
        generate_family_report(families, config, args)
        cs.emit("")
        cs.StatusIndicator("info").add_message(
            "Report complete. Use --dry-run to preview changes or remove --report to apply."
        ).emit(console)
        sys.exit(0)

    any_changes_needed = report_changes(families, family_plans, args, forced_groups)

    if not any_changes_needed:
        elapsed = time.time() - start_time
        cs.emit("")
        cs.StatusIndicator("success").add_message(
            "All families already normalized!"
        ).emit(console)
        cs.emit(
            f"{cs.INDENT}[darktext.dim]Total time: [bold]{elapsed:.1f}[/bold]s[/darktext.dim]",
            console=console,
        )
        sys.exit(0)

    if args.dry_run:
        process_all(measures, dry_run=True)
        cs.emit(
            f"{cs.INDENT}[darktext.dim]Total time: [bold]{time.time() - start_time:.1f}[/bold]s[/darktext.dim]",
            console=console,
        )
        return

    if not args.yes:
        confirm_or_exit(len(measures))

    process_all(measures, dry_run=False)
    cs.emit(
        f"{cs.INDENT}[darktext.dim]Total time: [bold]{time.time() - start_time:.1f}[/bold]s[/darktext.dim]",
        console=console,
    )
