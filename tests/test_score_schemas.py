import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load_validator(name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


class ScoreSchemaTests(unittest.TestCase):
    def setUp(self):
        self.evaluation_validator = load_validator("evaluation_score.schema.json")
        self.run_validator = load_validator("run_output.schema.json")
        self.manifest_validator = load_validator("run_manifest.schema.json")
        self.evaluation_record = {
            "eval_id": "example_eval",
            "run_id": "example_run",
            "task_id": "task_001",
            "scores": {
                "IF": 4.0,
                "BCS": 80.0,
                "AEC": 60.0,
                "VQ": 4.0,
                "TC": 3.0,
                "NC": 4.0,
                "Quality": 70.0,
            },
        }
        self.run_record = {
            "run_id": "example_run",
            "method": "Example",
            "task_id": "task_001",
            "video_id": "video_001",
            "audio_id": "audio_001",
            "prompt_type": "event",
            "status": "success",
            "output_video": "runs/example_run/task_outputs/task_001/output.mp4",
            "target_output_length_sec": 60,
            "target_shot_length_sec": 4.0,
            "actual_output_length_sec": 60,
            "wall_clock_sec": 1,
            "created_at": "2026-08-01T00:00:00+08:00",
        }

    def test_automatic_evaluation_accepts_only_six_metrics_and_quality(self):
        self.evaluation_validator.validate(self.evaluation_record)

    def test_automatic_evaluation_rejects_oq(self):
        variants = []
        for section in ("scores", "metric_details", "rationale"):
            record = copy.deepcopy(self.evaluation_record)
            record.setdefault(section, {})["OQ"] = 5.0
            variants.append(record)
        record = copy.deepcopy(self.evaluation_record)
        record["human_scores"] = {"OQ": 5.0}
        variants.append(record)
        for record in variants:
            with self.subTest(keys=record.keys()):
                self.assertTrue(list(self.evaluation_validator.iter_errors(record)))

    def test_run_output_rejects_embedded_human_scores(self):
        for field in ("human_scores", "scores"):
            with self.subTest(field=field):
                record = copy.deepcopy(self.run_record)
                record[field] = {"OQ": 5.0}
                self.assertTrue(list(self.run_validator.iter_errors(record)))

    def test_run_output_accepts_declared_duration_modes(self):
        for mode in ("task", "music"):
            with self.subTest(mode=mode):
                record = copy.deepcopy(self.run_record)
                record["target_duration_mode"] = mode
                self.run_validator.validate(record)

    def test_run_output_rejects_unknown_duration_mode(self):
        record = copy.deepcopy(self.run_record)
        record["target_duration_mode"] = "audio"
        self.assertTrue(list(self.run_validator.iter_errors(record)))

    def test_run_manifest_adapter_rejects_unknown_duration_mode(self):
        manifest = {
            "run_id": "example_run",
            "method": "Example",
            "benchmark": "Mashup-Benchmark",
            "task_file": "data/tasks/mashup_benchmark.jsonl",
            "created_at": "2026-08-01T00:00:00+08:00",
            "status": "success",
            "num_tasks": 1,
            "run_outputs": "runs/example_run/run_outputs.jsonl",
            "adapter": {
                "name": "run_cutmaster",
                "script": "scripts/run_cutmaster.py",
                "project_root": "/tmp/CutMaster",
                "python": "/tmp/CutMaster/.venv/bin/python",
                "benchmark_root": "/tmp/Mashup-Benchmark",
                "results_root": "runs",
                "task_selection": {"mode": "task_ids", "task_ids": ["task_001"]},
                "options": {"target_duration_mode": "audio"},
            },
        }

        errors = list(self.manifest_validator.iter_errors(manifest))

        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
