"""Springy line-box planning: solo spring → peer median → attract toward 1300.

Experimental path for `ebrium springy`. Cap-anchored, baseline-fixed.
X-height only nudges the attractor. Script/decorative faces are excluded from
the median but inherit the shared typo; Win uses full-group outline extremes.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import FontCore.core_console_styles as cs
from FontCore.core_console_styles import get_console

from .config import MetricsConfig
from .models import FontMeasures
from .planning import (
    Verbosity,
    compute_descender_for_centering,
    compute_family_normalized_extremes,
    finalize_metrics,
)

console = get_console()

XHEIGHT_PIVOT = 0.66
DEFAULT_BLEND = 0.4  # weight toward the 1300 attractor (rest keeps the median)


def springy_attractor(
    x_height: Optional[int],
    cap_h: Optional[int],
    config: MetricsConfig,
) -> float:
    """UPM-relative span attractor: floor at target_span, soft bump for large x/cap."""
    base = config.target_span
    if not config.adapt_for_xheight or not x_height or not cap_h or cap_h <= 0:
        return base
    x_ratio = x_height / float(cap_h)
    extra = config.xheight_softener * max(0.0, x_ratio - XHEIGHT_PIVOT)
    return min(1.6, base + extra)


def _cap(fm: FontMeasures) -> int:
    cap = fm.cap_optical or fm.cap_height
    if cap and cap > 0:
        return int(cap)
    return int(round(0.7 * fm.upm))


def _top_margin(fm: FontMeasures, config: MetricsConfig) -> float:
    if fm.is_unicase:
        return config.top_margin * 0.65
    return config.top_margin


def solo_spring(
    fm: FontMeasures, config: MetricsConfig
) -> Tuple[float, int, int, float]:
    """Cap-anchored solo spring toward this font's attractor.

    Returns (span_norm, typo_asc, typo_desc, attractor).
    Expands 60/40 when short of the attractor; does not shrink below the seed box.
    """
    upm = fm.upm
    cap = _cap(fm)
    typo_asc = int(round(cap + _top_margin(fm, config) * upm))
    # Centering only — do not deepen to real descender ink (that is Win overhang).
    desired_desc = compute_descender_for_centering(typo_asc, cap, actual_desc=None)
    attract = springy_attractor(fm.x_height, cap, config)
    target_span = int(round(attract * upm))
    span = typo_asc + abs(desired_desc)
    if span < target_span:
        extra = target_span - span
        typo_asc += int(round(extra * 0.6))
        desired_desc -= int(round(extra * 0.4))
    span_norm = (typo_asc + abs(desired_desc)) / float(upm)
    return span_norm, typo_asc, desired_desc, attract


def _is_outlier(fm: FontMeasures) -> bool:
    """Faces that must not pull the peer median (still inherit shared typo)."""
    return bool(
        getattr(fm, "is_script", False)
        or getattr(fm, "is_decorative_candidate", False)
        or getattr(fm, "is_decorative_outlier", False)
    )


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values))


def plan_springy_group(
    group: List[FontMeasures],
    config: MetricsConfig,
    verbosity: Verbosity = Verbosity.BRIEF,
    fam: str = "",
) -> Tuple[float, float, float]:
    """Plan one peer group with the springy policy.

    Returns (fam_min, fam_max, shared_asc_norm) for family_plans bookkeeping.
    """
    if not group:
        return (-1.0, 1.0, 0.95)

    fam_min, fam_max = compute_family_normalized_extremes(group)
    blend = getattr(config, "springy_blend", DEFAULT_BLEND)
    blend = min(1.0, max(0.0, float(blend)))

    core = [fm for fm in group if not _is_outlier(fm)]
    outliers = [fm for fm in group if _is_outlier(fm)]
    if not core:
        core = list(group)
        outliers = []

    solo_spans: List[float] = []
    for fm in core:
        span_n, _, _, _ = solo_spring(fm, config)
        solo_spans.append(span_n)

    median_span = _median(solo_spans)
    # Pull toward the configured letter-height floor (default 1.30), not the
    # x-height-bumped solo attractor — solos already sit on that attractor.
    floor = config.target_span
    span_star = (1.0 - blend) * median_span + blend * floor

    # Shared box from max cap in the core (UPM-normalized), then expand to span*
    cap_ratios = [_cap(fm) / float(fm.upm) for fm in core if fm.upm > 0]
    max_cap = max(cap_ratios) if cap_ratios else 0.7
    # Use the most common top_margin policy in core (unicase-only → softer)
    unicase_only = all(fm.is_unicase for fm in core)
    top = config.top_margin * (0.65 if unicase_only else 1.0)
    norm_typo_asc = max_cap + top
    norm_desc = -(norm_typo_asc - max_cap)  # == -top before expand
    # Do not deepen typo to the heaviest descender — that ink overhangs into Win.
    norm_span = norm_typo_asc + abs(norm_desc)
    if norm_span < span_star:
        extra = span_star - norm_span
        norm_typo_asc += extra * 0.6
        norm_desc -= extra * 0.4

    label = fam or "group"
    if verbosity >= Verbosity.BRIEF:
        cs.StatusIndicator("info").add_message(
            f"[field]Family:[/field] '{label}' — "
            f"[bold]springy[/bold]: {cs.fmt_count(len(core))} core"
            + (
                f", {cs.fmt_count(len(outliers))} outlier(s) inherit typo"
                if outliers
                else ""
            )
        ).add_item(
            f"solo median span {median_span:.3f} · floor {floor:.3f} · "
            f"blend {blend:.0%} → shared {span_star:.3f} "
            f"(typo ≈ {norm_typo_asc:.3f} / {norm_desc:.3f})",
            indent_level=1,
        ).emit(console)

    for fm in group:
        upm = fm.upm
        fm.target_win_asc = int(
            round(max(fam_max * upm * (1.0 + config.win_buffer), 0))
        )
        fm.target_win_desc = int(
            round(abs(fam_min * upm) * (1.0 + config.win_buffer))
        )
        fm.target_typo_asc = int(round(norm_typo_asc * upm))
        fm.target_typo_desc = int(round(norm_desc * upm))
        # Script faces: slightly roomier Win buffer
        if fm.is_script and config.script_win_buffer_multiplier > 1.0:
            extra = config.win_buffer * (config.script_win_buffer_multiplier - 1.0)
            fm.target_win_asc = int(round(max(fam_max * upm * (1.0 + config.win_buffer + extra), 0)))
            fm.target_win_desc = int(
                round(abs(fam_min * upm) * (1.0 + config.win_buffer + extra))
            )
        finalize_metrics(fm)

    if verbosity >= Verbosity.VERBOSE and outliers:
        names = ", ".join(Path(fm.path).name for fm in outliers[:8])
        more = "…" if len(outliers) > 8 else ""
        cs.StatusIndicator("info").add_message(
            f"Outliers inheriting shared typo (Win from group extremes): {names}{more}"
        ).emit(console)

    return fam_min, fam_max, norm_typo_asc
