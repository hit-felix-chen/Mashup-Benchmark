"""Run: python -m unittest discover -s web/human-pairwise-judge-webui -p 'test_*.py' -v"""

import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("human_judge", Path(__file__).with_name("app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tasks = []
        for tid in ("task_001", "task_002"):
            tasks.append(
                {
                    "id": tid,
                    "video": {"category": "film", "title_zh": "片名"},
                    "task": {"type": "narrative", "prompt": "剪一个故事", "target_output_length_sec": 60},
                }
            )
            for method in ("secret_a", "secret_b", "secret_c"):
                path = self.root / method / "task_outputs" / tid / "output.mp4"
                path.parent.mkdir(parents=True)
                path.write_bytes(b"0123456789")
        (self.root / "tasks.jsonl").write_text("\n".join(json.dumps(t) for t in tasks))
        self.config = {
            "study_id": "test",
            "title": "Test",
            "benchmark_root": ".",
            "task_manifest": "tasks.jsonl",
            "database": "db.sqlite3",
            "media_cache": "cache",
            "browser_proxies": True,
            "methods": [{"id": m, "name": m, "run_dir": m} for m in ("secret_a", "secret_b", "secret_c")],
        }
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps(self.config))
        self.study = app.Study(self.config_path)
        self.addCleanup(self.study.workers.shutdown)
        self.token = self.study.enroll("test-annotator")
        self.pid = self.study.participant(self.token)["id"]
        for key, source in self.study.sources.items():
            self.study.media_states[key] = {"status": "ready", "path": source["path"], "proxy": False, "source": source}

    def ratings(self, pair_id):
        self.study.finish(self.pid, pair_id, {"scores": {"OQ": 1}, "watched": {"a": True, "b": True}, "note": "理由"})

    def test_resume_and_concurrent_draw(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda _: self.study.draw(self.pid), range(16)))
        self.assertEqual(len(set(ids)), 1)
        restarted = app.Study(self.config_path)
        self.addCleanup(restarted.workers.shutdown)
        self.assertEqual(restarted.draw(self.pid), ids[0])

    def test_uniform_sampling_uses_task_then_distinct_methods(self):
        with patch.object(app.secrets, "choice", return_value="task_002") as choice:
            pair = self.study.pair(self.pid, self.study.draw(self.pid))
        choice.assert_called_once_with(["task_001", "task_002"])
        self.assertEqual(pair["task_id"], "task_002")
        self.assertNotEqual(pair["method_a"], pair["method_b"])

    def test_overall_ratings_are_idempotent(self):
        pair_id = self.study.draw(self.pid)
        self.ratings(pair_id)
        self.ratings(pair_id)
        self.assertEqual(self.study.public_pair(self.pid, pair_id)["completed"], 1)
        self.assertNotEqual(self.study.draw(self.pid), pair_id)

    def test_score_validation(self):
        pair_id = self.study.draw(self.pid)
        for bad in (True, 2, -2, "1", None, 0.5):
            with self.assertRaises(app.APIError):
                self.study.finish(self.pid, pair_id, {"scores": {"OQ": bad}, "watched": {"a": True, "b": True}})

    def test_optional_reasons_and_retry_conflict(self):
        pair_id = self.study.draw(self.pid)
        for invalid in (["unknown"], ["IF", "IF"], "IF", [None]):
            with self.assertRaises(app.APIError):
                self.study.finish(self.pid, pair_id, {"scores": {"OQ": 1}, "reasons": invalid, "watched": {"a": True, "b": True}})
        body = {"scores": {"OQ": -1}, "reasons": ["NC", "IF"], "watched": {"a": True, "b": True}}
        self.study.finish(self.pid, pair_id, body)
        self.study.finish(self.pid, pair_id, {**body, "reasons": ["IF", "NC"]})
        with self.assertRaises(app.APIError):
            self.study.finish(self.pid, pair_id, {**body, "reasons": []})

    def test_all_legacy_vote_combinations(self):
        from itertools import product
        for values in product([-1, 0, 1], repeat=4):
            scores = dict(zip(app.REASONS, values))
            overall, reasons = app.derive_overall(scores)
            a, b = values.count(1), values.count(-1)
            expected = 1 if a > b else -1 if b > a else 0
            self.assertEqual(overall, {"OQ": expected})
            self.assertEqual(reasons, [k for k, v in scores.items() if expected != 0 and v == expected])

    def test_migration_retains_raw_records_and_is_idempotent(self):
        pair_id = self.study.draw(self.pid)
        self.ratings(pair_id)
        legacy = {"IF": -1, "VQ": 0, "TC": -1, "NC": 1}
        snapshot = dict(self.study.snapshot)
        snapshot["protocol"] = {"version": "pairwise-v2-vlm-four-metrics", "metrics": app.LEGACY_METRICS}
        with closing(self.study.connect()) as db, db:
            db.execute("UPDATE studies SET snapshot=?,digest=?", (app.json_text(snapshot), app.fingerprint(snapshot)))
            db.execute("UPDATE pairs SET ratings=?,reasons=NULL,rating_origin=NULL WHERE id=?", (app.json_text(legacy), pair_id))
        app.migrate_overall(self.config_path)
        app.migrate_overall(self.config_path)
        reopened = app.Study(self.config_path)
        self.addCleanup(reopened.workers.shutdown)
        pair = reopened.pair(self.pid, pair_id)
        self.assertEqual(json.loads(pair["ratings"]), {"OQ": -1})
        self.assertEqual(json.loads(pair["reasons"]), ["IF", "TC"])
        self.assertEqual(json.loads(pair["legacy_ratings"]), legacy)
        self.assertEqual(pair["rating_origin"], "derived_four_metrics")
        self.assertEqual(pair["status"], "submitted")

    def test_skip_recorded_not_counted(self):
        pair_id = self.study.draw(self.pid)
        with self.assertRaises(app.APIError):
            self.study.finish(self.pid, pair_id, {"note": ""}, skip=True)
        self.study.finish(self.pid, pair_id, {"note": "播放异常"}, skip=True)
        self.assertEqual(self.study.pair(self.pid, pair_id)["status"], "skipped")
        self.assertEqual(self.study.public_pair(self.pid, pair_id)["completed"], 0)

    def test_no_identity_leak_or_cross_participant_access(self):
        pair_id = self.study.draw(self.pid)
        public = json.dumps(self.study.public_pair(self.pid, pair_id))
        for private in ("secret_a", "secret_b", "secret_c", str(self.root), "method_a", "ratings", "proxy"):
            self.assertNotIn(private, public)
        other = self.study.participant(self.study.enroll("other"))["id"]
        with self.assertRaises(app.APIError):
            self.study.pair(other, pair_id)

    def test_study_change_requires_new_id(self):
        self.config["methods"][0]["enabled"] = False
        self.config_path.write_text(json.dumps(self.config))
        with self.assertRaisesRegex(ValueError, "NEW study_id"):
            app.Study(self.config_path)
        self.config["study_id"] = "test-v2"
        self.config_path.write_text(json.dumps(self.config))
        changed = app.Study(self.config_path)
        changed.workers.shutdown()
        self.assertEqual(len(changed.methods), 2)

    def test_missing_media_fails_clearly(self):
        Path(next(iter(self.study.sources.values()))["path"]).unlink()
        with self.assertRaisesRegex(ValueError, "Missing/empty"):
            app.Study(self.config_path)

    def test_media_tool_falls_back_to_homebrew_path(self):
        with patch.object(app.shutil, "which", return_value=None), patch.object(
            app.Path, "is_file", return_value=True
        ), patch.object(app.Path, "stat") as stat:
            stat.return_value.st_mode = 0o755
            self.assertEqual(app.media_tool("ffprobe"), "/opt/homebrew/bin/ffprobe")

    def test_media_preparation_preserves_compatible_source(self):
        key = next(iter(self.study.sources))
        probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
            "format": {"duration": "60"},
        }
        with (
            patch.object(app.subprocess, "check_output", return_value=json.dumps(probe).encode()),
            patch.object(app.subprocess, "run") as encode,
        ):
            self.study._prepare(key)
        state = self.study.media_states[key]
        self.assertEqual(state["status"], "ready")
        self.assertFalse(state["proxy"])
        self.assertEqual(state["path"], self.study.sources[key]["path"])
        encode.assert_not_called()

    def test_high10_proxy_is_recorded_and_reused(self):
        key = next(iter(self.study.sources))
        probe = {
            "streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p10le"}],
            "format": {"duration": "60"},
        }

        def fake_encode(command, **kwargs):
            self.assertIn("yuv420p", command)
            self.assertIn("-map_metadata", command)
            Path(command[-1]).write_bytes(b"browser-compatible-test-fixture")

        with (
            patch.object(app.subprocess, "check_output", return_value=json.dumps(probe).encode()),
            patch.object(app.subprocess, "run", side_effect=fake_encode) as encode,
        ):
            self.study._prepare(key)
            self.study._prepare(key)
        state = self.study.media_states[key]
        self.assertTrue(state["proxy"])
        self.assertEqual(state["status"], "ready")
        encode.assert_called_once()
        self.assertEqual(Path(self.study.sources[key]["path"]).read_bytes(), b"0123456789")

    def test_export_keeps_method_direction_and_skips(self):
        pair_id = self.study.draw(self.pid)
        pair = self.study.pair(self.pid, pair_id)
        self.ratings(pair_id)
        skipped = self.study.draw(self.pid)
        self.study.finish(self.pid, skipped, {"note": "error"}, skip=True)
        destination = self.root / "exports"
        app.export_results(self.config_path, destination)
        records = [json.loads(line) for line in next(destination.glob("*.jsonl")).read_text().splitlines()]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["method_a"], pair["method_a"])
        self.assertEqual(records[0]["ratings"]["OQ"], 1)
        import csv

        with next(destination.glob("*.csv")).open(encoding="utf-8-sig") as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(len(rows), 1)
        self.assertEqual(next(r for r in rows if r["metric"] == "OQ")["winner"], pair["method_a"])
        self.assertTrue(next(destination.glob("*.study.json")).is_file())

    def test_http_range_privacy_origin_and_submit(self):
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        server.study = self.study
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        pair_id = self.study.draw(self.pid)
        headers = {"Cookie": f"judge_session={self.token}"}

        def request(path, extra=None, body=None):
            merged = {**headers, **(extra or {})}
            if body is not None:
                merged["Content-Type"] = "application/json"
            return urllib.request.urlopen(
                urllib.request.Request(
                    base + path, headers=merged, data=None if body is None else json.dumps(body).encode()
                )
            )

        with request(f"/media/{pair_id}/a", {"Range": "bytes=2-5"}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")
            self.assertEqual(response.read(), b"2345")
        with request(f"/media/{pair_id}/a", {"Range": "bytes=-3"}) as response:
            self.assertEqual(response.read(), b"789")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            request(f"/media/{pair_id}/a", {"Range": "bytes=20-"})
        self.assertEqual(caught.exception.code, 416)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            request("/api/next", {"Origin": "http://evil.example"}, {})
        self.assertEqual(caught.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            request(f"/media/{pair_id}/a", {"Cookie": ""})
        self.assertEqual(caught.exception.code, 401)
        for endpoint in ("/config.json", "/data/judgments.sqlite3", "/../config.json"):
            with self.assertRaises(urllib.error.HTTPError):
                request(endpoint)
        with request(
            f"/api/pairs/{pair_id}/ratings", body={"scores": {"OQ": 1}, "watched": {"a": True, "b": True}}
        ) as response:
            self.assertTrue(json.load(response)["ok"])
        with closing(self.study.connect()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM pairs WHERE status='submitted'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
