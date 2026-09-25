"""Face styles stay in the core cluster; effect cuts inherit as outliers."""

from __future__ import annotations

import unittest

from ebrium.clustering import cluster_group_helper
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
    def test_face_stays_core_effects_peel(self) -> None:
        faces = [_fm("Rig-MediumFace"), _fm("Rig-BoldFace")]
        effects = [_fm("Rig-MediumShadow"), _fm("Rig-FineBold"), _fm("Rig-BoldInline")]
        clusters, decorative, scripts = cluster_group_helper(
            faces + effects, 0.025, MetricsConfig()
        )
        core_paths = {fm.path for cluster in clusters for fm in cluster}
        self.assertTrue(all(f.path in core_paths for f in faces))
        self.assertEqual({fm.path for fm in decorative}, {fm.path for fm in effects})
        self.assertFalse(scripts)
        self.assertTrue(all(fm.is_decorative_outlier for fm in effects))

    def test_no_face_does_not_peel_effect_names(self) -> None:
        group = [_fm("Acme-Regular"), _fm("Acme-BoldShadow")]
        clusters, decorative, _scripts = cluster_group_helper(
            group, 0.025, MetricsConfig()
        )
        self.assertEqual(decorative, [])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 2)

    def test_assume_decorative_peels_without_face(self) -> None:
        regular = _fm("Acme-Regular")
        swash = _fm("Acme-Swash", decorative=True)
        _clusters, decorative, _scripts = cluster_group_helper(
            [regular, swash], 0.025, MetricsConfig()
        )
        self.assertEqual(decorative, [swash])
        self.assertTrue(swash.is_decorative_outlier)


if __name__ == "__main__":
    unittest.main()
