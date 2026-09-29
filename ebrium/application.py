"""Application functions for applying metrics to font files."""

import os
import shutil
from enum import Enum
from typing import Optional

import FontCore.core_console_styles as cs
from FontCore.core_console_styles import get_console

from . import font_io
from . import models

console = get_console()
FontMeasures = models.FontMeasures


class ApplyStatus(Enum):
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    ERROR = "error"
    PREVIEW = "preview"


def _or_old(new: Optional[int], old: int) -> int:
    """A planned 0 is a real value. Only a missing plan keeps the stored number."""
    return old if new is None else int(new)


def measured_os2_heights(fm: FontMeasures, os2) -> dict[str, int]:
    """Glyph x-height and cap height, when the OS/2 table can store them.

    Version 2 added ``sxHeight`` and ``sCapHeight``. An older table drops
    those fields on save, so writing them would change nothing and the next
    run would try again. A missing glyph measurement is left alone.
    """
    if os2 is None or int(getattr(os2, "version", 0) or 0) < 2:
        return {}
    heights: dict[str, int] = {}
    if fm.x_height and fm.x_height > 0:
        heights["sxHeight"] = int(fm.x_height)
    if fm.cap_height and fm.cap_height > 0:
        heights["sCapHeight"] = int(fm.cap_height)
    return heights


def _note_old_os2(indicator, os2) -> None:
    """Say when the typo box cannot be selected. Versioning stays elsewhere."""
    if os2 is None:
        return
    version = int(getattr(os2, "version", 0) or 0)
    if version >= 4:
        return
    indicator.add_item(
        "Use Typo Metrics is not set (OS/2 is older than version 4)",
        indent_level=1,
    )


def apply_metrics(fp: str, fm: FontMeasures, dry_run: bool) -> tuple[ApplyStatus, str]:
    """Apply computed metrics to font file."""
    font = None
    tmp = None
    try:
        font = font_io._read_ttfont(fp)
        orig_flavor = getattr(font, "flavor", None)

        old_vals: dict[str, int] = {}
        new_vals: dict[str, int] = {}

        os2 = font["OS/2"] if "OS/2" in font else None
        hhea = font["hhea"] if "hhea" in font else None

        # Gather old values
        if os2:
            old_vals["usWinAscent"] = int(getattr(os2, "usWinAscent", 0) or 0)
            old_vals["usWinDescent"] = int(getattr(os2, "usWinDescent", 0) or 0)
            old_vals["sTypoAscender"] = int(getattr(os2, "sTypoAscender", 0) or 0)
            old_vals["sTypoDescender"] = int(getattr(os2, "sTypoDescender", 0) or 0)
            old_vals["sTypoLineGap"] = int(getattr(os2, "sTypoLineGap", 0) or 0)
            old_vals["sxHeight"] = int(getattr(os2, "sxHeight", 0) or 0)
            old_vals["sCapHeight"] = int(getattr(os2, "sCapHeight", 0) or 0)
            old_vals["fsSelection"] = int(getattr(os2, "fsSelection", 0) or 0)
        if hhea:
            old_vals["hhea.ascent"] = int(getattr(hhea, "ascent", 0) or 0)
            old_vals["hhea.descent"] = int(getattr(hhea, "descent", 0) or 0)
            old_vals["hhea.lineGap"] = int(getattr(hhea, "lineGap", 0) or 0)

        # A font with no plan is left alone, including its line gap.
        has_plan = any(
            value is not None
            for value in (
                fm.target_win_asc,
                fm.target_win_desc,
                fm.target_typo_asc,
                fm.target_typo_desc,
            )
        )
        if not has_plan:
            indicator = (
                cs.StatusIndicator("unchanged")
                .add_file(fp, filename_only=False)
                .add_message("(no plan)")
            )
            _note_old_os2(indicator, os2)
            return ApplyStatus.UNCHANGED, indicator.build()

        # Compute new values (Win >= Typo already enforced in planning phase)
        win_asc = _or_old(fm.target_win_asc, old_vals.get("usWinAscent", 0))
        win_desc = _or_old(fm.target_win_desc, old_vals.get("usWinDescent", 0))
        typ_asc = _or_old(fm.target_typo_asc, old_vals.get("sTypoAscender", 0))
        typ_desc = _or_old(fm.target_typo_desc, old_vals.get("sTypoDescender", 0))
        line_gap = int(getattr(fm, "target_line_gap", 0) or 0)

        new_vals = {
            "usWinAscent": win_asc,
            "usWinDescent": win_desc,
            "sTypoAscender": typ_asc,
            "sTypoDescender": typ_desc,
            "sTypoLineGap": line_gap,
            "hhea.ascent": typ_asc,
            "hhea.descent": typ_desc,
            "hhea.lineGap": line_gap,
        }
        new_vals.update(measured_os2_heights(fm, os2))
        # USE_TYPO_METRICS is part of the plan. Count it even when the
        # ascender, descender, and line gap are already in place.
        if os2 and getattr(os2, "version", 0) >= 4:
            new_vals["fsSelection"] = int(old_vals.get("fsSelection", 0)) | (1 << 7)

        # Determine changes
        diff_keys = [k for k, v in new_vals.items() if old_vals.get(k) != v]
        if not diff_keys:
            indicator = (
                cs.StatusIndicator("unchanged")
                .add_file(fp, filename_only=False)
                .add_message("(no metric changes)")
            )
            _note_old_os2(indicator, os2)
            return ApplyStatus.UNCHANGED, indicator.build()

        # Compute summary
        old_span = old_vals.get("sTypoAscender", 0) + abs(
            old_vals.get("sTypoDescender", 0)
        )
        new_span = new_vals["sTypoAscender"] + abs(new_vals["sTypoDescender"])
        span_diff = ((new_span - old_span) / float(fm.upm)) * 100 if fm.upm > 0 else 0

        # Format UPM indicator if different from family majority
        upm_note = ""
        if fm.family_upm_majority is not None and fm.upm != fm.family_upm_majority:
            upm_note = f" [dim](UPM: {fm.upm}, family majority: {fm.family_upm_majority})[/dim]"

        if dry_run:
            indicator = cs.StatusIndicator("updated", dry_run=True).add_file(
                fp, filename_only=False
            )
            if upm_note:
                indicator.add_message(upm_note.strip())

            # Group OS/2 metrics
            os2_keys = [
                k
                for k in diff_keys
                if k
                in [
                    "usWinAscent",
                    "usWinDescent",
                    "sTypoAscender",
                    "sTypoDescender",
                    "sTypoLineGap",
                    "sxHeight",
                    "sCapHeight",
                    "fsSelection",
                ]
            ]
            if os2_keys:
                indicator.add_item("[bold]OS/2 table:[/bold]", indent_level=0)
                for k in os2_keys:
                    old_v = old_vals.get(k, "—")
                    new_v = new_vals.get(k, "—")
                    if k == "fsSelection":
                        # Show USE_TYPO_METRICS bit state
                        old_bit7 = "set" if (int(old_v) & (1 << 7)) else "clear"
                        new_bit7 = "set" if (int(new_v) & (1 << 7)) else "clear"
                        indicator.add_item(
                            f"fsSelection (USE_TYPO_METRICS): {old_bit7} → {new_bit7}",
                            indent_level=1,
                        )
                    else:
                        indicator.add_item(
                            f"{k}: {cs.fmt_change(str(old_v), str(new_v))}",
                            indent_level=1,
                        )

            # Group hhea metrics
            hhea_keys = [k for k in diff_keys if k.startswith("hhea.")]
            if hhea_keys:
                indicator.add_item("[bold]hhea table:[/bold]", indent_level=0)
                for k in hhea_keys:
                    short_name = k.replace("hhea.", "")
                    indicator.add_item(
                        f"{short_name}: {cs.fmt_change(str(old_vals.get(k, '—')), str(new_vals.get(k, '—')))}",
                        indent_level=1,
                    )
            indicator.add_item(
                f"[dim]vertical span:[/dim] {old_span} → {new_span} ({span_diff:+.1f}% UPM)",
                indent_level=1,
            )
            _note_old_os2(indicator, os2)
            return ApplyStatus.PREVIEW, indicator.build()

        # Apply changes
        if os2:
            os2.usWinAscent = int(win_asc)
            os2.usWinDescent = int(win_desc)
            os2.sTypoAscender = int(typ_asc)
            os2.sTypoDescender = int(typ_desc)
            os2.sTypoLineGap = line_gap
            if "sxHeight" in new_vals:
                os2.sxHeight = new_vals["sxHeight"]
            if "sCapHeight" in new_vals:
                os2.sCapHeight = new_vals["sCapHeight"]
            if "fsSelection" in new_vals:
                os2.fsSelection = new_vals["fsSelection"]
        if hhea:
            hhea.ascent = int(typ_asc)
            hhea.descent = int(typ_desc)
            hhea.lineGap = line_gap

        font.flavor = orig_flavor
        # Write through a symlink to the real file, and replace that file only
        # after the font handle is closed. Windows refuses to replace an open file.
        real = os.path.realpath(fp)
        tmp = f"{real}.ebrium-tmp"
        if str(real).lower().endswith(".ttx"):
            font.saveXML(tmp)
        else:
            font.save(tmp)
        font.close()
        font = None
        shutil.copymode(real, tmp)
        os.replace(tmp, real)
        tmp = None

        # Format UPM indicator if different from family majority
        upm_note = ""
        if fm.family_upm_majority is not None and fm.upm != fm.family_upm_majority:
            upm_note = f" [dim](UPM: {fm.upm}, family majority: {fm.family_upm_majority})[/dim]"

        # Compose report with grouped metrics using StatusIndicator
        indicator = cs.StatusIndicator("updated").add_file(fp, filename_only=False)
        if upm_note:
            indicator.add_message(upm_note.strip())

        # Group OS/2 metrics
        os2_keys = [
            k
            for k in diff_keys
            if k
            in [
                "usWinAscent",
                "usWinDescent",
                "sTypoAscender",
                "sTypoDescender",
                "sTypoLineGap",
                "sxHeight",
                "sCapHeight",
                "fsSelection",
            ]
        ]
        if os2_keys:
            indicator.add_item("[bold]OS/2 table:[/bold]", indent_level=0)
            for k in os2_keys:
                old_v = old_vals.get(k, "—")
                new_v = new_vals.get(k, "—")
                if k == "fsSelection":
                    # Show USE_TYPO_METRICS bit state
                    old_bit7 = "set" if (int(old_v) & (1 << 7)) else "clear"
                    new_bit7 = "set" if (int(new_v) & (1 << 7)) else "clear"
                    indicator.add_item(
                        f"fsSelection (USE_TYPO_METRICS): {old_bit7} → {new_bit7}",
                        indent_level=1,
                    )
                else:
                    indicator.add_item(
                        f"{k}: {cs.fmt_change(str(old_v), str(new_v))}", indent_level=1
                    )

        # Group hhea metrics
        hhea_keys = [k for k in diff_keys if k.startswith("hhea.")]
        if hhea_keys:
            indicator.add_item("[bold]hhea table:[/bold]", indent_level=0)
            for k in hhea_keys:
                short_name = k.replace("hhea.", "")
                indicator.add_item(
                    f"{short_name}: {cs.fmt_change(str(old_vals.get(k, '—')), str(new_vals.get(k, '—')))}",
                    indent_level=1,
                )
        indicator.add_item(
            f"[dim]vertical span:[/dim] {old_span} → {new_span} ({span_diff:+.1f}% UPM)",
            indent_level=1,
        )

        _note_old_os2(indicator, os2)
        msg = indicator.build()
        return ApplyStatus.UPDATED, msg

    except Exception as e:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        indicator = (
            cs.StatusIndicator("error")
            .add_file(fp, filename_only=False)
            .with_explanation(str(e))
        )
        return ApplyStatus.ERROR, indicator.build()
    finally:
        if font is not None:
            try:
                font.close()
            except Exception:
                pass
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def process_all(measures, dry_run=False):
    updated = unchanged = errors = 0
    for fm in measures:
        status, msg = apply_metrics(fm.path, fm, dry_run=dry_run)
        if status in (ApplyStatus.UPDATED, ApplyStatus.PREVIEW):
            updated += 1
        elif status is ApplyStatus.ERROR:
            errors += 1
        else:
            unchanged += 1
        cs.emit(msg, console=console)

    cs.emit("")
    cs.StatusIndicator("success", dry_run=dry_run).add_message(
        "Processing Completed!"
    ).with_summary_block(updated=updated, unchanged=unchanged, errors=errors).emit(
        console
    )

    return updated, unchanged, errors
