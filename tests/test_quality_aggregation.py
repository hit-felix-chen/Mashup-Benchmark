import unittest

from eval.aggregate_scores import compute_quality, summarize
from eval.run_evaluation import finalize_automatic_score_record

SIX_METRIC_SCORES = {
    "IF": 4.0,
    "BCS": 87.7846730194489,
    "AEC": 62.41566311851368,
    "VQ": 4.0,
    "TC": 3.0,
    "NC": 4.0,
}


class QualityAggregationTests(unittest.TestCase):
    def test_quality_is_arithmetic_mean(self):
        quality = compute_quality(SIX_METRIC_SCORES, {})
        self.assertAlmostEqual(quality, 70.86672268966043)

    def test_human_oq_never_changes_quality(self):
        expected = compute_quality(SIX_METRIC_SCORES, {})
        for oq in (1.0, 3.0, 5.0):
            with self.subTest(oq=oq):
                scores = {**SIX_METRIC_SCORES, "OQ": oq}
                self.assertEqual(compute_quality(scores, {}), expected)

    def test_legacy_seven_metric_config_ignores_oq_and_preserves_quality(self):
        legacy_config = {
            "metrics": {
                "weights": {
                    "IF": 0.10,
                    "BCS": 0.20,
                    "AEC": 0.20,
                    "VQ": 0.10,
                    "TC": 0.10,
                    "NC": 0.10,
                    "OQ": 0.20,
                }
            }
        }
        self.assertAlmostEqual(
            compute_quality({**SIX_METRIC_SCORES, "OQ": 1.0}, legacy_config),
            compute_quality(SIX_METRIC_SCORES, {}),
        )

    def test_missing_automatic_metric_still_renormalizes(self):
        quality = compute_quality({"BCS": 100.0, "IF": 1.0}, {})
        self.assertAlmostEqual(quality, 50.0)

    def test_empty_scores(self):
        self.assertIsNone(compute_quality({}, {}))

    def test_extreme_weights_ignored(self):
        self.assertEqual(compute_quality({"BCS": 100.0, "IF": 1.0}, {"metrics": {"weights": {"BCS": 100, "IF": 0}}}), 50.0)

    def test_summary_never_aggregates_oq(self):
        record = {"scores": {**SIX_METRIC_SCORES, "OQ": 5.0, "Quality": 50.0}}
        summary = summarize([record])
        self.assertNotIn("OQ", summary["metrics"])

    def test_finalizer_removes_legacy_human_fields_and_recomputes_quality(self):
        record = {
            "human_scores": {"OQ": 5.0},
            "scores": {**SIX_METRIC_SCORES, "OQ": 1.0, "Quality": 0.0},
            "metric_details": {"OQ": {"raw_score": 1.0}},
            "rationale": {"OQ": "legacy"},
        }
        finalized = finalize_automatic_score_record(record, {})
        self.assertNotIn("human_scores", finalized)
        self.assertNotIn("OQ", finalized["scores"])
        self.assertNotIn("OQ", finalized["metric_details"])
        self.assertNotIn("OQ", finalized["rationale"])
        self.assertAlmostEqual(finalized["scores"]["Quality"], 70.86672268966043)


if __name__ == "__main__":
    unittest.main()
