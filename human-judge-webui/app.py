"""Local, annotator-blinded pairwise video evaluation. Python 3.11+, stdlib only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import re
import secrets
import sqlite3
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
METRICS = {
    "OQ": [
        "整体质量",
        "结合提示词、背景音乐和目标时长，哪部成片整体更完整、自然、协调，更符合任务且具有可发布性？请先作整体判断。",
    ],
    "IF": [
        "指令遵循",
        "哪部成片更充分地满足提示词要求的主体、事件、风格、情绪或叙事意图？不要因一般画质或转场问题重复扣分。",
    ],
    "VQ": ["视觉质量", "哪部成片画面更清晰、构图更合理、主体更突出，模糊、遮挡等技术缺陷更少？"],
    "TC": ["转场连续性", "哪部成片的相邻片段在视觉语义、运动与构图上衔接更自然？此项不单独评价音乐卡点。"],
    "NC": ["叙事连贯性", "哪部成片具有更清晰、连贯且符合提示词的结构、推进过程或故事／情绪弧线？"],
}
PROTOCOL = {
    "version": "pairwise-v1",
    "metrics": METRICS,
    "scale": {
        "2": "A clearly better",
        "1": "A slightly better",
        "0": "tie",
        "-1": "B slightly better",
        "-2": "B clearly better",
    },
    "sampling": "uniform task, then uniform ordered pair of distinct methods; with replacement",
    "oq_first": True,
}


def now():
    return datetime.now(UTC).isoformat()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def fingerprint(value):
    return hashlib.sha256(json_text(value).encode()).hexdigest()


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Study:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        self.config = json.loads(self.config_path.read_text())
        cfg = self.config
        self.root = (self.config_path.parent / cfg["benchmark_root"]).resolve()
        self.db_path = (self.config_path.parent / cfg["database"]).resolve()
        self.cache = (self.config_path.parent / cfg["media_cache"]).resolve()
        self.study_id = cfg["study_id"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", self.study_id):
            raise ValueError("study_id must use 1–100 letters, numbers, underscores or hyphens")
        self.methods = {m["id"]: m for m in cfg["methods"] if m.get("enabled", True)}
        if len(self.methods) < 2 or len(self.methods) != sum(m.get("enabled", True) for m in cfg["methods"]):
            raise ValueError("Enable at least two methods, with unique IDs")
        manifest = (self.root / cfg["task_manifest"]).resolve()
        rows = [json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
        if len({row["id"] for row in rows}) != len(rows):
            raise ValueError("Duplicate task IDs in task manifest")
        requested = set(cfg.get("task_ids", []))
        self.tasks = {t["id"]: t for t in rows if not requested or t["id"] in requested}
        if not self.tasks or requested - self.tasks.keys():
            raise ValueError("Empty or unknown task_ids")
        self.sources = {}
        missing = []
        for tid in sorted(self.tasks):
            for mid, method in self.methods.items():
                pattern = method.get("output_pattern", "task_outputs/{task_id}/output.mp4")
                source = (self.root / method["run_dir"] / pattern.format(task_id=tid)).resolve()
                if not source.is_file() or source.stat().st_size == 0:
                    missing.append(str(source))
                else:
                    stat = source.stat()
                    self.sources[(tid, mid)] = {
                        "path": str(source),
                        "bytes": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    }
        if missing:
            raise ValueError("All enabled methods must cover all selected tasks. Missing/empty:\n" + "\n".join(missing))
        self.snapshot = {
            "protocol": PROTOCOL,
            "methods": self.methods,
            "tasks": self.tasks,
            "browser_proxies": cfg.get("browser_proxies", True),
            "proxy_encoding": "libx264 CRF18 fast yuv420p AAC160k faststart",
            "sources": {f"{tid}/{mid}": info for (tid, mid), info in self.sources.items()},
        }
        self.digest = fingerprint(self.snapshot)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.media_lock = threading.Lock()
        self.media_states = {}
        self.workers = ThreadPoolExecutor(max_workers=2)
        with closing(self.connect()) as db, db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS studies (
                    id TEXT PRIMARY KEY, digest TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS participants (
                    token TEXT PRIMARY KEY, id TEXT UNIQUE NOT NULL, label TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pairs (
                    id TEXT PRIMARY KEY, study_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                    task_id TEXT NOT NULL, method_a TEXT NOT NULL, method_b TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
                    oq INTEGER, oq_at TEXT, submitted_at TEXT, ratings TEXT, note TEXT,
                    watched TEXT, media_info TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_pending_pair
                    ON pairs(study_id, participant_id) WHERE status = 'pending';
            """)
            existing = db.execute("SELECT digest FROM studies WHERE id=?", (self.study_id,)).fetchone()
            if existing and existing["digest"] != self.digest:
                raise ValueError(
                    "Study contents/config changed. Choose a NEW study_id; existing results are preserved."
                )
            db.execute(
                "INSERT OR IGNORE INTO studies VALUES (?,?,?,?)",
                (self.study_id, self.digest, json_text(self.snapshot), now()),
            )

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def participant(self, token):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM participants WHERE token=?", (token,)).fetchone()
        if not row:
            raise APIError("请先输入标注者代号。", 401)
        return dict(row)

    def enroll(self, label):
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 64:
            raise APIError("标注者代号需为 1–64 个字符。")
        token, pid = secrets.token_urlsafe(32), str(uuid.uuid4())
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO participants VALUES (?,?,?,?)", (token, pid, label.strip(), now()))
        return token

    def pair(self, pid, pair_id):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT * FROM pairs WHERE id=? AND participant_id=? AND study_id=?", (pair_id, pid, self.study_id)
            ).fetchone()
        if not row:
            raise APIError("未找到当前比较。", 404)
        return dict(row)

    def draw(self, pid):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            pending = db.execute(
                "SELECT id FROM pairs WHERE study_id=? AND participant_id=? AND status='pending'", (self.study_id, pid)
            ).fetchone()
            if pending:
                return pending["id"]
            tid = secrets.choice(sorted(self.tasks))
            a, b = secrets.SystemRandom().sample(sorted(self.methods), 2)
            pair_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO pairs(id,study_id,participant_id,task_id,method_a,method_b,created_at) VALUES (?,?,?,?,?,?,?)",
                (pair_id, self.study_id, pid, tid, a, b, now()),
            )
            return pair_id

    def prepare(self, tid, mid):
        key = (tid, mid)
        with self.media_lock:
            if key not in self.media_states:
                self.media_states[key] = {"status": "preparing"}
                self.workers.submit(self._prepare, key)
            return dict(self.media_states[key])

    def _prepare(self, key):
        info = self.sources[key]
        path = Path(info["path"])
        try:
            stat = path.stat()
            if stat.st_size != info["bytes"] or stat.st_mtime_ns != info["mtime_ns"]:
                raise ValueError("Source changed during study")
            probe = json.loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_streams",
                        "-show_format",
                        "-of",
                        "json",
                        str(path),
                    ],
                    timeout=30,
                )
            )
            video = next(s for s in probe["streams"] if s["codec_type"] == "video")
            audio = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
            needs_proxy = (
                video["codec_name"] != "h264"
                or video.get("pix_fmt") not in ("yuv420p", "yuvj420p")
                or (audio and audio["codec_name"] not in ("aac", "mp3"))
            )
            served, proxy = path, bool(needs_proxy and self.config.get("browser_proxies", True))
            if proxy:
                served = self.cache / (
                    fingerprint({"source": info, "encoding": self.snapshot["proxy_encoding"]}) + ".mp4"
                )
                if not served.is_file():
                    temporary = self.cache / (str(uuid.uuid4()) + ".tmp.mp4")
                    try:
                        subprocess.run(
                            [
                                "ffmpeg",
                                "-nostdin",
                                "-v",
                                "error",
                                "-i",
                                str(path),
                                "-map",
                                "0:v:0",
                                "-map",
                                "0:a:0?",
                                "-map_metadata",
                                "-1",
                                "-map_chapters",
                                "-1",
                                "-c:v",
                                "libx264",
                                "-crf",
                                "18",
                                "-preset",
                                "fast",
                                "-threads",
                                "2",
                                "-pix_fmt",
                                "yuv420p",
                                "-c:a",
                                "aac",
                                "-b:a",
                                "160k",
                                "-movflags",
                                "+faststart",
                                str(temporary),
                            ],
                            check=True,
                            capture_output=True,
                            timeout=1800,
                        )
                        temporary.replace(served)
                    finally:
                        temporary.unlink(missing_ok=True)
            state = {
                "status": "ready",
                "path": str(served),
                "proxy": proxy,
                "source": info,
                "duration": float(probe["format"].get("duration", 0)),
                "video_codec": video["codec_name"],
                "pixel_format": video.get("pix_fmt"),
                "has_audio": bool(audio),
            }
        except Exception as exc:
            print(f"Media preparation failed for {key}: {exc}", flush=True)
            state = {"status": "error"}
        with self.media_lock:
            self.media_states[key] = state

    def public_pair(self, pid, pair_id):
        pair = self.pair(pid, pair_id)
        task = self.tasks[pair["task_id"]]
        media = {}
        for side in ("a", "b"):
            state = self.prepare(pair["task_id"], pair[f"method_{side}"])
            media[side] = {
                "status": state["status"],
                "url": f"/media/{pair_id}/{side}",
                "has_audio": state.get("has_audio", True),
            }
        with closing(self.connect()) as db:
            count = db.execute(
                "SELECT count(*) FROM pairs WHERE participant_id=? AND study_id=? AND status='submitted'",
                (pid, self.study_id),
            ).fetchone()[0]
        return {
            "id": pair_id,
            "status": pair["status"],
            "oq": pair["oq"],
            "completed": count,
            "task": {
                "id": pair["task_id"],
                "prompt": task["task"]["prompt"],
                "domain": task["video"]["category"],
                "intent": task["task"].get("type_zh", task["task"]["type"]),
                "source_title": task["video"].get("title_zh", task["video"].get("title_en", "")),
                "target_seconds": task["task"]["target_output_length_sec"],
                "bgm_title": task.get("audio", {}).get("title", ""),
                "bgm_moods": task.get("audio", {}).get("mood_tags", []),
            },
            "media": media,
        }

    @staticmethod
    def validate_score(score):
        if type(score) is not int or score not in (-2, -1, 0, 1, 2):
            raise APIError("每项请选择 A 明显更好、A 略好、相当、B 略好或 B 明显更好。")

    def save_oq(self, pid, pair_id, body):
        score = body.get("score")
        self.validate_score(score)
        if body.get("watched") != {"a": True, "b": True}:
            raise APIError("请确认已带声完整观看 A 和 B。")
        pair = self.pair(pid, pair_id)
        if any(self.prepare(pair["task_id"], pair[f"method_{s}"])["status"] != "ready" for s in ("a", "b")):
            raise APIError("视频尚未准备完成。", 409)
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM pairs WHERE id=?", (pair_id,)).fetchone()
            if row["oq"] is not None:
                if row["oq"] != score:
                    raise APIError("整体质量已提交，不能回改。", 409)
                return
            if row["status"] != "pending":
                raise APIError("这一轮已结束。", 409)
            media = {s: self.prepare(row["task_id"], row[f"method_{s}"]) for s in ("a", "b")}
            db.execute(
                "UPDATE pairs SET oq=?,oq_at=?,watched=?,media_info=? WHERE id=?",
                (score, now(), json_text(body["watched"]), json_text(media), pair_id),
            )

    def finish(self, pid, pair_id, body, skip=False):
        self.pair(pid, pair_id)
        note = body.get("note", "")
        if not isinstance(note, str) or len(note) > 2000 or (skip and not note.strip()):
            raise APIError("跳过时需填写原因；备注不超过 2000 字。")
        scores = body.get("scores")
        if not skip:
            if not isinstance(scores, dict) or set(scores) != {"IF", "VQ", "TC", "NC"}:
                raise APIError("请完成 IF、VQ、TC、NC 四项比较。")
            for score in scores.values():
                self.validate_score(score)
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            pair = db.execute("SELECT * FROM pairs WHERE id=?", (pair_id,)).fetchone()
            status = "skipped" if skip else "submitted"
            if pair["status"] == status:
                if not skip and json.loads(pair["ratings"]) != scores:
                    raise APIError("这一轮已保存，不能覆盖评分。", 409)
                return
            if pair["status"] != "pending" or (not skip and pair["oq"] is None):
                raise APIError("请先提交整体质量，或这一轮已结束。", 409)
            db.execute(
                "UPDATE pairs SET status=?,submitted_at=?,ratings=?,note=? WHERE id=?",
                (status, now(), None if skip else json_text(scores), note, pair_id),
            )


class Handler(BaseHTTPRequestHandler):
    server_version = "HumanJudge/1.0"

    @property
    def study(self):
        return self.server.study

    def json_response(self, value, status=200, cookie=None):
        data = json_text(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'",
        )
        super().end_headers()

    def identity(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return self.study.participant(cookie["judge_session"].value if "judge_session" in cookie else "")

    def do_GET(self):
        self.dispatch(False)

    def do_HEAD(self):
        self.dispatch(False, head=True)

    def do_POST(self):
        self.dispatch(True)

    def dispatch(self, post, head=False):
        try:
            path = urlparse(self.path).path
            if post:
                origin = self.headers.get("Origin")
                if origin and urlparse(origin).netloc != self.headers.get("Host"):
                    raise APIError("Cross-origin requests are not allowed", 403)
                if self.headers.get_content_type() != "application/json":
                    raise APIError("Expected application/json", 415)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise APIError("Invalid request size", 413)
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise APIError("Expected JSON object")
                if path == "/api/session":
                    token = self.study.enroll(body.get("label"))
                    self.json_response(
                        {"ok": True},
                        cookie=f"judge_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000",
                    )
                    return
                if path == "/api/logout":
                    self.json_response(
                        {"ok": True}, cookie="judge_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
                    )
                    return
                pid = self.identity()["id"]
                if path == "/api/next":
                    self.json_response(self.study.public_pair(pid, self.study.draw(pid)))
                    return
                match = re.fullmatch(r"/api/pairs/([a-f0-9-]{36})/(oq|ratings|skip)", path)
                if match:
                    pair_id, action = match.groups()
                    if action == "oq":
                        self.study.save_oq(pid, pair_id, body)
                    else:
                        self.study.finish(pid, pair_id, body, skip=action == "skip")
                    self.json_response({"ok": True})
                    return
            else:
                static = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
                if path in static:
                    self.serve_file(BASE / "static" / static[path], head)
                    return
                if path == "/api/bootstrap":
                    try:
                        person = self.identity()
                        person = {"id": person["id"], "label": person["label"]}
                    except APIError:
                        person = None
                    self.json_response(
                        {
                            "title": self.study.config["title"],
                            "study_id": self.study.study_id,
                            "participant": person,
                            "task_count": len(self.study.tasks),
                            "metrics": METRICS,
                        }
                    )
                    return
                pid = self.identity()["id"]
                match = re.fullmatch(r"/api/pairs/([a-f0-9-]{36})", path)
                if match:
                    self.json_response(self.study.public_pair(pid, match[1]))
                    return
                match = re.fullmatch(r"/media/([a-f0-9-]{36})/([ab])", path)
                if match:
                    pair = self.study.pair(pid, match[1])
                    state = self.study.prepare(pair["task_id"], pair[f"method_{match[2]}"])
                    if state["status"] != "ready":
                        raise APIError("视频正在准备，请稍候。", 503)
                    source = state["source"]
                    stat = Path(source["path"]).stat()
                    if stat.st_size != source["bytes"] or stat.st_mtime_ns != source["mtime_ns"]:
                        raise APIError("源视频已变更，请联系管理员启动新实验。", 409)
                    self.serve_file(Path(state["path"]), head)
                    return
            raise APIError("Not found", 404)
        except APIError as exc:
            self.json_response({"error": str(exc)}, exc.status)
        except (ValueError, KeyError):
            self.json_response({"error": "请求格式错误。"}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            print(f"Request error: {type(exc).__name__}: {exc}", flush=True)
            self.json_response({"error": "保存或读取失败，请重试；已有记录仍保留。"}, 500)

    def serve_file(self, path, head=False):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        if self.headers.get("Range"):
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers["Range"])
            try:
                if not match or not any(match.groups()):
                    raise ValueError
                left, right = match.groups()
                if left:
                    start, end = int(left), min(int(right), size - 1) if right else size - 1
                else:
                    start = max(0, size - int(right))
                if start > end or start >= size:
                    raise ValueError
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "private, no-store")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not head:
            with path.open("rb") as media:
                media.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = media.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    def log_message(self, format, *args):
        # Avoid logging opaque media/session URLs during normal playback.
        if len(args) > 1 and str(args[1]).startswith("5"):
            super().log_message(format, *args)


def export_results(config_path, output):
    cfg_path = Path(config_path).resolve()
    cfg = json.loads(cfg_path.read_text())
    db_path = (cfg_path.parent / cfg["database"]).resolve()
    if not db_path.is_file():
        raise ValueError("No database yet. Run serve/check first.")
    with closing(sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        study = db.execute("SELECT * FROM studies WHERE id=?", (cfg["study_id"],)).fetchone()
        if not study:
            raise ValueError("Study ID not found in database")
        snapshot = json.loads(study["snapshot"])
        records = db.execute(
            "SELECT pairs.*, participants.label AS annotator_label FROM pairs JOIN participants ON pairs.participant_id=participants.id WHERE study_id=? ORDER BY created_at,id",
            (cfg["study_id"],),
        ).fetchall()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Timestamped exports never overwrite an earlier export.
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    prefix = output / f"{cfg['study_id']}_{stamp}"
    full = []
    flat = []
    for record in records:
        row = dict(record)
        for key in ("ratings", "watched", "media_info"):
            row[key] = json.loads(row[key]) if row[key] else None
        row["study_digest"] = study["digest"]
        for side in ("a", "b"):
            mid = row[f"method_{side}"]
            row[f"method_{side}_name"] = snapshot["methods"][mid]["name"]
            row[f"run_{side}"] = snapshot["methods"][mid]["run_dir"]
        full.append(row)
        if row["status"] != "submitted":
            continue
        for metric, value in {"OQ": row["oq"], **row["ratings"]}.items():
            flat.append(
                {
                    "study_id": row["study_id"],
                    "pair_id": row["id"],
                    "participant_id": row["participant_id"],
                    "annotator_label": row["annotator_label"],
                    "task_id": row["task_id"],
                    "method_a": row["method_a"],
                    "run_a": row["run_a"],
                    "method_b": row["method_b"],
                    "run_b": row["run_b"],
                    "metric": metric,
                    "preference": value,
                    "winner": row["method_a"] if value > 0 else row["method_b"] if value < 0 else "tie",
                    "proxy_a": row["media_info"]["a"]["proxy"],
                    "proxy_b": row["media_info"]["b"]["proxy"],
                    "created_at": row["created_at"],
                    "oq_at": row["oq_at"],
                    "submitted_at": row["submitted_at"],
                    "note": row["note"],
                }
            )
    prefix.with_suffix(".jsonl").write_text("".join(json_text(row) + "\n" for row in full))
    fields = [
        "study_id",
        "pair_id",
        "participant_id",
        "annotator_label",
        "task_id",
        "method_a",
        "run_a",
        "method_b",
        "run_b",
        "metric",
        "preference",
        "winner",
        "proxy_a",
        "proxy_b",
        "created_at",
        "oq_at",
        "submitted_at",
        "note",
    ]
    with prefix.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in flat:
            # Protect spreadsheet users from formulas entered in free text.
            writer.writerow(
                {
                    k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v
                    for k, v in row.items()
                }
            )
    prefix.with_suffix(".study.json").write_text(json_text(snapshot) + "\n")
    print(
        f"Exported {len(flat) // 5} completed comparisons; {len(full)} total records.\n{prefix}.csv\n{prefix}.jsonl\n{prefix}.study.json"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=["serve", "check", "prepare-media", "export"], default="serve")
    parser.add_argument("--config", default=str(BASE / "config.json"))
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--output", default=str(BASE / "exports"))
    args = parser.parse_args()
    if args.command == "export":
        export_results(args.config, args.output)
        return
    study = Study(args.config)
    if args.command == "check":
        print(
            json_text(
                {
                    "study": study.study_id,
                    "tasks": len(study.tasks),
                    "methods": list(study.methods),
                    "videos": len(study.sources),
                    "database": str(study.db_path),
                }
            )
        )
        study.workers.shutdown()
        return
    if args.command == "prepare-media":
        for tid, mid in study.sources:
            study.prepare(tid, mid)
        study.workers.shutdown(wait=True)
        errors = [k for k, v in study.media_states.items() if v["status"] != "ready"]
        print(
            json_text(
                {
                    "ready": len(study.media_states) - len(errors),
                    "errors": errors,
                    "proxies": sum(v.get("proxy", False) for v in study.media_states.values()),
                }
            )
        )
        if errors:
            raise SystemExit(1)
        return
    host, port = args.host or study.config.get("host", "127.0.0.1"), args.port or study.config.get("port", 8765)
    server = ThreadingHTTPServer((host, port), Handler)
    server.study = study
    print(
        f"Human Judge: http://{host}:{port}\n{len(study.tasks)} tasks / {len(study.methods)} methods / {len(study.sources)} videos\nDatabase: {study.db_path}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        study.workers.shutdown(wait=True)


if __name__ == "__main__":
    main()
