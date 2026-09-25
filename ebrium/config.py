"""Configuration constants and dataclasses for metrics normalization."""

from dataclasses import dataclass
from typing import Optional, Tuple


# --- Unicode codepoints for referenced glyphs ---
LOWER_ASCENDER_CODEPOINTS: Tuple[int, ...] = (
    0x0062,
    0x0064,
    0x0068,
    0x006B,
    0x006C,
)  # b d h k l
LOWER_DESCENDER_CODEPOINTS: Tuple[int, ...] = (
    0x0067,
    0x006A,
    0x0070,
    0x0071,
    0x0079,
)  # g j p q y
CAP_HEIGHT_GLYPHS: Tuple[int, ...] = (0x0048, 0x0049)  # 'H', 'I'
U_LOWER_X: int = 0x0078  # 'x'
UPPER_A: int = 0x0041
UPPER_Z: int = 0x005A

# Lowercase letters for x-height sampling (exclude ascenders/descenders)
LOWERCASE_XHEIGHT_SAMPLES: Tuple[int, ...] = (
    0x0061,  # a
    0x0063,  # c
    0x0065,  # e
    0x006D,  # m
    0x006E,  # n
    0x006F,  # o
    0x0072,  # r
    0x0073,  # s
    0x0075,  # u
    0x0076,  # v
    0x0077,  # w
    0x0078,  # x
    0x007A,  # z
)

# Codepoints for uniwidth detection (A-Z, a-z, 0-9)
UNIWIDTH_SAMPLE_CODEPOINTS: Tuple[int, ...] = (
    *range(0x0041, 0x005B),  # A-Z
    *range(0x0061, 0x007B),  # a-z
    *range(0x0030, 0x003A),  # 0-9
)

# Uppercase letters for cap height sampling (flat tops, no curves that might exceed)
UPPERCASE_CAPHEIGHT_SAMPLES: Tuple[int, ...] = (
    0x0042,  # B
    0x0044,  # D
    0x0045,  # E
    0x0046,  # F
    0x0048,  # H
    0x0049,  # I
    0x004B,  # K
    0x004C,  # L
    0x004D,  # M
    0x004E,  # N
    0x0050,  # P
    0x0052,  # R
    0x0054,  # T
)

# Accented capitals used as a hard typo-ascender clearance floor (GF-style).
# If none of these exist in the font, planning estimates and flags a re-check.
ACCENTED_CAP_CODEPOINTS: Tuple[int, ...] = (
    0x00C0,  # À
    0x00C1,  # Á
    0x00C2,  # Â
    0x00C3,  # Ã
    0x00C4,  # Ä
    0x00C5,  # Å
    0x00C8,  # È
    0x00C9,  # É
    0x00CA,  # Ê
    0x00CB,  # Ë
    0x00CC,  # Ì
    0x00CD,  # Í
    0x00CE,  # Î
    0x00CF,  # Ï
    0x00D2,  # Ò
    0x00D3,  # Ó
    0x00D4,  # Ô
    0x00D5,  # Õ
    0x00D6,  # Ö
    0x00D9,  # Ù
    0x00DA,  # Ú
    0x00DB,  # Û
    0x00DC,  # Ü
    0x00DD,  # Ý
    0x0102,  # Ă
    0x01CD,  # Ǎ
    0x1EA0,  # Ạ
    0x1EA2,  # Ả
    0x1EA4,  # Ấ
    0x1EA6,  # Ầ
    0x1EA8,  # Ẩ
    0x1EAA,  # Ẫ
    0x1EAC,  # Ậ
    0x1EAE,  # Ắ
    0x1EB0,  # Ằ
    0x1EB2,  # Ẳ
    0x1EB4,  # Ẵ
    0x1EB6,  # Ặ
)


@dataclass
class MetricsConfig:
    """Configuration constants for metrics normalization."""

    # Internal representation: all stored as fractions (convert from percentage input)
    target_span: float = 1.3  # Internal: as multiplier (1.3x = 130% of UPM)
    win_buffer: float = 0.02  # Internal: as fraction (0.02 = 2%)
    optical_threshold: float = (
        0.025  # 2.5% UPM for identical detection (validated optimal)
    )
    top_margin: float = 0.25  # Internal: as fraction (0.25 = 25% of UPM)
    ascender_override_threshold: float = (
        0.5  # Fraction of top_margin to trigger ascender override (default: 0.5 = 50%)
    )
    max_adjustment: Optional[float] = (
        None  # Internal: as fraction (0.08 = 8% max adjustment)
    )
    # Clustering thresholds
    max_span_ratio: float = (
        1.5  # Pre-check rejection threshold (separate from decorative detection)
    )
    # Type detection thresholds (in order of specificity)
    unicase_threshold: float = 0.05  # 5% UPM x-height ≈ cap-height
    script_span_threshold: float = 2.0  # 2.0x span minimum for script
    script_asymmetry_ratio: float = 1.2  # 1.2x descender-dominant
    decorative_span_threshold: float = (
        1.4  # 1.4x span minimum (changed from 1.3x to create gap with script)
    )
    script_win_buffer_multiplier: float = (
        1.5  # Buffer multiplier for script fonts (1.5x default)
    )
    # Kept for CLI --no-auto-adjust compatibility; x-height no longer raises the span floor.
    auto_adjust_target: bool = False
    # Unify typo line box across a family for UI centering issues (mixed width masters)
    force_baseline: bool = False
    # Prefer reference master from largest optical cluster only (omit height/width extremes)
    force_baseline_main_cluster_only: bool = False
    # Exact path, basename, or glob fnmatch basename (e.g. "Family-Bold.otf", "Flexible-*W500.otf")
    force_baseline_from_pattern: Optional[str] = None
    # Uniwidth detection
    uniwidth_consistency_threshold: float = (
        0.90  # 90% of sampled glyphs must have identical advance widths
    )
