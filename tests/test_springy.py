"""Springy plan: solo → median → soft attract toward letter-height floor."""

from __future__ import annotations

import unittest

from ebrium.config import MetricsConfig
from ebrium.models import FontMeasures
from ebrium.springy import plan_springy_group, solo_spring, springy_attractor


def _fm(
    name: str,
    *,
    upm: int = 1000,
    cap: int = 706,
    x: int = 496,
    bbox_max: int = 1150,
    bbox_min: int = -350,
    desc: int = -350,
    script: bool = False,
    decorative: bool = False,
) -> FontMeasures:
    fm = FontMeasures(f"/tmp/{name}.ttf", upm)
    fm.family_name = "Register"
    fm.cap_height = cap
    fm.x_height = x
    fm.max_y = bbox_max
    fm.min_y = bbox_min
    fm.descender_min = desc
    fm.ascender_max = bbox_max
    fm.is_script = script
    fm.is_decorative_candidate = decorative
    return fm


class SpringyTest(unittest.TestCase):
    def test_attractor_bumps_for_large_x_ratio(self) -> None:
        cfg = MetricsConfig()
        base = springy_attractor(None, 700, cfg)
        self.assertAlmostEqual(base, 1.3)
        bumped = springy_attractor(496, 706, cfg)  # ≈ 0.70
        self.assertGreater(bumped, 1.3)
        self.assertLess(bumped, 1.35)

    def test_solo_spring_near_attractor(self) -> None:
        cfg = MetricsConfig()
        fm = _fm("Regular")
        span_n, asc, desc, attract = solo_spring(fm, cfg)
        self.assertAlmostEqual(span_n, attract, delta=0.01)
        self.assertGreater(asc, fm.cap_height)
        self.assertLess(desc, 0)

    def test_group_shares_typo_and_blends(self) -> None:
        cfg = MetricsConfig(springy_blend=0.4)
        thin = _fm("Thin", bbox_max=1159, bbox_min=-346, desc=-346)
        black = _fm("Black", bbox_max=1210, bbox_min=-530, desc=-530)
        plan_springy_group([thin, black], cfg, fam="Register")
        self.assertIsNotNone(thin.target_typo_asc)
        self.assertEqual(thin.target_typo_asc, black.target_typo_asc)
        self.assertEqual(thin.target_typo_desc, black.target_typo_desc)
        # Win follows Black extremes (with buffer)
        self.assertGreaterEqual(thin.target_win_asc, 1210)
        self.assertGreaterEqual(thin.target_win_asc, thin.target_typo_asc)
        span = thin.target_typo_asc + abs(thin.target_typo_desc)
        # median solos ~1326, 40% toward 1300 → ~1316
        self.assertGreaterEqual(span, 1305)
        self.assertLess(span, 1330)

    def test_decorative_excluded_from_median_still_inherits(self) -> None:
        cfg = MetricsConfig(springy_blend=0.4)
        regular = _fm("Regular")
        display = _fm(
            "Display",
            bbox_max=1600,
            bbox_min=-800,
            desc=-800,
            decorative=True,
        )
        plan_springy_group([regular, display], cfg, fam="Demo")
        self.assertEqual(regular.target_typo_asc, display.target_typo_asc)
        # Display still widens Win
        self.assertGreaterEqual(regular.target_win_asc, 1600)


class SpringyParserTest(unittest.TestCase):
    def test_springy_subcommand_and_flags(self) -> None:
        from ebrium.cli_parser import build_parser, finalize_args

        args = build_parser().parse_args(
            ["springy", "--superfamily", "--blend", "25", "-r", "fonts/"]
        )
        finalize_args(args)
        self.assertTrue(args.springy)
        self.assertEqual(args.plan_mode, "springy")
        self.assertEqual(args.grouping_mode, "superfamily")
        self.assertEqual(args.blend, 25.0)

        by_family = build_parser().parse_args(["springy", "fonts/"])
        finalize_args(by_family)
        self.assertEqual(by_family.grouping_mode, "family")
        self.assertEqual(by_family.plan_mode, "springy")


if __name__ == "__main__":
    unittest.main()
