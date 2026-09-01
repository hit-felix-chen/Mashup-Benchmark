from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval import run_evaluation


class PartialReuseEvaluationTests(unittest.TestCase):
    def test_reevaluated_reused_record_refreshes_current_run_accounting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "runs" / "test_run"
            run_dir.mkdir(parents=True)
            run_record = {
                "task_id": "task_012",
                "method": "Current Method",
                "method_version": "current-v2",
                "status": "success",
                "output_video": "runs/test_run/task_outputs/task_012/output.mp4",
                "api_cost_usd": 7.5,
                "wall_clock_sec": 12.5,
            }
            (run_dir / "run_outputs.jsonl").write_text(json.dumps(run_record) + "\n", encoding="utf-8")

            task_file = root / "tasks.jsonl"
            task_file.write_text(
                json.dumps({"id": "task_012", "task": {"type": "narrative"}}) + "\n",
                encoding="utf-8",
            )

            reused_dir = root / "eval_results" / "source_eval"
            reused_dir.mkdir(parents=True)
            reused_record = {
                "eval_id": "source_eval",
                "run_id": "test_run",
                "task_id": "task_012",
                "method": "Current Method",
                "method_version": "current-v2",
                "status": "skipped",
                "scores": {"IF": 4.0, "AEC": None, "Quality": 75.0},
                "metric_details": {},
                "judge": None,
                "rationale": {},
                "cost": {"api_cost_usd": 1.0},
                "efficiency": {"wall_clock_sec": 2.0},
            }
            (reused_dir / "evaluation_scores.jsonl").write_text(
                json.dumps(reused_record) + "\n",
                encoding="utf-8",
            )

            argv = [
                "run_evaluation",
                "--run",
                "runs/test_run",
                "--config",
                "eval/config.yaml",
                "--reuse-eval-id",
                "source_eval",
                "--eval-id",
                "target_eval",
                "--task-id",
                "task_012",
                "--metrics",
                "AEC",
                "--concurrency",
                "1",
            ]
            with (
                patch.object(run_evaluation, "ROOT", root),
                patch.object(run_evaluation, "TASK_FILE", task_file),
                patch.object(run_evaluation, "validate_run_target_durations"),
                patch.object(run_evaluation, "load_config", return_value={}),
                patch.object(
                    run_evaluation,
                    "audio_visual_energy_correspondence",
                    return_value={"score": 42.0},
                ),
                patch.object(sys, "argv", argv),
            ):
                self.assertEqual(run_evaluation.main(), 0)

            result_path = root / "eval_results" / "target_eval" / "evaluation_scores.jsonl"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["cost"], {"api_cost_usd": 7.5})
            self.assertEqual(result["efficiency"], {"wall_clock_sec": 12.5})
            self.assertEqual(result["scores"]["IF"], 4.0)
            self.assertEqual(result["scores"]["AEC"], 42.0)


if __name__ == "__main__":
    unittest.main()
