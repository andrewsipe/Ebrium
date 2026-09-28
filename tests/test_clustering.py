"""Outline companions inherit the base line box. File names do not."""

from __future__ import annotations

import unittest
from pathlib import Path

from ebrium.clustering import cluster_group_helper, peel_effect_outliers
from ebrium.config import MetricsConfig
from ebrium.models import FontMeasures


def _fm(name: str, *, decorative: bool = False) -> FontMeasures:
    fm = FontMeasures(f"/tmp/{name}.ttf", 1000)
    fm.family_name = "Rig"
    fm.cap_optical = 700
    fm.cap_height = 700
    fm.x_height = 500
    fm.descender_min = -200
    fm.max_y = 1100
    fm.min_y = -300
    fm.is_decorative_candidate = decorative
    return fm


class EffectMembershipTest(unittest.TestCase):
    def test_effect_names_do_not_peel(self) -> None:
        faces = [_fm("Rig-MediumFace"), _fm("Rig-BoldFace")]
        effects = [_fm("Rig-MediumShadow"), _fm("Rig-FineBold"), _fm("Rig-BoldInline")]
        clusters, decorative, scripts = cluster_group_helper(
            faces + effects, 0.025, MetricsConfig()
        )
        self.assertEqual(decorative, [])
        self.assertFalse(scripts)
        self.assertEqual(len(clusters[0]), 5)

    def test_no_face_does_not_peel_effect_names(self) -> None:
        group = [_fm("Acme-Regular"), _fm("Acme-BoldShadow")]
        clusters, decorative, _scripts = cluster_group_helper(
            group, 0.025, MetricsConfig()
        )
        self.assertEqual(decorative, [])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 2)

    def test_a_tall_bbox_alone_does_not_peel(self) -> None:
        regular = _fm("Acme-Regular")
        other = _fm("Acme-Ornament", decorative=True)
        clusters, decorative, _scripts = cluster_group_helper(
            [regular, other], 0.025, MetricsConfig()
        )
        self.assertEqual(decorative, [])
        self.assertEqual(len(clusters[0]), 2)

    def test_extra_ink_keeps_the_base_box(self) -> None:
        base = _fm("Layer-Base")
        base.min_y = -480
        base.max_y = 1600
        layer = _fm("Layer-Overlay")
        layer.cap_optical = 740
        layer.min_y = -1080
        layer.max_y = 1680
        layer.descender_min = -960
        swash = _fm("Script-Alternate")
        swash.min_y = -700
        swash.max_y = 1800
        _, peeled = peel_effect_outliers([base, layer, swash], MetricsConfig())
        names = {Path(fm.path).stem for fm in peeled}
        self.assertEqual(names, {"Layer-Overlay", "Script-Alternate"})
        self.assertTrue(all(fm.clip_with_family for fm in peeled))

    def test_a_name_does_not_make_a_companion(self) -> None:
        group = [_fm("FamilyA-Regular"), _fm("FamilyB-Bold")]
        _, peeled = peel_effect_outliers(group, MetricsConfig())
        self.assertEqual(peeled, [])

    def test_a_taller_cap_is_not_extra_ink(self) -> None:
        short = _fm("Height-Short")
        tall = _fm("Height-Tall")
        tall.cap_optical = 1225
        tall.min_y = -900
        _, peeled = peel_effect_outliers([short, tall], MetricsConfig())
        self.assertEqual(peeled, [])

    def test_a_small_descender_change_stays(self) -> None:
        regular = _fm("Text-Regular")
        regular.min_y = -242
        bold = _fm("Text-Black")
        bold.min_y = -272
        _, peeled = peel_effect_outliers([regular, bold], MetricsConfig())
        self.assertEqual(peeled, [])

    def test_all_caps_cannot_pull_the_text_styles_out(self) -> None:
        caps = _fm("Acme-Caps")
        caps.min_y = -10
        caps.max_y = 800
        caps.descender_min = None
        text = _fm("Acme-Regular")
        text.min_y = -250
        _, peeled = peel_effect_outliers([caps, text], MetricsConfig())
        self.assertEqual(peeled, [])


if __name__ == "__main__":
    unittest.main()
