"""A checkpoint is reused only while the file itself is unchanged."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ebrium.checkpoints import load_measurements_checkpoint, save_measurements_checkpoint
from ebrium.config import MetricsConfig
from ebrium.models import FontMeasures


class CheckpointFreshnessTest(unittest.TestCase):
    def test_a_replaced_file_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "A.ttf"
            path.write_bytes(b"one")
            fm = FontMeasures(str(path), 1000)
            fm.family_name = "A"
            fm.cap_height = 700
            checkpoint = Path(tmp) / "checkpoint.json"
            clusters = {"A": {"main_cluster": [str(path)], "no_core": False}}
            save_measurements_checkpoint(
                [fm], checkpoint, config=MetricsConfig(), clusters=clusters
            )

            loaded, _missing, cached = load_measurements_checkpoint(
                checkpoint, expected_files=[str(path)], config=MetricsConfig()
            )
            self.assertEqual([item.cap_height for item in loaded], [700])
            self.assertEqual(cached["A"]["main_cluster"], [str(path)])

            path.write_bytes(b"one-replaced")
            loaded, missing, cached = load_measurements_checkpoint(
                checkpoint, expected_files=[str(path)], config=MetricsConfig()
            )
            self.assertEqual(loaded, [])
            self.assertIsNone(cached)
            self.assertEqual(missing, [str(path)])

    def test_a_checkpoint_without_timestamps_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "A.ttf"
            path.write_bytes(b"one")
            checkpoint = Path(tmp) / "checkpoint.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "version": "1.1",
                        "measures": [
                            {
                                "path": str(path),
                                "upm": 1000,
                                "family_name": "A",
                                "cap_height": 700,
                            }
                        ],
                        "clusters": {"A": {"main_cluster": [str(path)]}},
                        "config_hash": "unused",
                    }
                ),
                encoding="utf-8",
            )
            loaded, missing, cached = load_measurements_checkpoint(
                checkpoint, expected_files=[str(path)], config=MetricsConfig()
            )
            self.assertEqual(loaded, [])
            self.assertIsNone(cached)
            self.assertEqual(missing, [str(path)])


if __name__ == "__main__":
    unittest.main()
