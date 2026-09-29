"""Optical clustering logic for grouping similar fonts."""

from typing import Optional

from . import config
from . import models

MetricsConfig = config.MetricsConfig
FontMeasures = models.FontMeasures

def compute_optical_similarity(
    fm1: FontMeasures, fm2: FontMeasures, threshold: float, config: MetricsConfig
) -> bool:
    """Compare cap height and baseline alignment - the stable anchors.

    Cap height is the primary metric. X-height can vary (optical sizes).
    Descender is checked with more leniency.

    Always uses optical cap height measurement for clustering consistency.
    """

    def normalize(value: Optional[int], upm: int) -> Optional[float]:
        if value is None or upm <= 0:
            return None
        return float(value) / float(upm)

    # Pre-check: Overall bounds span (detect structurally different fonts)
    # Script fonts or highly decorative fonts may have same cap height but 2-3x span
    if (
        fm1.max_y is not None
        and fm1.min_y is not None
        and fm2.max_y is not None
        and fm2.min_y is not None
    ):
        span1 = normalize(fm1.max_y - fm1.min_y, fm1.upm)
        span2 = normalize(fm2.max_y - fm2.min_y, fm2.upm)

        if span1 and span2 and span1 > 0 and span2 > 0:
            span_ratio = max(span1, span2) / min(span1, span2)
            # Use max_span_ratio for pre-check (separate from decorative detection)
            if span_ratio > config.max_span_ratio:
                return False

    # Primary: Cap height ratio (the stable anchor) - always use optical
    if fm1.cap_optical is None or fm2.cap_optical is None:
        return False  # Require optical measurement for clustering
    cap1 = normalize(fm1.cap_optical, fm1.upm)
    cap2 = normalize(fm2.cap_optical, fm2.upm)

    if cap1 is None or cap2 is None:
        return False

    cap_diff = abs(cap1 - cap2)
    if cap_diff > threshold:
        return False

    # Secondary: x-height (more lenient - allows optical size variants)
    xh1 = normalize(fm1.x_height, fm1.upm)
    xh2 = normalize(fm2.x_height, fm2.upm)

    if xh1 is not None and xh2 is not None:
        xh_diff = abs(xh1 - xh2)
        if xh_diff > threshold * 2.0:  # 2x lenient
            return False

    # Tertiary: Descender ratio (somewhat lenient)
    desc1 = normalize(fm1.descender_min, fm1.upm)
    desc2 = normalize(fm2.descender_min, fm2.upm)

    if desc1 is not None and desc2 is not None:
        desc_diff = abs(abs(desc1) - abs(desc2))
        if desc_diff > threshold * 1.5:  # 1.5x lenient
            return False

    return True


def detect_decorative_outlier(
    fm: FontMeasures,
    core_cluster: list[FontMeasures],
    threshold: float,
    config: MetricsConfig,
) -> bool:
    """Refine decorative detection using cluster context.

    Confirms/rejects decorative candidate flag from measurement phase.

    Requirements:
    - Standalone detection flagged as candidate OR
    - Core metrics match cluster but span is 1.4x+ larger
    """
    if not core_cluster:
        # No cluster context - trust standalone detection
        return fm.is_decorative_candidate

    # Pre-check: Reject structurally different fonts (script, extreme display)
    # Compare span against cluster average
    if fm.max_y is not None and fm.min_y is not None and fm.upm > 0:
        fm_span = (fm.max_y - fm.min_y) / fm.upm
        cluster_spans = [
            (cfm.max_y - cfm.min_y) / cfm.upm
            for cfm in core_cluster
            if cfm.max_y is not None and cfm.min_y is not None and cfm.upm > 0
        ]

        if cluster_spans:
            avg_cluster_span = sum(cluster_spans) / len(cluster_spans)
            if avg_cluster_span > 0:
                span_ratio = max(fm_span, avg_cluster_span) / min(
                    fm_span, avg_cluster_span
                )
                # Use max_span_ratio for structural rejection
                if span_ratio > config.max_span_ratio:
                    return False

    # Check if core metrics match any font in cluster
    matches_core = any(
        compute_optical_similarity(fm, core_fm, threshold, config)
        for core_fm in core_cluster
    )

    if not matches_core:
        # Different structure - not a decorative variant
        return False

    # Check bounds inflation vs cluster
    cluster_max_avg = sum(
        cfm.max_y / cfm.upm for cfm in core_cluster if cfm.max_y
    ) / len(core_cluster)
    cluster_min_avg = sum(
        cfm.min_y / cfm.upm for cfm in core_cluster if cfm.min_y
    ) / len(core_cluster)

    fm_max_norm = fm.max_y / fm.upm if fm.max_y and fm.upm > 0 else 0
    fm_min_norm = fm.min_y / fm.upm if fm.min_y and fm.upm > 0 else 0

    # If bounds clear the cluster by more than 15% plus the exclusion margin.
    max_inflation = (
        (fm_max_norm - cluster_max_avg) / cluster_max_avg if cluster_max_avg else 0
    )
    min_inflation = (
        abs((fm_min_norm - cluster_min_avg) / cluster_min_avg) if cluster_min_avg else 0
    )
    margin = config.optical_threshold / 2.0
    return max_inflation > 0.15 + margin or min_inflation > 0.15 + margin


def detect_script_font(
    fm: FontMeasures,
    core_cluster: list[FontMeasures],
    config: MetricsConfig,
) -> bool:
    """A companion is a script when it matches the core and its span is twice as tall.

    The absolute 2.0× em check already happened in measurement. This one
    compares the font with the core, and it does not skip that comparison
    because measurement already set a flag.
    """
    if not core_cluster:
        return fm.is_script

    # Relative check against the core.
    # Check if core metrics match any font in cluster (same letter body)
    matches_core = any(
        compute_optical_similarity(fm, core_fm, config.optical_threshold, config)
        for core_fm in core_cluster
    )

    if not matches_core:
        return False  # Different structure, not a script variant

    # Check span ratio (script fonts have much larger span)
    if fm.max_y is None or fm.min_y is None or fm.upm <= 0:
        return False

    fm_span = (fm.max_y - fm.min_y) / fm.upm
    cluster_spans = [
        (cfm.max_y - cfm.min_y) / cfm.upm
        for cfm in core_cluster
        if cfm.max_y is not None and cfm.min_y is not None and cfm.upm > 0
    ]

    if not cluster_spans:
        return False

    avg_cluster_span = sum(cluster_spans) / len(cluster_spans)
    if avg_cluster_span <= 0:
        return False

    span_ratio = fm_span / avg_cluster_span

    # Script threshold: 2.0x span (vs decorative 1.3x)
    if span_ratio < config.exclusion_span(config.script_span_threshold):
        return False

    # AND descender-dominant (script swashes go down more than up)
    fm_desc_ratio = abs(fm.min_y / fm.upm) if fm.min_y else 0
    fm_asc_ratio = (fm.max_y / fm.upm) if fm.max_y else 0

    # Script: descender deeper than ascender is tall (by configurable ratio)
    if fm_desc_ratio > fm_asc_ratio * config.script_asymmetry_ratio:
        return True

    return False


def _upm_fraction(value: Optional[int], upm: int) -> Optional[float]:
    if value is None or upm <= 0:
        return None
    return float(value) / float(upm)


def _can_anchor_ink(fm: FontMeasures) -> bool:
    """A reference style has real letter descenders, so an all-caps cut cannot pose as the base."""
    depth = _upm_fraction(fm.descender_min, fm.upm)
    return depth is not None and depth <= -0.05


def _extends_past_sibling(fm: FontMeasures, other: FontMeasures, config: MetricsConfig) -> bool:
    """True when fm's outlines pass other's by the companion margin and the caps still match."""
    if not _can_anchor_ink(other):
        return False
    cap = _upm_fraction(fm.cap_optical, fm.upm)
    ocap = _upm_fraction(other.cap_optical, other.upm)
    ink_min = _upm_fraction(fm.min_y, fm.upm)
    ink_max = _upm_fraction(fm.max_y, fm.upm)
    omin = _upm_fraction(other.min_y, other.upm)
    omax = _upm_fraction(other.max_y, other.upm)
    if None in (cap, ocap, ink_min, ink_max, omin, omax):
        return False
    # Three times the optical match. A shadow can lift the cap box a little.
    # A Short / Tall pair is much further apart and stays one height family.
    if abs(cap - ocap) > config.optical_threshold * 3:
        return False
    extra = config.companion_ink_extra
    deeper = omin - ink_min
    taller = ink_max - omax
    # The sibling stays inside this outline. Two styles that bulge in
    # opposite directions are not a base and a companion.
    sibling_inside = (ink_min - omin) < extra and (omax - ink_max) < extra
    return sibling_inside and (deeper >= extra or taller >= extra)


def _is_outline_companion(fm: FontMeasures, group: list[FontMeasures], config: MetricsConfig) -> bool:
    return any(other is not fm and _extends_past_sibling(fm, other, config) for other in group)


def peel_effect_outliers(
    group: list[FontMeasures],
    config: Optional[MetricsConfig] = None,
) -> tuple[list[FontMeasures], list[FontMeasures]]:
    """Split outline companions from the base styles.

    A style whose cap still matches a sibling, but whose outlines run at least
    10% of the em past that sibling, keeps the base line box and may clip.
    The file name is not used. A tall bounding box by itself does not peel.

    Returns (remaining, decorative_outliers). Remaining is never emptied
    solely by this split — if nothing would be left to plan, the group is
    returned unchanged.
    """
    config = config or MetricsConfig()
    if len(group) < 2:
        return group, []

    remaining: list[FontMeasures] = []
    peeled: list[FontMeasures] = []

    for fm in group:
        companion = _is_outline_companion(fm, group, config)
        if companion:
            fm.is_decorative_outlier = True
            fm.is_decorative_candidate = False
            fm.clip_with_family = True
            peeled.append(fm)
        else:
            remaining.append(fm)

    if not remaining:
        for fm in peeled:
            fm.is_decorative_outlier = False
            fm.clip_with_family = False
        return group, []

    return remaining, peeled


def cluster_group_helper(
    group: list[FontMeasures],
    threshold: float,
    config: MetricsConfig,
) -> tuple[list[list[FontMeasures]], list[FontMeasures], list[FontMeasures]]:
    """Cluster a single group of fonts (original clustering logic).

    Returns: (core_clusters, decorative_outliers, script_outliers)
    """
    if len(group) <= 1:
        return ([group] if group else [], [], [])

    group, peeled_effects = peel_effect_outliers(group, config)
    if len(group) <= 1:
        return ([group] if group else [], peeled_effects, [])

    # Build similarity graph based on cap height + x-height + descender
    n = len(group)
    similar_pairs: list[tuple[int, int]] = []

    for i in range(n):
        for j in range(i + 1, n):
            if compute_optical_similarity(group[i], group[j], threshold, config):
                similar_pairs.append((i, j))

    # Union-Find clustering
    parent = list(range(n))

    def find(x: int) -> int:
        # Iterative find with path compression to avoid recursion depth issues
        root = x
        # Find the root by traversing up the parent chain
        while parent[root] != root:
            root = parent[root]
        # Path compression: update all nodes along the path to point directly to root
        while parent[x] != root:
            next_node = parent[x]
            parent[x] = root
            x = next_node
        return root

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i, j in similar_pairs:
        union(i, j)

    # Group by cluster
    clusters_dict: dict[int, list[FontMeasures]] = {}
    for idx, fm in enumerate(group):
        root = find(idx)
        clusters_dict.setdefault(root, []).append(fm)
        fm.cluster_id = root

    core_clusters = [c for c in clusters_dict.values() if len(c) > 1]
    singletons = [c[0] for c in clusters_dict.values() if len(c) == 1]

    # No pair was close enough to form a core. Measurement flags still apply:
    # a script or decorative candidate must not set the family's typo box.
    # The styles that remain each stay a cluster so the planner can share one box.
    if not core_clusters:
        scripts: list[FontMeasures] = []
        decorative: list[FontMeasures] = list(peeled_effects)
        kept: list[FontMeasures] = []
        for fm in singletons:
            if fm.is_script:
                scripts.append(fm)
                continue
            if fm.is_decorative_candidate:
                fm.is_decorative_outlier = True
                fm.is_decorative_candidate = False
                decorative.append(fm)
                continue
            kept.append(fm)
        return ([[fm] for fm in kept], decorative, scripts)

    main_cluster = max(core_clusters, key=len)

    # Check singletons: script, decorative variants, or true outliers?
    # Check scripts FIRST (more specific pattern than decorative)
    script_outliers = []
    decorative_outliers = []
    true_outliers = []

    for fm in singletons:
        # Absolute 2.0× em scripts stay scripts. This can also add a
        # companion that is twice the core even when it is under 2.0× the em.
        is_script_refined = detect_script_font(fm, main_cluster, config)
        if is_script_refined or fm.is_script:
            script_outliers.append(fm)
            fm.is_script = True  # Confirm
            continue

        # Refine decorative detection (measurement flag + cluster check)
        is_decorative_refined = detect_decorative_outlier(
            fm, main_cluster, threshold, config
        )
        if is_decorative_refined:
            decorative_outliers.append(fm)
            fm.is_decorative_outlier = True  # Confirm
            fm.is_decorative_candidate = False  # No longer candidate
            continue

        # True outlier (neither script nor decorative)
        true_outliers.append(fm)
        fm.is_decorative_candidate = False  # Reject candidate status

    # True outliers become single-font clusters
    all_clusters = core_clusters + [[fm] for fm in true_outliers]

    return (all_clusters, decorative_outliers + peeled_effects, script_outliers)


def detect_optical_clusters(
    measures: list[FontMeasures], threshold: float, config: MetricsConfig
) -> tuple[list[list[FontMeasures]], list[FontMeasures], list[FontMeasures]]:
    """Detect core clusters and decorative outliers based on cap height.

    Unicase fonts are treated as special decorative variants that inherit
    baseline alignment from traditional fonts in mixed families.
    Script fonts are detected separately with larger span and descender-dominant characteristics.

    Returns: (core_clusters, decorative_outliers, script_outliers)
    """
    if len(measures) <= 1:
        return ([measures] if measures else [], [], [])

    measures, peeled_effects = peel_effect_outliers(measures, config)
    if len(measures) <= 1:
        return ([measures] if measures else [], peeled_effects, [])

    # Separate unicase and non-unicase fonts
    unicase_fonts = [fm for fm in measures if fm.is_unicase]
    non_unicase_fonts = [fm for fm in measures if not fm.is_unicase]

    # If we have BOTH unicase and non-unicase fonts in this family,
    # treat unicase as decorative outliers (inherit baseline from traditional)
    if unicase_fonts and non_unicase_fonts:
        # Cluster only the traditional fonts normally
        clusters, decorative, scripts = cluster_group_helper(
            non_unicase_fonts, threshold, config
        )

        # Mark unicase fonts as decorative outliers
        for fm in unicase_fonts:
            fm.is_decorative_outlier = True

        # Add unicase to decorative outliers list
        all_decorative = decorative + unicase_fonts + peeled_effects

        return (clusters, all_decorative, scripts)

    # If ALL fonts are unicase, cluster them normally (pure unicase family)
    elif unicase_fonts and not non_unicase_fonts:
        clusters, decorative, scripts = cluster_group_helper(
            unicase_fonts, threshold, config
        )
        return (clusters, decorative + peeled_effects, scripts)

    # If no unicase fonts, cluster normally
    else:
        clusters, decorative, scripts = cluster_group_helper(
            non_unicase_fonts, threshold, config
        )
        return (clusters, decorative + peeled_effects, scripts)
