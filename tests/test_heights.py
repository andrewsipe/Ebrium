"""Short and Tall in one family share the tall cap's line box."""

from __future__ import annotations

import unittest

from ebrium.config import MetricsConfig
from ebrium.models import FontMeasures
from ebrium.planning import build_plans, family_cap_anchor, plan_identical_metrics


def _fm(name: str, cap: int) -> FontMeasures:
    fm = FontMeasures(f"/tmp/{name}.ttf", 1750)
    fm.family_name = "Height"
    fm.cap_height = cap
    fm.cap_optical = cap
    fm.x_height = cap
    fm.descender_min = -300
    fm.max_y = cap + 200
    fm.min_y = -300
    return fm


class HeightFamilyTest(unittest.TestCase):
    def test_a_shorter_cluster_anchors_when_the_core_is_already_tall(self) -> None:
        tall = [_fm(f"Height-Tall{i}", 1225) for i in range(3)]
        short = [_fm(f"Height-Short{i}", 700) for i in range(3)]
        anchor = family_cap_anchor(tall + short, tall, MetricsConfig())
        self.assertAlmostEqual(anchor, 1225 / 1750)

    def test_tallest_cap_is_the_anchor(self) -> None:
        short = [_fm(f"Height-Short{i}", 700) for i in range(5)]
        tall = [_fm(f"Height-Tall{i}", 1225) for i in range(5)]
        anchor = family_cap_anchor(short + tall, short, MetricsConfig())
        self.assertAlmostEqual(anchor, 1225 / 1750)

    def test_one_height_has_no_anchor(self) -> None:
        group = [_fm(f"Height-{i}", 700) for i in range(4)]
        self.assertIsNone(family_cap_anchor(group, group, MetricsConfig()))

    def test_weight_drift_inside_one_cluster_is_not_an_anchor(self) -> None:
        # Nine weights, each 0.5% of the em taller than the last: one
        # single-linkage cluster, 4% from end to end.
        group = [_fm(f"Height-W{i}", 700 + 9 * i) for i in range(9)]
        self.assertIsNone(family_cap_anchor(group, group, MetricsConfig()))

    def test_no_core_still_anchors_on_the_tallest(self) -> None:
        short = _fm("Height-Short", 700)
        tall = _fm("Height-Tall", 1225)
        anchor = family_cap_anchor([short, tall], [short], MetricsConfig())
        self.assertAlmostEqual(anchor, 1225 / 1750)

    def test_a_shorter_unicase_does_not_anchor_a_core(self) -> None:
        core = [_fm(f"Height-{i}", 700) for i in range(3)]
        unicase = _fm("Height-Unicase", 480)
        unicase.is_unicase = True
        unicase.is_decorative_outlier = True
        self.assertIsNone(family_cap_anchor(core + [unicase], core, MetricsConfig()))

    def test_short_cluster_uses_the_tall_box(self) -> None:
        short = [_fm("Height-ShortA", 700), _fm("Height-ShortB", 700)]
        anchor = 1225 / 1750
        plan_identical_metrics(
            short, -0.2, 1.0, 0.65, MetricsConfig(), cap_anchor=anchor
        )
        # Centered on cap 1225 in a 1750 em, span 130%: 1750 / -525.
        self.assertEqual(short[0].target_typo_asc, 1750)
        self.assertEqual(short[0].target_typo_desc, -525)
        self.assertEqual(short[1].target_typo_asc, short[0].target_typo_asc)
        self.assertEqual(short[1].target_typo_desc, short[0].target_typo_desc)

    def test_a_tight_span_still_clears_the_tall_cap(self) -> None:
        short = [_fm(f"Height-Short{i}", 1225) for i in range(3)]
        tall = _fm("Height-Tall", 1575)
        config = MetricsConfig(target_span=1.0)
        build_plans({"Height": short + [tall]}, config, emit_review_report=False)
        # Cap 1575 plus the 25% headroom, in a 1750 em.
        self.assertGreaterEqual(short[0].target_typo_asc, 1575 + int(1750 * 0.25))
        self.assertEqual(tall.target_typo_asc, short[0].target_typo_asc)
