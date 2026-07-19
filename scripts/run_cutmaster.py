#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CUTMASTER_ROOT = BENCHMARK_ROOT.parent / "CutMaster"
DEFAULT_RESULTS_ROOT = BENCHMARK_ROOT / "runs"
TASK_FILE_REL = Path("data/tasks/mashup_benchmark.jsonl")
CUTMASTER_REPOSITORY_URL = "https://github.com/hit-cxf/CutMaster"


def now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat()


def load_tasks(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def resolve_python(project_root: Path, explicit: Path | None) -> Path:
    if explicit:
        return explicit.expanduser().absolute()
    candidate = project_root / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable).absolute()


def repo_info(project_root: Path) -> dict[str, Any]:
    if not (project_root / ".git").exists():
        return {
            "repo": "CutMaster",
            "repo_url": CUTMASTER_REPOSITORY_URL,
        }

    def git(*args: str) -> str | None:
        try:
            return subprocess.check_output(
                ["git", *args],
                cwd=project_root,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:
            return None

    branch = git("branch", "--show-current")
    commit = git("rev-parse", "HEAD")
    status = git("status", "--short")
    info: dict[str, Any] = {
        "repo": "CutMaster",
        "repo_url": CUTMASTER_REPOSITORY_URL,
    }
    if branch:
        info["branch"] = branch
    if commit:
        info["commit"] = commit
    if status is not None:
        info["dirty"] = bool(status)
    return info


def stream_command(command: list[str], log_path: Path, cwd: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    display = shlex.join(command)
    print(f"$ {display}")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {display}\n\n")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log.write(line)
        return process.wait()


def ffprobe_duration(path: Path) -> float:
    output = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        text=True,
    ).strip()
    return float(output)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def copy_artifact(source: Path, destination: Path) -> str | None:
    if not source.exists():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return str(destination)


def load_record(task_dir: Path) -> dict[str, Any] | None:
    try:
        return json.loads((task_dir / "run_output.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def collect_records(run_dir: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((run_dir / "task_outputs").glob("task_*/run_output.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return records


def write_run_index(
    run_dir: Path,
    benchmark_root: Path,
    run_id: str,
    method: str,
    method_version: str,
    started_at: str,
    project_root: Path,
    python: Path,
    adapter: dict[str, Any],
) -> None:
    records = collect_records(run_dir)
    outputs_path = run_dir / "run_outputs.jsonl"
    with outputs_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    successes = sum(record.get("status") == "success" for record in records)
    failures = sum(record.get("status") == "failed" for record in records)
    status = "success" if records and failures == 0 else "failed" if records and successes == 0 else "partial"
    write_json(
        run_dir / "run_manifest.json",
        {
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
            "num_success": successes,
            "num_failed": failures,
            "run_outputs": relative(outputs_path, benchmark_root),
            "code": repo_info(project_root),
            "environment": {"platform": platform.platform(), "python": str(python)},
            "adapter": adapter,
            "aggregate": {
                "total_wall_clock_sec": sum(float(row.get("wall_clock_sec") or 0) for row in records),
                "total_api_cost_usd": sum(float(row.get("api_cost_usd") or 0) for row in records),
            },
        },
    )


def run_task(
    task: dict[str, Any],
    *,
    benchmark_root: Path,
    project_root: Path,
    python: Path,
    config: Path,
    run_dir: Path,
    run_id: str,
    method: str,
    method_version: str,
    overwrite: bool,
    subtitle: Path | None,
) -> dict[str, Any]:
    task_id = task["id"]
    task_dir = run_dir / "task_outputs" / task_id
    logs_dir = task_dir / "logs"
    artifacts_dir = task_dir / "artifacts"
    work_dir = artifacts_dir / "cutmaster"
    output_video = task_dir / "output.mp4"
    existing = load_record(task_dir)
    if output_video.exists() and not overwrite and (existing or {}).get("status") == "success":
        print(f"[{task_id}] reusing successful output: {output_video}")
        return existing

    video = benchmark_root / task["video"]["local_path"]
    audio = benchmark_root / task["audio"]["local_path"]
    if not video.is_file() or not audio.is_file():
        raise FileNotFoundError(f"Missing benchmark media: video={video.is_file()}, audio={audio.is_file()}")

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    write_json(artifacts_dir / "benchmark_task.json", task)
    started_at = now_iso()
    started = time.monotonic()
    command = [
        str(python), "-m", "cutmaster", "run",
        "--video", str(video),
        "--audio", str(audio),
        "--prompt", task["task"]["prompt"],
        "--output-dir", str(work_dir),
        "--config", str(config),
        "--target-duration", str(task["task"]["target_output_length_sec"]),
        "--target-shot-length", str(task["task"]["target_shot_length_sec"]),
        "--prompt-type", task["task"]["type"],
        "--video-title", task["video"].get("title_zh") or task["video"].get("title_en") or "",
    ]
    if subtitle:
        command += ["--subtitle", str(subtitle)]
    if overwrite:
        command.append("--overwrite")

    return_code = stream_command(command, logs_dir / "backend.log", project_root)
    if return_code:
        raise RuntimeError(f"CutMaster exited with code {return_code}")
    result = json.loads((work_dir / "result.json").read_text(encoding="utf-8"))
    shutil.copy2(work_dir / "output.mp4", output_video)
    artifact_map = {
        "benchmark_task": relative(artifacts_dir / "benchmark_task.json", benchmark_root),
        "script_raw": relative(work_dir / "script_raw.json", benchmark_root),
        "script_adapted": relative(work_dir / "script_adapted.json", benchmark_root),
        "dialogues_json": relative(work_dir / "dialogues.json", benchmark_root),
        "processed_subtitle": relative(work_dir / "dialogue_merged.srt", benchmark_root),
        "cutmaster_result": relative(work_dir / "result.json", benchmark_root),
        "backend_log": relative(logs_dir / "backend.log", benchmark_root),
        "cutmaster_log": relative(work_dir / "cutmaster.log", benchmark_root),
    }
    ended_at = now_iso()
    record = {
        "run_id": run_id,
        "method": method,
        "method_version": method_version,
        "task_id": task_id,
        "video_id": task["video"]["id"],
        "audio_id": task["audio"]["id"],
        "prompt_type": task["task"]["type"],
        "status": "success",
        "output_video": relative(output_video, benchmark_root),
        "target_output_length_sec": float(task["task"]["target_output_length_sec"]),
        "target_shot_length_sec": float(task["task"]["target_shot_length_sec"]),
        "actual_output_length_sec": ffprobe_duration(output_video),
        "wall_clock_sec": time.monotonic() - started,
        "api_cost_usd": 0.0,
        "created_at": ended_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "code_commit": repo_info(project_root)["commit"],
        "config": {
            "cutmaster_config": str(config),
            "subtitle_source": str(subtitle) if subtitle else "dashscope_fun_asr",
            "stage_timings_sec": result.get("stage_timings_sec", {}),
            "num_raw_clips": result.get("num_raw_clips"),
            "num_adapted_clips": result.get("num_adapted_clips"),
        },
        "artifacts": artifact_map,
        "error": None,
    }
    write_json(task_dir / "run_output.json", record)
    return record


def write_failure(
    task: dict[str, Any], benchmark_root: Path, run_dir: Path, run_id: str,
    method: str, method_version: str, started_at: str, exc: BaseException,
) -> None:
    task_dir = run_dir / "task_outputs" / task["id"]
    output = task_dir / "output.mp4"
    ended_at = now_iso()
    write_json(
        task_dir / "run_output.json",
        {
            "run_id": run_id,
            "method": method,
            "method_version": method_version,
            "task_id": task["id"],
            "video_id": task["video"]["id"],
            "audio_id": task["audio"]["id"],
            "prompt_type": task["task"]["type"],
            "status": "failed",
            "output_video": relative(output, benchmark_root),
            "target_output_length_sec": float(task["task"]["target_output_length_sec"]),
            "target_shot_length_sec": float(task["task"]["target_shot_length_sec"]),
            "actual_output_length_sec": 0.0,
            "wall_clock_sec": 0.0,
            "api_cost_usd": 0.0,
            "created_at": ended_at,
            "started_at": started_at,
            "ended_at": ended_at,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the backend-only CutMaster pipeline on benchmark tasks.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--task-id", nargs="+")
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--list-tasks", action="store_true")
    parser.add_argument("--benchmark-root", type=Path, default=BENCHMARK_ROOT)
    parser.add_argument("--cutmaster-root", type=Path, default=DEFAULT_CUTMASTER_ROOT)
    parser.add_argument("--cutmaster-python", type=Path)
    parser.add_argument("--cutmaster-config", type=Path)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--run-id", default="cutmaster_benchmark")
    parser.add_argument("--method", default="CutMaster")
    parser.add_argument("--method-version", default="backend-mvp")
    parser.add_argument("--subtitle-path", type=Path, help="Optional SRT for a single selected task; otherwise run Fun-ASR.")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    benchmark_root = args.benchmark_root.resolve()
    project_root = args.cutmaster_root.resolve()
    python = resolve_python(project_root, args.cutmaster_python)
    config = (args.cutmaster_config or project_root / "config.toml").resolve()
    results_root = args.results_root.resolve()
    if not project_root.is_dir() or not python.exists() or not config.is_file():
        raise SystemExit(f"Invalid CutMaster setup: root={project_root}, python={python}, config={config}")
    try:
        results_root.relative_to(benchmark_root)
    except ValueError as exc:
        raise SystemExit("--results-root must be inside the benchmark repository") from exc

    tasks = load_tasks(benchmark_root / TASK_FILE_REL)
    lookup = {task["id"]: task for task in tasks}
    if args.list_tasks:
        for task in tasks:
            print(f"{task['id']}\t{task['task']['type']}\t{task['task']['prompt']}")
        return 0
    if args.all:
        selected = tasks
    elif args.task_id:
        missing = [task_id for task_id in args.task_id if task_id not in lookup]
        if missing:
            raise SystemExit(f"Unknown task ids: {', '.join(missing)}")
        selected = [lookup[task_id] for task_id in args.task_id]
    else:
        raise SystemExit("Use --task-id, --all, or --list-tasks")
    if args.subtitle_path and len(selected) != 1:
        raise SystemExit("--subtitle-path can only be used with one selected task")
    subtitle = args.subtitle_path.resolve() if args.subtitle_path else None
    if subtitle and not subtitle.is_file():
        raise SystemExit(f"Subtitle not found: {subtitle}")

    run_dir = results_root / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    adapter = {
        "name": "run_cutmaster",
        "script": "scripts/run_cutmaster.py",
        "project_root": str(project_root),
        "python": str(python),
        "benchmark_root": str(benchmark_root),
        "results_root": results_root.relative_to(benchmark_root).as_posix(),
        "task_selection": {
            "mode": "all" if args.all else "task_ids",
            "task_ids": [task["id"] for task in selected],
        },
        "options": {
            "overwrite": bool(args.overwrite),
            "config": str(config),
            "subtitle_path": str(subtitle) if subtitle else None,
        },
    }
    failures = 0
    for index, task in enumerate(selected, start=1):
        print(f"\n[{index}/{len(selected)}] Running {task['id']}")
        task_started = now_iso()
        try:
            run_task(
                task,
                benchmark_root=benchmark_root,
                project_root=project_root,
                python=python,
                config=config,
                run_dir=run_dir,
                run_id=args.run_id,
                method=args.method,
                method_version=args.method_version,
                overwrite=args.overwrite,
                subtitle=subtitle,
            )
        except Exception as exc:
            failures += 1
            print(f"[{task['id']}] FAILED: {exc}")
            write_failure(task, benchmark_root, run_dir, args.run_id, args.method, args.method_version, task_started, exc)
        finally:
            write_run_index(
                run_dir, benchmark_root, args.run_id, args.method, args.method_version,
                started_at, project_root, python, adapter,
            )
    print(f"Run directory: {run_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
