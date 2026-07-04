#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEOAGENT_ROOT = BENCHMARK_ROOT.parent / "VideoAgent"
DEFAULT_RESULTS_ROOT = BENCHMARK_ROOT / "runs"
TASK_FILE_REL = Path("data/tasks/mashup_benchmark.jsonl")


def normalize_thread_count(value):
    if value is None:
        return "1"
    value = value.strip()
    if not value:
        return "1"
    try:
        parsed = int(value)
    except ValueError:
        return "1"
    return str(parsed) if parsed > 0 else "1"


for _thread_env_name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ[_thread_env_name] = normalize_thread_count(os.environ.get(_thread_env_name))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_tasks(task_file: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    with task_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tasks.append(json.loads(line))
    return tasks


def task_lookup(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {task["id"]: task for task in tasks}


def resolve_videoagent_python(videoagent_root: Path, explicit_python: Path | None = None) -> Path:
    if explicit_python is not None:
        explicit_python = explicit_python.expanduser()
        return explicit_python if explicit_python.is_absolute() else explicit_python.absolute()
    candidates = [
        videoagent_root / ".venv" / "bin" / "python",
        Path("/root/miniconda3/envs/videoagent/bin/python"),
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable).absolute()


def rel_to_benchmark(path: Path, benchmark_root: Path) -> str:
    return path.resolve().relative_to(benchmark_root.resolve()).as_posix()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def clear_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def safe_alias(asset_id: str) -> str:
    # VideoAgent's editor parses segment ids with split('_') and only supports 2 or 3 parts.
    # Use an underscore-free basename so retrieved ids look like video001_12.
    return asset_id.replace("_", "")


def repo_info(root: Path, repo_name: str) -> dict[str, Any]:
    def git(args: list[str]) -> str | None:
        try:
            return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
        except Exception:
            return None

    status = git(["status", "--short"])
    return {
        "repo": repo_name,
        "branch": git(["branch", "--show-current"]),
        "commit": git(["rev-parse", "HEAD"]),
        "dirty": bool(status),
    }


def ffprobe_duration(path: Path) -> float | None:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            text=True,
        ).strip()
        return float(out)
    except Exception:
        return None


def stream_command(cmd: list[str], log_path: Path, *, cwd: Path, dry_run: bool = False) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print("$ " + " ".join(subprocess.list2cmdline([arg]) for arg in cmd))
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(subprocess.list2cmdline([arg]) for arg in cmd) + "\n\n")
        log.flush()
        if dry_run:
            log.write("[dry-run] command not executed\n")
            return 0
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["OMP_NUM_THREADS"] = normalize_thread_count(env.get("OMP_NUM_THREADS"))
        env["NUMEXPR_NUM_THREADS"] = normalize_thread_count(env.get("NUMEXPR_NUM_THREADS"))
        env["OPENBLAS_NUM_THREADS"] = normalize_thread_count(env.get("OPENBLAS_NUM_THREADS"))
        env["MKL_NUM_THREADS"] = normalize_thread_count(env.get("MKL_NUM_THREADS"))
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            log.write(line)
        return proc.wait()


def load_existing_records(run_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((run_dir / "task_outputs").glob("task_*/run_output.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return records


def gpu_name() -> str | None:
    try:
        return subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True,
        ).strip().splitlines()[0]
    except Exception:
        return None


def write_run_index(
    *,
    run_dir: Path,
    run_id: str,
    method: str,
    method_version: str,
    benchmark_root: Path,
    videoagent_root: Path,
    videoagent_python: Path,
    started_at: str,
    adapter: dict[str, Any],
    notes: str | None,
) -> None:
    records = load_existing_records(run_dir)
    run_outputs_path = run_dir / "run_outputs.jsonl"
    with run_outputs_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    num_success = sum(1 for r in records if r.get("status") == "success")
    num_failed = sum(1 for r in records if r.get("status") == "failed")
    if not records:
        status = "running"
    elif num_failed == 0 and num_success == len(records):
        status = "success"
    elif num_success == 0 and num_failed == len(records):
        status = "failed"
    else:
        status = "partial"

    manifest = {
        "run_id": run_id,
        "method": method,
        "method_version": method_version,
        "benchmark": "Mashup-Benchmark",
        "task_file": TASK_FILE_REL.as_posix(),
        "created_at": started_at,
        "started_at": started_at,
        "ended_at": now_iso(),
        "status": status,
        "num_tasks": len(records),
        "num_success": num_success,
        "num_failed": num_failed,
        "run_outputs": rel_to_benchmark(run_outputs_path, benchmark_root),
        "code": repo_info(videoagent_root, "VideoAgent"),
        "environment": {
            "platform": platform.platform(),
            "python": str(videoagent_python),
            "gpu": gpu_name(),
        },
        "adapter": adapter,
        "config": {
            "baseline": "VideoAgent",
            "pipeline": [
                "VideoPreloader",
                "RhythmDetector",
                "RhythmContentGenerator",
                "VideoSearcher",
                "VideoEditor",
            ],
        },
        "aggregate": {
            "total_wall_clock_sec": sum(float(r.get("wall_clock_sec") or 0.0) for r in records),
            "total_api_cost_usd": sum(float(r.get("api_cost_usd") or 0.0) for r in records),
        },
    }
    if notes:
        manifest["notes"] = notes
    write_json(run_dir / "run_manifest.json", manifest)


def task_paths(task: dict[str, Any], benchmark_root: Path) -> tuple[Path, Path]:
    return benchmark_root / task["video"]["local_path"], benchmark_root / task["audio"]["local_path"]


def worker_result_path(artifacts_dir: Path) -> Path:
    return artifacts_dir / "videoagent_worker_result.json"


def run_one_task(
    *,
    task: dict[str, Any],
    benchmark_root: Path,
    videoagent_root: Path,
    videoagent_python: Path,
    results_root: Path,
    run_id: str,
    method: str,
    method_version: str,
    overwrite: bool,
    dry_run: bool,
    reuse_video_cache: bool,
    force_preload: bool,
    trim_audio_to_target: bool,
) -> dict[str, Any]:
    task_id = task["id"]
    run_dir = results_root / run_id
    task_dir = run_dir / "task_outputs" / task_id
    logs_dir = task_dir / "logs"
    artifacts_dir = task_dir / "artifacts"
    output_video = task_dir / "output.mp4"
    task_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    video_path, audio_path = task_paths(task, benchmark_root)
    target_output = float(task["task"]["target_output_length_sec"])
    target_shot = float(task["task"]["target_shot_length_sec"])
    prompt_type = task["task"]["type"]
    started_at = now_iso()
    t0 = time.time()

    write_json(artifacts_dir / "benchmark_task.json", task)

    if output_video.exists() and not overwrite:
        print(f"[{task_id}] output exists, reusing: {output_video}")
    else:
        if not video_path.exists():
            raise FileNotFoundError(f"Benchmark video not found: {video_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"Benchmark audio not found: {audio_path}")
        cmd = [
            str(videoagent_python), str(Path(__file__).resolve()),
            "--worker-run-task",
            "--videoagent-root", str(videoagent_root),
            "--benchmark-root", str(benchmark_root),
            "--task-id", task_id,
            "--video-id", task["video"]["id"],
            "--audio-id", task["audio"]["id"],
            "--video-path", str(video_path),
            "--audio-path", str(audio_path),
            "--prompt", task["task"]["prompt"],
            "--target-output-length-sec", str(target_output),
            "--output-video", str(output_video),
            "--artifacts-dir", str(artifacts_dir),
        ]
        if reuse_video_cache:
            cmd.append("--reuse-video-cache")
        if force_preload:
            cmd.append("--force-preload")
        if trim_audio_to_target:
            cmd.append("--trim-audio-to-target")

        rc = stream_command(cmd, logs_dir / "pipeline.log", cwd=videoagent_root, dry_run=dry_run)
        if rc != 0:
            raise RuntimeError(f"VideoAgent worker failed with exit code {rc}")
        if not dry_run and not output_video.exists():
            raise FileNotFoundError(f"VideoAgent output not found: {output_video}")

    actual_duration = ffprobe_duration(output_video) if output_video.exists() else 0.0
    ended_at = now_iso()
    result_payload: dict[str, Any] = {}
    if worker_result_path(artifacts_dir).exists():
        try:
            result_payload = json.loads(worker_result_path(artifacts_dir).read_text(encoding="utf-8"))
        except Exception:
            result_payload = {}

    record = {
        "run_id": run_id,
        "method": method,
        "method_version": method_version,
        "task_id": task_id,
        "video_id": task["video"]["id"],
        "audio_id": task["audio"]["id"],
        "prompt_type": prompt_type,
        "status": "skipped" if dry_run else "success",
        "output_video": rel_to_benchmark(output_video, benchmark_root),
        "target_output_length_sec": target_output,
        "target_shot_length_sec": target_shot,
        "actual_output_length_sec": float(actual_duration or 0.0),
        "wall_clock_sec": time.time() - t0,
        "api_cost_usd": 0.0,
        "created_at": ended_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "code_commit": repo_info(videoagent_root, "VideoAgent").get("commit"),
        "config": {
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "videoagent_root": str(videoagent_root),
            "videoagent_python": str(videoagent_python),
            "reuse_video_cache": reuse_video_cache,
            "force_preload": force_preload,
            "trim_audio_to_target": trim_audio_to_target,
            "source_video_alias": result_payload.get("source_video_alias"),
            "worker_result": result_payload,
        },
        "artifacts": {
            "benchmark_task": rel_to_benchmark(artifacts_dir / "benchmark_task.json", benchmark_root),
            "backend_log": rel_to_benchmark(logs_dir / "pipeline.log", benchmark_root),
            "run_log": rel_to_benchmark(logs_dir / "pipeline.log", benchmark_root),
        },
        "error": None,
    }
    for key, filename in {
        "storyboard": "video_scene.json",
        "cut_points": "cut_points.json",
        "visual_retrieved_segments": "visual_retrieved_segments.json",
        "textual_segmentations": "textual_segmentations.json",
        "videoagent_worker_result": "videoagent_worker_result.json",
    }.items():
        artifact_path = artifacts_dir / filename
        if artifact_path.exists():
            record["artifacts"][key] = rel_to_benchmark(artifact_path, benchmark_root)
    write_json(task_dir / "run_output.json", record)
    return record


def write_failed_record(
    *,
    task: dict[str, Any],
    benchmark_root: Path,
    results_root: Path,
    run_id: str,
    method: str,
    method_version: str,
    started_at: str,
    exc: BaseException,
) -> dict[str, Any]:
    task_id = task["id"]
    task_dir = results_root / run_id / "task_outputs" / task_id
    output_video = task_dir / "output.mp4"
    ended_at = now_iso()
    record = {
        "run_id": run_id,
        "method": method,
        "method_version": method_version,
        "task_id": task_id,
        "video_id": task["video"]["id"],
        "audio_id": task["audio"]["id"],
        "prompt_type": task["task"]["type"],
        "status": "failed",
        "output_video": rel_to_benchmark(output_video, benchmark_root),
        "target_output_length_sec": float(task["task"]["target_output_length_sec"]),
        "target_shot_length_sec": float(task["task"]["target_shot_length_sec"]),
        "actual_output_length_sec": 0.0,
        "wall_clock_sec": 0.0,
        "api_cost_usd": 0.0,
        "created_at": ended_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "config": {},
        "artifacts": {},
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
    }
    write_json(task_dir / "run_output.json", record)
    return record


def maybe_symlink_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        dst.symlink_to(src.resolve())
    except Exception:
        shutil.copy2(src, dst)


def trim_audio(audio_path: Path, output_path: Path, target_sec: float) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(audio_path),
        "-t", f"{target_sec:.3f}",
        "-vn", "-acodec", "libmp3lame", "-q:a", "2",
        str(output_path),
    ]
    subprocess.check_call(cmd)
    return output_path


def copy_artifacts(videoagent_root: Path, artifacts_dir: Path) -> None:
    scene_output = videoagent_root / "dataset" / "video_edit" / "scene_output"
    audio_analysis = videoagent_root / "dataset" / "video_edit" / "audio_analysis"
    mapping = {
        scene_output / "video_scene.json": artifacts_dir / "video_scene.json",
        scene_output / "visual_retrieved_segments.json": artifacts_dir / "visual_retrieved_segments.json",
        scene_output / "textual_segmentations.json": artifacts_dir / "textual_segmentations.json",
        audio_analysis / "cut_points.json": artifacts_dir / "cut_points.json",
        audio_analysis / "rhythm_detection.png": artifacts_dir / "rhythm_detection.png",
        audio_analysis / "rhythm_distribution.png": artifacts_dir / "rhythm_distribution.png",
    }
    for src, dst in mapping.items():
        copy_if_exists(src, dst)


def worker_run_task(args: argparse.Namespace) -> int:
    videoagent_root = args.videoagent_root.resolve()
    benchmark_root = args.benchmark_root.resolve()
    video_path = args.video_path.resolve()
    audio_path = args.audio_path.resolve()
    output_video = args.output_video.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    os.chdir(videoagent_root)
    sys.path.insert(0, str(videoagent_root))

    dataset_dir = videoagent_root / "dataset"
    video_edit_dir = dataset_dir / "video_edit"
    audio_analysis_dir = video_edit_dir / "audio_analysis"
    scene_output_dir = video_edit_dir / "scene_output"
    working_dir = video_edit_dir / "videosource-workdir"
    final_video = dataset_dir / "final.mp4"
    cache_root = dataset_dir / "videoagent_adapter_cache"
    cache_dir = cache_root / args.video_id
    source_root = dataset_dir / "videoagent_adapter_sources"
    source_dir = source_root / args.video_id
    source_dir.mkdir(parents=True, exist_ok=True)

    video_alias_stem = safe_alias(args.video_id)
    video_alias = source_dir / f"{video_alias_stem}{video_path.suffix.lower()}"
    maybe_symlink_or_copy(video_path, video_alias)

    audio_for_run = audio_path
    if args.trim_audio_to_target:
        audio_for_run = source_root / "audios" / f"{args.task_id}_{safe_alias(args.audio_id)}.mp3"
        trim_audio(audio_path, audio_for_run, args.target_output_length_sec)

    clear_dir(audio_analysis_dir)
    clear_dir(scene_output_dir)
    if final_video.exists():
        final_video.unlink()

    restored_cache = bool(args.reuse_video_cache and cache_dir.exists() and not args.force_preload)
    if restored_cache:
        print(f"[VideoAgentAdapter] Restoring cached VideoRAG index: {cache_dir}")
        clear_dir(working_dir)
        shutil.copytree(cache_dir, working_dir, dirs_exist_ok=True)
    else:
        print(f"[VideoAgentAdapter] Building VideoRAG index for {args.video_id} from {source_dir}")
        clear_dir(working_dir)
        from environment.roles.vid_preloader import VideoPreloader
        preload_result = VideoPreloader().execute(video_dir=str(source_dir))
        print(f"[VideoAgentAdapter] Preload result: {preload_result}")
        if preload_result.get("status") != "success":
            raise RuntimeError(f"VideoPreloader failed: {preload_result}")
        if args.reuse_video_cache:
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            shutil.copytree(working_dir, cache_dir)
            print(f"[VideoAgentAdapter] Cached VideoRAG index at {cache_dir}")

    from environment.roles.vid_rhythm.rhythm_detector import RhythmDetector
    from environment.roles.vid_rhythm.rhythm_story_gen import RhythmContentGenerator
    from environment.roles.vid_searcher import VideoSearcher
    from environment.roles.vid_editor import VideoEditor

    rhythm_result = RhythmDetector().execute(audio_path=str(audio_for_run))
    print(f"[VideoAgentAdapter] Rhythm result: {rhythm_result}")
    rhythm_dir = rhythm_result["rhythm_analysis_dir"]

    storyboard_result = RhythmContentGenerator().execute(
        reqs=args.prompt,
        rhythm_analysis_dir=rhythm_dir,
    )
    print(f"[VideoAgentAdapter] Storyboard result: {storyboard_result}")
    video_scene_path = storyboard_result["video_scene_path"]
    timestamp_path = storyboard_result["timestamp_path"]

    search_result = VideoSearcher().execute(video_scene_path=video_scene_path)
    print(f"[VideoAgentAdapter] Search result: {search_result}")
    if search_result.get("status") != "success":
        raise RuntimeError(f"VideoSearcher failed: {search_result}")

    editor_result = VideoEditor().execute(
        video_dir=str(source_dir),
        audio_path=str(audio_for_run),
        timestamp_path=timestamp_path,
    )
    print(f"[VideoAgentAdapter] Editor result: {editor_result}")
    produced = Path(editor_result.get("video_path") or final_video)
    if not produced.is_absolute():
        produced = videoagent_root / produced
    if not produced.exists():
        raise FileNotFoundError(f"VideoEditor did not produce output: {produced}")

    output_video.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(produced, output_video)
    copy_artifacts(videoagent_root, artifacts_dir)

    result = {
        "status": "success",
        "task_id": args.task_id,
        "video_id": args.video_id,
        "audio_id": args.audio_id,
        "source_video_alias": video_alias.name,
        "source_video_dir": str(source_dir),
        "audio_for_run": str(audio_for_run),
        "trim_audio_to_target": bool(args.trim_audio_to_target),
        "cache_dir": str(cache_dir),
        "used_cache": restored_cache,
        "video_scene_path": video_scene_path,
        "timestamp_path": timestamp_path,
        "output_video": str(output_video),
    }
    write_json(worker_result_path(artifacts_dir), result)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run VideoAgent on Mashup-Benchmark tasks.")
    parser.add_argument("--worker-run-task", action="store_true", help=argparse.SUPPRESS)

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--task-id", nargs="+", help="Task id(s), e.g. task_001.")
    group.add_argument("--all", action="store_true", help="Run all benchmark tasks.")
    parser.add_argument("--list-tasks", action="store_true", help="List available task ids and exit.")

    parser.add_argument("--benchmark-root", type=Path, default=BENCHMARK_ROOT)
    parser.add_argument("--videoagent-root", type=Path, default=DEFAULT_VIDEOAGENT_ROOT)
    parser.add_argument("--videoagent-python", type=Path, default=None)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--run-id", default="videoagent_benchmark")
    parser.add_argument("--method", default="VideoAgent")
    parser.add_argument("--method-version", default="rhythm_video_edit")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-reuse-video-cache", action="store_true", help="Disable per-video VideoRAG cache reuse.")
    parser.add_argument("--force-preload", action="store_true", help="Rebuild VideoRAG cache even if one exists.")
    parser.add_argument("--no-trim-audio-to-target", action="store_true", help="Use the full BGM instead of trimming it to target_output_length_sec.")
    parser.add_argument("--notes", default=None)

    # Worker-only arguments.
    parser.add_argument("--video-id")
    parser.add_argument("--audio-id")
    parser.add_argument("--video-path", type=Path)
    parser.add_argument("--audio-path", type=Path)
    parser.add_argument("--prompt")
    parser.add_argument("--target-output-length-sec", type=float)
    parser.add_argument("--output-video", type=Path)
    parser.add_argument("--artifacts-dir", type=Path)
    parser.add_argument("--reuse-video-cache", action="store_true")
    parser.add_argument("--trim-audio-to-target", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.worker_run_task:
        return worker_run_task(args)

    benchmark_root = args.benchmark_root.resolve()
    videoagent_root = args.videoagent_root.resolve()
    videoagent_python = resolve_videoagent_python(videoagent_root, args.videoagent_python)
    results_root = args.results_root.resolve()
    if not videoagent_root.exists():
        raise SystemExit(f"VideoAgent root does not exist: {videoagent_root}")
    if not videoagent_python.exists():
        raise SystemExit(f"VideoAgent Python executable does not exist: {videoagent_python}")
    try:
        results_root.relative_to(benchmark_root)
    except ValueError as exc:
        raise SystemExit("--results-root must be inside --benchmark-root so run paths remain benchmark-relative.") from exc

    task_file = benchmark_root / TASK_FILE_REL
    tasks = load_tasks(task_file)
    by_id = task_lookup(tasks)

    if args.list_tasks:
        for task in tasks:
            print(
                f"{task['id']}\t{task['video']['id']}\t{task['audio']['id']}\t"
                f"{task['task']['type']}\t{task['task']['prompt']}"
            )
        return 0

    if args.all:
        selected = tasks
    elif args.task_id:
        missing = [task_id for task_id in args.task_id if task_id not in by_id]
        if missing:
            raise SystemExit(f"Unknown task id(s): {', '.join(missing)}")
        selected = [by_id[task_id] for task_id in args.task_id]
    else:
        raise SystemExit("Use --task-id task_001, --all, or --list-tasks.")

    run_dir = results_root / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    reuse_video_cache = not args.no_reuse_video_cache
    trim_audio_to_target = not args.no_trim_audio_to_target
    adapter_metadata = {
        "name": "run_videoagent",
        "script": "scripts/run_videoagent.py",
        "project_root": str(videoagent_root),
        "python": str(videoagent_python),
        "benchmark_root": str(benchmark_root),
        "results_root": rel_to_benchmark(results_root, benchmark_root),
        "raw_output_root": str(videoagent_root / "dataset"),
        "model_policy": {
            "audio_analysis": "local_librosa_scipy",
            "audio_analysis_requested_model": "qwen3.5-omni-plus",
            "visual_model": "qwen3.7-plus",
            "llm_model": "qwen3.7-max",
        },
        "task_selection": {
            "mode": "all" if args.all else "task_ids",
            "task_ids": [task["id"] for task in selected],
        },
        "options": {
            "overwrite": bool(args.overwrite),
            "dry_run": bool(args.dry_run),
            "reuse_video_cache": reuse_video_cache,
            "force_preload": bool(args.force_preload),
            "trim_audio_to_target": trim_audio_to_target,
        },
    }

    failures = 0
    for index, task in enumerate(selected, 1):
        print(f"\n[{index}/{len(selected)}] Running {task['id']}")
        task_started_at = now_iso()
        try:
            run_one_task(
                task=task,
                benchmark_root=benchmark_root,
                videoagent_root=videoagent_root,
                videoagent_python=videoagent_python,
                results_root=results_root,
                run_id=args.run_id,
                method=args.method,
                method_version=args.method_version,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                reuse_video_cache=reuse_video_cache,
                force_preload=args.force_preload,
                trim_audio_to_target=trim_audio_to_target,
            )
        except Exception as exc:
            failures += 1
            print(f"[{task['id']}] FAILED: {exc}")
            write_failed_record(
                task=task,
                benchmark_root=benchmark_root,
                results_root=results_root,
                run_id=args.run_id,
                method=args.method,
                method_version=args.method_version,
                started_at=task_started_at,
                exc=exc,
            )
        finally:
            write_run_index(
                run_dir=run_dir,
                run_id=args.run_id,
                method=args.method,
                method_version=args.method_version,
                videoagent_root=videoagent_root,
                videoagent_python=videoagent_python,
                benchmark_root=benchmark_root,
                started_at=started_at,
                adapter=adapter_metadata,
                notes=args.notes,
            )

    print(f"\nRun directory: {run_dir}")
    print(f"Completed {len(selected)} task(s), failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
