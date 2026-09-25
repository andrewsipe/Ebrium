"""A script is 2.0 times the em and descender-heavy. 1.5 times is not."""

from __future__ import annotations

import unittest

from ebrium.config import MetricsConfig
from ebrium.measurements import is_script_font
from ebrium.models import FontMeasures
from ebrium.planning import compute_family_normalized_ascender


def _fm(max_y: int, min_y: int) -> FontMeasures:
    fm = FontMeasures("/tmp/Script.otf", 1000)
    fm.max_y = max_y
    fm.min_y = min_y
    return fm


class ScriptThresholdTest(unittest.TestCase):
    def test_one_and_a_half_em_is_not_a_script(self) -> None:
        # Span 1600 on a 1000 em, descenders heavier than ascenders.
        self.assertFalse(is_script_font(_fm(600, -1000)))

    def test_twice_the_em_and_descender_heavy_is_a_script(self) -> None:
        self.assertTrue(is_script_font(_fm(700, -1400)))

    def test_just_over_two_em_stays_in_the_shared_box(self) -> None:
        # Span 2010 is 2.01 of the em, inside the exclusion margin above 2.0.
        self.assertFalse(is_script_font(_fm(600, -1410)))


class AscenderSeedTest(unittest.TestCase):
    def test_lowercase_ascenders_do_not_raise_the_seed(self) -> None:
        fm = FontMeasures("/tmp/Text.otf", 1000)
        fm.cap_height = 700
        fm.ascender_max = 1200
        seed = compute_family_normalized_ascender([fm], MetricsConfig())
        self.assertAlmostEqual(seed, 0.95)
