"""Metrics planning functions for computing normalization targets."""

from pathlib import Path
from typing import Optional

import FontCore.core_console_styles as cs
from FontCore.core_console_styles import get_console
from FontCore.core_logging_config import Verbosity

from . import clustering
from . import config
from . import font_io
from . import models
from .review import emit_review, review_notes, stamp_layered_metrics

console = get_console()
MetricsConfig = config.MetricsConfig
FontMeasures = models.FontMeasures

# Import clustering functions
detect_optical_clusters = clustering.detect_optical_clusters

# Import font I/O for analyze_family_impact
_read_ttfont = font_io._read_ttfont


def detect_uniwidth_family(
    group: list[FontMeasures],
    threshold: float = 0.90,
) -> tuple[bool, float, int, int]:
    """Detect if fonts in a group share identical advance widths (uniwidth).

    A uniwidth family maintains identical advance widths per glyph across all
    styles (weights, slants), so text layout doesn't reflow when switching styles.

    Compares advance widths for sampled codepoints across all family members.
    For mixed-UPM families, widths are normalized before comparison.

    Args:
        group: Font measures to check (should be from the same family)
        threshold: Minimum fraction of consistent codepoints to flag as uniwidth

    Returns:
        (is_uniwidth, score, consistent_count, total_count)
    """
    fonts_with_widths = [
        fm for fm in group if fm.advance_widths and fm.upm > 0
    ]

    if len(fonts_with_widths) < 2:
        return (False, 0.0, 0, 0)

    upms = {fm.upm for fm in fonts_with_widths}
    same_upm = len(upms) == 1

    codepoint_sets = [set(fm.advance_widths.keys()) for fm in fonts_with_widths]
    common_codepoints = codepoint_sets[0]
    for s in codepoint_sets[1:]:
        common_codepoints = common_codepoints & s

    if not common_codepoints:
        return (False, 0.0, 0, 0)

    consistent_count = 0
    total_count = len(common_codepoints)

    for cp in sorted(common_codepoints):
        if same_upm:
            widths = {fm.advance_widths[cp] for fm in fonts_with_widths}
        else:
            widths = {
                round(fm.advance_widths[cp] * 1000 / fm.upm)
                for fm in fonts_with_widths
            }

        if len(widths) == 1:
            consistent_count += 1

    score = consistent_count / total_count if total_count > 0 else 0.0
    is_uniwidth = score >= threshold

    return (is_uniwidth, score, consistent_count, total_count)


def compute_family_normalized_extremes(
    measures: list[FontMeasures],
) -> tuple[float, float]:
    """Compute family-wide extremes in normalized units (handles mixed UPMs)."""
    norm_mins: list[float] = []
    norm_maxs: list[float] = []

    for fm in measures:
        if fm.min_y is None or fm.max_y is None or fm.upm <= 0:
            continue
        norm_mins.append(fm.min_y / fm.upm)
        norm_maxs.append(fm.max_y / fm.upm)

    if not norm_mins or not norm_maxs:
        return (-1.0, 1.0)  # Conservative fallback

    return (min(norm_mins), max(norm_maxs))


def compute_descender_for_centering(
    typo_asc: int, cap_h: int, actual_desc: Optional[int]
) -> int:
    """Center cap height within typo bounds.

    Returns deeper of:
    - Calculated descender (centers caps)
    - Actual descender (prevents clipping)

    Args:
        typo_asc: Typographic ascender value
        cap_h: Cap height value
        actual_desc: Actual measured descender (negative value, or None)

    Returns:
        Descender value (negative integer)
    """
    # Calculate descender that centers cap height within typo bounds
    desired_desc = -(typo_asc - cap_h)

    # Clamp to actual descender to prevent clipping
    # (min because descenders are negative - more negative = deeper)
    if actual_desc is not None:
        return min(desired_desc, actual_desc)

    return desired_desc


def compute_cluster_target_percent(
    cluster: list[FontMeasures],
    config: MetricsConfig,
) -> float:
    """Letter-height floor for the cluster (UPM-relative).

    X-height no longer raises this floor — denser text is a CSS leading concern.
    """
    return config.target_span


def compute_family_normalized_ascender(
    measures: list[FontMeasures], config: MetricsConfig
) -> float:
    """Seed the line box from cap height plus headroom.

    Tall glyphs do not raise this seed. ``plan_typo_box`` deepens the box
    for a measured descender. A tall accent stays in the clipping box.
    """
    cap_ratios: list[float] = []
    is_unicase_cluster = all(fm.is_unicase for fm in measures) and len(measures) > 0

    for fm in measures:
        if fm.upm <= 0:
            continue
        cap = fm.cap_optical or fm.cap_height
        if cap:
            cap_ratios.append(cap / fm.upm)

    if not cap_ratios:
        return 0.85

    top_margin = config.top_margin * 0.65 if is_unicase_cluster else config.top_margin
    return max(cap_ratios) + top_margin


def plan_typo_box(
    *,
    upm: int,
    cap: int,
    typo_asc_seed: int,
    descender_min: Optional[int],
    accented_cap_max: Optional[int],
    accented_cap_missing: bool,
    target_span_norm: float,
) -> tuple[int, int, bool]:
    """Build a typo box: center on caps, then apply measured floors.

    1. Seed ascender, center descender (rule 9: ``asc − cap == |desc|``).
    2. If span is under the letter-height floor, expand **while staying centered**.
    3. Deepen the descender when a measured descender needs it. A tall accent
       does not raise the line box. Win covers it.
    4. If the descender floor needs more than the span target, the span is
       allowed to exceed it.

    Returns ``(typo_asc, typo_desc, exceeded_target)``.
    """
    if upm <= 0:
        upm = 1000
    if cap <= 0:
        cap = int(round(0.7 * upm))

    typo_asc = int(typo_asc_seed)
    # Center only — do not deepen to ink yet (that is a measured floor below).
    desired_desc = compute_descender_for_centering(typo_asc, cap, actual_desc=None)

    target_span = int(round(target_span_norm * upm))
    span = typo_asc + abs(desired_desc)
    if span < target_span:
        # Stay centered: span = 2*asc − cap  ⇒  asc = (span + cap) / 2
        typo_asc = int(round((target_span + cap) / 2.0))
        desired_desc = -(typo_asc - cap)

    # A deep descender can lower this side. Accents stay in Win.
    if descender_min is not None and desired_desc > descender_min:
        # descender_min is more negative when deeper
        desired_desc = int(descender_min)

    final_span = typo_asc + abs(desired_desc)
    exceeded = final_span > target_span + 1  # 1-unit tolerance for rounding
    return typo_asc, desired_desc, exceeded


def cap_norm(fm: FontMeasures) -> Optional[float]:
    """Cap height as a fraction of the em."""
    cap = fm.cap_optical or fm.cap_height
    if cap and fm.upm > 0:
        return cap / fm.upm
    return None


def family_cap_anchor(
    group: list[FontMeasures],
    main_cluster: list[FontMeasures],
    config: MetricsConfig,
) -> Optional[float]:
    """Tallest cap in the family, when the heights are not one cluster.

    Short, Normal, and Tall in one family share the tall cap's line box.
    A single height keeps the usual plan.
    """
    fonts = [
        fm
        for fm in group
        if fm.upm > 0
        and not fm.is_script
        and not (fm.is_decorative_outlier and not fm.is_unicase)
    ] or list(main_cluster)
    ratios = [ratio for fm in fonts if (ratio := cap_norm(fm)) is not None]
    if len(ratios) < 2:
        return None
    tallest = max(ratios)
    core = [ratio for fm in main_cluster if (ratio := cap_norm(fm)) is not None]
    core_cap = max(core) if core else tallest
    if tallest - core_cap <= config.optical_threshold:
        return None
    return tallest


def planned_typo_norm(
    fonts: list[FontMeasures],
    config: MetricsConfig,
    norm_asc: Optional[float] = None,
    cap_anchor: Optional[float] = None,
) -> Optional[tuple[float, float, bool]]:
    """Normalized typo ascender, descender, and whether the span exceeded the floor.

    Does not write targets. ``norm_asc`` is the cap-plus-headroom seed; when
    omitted it is computed from ``fonts``.
    """
    if not fonts:
        return None

    if cap_anchor is not None:
        norm_cap_h = cap_anchor
    else:
        cap_height_ratios: list[float] = []
        for fm in fonts:
            ratio = cap_norm(fm)
            if ratio is not None:
                cap_height_ratios.append(ratio)
        if not cap_height_ratios:
            norm_cap_h = 0.7
        else:
            cap_height_ratios.sort()
            n = len(cap_height_ratios)
            norm_cap_h = (
                cap_height_ratios[n // 2]
                if n % 2 == 1
                else (cap_height_ratios[n // 2 - 1] + cap_height_ratios[n // 2]) / 2.0
            )

    accented_norms = [
        fm.accented_cap_max / fm.upm
        for fm in fonts
        if fm.accented_cap_max and fm.upm > 0
    ]
    norm_accented = max(accented_norms) if accented_norms else None
    any_accented_missing = any(fm.accented_cap_missing for fm in fonts)
    norm_descenders = [
        float(fm.descender_min) / float(fm.upm)
        for fm in fonts
        if fm.descender_min and fm.upm > 0
    ]
    norm_desc_floor = min(norm_descenders) if norm_descenders else None
    if norm_asc is None:
        norm_asc = compute_family_normalized_ascender(fonts, config)

    scale = 1000
    typo_asc, typo_desc, exceeded = plan_typo_box(
        upm=scale,
        cap=int(round(norm_cap_h * scale)),
        typo_asc_seed=int(round(norm_asc * scale)),
        descender_min=(
            int(round(norm_desc_floor * scale)) if norm_desc_floor is not None else None
        ),
        accented_cap_max=(
            int(round(norm_accented * scale)) if norm_accented is not None else None
        ),
        accented_cap_missing=any_accented_missing and norm_accented is None,
        target_span_norm=compute_cluster_target_percent(fonts, config),
    )
    return typo_asc / float(scale), typo_desc / float(scale), exceeded


def plan_identical_metrics(
    cluster: list[FontMeasures],
    family_norm_min: float,
    family_norm_max: float,
    family_norm_asc: float,
    config: MetricsConfig,
    verbosity: Verbosity = Verbosity.BRIEF,
    cap_anchor: Optional[float] = None,
) -> None:
    """Apply identical normalization to optically identical fonts.

    Works in normalized units, scales to each font's UPM.
    """
    if not cluster:
        return

    planned = planned_typo_norm(
        cluster, config, norm_asc=family_norm_asc, cap_anchor=cap_anchor
    )
    if planned is None:
        return
    norm_typo_asc, norm_desired_desc, exceeded = planned
    any_accented_missing = any(fm.accented_cap_missing for fm in cluster) and not any(
        fm.accented_cap_max for fm in cluster if fm.upm > 0
    )
    cluster_target = compute_cluster_target_percent(cluster, config)

    if verbosity >= Verbosity.BRIEF and exceeded:
        cs.StatusIndicator("info").add_message(
            "Typo span exceeds letter-height floor after measured clearance "
            f"({(norm_typo_asc + abs(norm_desired_desc)):.3f} > {cluster_target:.3f}) — flagged for review"
        ).emit(console)

    if verbosity >= Verbosity.BRIEF and any_accented_missing:
        cs.StatusIndicator("info").add_message(
            "No accented-capital samples found — re-check when extended Latin / Vietnamese is added"
        ).emit(console)

    # Apply to each font, scaling to its UPM
    for fm in cluster:
        upm = fm.upm
        fm.target_win_asc = int(
            round(max(family_norm_max * upm * (1.0 + config.win_buffer), 0))
        )
        fm.target_win_desc = int(
            round(abs(family_norm_min * upm) * (1.0 + config.win_buffer))
        )
        fm.target_typo_asc = int(round(norm_typo_asc * upm))
        fm.target_typo_desc = int(round(norm_desired_desc * upm))
        fm.span_exceeded_target = exceeded

        if fm.descender_min and fm.target_typo_desc:
            if fm.target_typo_desc > fm.descender_min:
                fm.target_typo_desc = fm.descender_min


def finalize_metrics(fm: FontMeasures) -> None:
    """Ensure Win >= Typo after all planning."""
    if fm.target_win_asc is not None and fm.target_typo_asc is not None:
        fm.target_win_asc = max(fm.target_win_asc, fm.target_typo_asc)
    if fm.target_win_desc is not None and fm.target_typo_desc is not None:
        fm.target_win_desc = max(fm.target_win_desc, abs(fm.target_typo_desc))



def get_cluster_normalized_typo(
    cluster: list[FontMeasures],
) -> tuple[float, float]:
    """Get representative normalized typo metrics from cluster (after all adjustments)."""
    asc_ratios = [
        fm.target_typo_asc / fm.upm
        for fm in cluster
        if fm.target_typo_asc is not None and fm.upm > 0
    ]
    desc_ratios = [
        fm.target_typo_desc / fm.upm
        for fm in cluster
        if fm.target_typo_desc is not None and fm.upm > 0
    ]
    norm_asc = sum(asc_ratios) / len(asc_ratios) if asc_ratios else 0.85
    norm_desc = sum(desc_ratios) / len(desc_ratios) if desc_ratios else -0.25
    return (norm_asc, norm_desc)


def plan_safe_metrics(group: list[FontMeasures], config: MetricsConfig) -> None:
    """Conservative bbox approach - all fonts get same normalized bounds.

    Win and Typo both use family extremes. This guarantees no clipping but
    wastes vertical space. Good for extremely decorative fonts or fonts with
    unexpected outliers (mathematical symbols, dingbats).
    """
    fam_min, fam_max = compute_family_normalized_extremes(group)

    for fm in group:
        upm = fm.upm
        # Win and Typo both use family extremes
        win_asc = int(round(fam_max * upm * (1.0 + config.win_buffer)))
        win_desc = int(round(abs(fam_min * upm) * (1.0 + config.win_buffer)))

        fm.target_win_asc = win_asc
        fm.target_win_desc = win_desc
        fm.target_typo_asc = win_asc
        fm.target_typo_desc = -win_desc
        # Finalize ensures consistency (should be no-op here, but safe)
        finalize_metrics(fm)


def validate_cluster_consistency(cluster: list[FontMeasures]) -> None:
    """Validate that cluster fonts have identical normalized typo ratios."""
    if len(cluster) <= 1:
        return
    asc_ratios = [
        fm.target_typo_asc / fm.upm
        for fm in cluster
        if fm.target_typo_asc is not None and fm.upm > 0
    ]
    desc_ratios = [
        fm.target_typo_desc / fm.upm
        for fm in cluster
        if fm.target_typo_desc is not None and fm.upm > 0
    ]
    if asc_ratios:
        asc_range = max(asc_ratios) - min(asc_ratios)
        if asc_range > 0.001:
            cs.StatusIndicator("warning").add_message(
                f"Cluster normalization inconsistency detected: "
                f"ascender ratio range {asc_range:.6f} (should be < 0.001)"
            ).emit(console)
    if desc_ratios:
        desc_range = max(desc_ratios) - min(desc_ratios)
        if desc_range > 0.001:
            cs.StatusIndicator("warning").add_message(
                f"Cluster normalization inconsistency detected: "
                f"descender ratio range {desc_range:.6f} (should be < 0.001)"
            ).emit(console)


def plan_adaptive_metrics(
    cluster: list[FontMeasures],
    family_norm_min: float,
    family_norm_max: float,
    family_norm_asc: float,
    config: MetricsConfig,
    verbosity: Verbosity = Verbosity.BRIEF,
    cap_anchor: Optional[float] = None,
) -> None:
    """Apply per-font adaptive normalization for varied fonts."""
    for fm in cluster:
        upm = fm.upm

        fm.target_win_asc = int(
            round(max(family_norm_max * upm * (1.0 + config.win_buffer), 0))
        )
        fm.target_win_desc = int(
            round(abs(family_norm_min * upm) * (1.0 + config.win_buffer))
        )

        typo_asc_seed = int(round(family_norm_asc * upm))
        cap_ref = fm.cap_optical or fm.cap_height
        if cap_anchor is not None:
            cap_h = int(round(cap_anchor * upm))
        else:
            cap_h = cap_ref if cap_ref else int(round(0.7 * upm))
        cluster_target = compute_cluster_target_percent([fm], config)

        typo_asc, desired_desc, exceeded = plan_typo_box(
            upm=upm,
            cap=cap_h,
            typo_asc_seed=typo_asc_seed,
            descender_min=fm.descender_min,
            accented_cap_max=fm.accented_cap_max,
            accented_cap_missing=fm.accented_cap_missing,
            target_span_norm=cluster_target,
        )

        fm.target_typo_asc = typo_asc
        fm.target_typo_desc = desired_desc
        fm.span_exceeded_target = exceeded

        if fm.descender_min and fm.target_typo_desc:
            if fm.target_typo_desc > fm.descender_min:
                fm.target_typo_desc = fm.descender_min


def analyze_family_impact(
    measures: list[FontMeasures],
) -> tuple[float, float, int, bool]:
    """Analyze the impact of planned changes.

    Returns: (avg_typo_change_pct, avg_span_change_pct, num_fonts, has_any_changes)
    """
    typo_changes: list[float] = []
    span_changes: list[float] = []
    has_any_changes = False

    for fm in measures:
        try:
            font = _read_ttfont(fm.path)
            os2 = font.get("OS/2")
            hhea = font.get("hhea")
            if not os2:
                font.close()
                continue

            old_typo_asc = int(getattr(os2, "sTypoAscender", 0) or 0)
            old_typo_desc = int(getattr(os2, "sTypoDescender", 0) or 0)
            old_typo_gap = int(getattr(os2, "sTypoLineGap", 0) or 0)
            old_win_asc = int(getattr(os2, "usWinAscent", 0) or 0)
            old_win_desc = int(getattr(os2, "usWinDescent", 0) or 0)
            old_span = old_typo_asc + abs(old_typo_desc)

            old_hhea_asc = int(getattr(hhea, "ascent", 0) or 0) if hhea else 0
            old_hhea_desc = int(getattr(hhea, "descent", 0) or 0) if hhea else 0
            old_hhea_gap = int(getattr(hhea, "lineGap", 0) or 0) if hhea else 0

            new_typo_asc = fm.target_typo_asc or old_typo_asc
            new_typo_desc = fm.target_typo_desc or old_typo_desc
            new_win_asc = fm.target_win_asc or old_win_asc
            new_win_desc = fm.target_win_desc or old_win_desc
            new_span = new_typo_asc + abs(new_typo_desc)
            new_gap = int(getattr(fm, "target_line_gap", 0) or 0)

            if (
                old_typo_asc != new_typo_asc
                or old_typo_desc != new_typo_desc
                or old_win_asc != new_win_asc
                or old_win_desc != new_win_desc
                or old_typo_gap != new_gap
                or old_hhea_gap != new_gap
                or old_hhea_asc != new_typo_asc
                or old_hhea_desc != new_typo_desc
            ):
                has_any_changes = True

            if old_span > 0:
                span_change_pct = ((new_span - old_span) / float(old_span)) * 100.0
                span_changes.append(span_change_pct)

            typo_change = abs(new_typo_asc - old_typo_asc) + abs(
                new_typo_desc - old_typo_desc
            )
            if fm.upm > 0:
                typo_change_pct = (typo_change / float(fm.upm)) * 100.0
                typo_changes.append(typo_change_pct)

            font.close()
        except Exception:
            continue

    avg_typo = sum(typo_changes) / len(typo_changes) if typo_changes else 0.0
    avg_span = sum(span_changes) / len(span_changes) if span_changes else 0.0

    return (avg_typo, avg_span, len(measures), has_any_changes)




def build_plans(
    families: dict[str, list[FontMeasures]],
    config: MetricsConfig,
    verbosity: Verbosity = Verbosity.BRIEF,
    cached_clusters: Optional[dict[str, dict[str, list[str]]]] = None,
    grouping_mode: str = "family",
    review_sink: Optional[dict[str, list[str]]] = None,
    emit_review_report: bool = True,
) -> tuple[dict[str, tuple[float, float, float]], dict[str, dict[str, list[str]]]]:
    """Build normalization plans with optical clustering.

    Returns:
        Tuple of (family_plans, clusters_cache) where:
        - family_plans: Dict mapping family name to (fam_min, fam_max, fam_asc)
        - clusters_cache: Dict mapping family name to cluster assignments
    """
    family_plans = {}
    clusters_cache: dict[str, dict[str, list[str]]] = {}
    review: dict[str, list[str]] = review_sink if review_sink is not None else {}

    def _close(name: str, fonts: list[FontMeasures]) -> None:
        stamp_layered_metrics(fonts, config)
        gap = float(getattr(config, "line_gap", 0.0) or 0.0)
        for fm in fonts:
            fm.target_line_gap = int(round(gap * fm.upm)) if fm.upm > 0 else 0
        review[name] = review_notes(fonts, config)

    for fam, group in families.items():
        # Compute UPM majority for status reporting
        upm_counts: dict[int, int] = {}
        for fm in group:
            upm_counts[fm.upm] = upm_counts.get(fm.upm, 0) + 1
        family_upm_majority = (
            max(upm_counts.items(), key=lambda x: x[1])[0] if upm_counts else None
        )
        # Store in each font measure for status output
        for fm in group:
            fm.family_upm_majority = family_upm_majority

        # Uniwidth detection (family-level)
        if len(group) >= 2:
            is_uni, uni_score, uni_consistent, uni_total = detect_uniwidth_family(
                group, config.uniwidth_consistency_threshold
            )
            if is_uni:
                for fm in group:
                    fm.is_uniwidth = True
                cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"[bold]Uniwidth detected:[/bold] {uni_score:.0%} consistency "
                    f"({cs.fmt_count(uni_consistent)}/{cs.fmt_count(uni_total)} glyphs identical "
                    f"across {cs.fmt_count(len(group))} fonts)"
                ).emit(console)
            elif uni_total > 0 and uni_score >= 0.50:
                cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"[bold]Partial uniwidth:[/bold] {uni_score:.0%} consistency "
                    f"({cs.fmt_count(uni_consistent)}/{cs.fmt_count(uni_total)} glyphs identical) — "
                    f"may contain distinct width classes"
                ).emit(console)

        if grouping_mode == "conservative":
            # Outline extremes for the whole family, so nothing clips.
            plan_safe_metrics(group, config)
            family_plans[fam] = (
                compute_family_normalized_extremes(group)[0],
                compute_family_normalized_extremes(group)[1],
                compute_family_normalized_ascender(group, config),
            )
            _close(fam, group)
            continue

        # Report unicase detection
        unicase_count = sum(1 for fm in group if fm.is_unicase)
        non_unicase_count = len(group) - unicase_count
        if unicase_count > 0:
            unicase_names = [Path(fm.path).name for fm in group if fm.is_unicase]
            if non_unicase_count > 0:
                # Mixed family: unicase will inherit baseline from traditional
                indicator = cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"[bold]Unicase detected:[/bold] {cs.fmt_count(unicase_count)} unicase font(s) "
                    f"mixed with {cs.fmt_count(non_unicase_count)} traditional font(s)"
                )
                if verbosity >= Verbosity.VERBOSE:
                    indicator.add_item(
                        f"Unicase fonts: {', '.join(unicase_names[:5])}{'...' if len(unicase_names) > 5 else ''}",
                        indent_level=1,
                    )
                indicator.add_item(
                    "Unicase fonts will inherit baseline from traditional fonts for alignment",
                    indent_level=1,
                ).emit(console)
            else:
                # Pure unicase family: will cluster normally
                cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"[bold]Pure unicase family:[/bold] {cs.fmt_count(unicase_count)} font(s) "
                    f"(x-height ≈ cap-height, clustering normally)"
                ).emit(console)

        # Level 1: Compute family-wide extremes (in normalized units) - for Win metrics
        fam_min, fam_max = compute_family_normalized_extremes(group)

        # Level 2: Detect optical clusters (always enabled)
        if len(group) > 1:
            if verbosity >= Verbosity.DEBUG:
                cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"[dim]DEBUG:[/dim] Detecting optical clusters from {len(group)} font(s)"
                ).emit(console)
            # Check for cached clusters first
            family_clusters = None
            if cached_clusters and fam in cached_clusters:
                family_clusters = cached_clusters[fam]
                # Validate cached clusters match current font set
                cached_paths = set()
                if family_clusters.get("main_cluster"):
                    cached_paths.update(family_clusters["main_cluster"])
                if family_clusters.get("decorative"):
                    cached_paths.update(family_clusters["decorative"])
                if family_clusters.get("script"):
                    cached_paths.update(family_clusters.get("script", []))
                if family_clusters.get("unicase"):
                    cached_paths.update(family_clusters["unicase"])
                current_paths = {fm.path for fm in group}

                if cached_paths == current_paths:
                    # Reconstruct clusters from cached data
                    path_to_fm = {fm.path: fm for fm in group}
                    clusters = []
                    decorative_outliers = []
                    script_outliers = []
                    main_cluster = []

                    # Reconstruct main cluster
                    if family_clusters.get("main_cluster"):
                        main_cluster = [
                            path_to_fm[path]
                            for path in family_clusters["main_cluster"]
                            if path in path_to_fm
                        ]
                        if main_cluster:
                            clusters.append(main_cluster)

                    # Reconstruct decorative outliers
                    if family_clusters.get("decorative"):
                        decorative_outliers = [
                            path_to_fm[path]
                            for path in family_clusters["decorative"]
                            if path in path_to_fm
                        ]
                        for fm in decorative_outliers:
                            fm.is_decorative_outlier = True

                    # Reconstruct script outliers
                    if family_clusters.get("script"):
                        script_outliers = [
                            path_to_fm[path]
                            for path in family_clusters["script"]
                            if path in path_to_fm
                        ]
                        for fm in script_outliers:
                            # is_script is already set during measurement, but confirm/refine here
                            fm.is_script = True

                    # Reconstruct unicase (already marked in decorative)
                    if family_clusters.get("unicase"):
                        for path in family_clusters["unicase"]:
                            if path in path_to_fm:
                                path_to_fm[path].is_unicase = True
                else:
                    # Paths don't match - invalidate cache and recompute
                    if verbosity >= Verbosity.DEBUG:
                        cs.StatusIndicator("info").add_message(
                            f"Cluster cache invalid for '{fam}' (file set changed) - reclustering"
                        ).emit(console)
                    family_clusters = None
                    main_cluster = []
                    script_outliers = []

            if not family_clusters:
                # No valid cache - compute clusters normally
                clusters, decorative_outliers, script_outliers = (
                    detect_optical_clusters(group, config.optical_threshold, config)
                )
                main_cluster = max(clusters, key=len) if clusters else []
            else:
                # Using cached clusters - main_cluster already set during reconstruction
                pass

            # Report clustering results (main_cluster is now defined in both paths)

            # Report font type detection (script, decorative, unicase)
            # These messages indicate which detector identified which fonts

            # Script detection: 2x+ span AND descender-dominant
            if script_outliers:
                # Calculate span ratios for reporting
                span_ratios = []
                if main_cluster:
                    cluster_spans = [
                        (cfm.max_y - cfm.min_y) / cfm.upm
                        for cfm in main_cluster
                        if cfm.max_y is not None
                        and cfm.min_y is not None
                        and cfm.upm > 0
                    ]
                    avg_cluster_span = (
                        sum(cluster_spans) / len(cluster_spans) if cluster_spans else 0
                    )

                    for fm in script_outliers:
                        if fm.max_y and fm.min_y and fm.upm > 0:
                            fm_span = (fm.max_y - fm.min_y) / fm.upm
                            ratio = (
                                fm_span / avg_cluster_span
                                if avg_cluster_span > 0
                                else 0
                            )
                            span_ratios.append(ratio)

                # Build message with span ratio info
                if span_ratios and verbosity >= Verbosity.VERBOSE:
                    avg_ratio = sum(span_ratios) / len(span_ratios)
                    ratio_text = f"span ratio: {avg_ratio:.1f}x vs cluster avg"
                else:
                    ratio_text = "2x+ span, descender-dominant"

                indicator = cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"[bold]Script detector:[/bold] {cs.fmt_count(len(script_outliers))} font(s) "
                    f"({ratio_text})"
                )
                if verbosity >= Verbosity.VERBOSE:
                    script_names = [Path(fm.path).name for fm in script_outliers]
                    indicator.add_item(
                        f"Detected as script: {', '.join(script_names[:5])}{'...' if len(script_names) > 5 else ''}",
                        indent_level=1,
                    )
                indicator.emit(console)

            # Decorative detection: expanded bounds, core metrics match (but not script/unicase)
            other_decorative = [
                fm
                for fm in decorative_outliers
                if not fm.is_unicase and not fm.is_script
            ]
            if other_decorative:
                span_note = ""
                if main_cluster:
                    cluster_spans = [
                        (cfm.max_y - cfm.min_y) / cfm.upm
                        for cfm in main_cluster
                        if cfm.max_y is not None and cfm.min_y is not None and cfm.upm > 0
                    ]
                    avg_cluster_span = (
                        sum(cluster_spans) / len(cluster_spans) if cluster_spans else 0
                    )
                    ratios = []
                    for fm in other_decorative:
                        if fm.max_y and fm.min_y and fm.upm > 0 and avg_cluster_span > 0:
                            ratios.append((fm.max_y - fm.min_y) / fm.upm / avg_cluster_span)
                    if ratios:
                        span_note = f", span {min(ratios):.2f}–{max(ratios):.2f}× the core"
                cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"{cs.fmt_count(len(other_decorative))} style(s) inherit the core line box"
                    f"{span_note}"
                ).emit(console)

            # Unicase detection: x-height ≈ cap-height
            unicase_in_clusters = sum(
                1 for cluster in clusters for fm in cluster if fm.is_unicase
            )
            unicase_in_decorative = sum(
                1 for fm in decorative_outliers if fm.is_unicase
            )
            if unicase_in_clusters > 0 or unicase_in_decorative > 0:
                total_unicase = unicase_in_clusters + unicase_in_decorative
                if unicase_in_decorative > 0:
                    indicator = cs.StatusIndicator("info").add_message(
                        f"[field]Family:[/field] '{fam}' — "
                        f"[bold]Unicase detector:[/bold] {cs.fmt_count(total_unicase)} font(s) "
                        f"(x-height ≈ cap-height) - separated for baseline alignment"
                    )
                    if verbosity >= Verbosity.VERBOSE:
                        unicase_names = [
                            Path(fm.path).name
                            for fm in decorative_outliers
                            if fm.is_unicase
                        ]
                        indicator.add_item(
                            f"Detected as unicase: {', '.join(unicase_names[:5])}{'...' if len(unicase_names) > 5 else ''}",
                            indent_level=1,
                        )
                    indicator.emit(console)

            # Level 3: Compute typo baseline from CORE CLUSTER only (not decorative outliers)
            if main_cluster:
                core_asc = compute_family_normalized_ascender(main_cluster, config)
            else:
                core_asc = compute_family_normalized_ascender(group, config)

            if len(main_cluster) > 1:
                # Get UPM info
                upms = {fm.upm for fm in main_cluster}
                if len(upms) == 1:
                    upm_info = f"UPM: {list(upms)[0]}"
                else:
                    # Mixed UPMs - show normalized impact
                    upm_counts: dict[int, int] = {}
                    for fm in main_cluster:
                        upm_counts[fm.upm] = upm_counts.get(fm.upm, 0) + 1

                    upm_list = ", ".join(
                        f"{upm} ({count})" for upm, count in sorted(upm_counts.items())
                    )

                    # Calculate normalization variance
                    cap_ratios = [
                        (fm.cap_optical or fm.cap_height) / fm.upm
                        for fm in main_cluster
                        if (fm.cap_optical or fm.cap_height) and fm.upm > 0
                    ]

                    if cap_ratios:
                        mean_cap_ratio = sum(cap_ratios) / len(cap_ratios)
                        variance = sum(
                            (r - mean_cap_ratio) ** 2 for r in cap_ratios
                        ) / len(cap_ratios)
                        std_dev = variance**0.5
                        cv = (
                            (std_dev / mean_cap_ratio * 100)
                            if mean_cap_ratio != 0
                            else 0.0
                        )

                        if cv < 1.0:
                            quality = "excellent normalization"
                        elif cv < 2.5:
                            quality = "good normalization"
                        else:
                            quality = "significant variance"

                        upm_info = f"[warning]Mixed UPM: {upm_list}[/warning] ([dim]{quality}, CV={cv:.1f}%[/dim])"
                    else:
                        upm_info = f"[warning]Mixed UPM: {upm_list}[/warning]"

                cluster_msg = (
                    f"[field]Family:[/field] '{fam}' — "
                    f"Core cluster: {cs.fmt_count(len(main_cluster))} fonts"
                )
                if verbosity >= Verbosity.VERBOSE:
                    cluster_msg += (
                        f" (cap height ≈ {main_cluster[0].cap_height}/{main_cluster[0].upm} = "
                        f"{(main_cluster[0].cap_height or 0) / main_cluster[0].upm:.3f})"
                    )
                cluster_msg += f" | {upm_info}"
                if verbosity >= Verbosity.BRIEF:
                    cs.StatusIndicator("info").add_message(cluster_msg).emit(console)

            if decorative_outliers:
                unicase_outliers = [fm for fm in decorative_outliers if fm.is_unicase]

                if unicase_outliers:
                    indicator = cs.StatusIndicator("info").add_message(
                        f"[field]Family:[/field] '{fam}' — "
                        f"[bold]Unicase baseline preservation:[/bold] {cs.fmt_count(len(unicase_outliers))} font(s)"
                    )
                    if verbosity >= Verbosity.VERBOSE:
                        outlier_names = [Path(fm.path).name for fm in unicase_outliers]
                        indicator.add_item(
                            f"Unicase fonts: {', '.join(outlier_names[:5])}{'...' if len(outlier_names) > 5 else ''}",
                            indent_level=1,
                        )
                    indicator.add_item(
                        "Aligned by x-height (not cap-height) to maintain baseline alignment with traditional fonts",
                        indent_level=1,
                    ).emit(console)

            # Report script font handling (already reported detection above, this is for processing)
            if script_outliers and verbosity >= Verbosity.VERBOSE:
                cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"Script fonts will inherit core typo metrics and expand win bounds with {config.script_win_buffer_multiplier}x buffer"
                ).emit(console)

            # Level 4: Apply normalization per cluster.
            # Several heights in one family share the tallest cap's line box.
            cap_anchor = family_cap_anchor(group, main_cluster, config)
            if cap_anchor is not None and verbosity >= Verbosity.BRIEF:
                cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"heights share one line box, centered on the tallest cap"
                ).emit(console)
            if verbosity >= Verbosity.DEBUG:
                cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"[dim]DEBUG:[/dim] Level 4: Processing {len(clusters)} cluster(s)"
                ).emit(console)
            for cluster in clusters:
                # Skip decorative outliers if they somehow ended up in clusters
                cluster_fonts = [
                    fm
                    for fm in cluster
                    if not getattr(fm, "is_decorative_outlier", False)
                ]
                decorative_in_cluster = [
                    fm for fm in cluster if getattr(fm, "is_decorative_outlier", False)
                ]
                if decorative_in_cluster and verbosity >= Verbosity.DEBUG:
                    decorative_names = [
                        Path(fm.path).name for fm in decorative_in_cluster
                    ]
                    cs.StatusIndicator("warning").add_message(
                        f"[field]Family:[/field] '{fam}' — "
                        f"WARNING: Decorative fonts found in clusters (should not happen): {', '.join(decorative_names)}"
                    ).emit(console)
                if not cluster_fonts:
                    continue  # Skip clusters that only contain decorative outliers

                if len(cluster_fonts) > 1:
                    # Core cluster: identical metrics (normalized across UPMs)
                    plan_identical_metrics(
                        cluster_fonts,
                        fam_min,
                        fam_max,
                        core_asc,
                        config,
                        verbosity,
                        cap_anchor=cap_anchor,
                    )
                else:
                    # True outlier: compute own ascender (don't use main cluster's)
                    outlier_asc = compute_family_normalized_ascender(
                        cluster_fonts, config
                    )
                    plan_adaptive_metrics(
                        cluster_fonts,
                        fam_min,
                        fam_max,
                        outlier_asc,
                        config,
                        verbosity,
                        cap_anchor=cap_anchor,
                    )

            # Level 5: FINALIZE: Ensure Win >= Typo for ALL fonts (before decorative inheritance)
            if verbosity >= Verbosity.DEBUG:
                cs.StatusIndicator("info").add_message(
                    f"[field]Family:[/field] '{fam}' — "
                    f"[dim]DEBUG:[/dim] Level 5: Finalizing metrics for {len(group)} font(s)"
                ).emit(console)
            for fm in group:
                finalize_metrics(fm)

            # Level 7: Now get normalized typo from main cluster (after finalization)
            if decorative_outliers:
                if verbosity >= Verbosity.DEBUG:
                    cs.StatusIndicator("info").add_message(
                        f"[field]Family:[/field] '{fam}' — "
                        f"[dim]DEBUG:[/dim] Level 7: Processing {len(decorative_outliers)} decorative outlier(s)"
                    ).emit(console)
                # Use main_cluster as typo source (fallback handled in max-pull path)
                typo_source = main_cluster if main_cluster else None
                if typo_source:
                    norm_typo_asc, norm_typo_desc = get_cluster_normalized_typo(
                        typo_source
                    )
                    inherited_asc = int(round(norm_typo_asc * typo_source[0].upm))
                    inherited_desc = int(round(norm_typo_desc * typo_source[0].upm))
                    if verbosity >= Verbosity.DEBUG:
                        cs.StatusIndicator("info").add_message(
                            f"[field]Family:[/field] '{fam}' — "
                            f"inherited line box {inherited_asc} / {inherited_desc}"
                        ).emit(console)
                else:
                    # Fallback: compute adaptive metrics for decorative outliers
                    for fm in decorative_outliers:
                        decorative_asc = compute_family_normalized_ascender(
                            [fm], config
                        )
                        plan_adaptive_metrics(
                            [fm],
                            fam_min,
                            fam_max,
                            decorative_asc,
                            config,
                            verbosity,
                        )
                    continue  # Skip the inherited typo logic below

                for fm in decorative_outliers:
                    # SPECIAL HANDLING FOR UNICASE: Inherit traditional metrics directly
                    if fm.is_unicase and typo_source:
                        # Unicase: Just inherit traditional typo metrics directly
                        # The unicase cap (which equals its x-height) will naturally
                        # align with the traditional x-height since both use same baseline
                        fm.target_typo_asc = int(round(norm_typo_asc * fm.upm))
                        fm.target_typo_desc = int(round(norm_typo_desc * fm.upm))
                    else:
                        # Regular decorative outlier: inherit typo as-is
                        fm.target_typo_asc = int(round(norm_typo_asc * fm.upm))
                        fm.target_typo_desc = int(round(norm_typo_desc * fm.upm))

                    # Layer and swash keep the family's clipping box too. The extra
                    # ink may clip. A shadow effect still widens Win around its outlines.
                    if getattr(fm, "clip_with_family", False) and typo_source:
                        ref = typo_source[0]
                        if ref.upm > 0 and ref.target_win_asc is not None:
                            fm.target_win_asc = int(round(ref.target_win_asc / ref.upm * fm.upm))
                            fm.target_win_desc = int(round((ref.target_win_desc or 0) / ref.upm * fm.upm))
                        else:
                            fm.target_win_asc = fm.target_typo_asc
                            fm.target_win_desc = abs(fm.target_typo_desc or 0)
                    elif fm.max_y and fm.min_y:
                        fm.target_win_asc = int(
                            round(fm.max_y * (1.0 + config.win_buffer))
                        )
                        fm.target_win_desc = int(
                            round(abs(fm.min_y) * (1.0 + config.win_buffer))
                        )
                    else:
                        # Fallback to family extremes
                        fm.target_win_asc = int(
                            round(fam_max * fm.upm * (1.0 + config.win_buffer))
                        )
                        fm.target_win_desc = int(
                            round(abs(fam_min * fm.upm) * (1.0 + config.win_buffer))
                        )
                    # Ensure Win >= Typo after decorative planning
                    finalize_metrics(fm)

            # Level 7b: Handle script outliers (similar to decorative but with larger buffer)
            if script_outliers:
                # Use main_cluster as typo source (same as decorative)
                typo_source = main_cluster if main_cluster else None
                if typo_source:
                    norm_typo_asc, norm_typo_desc = get_cluster_normalized_typo(
                        typo_source
                    )
                else:
                    # Fallback: compute adaptive metrics for script outliers
                    for fm in script_outliers:
                        script_asc = compute_family_normalized_ascender([fm], config)
                        plan_adaptive_metrics(
                            [fm],
                            fam_min,
                            fam_max,
                            script_asc,
                            config,
                            verbosity,
                        )
                    # Skip inherited typo logic below
                    script_outliers = []

                for fm in script_outliers:
                    # Script fonts: inherit typo from main cluster
                    fm.target_typo_asc = int(round(norm_typo_asc * fm.upm))
                    fm.target_typo_desc = int(round(norm_typo_desc * fm.upm))

                    # Expand win with script buffer (larger than decorative)
                    script_buffer = (
                        config.win_buffer * config.script_win_buffer_multiplier
                    )
                    if fm.max_y and fm.min_y:
                        fm.target_win_asc = int(round(fm.max_y * (1.0 + script_buffer)))
                        fm.target_win_desc = int(
                            round(abs(fm.min_y) * (1.0 + script_buffer))
                        )
                    else:
                        # Fallback to family extremes
                        fm.target_win_asc = int(
                            round(fam_max * fm.upm * (1.0 + script_buffer))
                        )
                        fm.target_win_desc = int(
                            round(abs(fam_min * fm.upm) * (1.0 + script_buffer))
                        )
                    # Ensure Win >= Typo after script planning
                    finalize_metrics(fm)

            # Level 8: VALIDATE: Check cluster consistency
            if main_cluster and len(main_cluster) > 1:
                validate_cluster_consistency(main_cluster)
        else:
            # Single font family: compute ascender and use adaptive
            core_asc = compute_family_normalized_ascender(group, config)
            plan_adaptive_metrics(group, fam_min, fam_max, core_asc, config, verbosity)
            # Finalize single font
            for fm in group:
                finalize_metrics(fm)

        family_plans[fam] = (
            fam_min,
            fam_max,
            core_asc
            if len(group) > 1
            else compute_family_normalized_ascender(group, config),
        )

        # Store cluster info for checkpoint (if clustering was performed)
        if len(group) > 1 and grouping_mode != "conservative":
            main_cluster = max(clusters, key=len) if clusters else []
            clusters_cache[fam] = {
                "main_cluster": [fm.path for fm in main_cluster]
                if main_cluster
                else [],
                "decorative": [fm.path for fm in decorative_outliers],
                "script": [fm.path for fm in script_outliers],
                "unicase": [fm.path for fm in group if fm.is_unicase],
                "is_uniwidth": any(fm.is_uniwidth for fm in group),
            }

        _close(fam, group)

    if emit_review_report:
        emit_review(review)
    return family_plans, clusters_cache
