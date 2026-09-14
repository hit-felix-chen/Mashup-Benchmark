"""Run: python -m unittest discover -s web/human-likert-judge-webui -p 'test_*.py' -v"""

import importlib.util
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("human_likert", Path(__file__).with_name("app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class LikertStudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tasks = []
        for task_id in ("task_001", "task_002"):
            tasks.append({"id": task_id, "video": {"category": "film", "title_zh": "片名"}, "task": {"type": "narrative", "prompt": "剪一个故事", "target_output_length_sec": 60}})
            for method in ("secret_a", "secret_b"):
                output = self.root / method / "task_outputs" / task_id / "output.mp4"
                output.parent.mkdir(parents=True)
                output.write_bytes(b"0123456789")
        (self.root / "tasks.jsonl").write_text("\n".join(json.dumps(task) for task in tasks))
        self.config = {"study_id": "test", "title": "Test", "benchmark_root": ".", "task_manifest": "tasks.jsonl", "database": "db.sqlite3", "methods": [{"id": method, "name": method, "run_dir": method} for method in ("secret_a", "secret_b")]}
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps(self.config))
        self.study = app.Study(self.config_path)
        token = self.study.enroll("annotator")
        self.pid = self.study.participant(token)["id"]

    def test_draw_is_anonymous_and_resumable(self):
        with patch.object(app.secrets, "choice", side_effect=["task_002", "secret_b"]):
            rating_id = self.study.draw(self.pid)
        self.assertEqual(self.study.draw(self.pid), rating_id)
        public = json.dumps(self.study.public(self.pid, rating_id))
        self.assertNotIn("secret_b", public)
        self.assertNotIn(str(self.root), public)

    def test_requires_all_scores_and_watched(self):
        rating_id = self.study.draw(self.pid)
        with self.assertRaises(app.APIError):
            self.study.finish(self.pid, rating_id, {"scores": {"IF": 5}, "watched": True})
        with self.assertRaises(app.APIError):
            self.study.finish(self.pid, rating_id, {"scores": {metric: 3 for metric in app.METRICS}, "watched": False})
        scores = {"IF": 5, "VQ": 4, "TC": 3, "NC": 2}
        self.study.finish(self.pid, rating_id, {"scores": scores, "watched": True, "note": "evidence"})
        self.study.finish(self.pid, rating_id, {"scores": scores, "watched": True, "note": "evidence"})
        self.assertEqual(self.study.public(self.pid, rating_id)["completed"], 1)

    def test_skip_and_export(self):
        rating_id = self.study.draw(self.pid)
        self.study.finish(self.pid, rating_id, {"note": "无法播放"}, skip=True)
        next_id = self.study.draw(self.pid)
        self.study.finish(self.pid, next_id, {"scores": {metric: 4 for metric in app.METRICS}, "watched": True})
        destination = self.root / "exports"
        app.export_results(self.config_path, destination)
        with next(destination.glob("*.csv")).open(encoding="utf-8") as file:
            self.assertEqual(len(file.readlines()), 5)
        with closing(self.study.connect()) as db:
            self.assertEqual(db.execute("select count(*) from ratings where status='skipped'").fetchone()[0], 1)

    def test_new_id_is_required_after_source_change(self):
        self.config["methods"][0]["enabled"] = False
        self.config_path.write_text(json.dumps(self.config))
        with self.assertRaisesRegex(ValueError, "NEW study_id"):
            app.Study(self.config_path)


if __name__ == "__main__":
    unittest.main()
