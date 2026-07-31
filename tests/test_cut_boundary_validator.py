from __future__ import annotations

import math
import unittest
from unittest.mock import patch

from eval.evaluators.cut_boundary_validator import _validate_binary_response
from eval.metrics.alignment import beat_cut_synchronization


class FakeCutValidator:
    def validate(self, _video_path, candidate_cuts):
        return {
            "cuts": [candidate_cuts[0]],
            "candidates": [
                {
                    "time_sec": candidate_cuts[0],
                    "is_cut": True,
                    "reason": "different shot",
                },
                {
                    "time_sec": candidate_cuts[1],
                    "is_cut": False,
                    "reason": "continuous motion",
                },
            ],
            "model": "fake-vlm",
            "provider": "fake",
            "fps": 30.0,
            "frame_sampling": "adjacent",
            "classification": "binary_is_cut",
            "enable_thinking": False,
            "usage": {"total_tokens": 10},
        }


class CutBoundaryValidatorTests(unittest.TestCase):
    def test_binary_response_requires_json_boolean(self):
        self.assertEqual(
            _validate_binary_response({"is_cut": True, "reason": "different framing"}),
            (True, "different framing"),
        )
        with self.assertRaises(ValueError):
            _validate_binary_response({"is_cut": "true", "reason": "bad type"})

    @patch(
        "eval.metrics.alignment.detect_audio_beats_librosa",
        return_value=[1.05],
    )
    @patch(
        "eval.metrics.alignment.detect_visual_cuts",
        return_value=[1.0, 2.0],
    )
    def test_bcs_scores_only_vlm_confirmed_cuts(
        self,
        _detect_visual_cuts,
        _detect_audio_beats,
    ):
        result = beat_cut_synchronization(
            "output.mp4",
            cut_validator=FakeCutValidator(),
            tau_sec=0.1,
        )
        self.assertEqual(result["num_candidate_cuts"], 2)
        self.assertEqual(result["num_cuts"], 1)
        self.assertAlmostEqual(
            result["score"],
            math.exp(-0.05 / 0.1) * 100,
        )
        self.assertEqual(
            result["cut_validation"],
            "vlm_binary_adjacent_frames",
        )


if __name__ == "__main__":
    unittest.main()
