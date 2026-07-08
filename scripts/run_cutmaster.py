#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CUTMASTER_ROOT = BENCHMARK_ROOT.parent / "CutMaster"
DEFAULT_RESULTS_ROOT = BENCHMARK_ROOT / "runs"
TASK_FILE_REL = Path("data/tasks/mashup_benchmark.jsonl")


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


def resolve_cutmaster_python(cutmaster_root: Path, explicit_python: Path | None = None) -> Path:
    if explicit_python is not None:
        explicit_python = explicit_python.expanduser()
        return explicit_python if explicit_python.is_absolute() else explicit_python.absolute()
    venv_python = cutmaster_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        # Keep the venv entrypoint path instead of resolving its symlink target.
        # uv-created venvs often point bin/python at the managed base interpreter;
        # executing the resolved target bypasses pyvenv.cfg and loses site-packages.
        return venv_python
    return Path(sys.executable).absolute()


def cutmaster_media_id(path: Path) -> str:
    return path.stem.replace(".", "_").replace(" ", "_")


def cutmaster_instruction_id(instruction: str) -> str:
    instruction_hash = hashlib.md5(instruction.encode("utf-8")).hexdigest()[:8]
    instruction_safe = re.sub(r"[^\w\s-]", "", instruction)[:50].strip().replace(" ", "_")
    if instruction_safe:
        return f"{instruction_safe}_{instruction_hash}"
    return f"instruction_{instruction_hash}"


def derive_cutmaster_outputs(cutmaster_root: Path, video_path: Path, audio_path: Path, instruction: str) -> tuple[Path, Path]:
    video_id = cutmaster_media_id(video_path)
    audio_id = cutmaster_media_id(audio_path)
    instruction_id = cutmaster_instruction_id(instruction)
    out_dir = cutmaster_root / "Output" / "Output" / f"{video_id}_{audio_id}"
    return (
        out_dir / f"shot_plan_{instruction_id}.json",
        out_dir / f"shot_point_{instruction_id}.json",
    )


def shot_duration_bounds(shot_length: float) -> tuple[float, float]:
    min_target = 0.2
    floor = 1.0
    range_cap = 1.0
    shot_length = max(min_target, float(shot_length))
    radius = min(range_cap, max(floor, shot_length))
    return round(max(floor, shot_length - radius), 3), round(shot_length + radius, 3)


def repo_info(cutmaster_root: Path) -> dict[str, Any]:
    def git(args: list[str]) -> str | None:
        try:
            return subprocess.check_output(["git", *args], cwd=cutmaster_root, text=True).strip()
        except Exception:
            return None

    status = git(["status", "--short"])
    return {
        "repo": "CutMaster",
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
    display = shlex.join(cmd)
    print(f"$ {display}")
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {display}\n\n")
        log.flush()
        if dry_run:
            log.write("[dry-run] command not executed\n")
            return 0

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
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


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def rel_to_benchmark(path: Path, benchmark_root: Path) -> str:
    return path.resolve().relative_to(benchmark_root.resolve()).as_posix()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_existing_records(run_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((run_dir / "task_outputs").glob("task_*/run_output.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return records


def load_existing_record(task_dir: Path) -> dict[str, Any] | None:
    path = task_dir / "run_output.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_run_index(
    *,
    run_dir: Path,
    results_root: Path,
    run_id: str,
    method: str,
    method_version: str,
    benchmark_root: Path,
    cutmaster_root: Path,
    cutmaster_python: Path,
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
        "code": repo_info(cutmaster_root),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "adapter": adapter,
        "config": {
            "baseline": "CutMaster",
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
    video_path = benchmark_root / task["video"]["local_path"]
    audio_path = benchmark_root / task["audio"]["local_path"]
    return video_path, audio_path


def run_one_task(
    *,
    task: dict[str, Any],
    benchmark_root: Path,
    cutmaster_root: Path,
    cutmaster_python: Path,
    results_root: Path,
    run_id: str,
    method: str,
    method_version: str,
    cutmaster_video_type: str,
    overwrite: bool,
    dry_run: bool,
    include_hook_dialogue: bool,
    include_ending: bool,
    crop_ratio: str | None,
    original_audio_volume: float,
) -> dict[str, Any]:
    task_id = task["id"]
    run_dir = results_root / run_id
    task_dir = run_dir / "task_outputs" / task_id
    logs_dir = task_dir / "logs"
    artifacts_dir = task_dir / "artifacts"
    output_video = task_dir / "output.mp4"
    existing_record = load_existing_record(task_dir)

    video_path, audio_path = task_paths(task, benchmark_root)
    instruction = task["task"]["prompt"]
    target_output = float(task["task"]["target_output_length_sec"])
    target_shot = float(task["task"]["target_shot_length_sec"])
    prompt_type = task["task"]["type"]

    started_at = now_iso()
    t0 = time.time()
    error: dict[str, Any] | None = None
    status = "skipped" if dry_run else "success"

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    write_json(artifacts_dir / "benchmark_task.json", task)

    shot_plan_path, shot_point_path = derive_cutmaster_outputs(cutmaster_root, video_path, audio_path, instruction)
    can_reuse_success = (
        output_video.exists()
        and not overwrite
        and (existing_record is None or existing_record.get("status") == "success")
        and not (existing_record or {}).get("error")
    )
    if can_reuse_success:
        print(f"[{task_id}] success output exists, reusing: {output_video}")
    else:
        if existing_record and existing_record.get("status") != "success" and not overwrite:
            print(f"[{task_id}] existing record is {existing_record.get('status')}, retrying in same run")
        if not video_path.exists():
            raise FileNotFoundError(f"Benchmark video not found: {video_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"Benchmark audio not found: {audio_path}")

        min_duration = max(5.0, target_output - 5.0)
        max_duration = target_output + 5.0
        min_seg_duration, max_seg_duration = shot_duration_bounds(target_shot)
        instruction_type = "narrative" if prompt_type == "narrative" else "object"

        pipeline_cmd = [
            str(cutmaster_python), "local_run.py",
            "--Video_Path", str(video_path),
            "--Audio_Path", str(audio_path),
            "--Instruction", instruction,
            "--type", cutmaster_video_type,
            "--instruction_type", instruction_type,
            "--config.AUDIO_SEGMENT_MIN_DURATION_SEC", str(min_duration),
            "--config.AUDIO_SEGMENT_MAX_DURATION_SEC", str(max_duration),
            "--config.AUDIO_MIN_SEGMENT_DURATION", str(min_seg_duration),
            "--config.AUDIO_MAX_SEGMENT_DURATION", str(max_seg_duration),
            "--config.HOOK_DIALOGUE_TARGET_RATIO", "0.2",
            "--config.HOOK_DIALOGUE_MAX_DURATION_SEC", "10.0",
        ]
        rc = stream_command(pipeline_cmd, logs_dir / "pipeline.log", cwd=cutmaster_root, dry_run=dry_run)
        if rc != 0:
            raise RuntimeError(f"local_run.py failed with exit code {rc}")

        if not dry_run and not shot_plan_path.exists():
            raise FileNotFoundError(f"Shot plan was not produced: {shot_plan_path}")
        if not dry_run and not shot_point_path.exists():
            raise FileNotFoundError(f"Shot point was not produced: {shot_point_path}")

        render_cmd = [
            str(cutmaster_python), "render/render_video.py",
            "--shot-plan", str(shot_plan_path),
            "--shot-json", str(shot_point_path),
            "--video", str(video_path),
            "--audio", str(audio_path),
            "--output", str(output_video),
            "--no-labels",
            "--original-audio-volume", str(original_audio_volume),
        ]
        if include_hook_dialogue:
            render_cmd.append("--render-hook-dialogue")
        if crop_ratio:
            render_cmd += ["--crop-ratio", crop_ratio]
        if include_ending:
            ending = cutmaster_root / "resource" / "ending" / "ending.mp4"
            if ending.exists():
                render_cmd += ["--ending-video", str(ending)]
        else:
            render_cmd += ["--ending-video", ""]
        font = cutmaster_root / "resource" / "font" / "Pulp Fiction Italic M54.ttf"
        if font.exists():
            render_cmd += ["--dialogue-font", str(font)]

        rc = stream_command(render_cmd, logs_dir / "render.log", cwd=cutmaster_root, dry_run=dry_run)
        if rc != 0:
            raise RuntimeError(f"render_video.py failed with exit code {rc}")

    copy_if_exists(shot_plan_path, artifacts_dir / "shot_plan.json")
    copy_if_exists(shot_point_path, artifacts_dir / "shot_point.json")
    actual_duration = ffprobe_duration(output_video) if output_video.exists() else 0.0
    if not output_video.exists() and not dry_run:
        raise FileNotFoundError(f"Rendered output not found: {output_video}")

    ended_at = now_iso()
    wall_clock = time.time() - t0
    record = {
        "run_id": run_id,
        "method": method,
        "method_version": method_version,
        "task_id": task_id,
        "video_id": task["video"]["id"],
        "audio_id": task["audio"]["id"],
        "prompt_type": prompt_type,
        "status": status,
        "output_video": rel_to_benchmark(output_video, benchmark_root),
        "target_output_length_sec": target_output,
        "target_shot_length_sec": target_shot,
        "actual_output_length_sec": float(actual_duration or 0.0),
        "wall_clock_sec": wall_clock,
        "api_cost_usd": 0.0,
        "created_at": ended_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "code_commit": repo_info(cutmaster_root).get("commit"),
        "config": {
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "cutmaster_python": str(cutmaster_python),
            "cutmaster_video_type": cutmaster_video_type,
            "instruction_type": "narrative" if prompt_type == "narrative" else "object",
            "render_hook_dialogue": include_hook_dialogue,
            "include_ending": include_ending,
            "crop_ratio": crop_ratio,
            "original_audio_volume": original_audio_volume,
        },
        "artifacts": {
            "shot_plan": rel_to_benchmark(artifacts_dir / "shot_plan.json", benchmark_root),
            "shot_point": rel_to_benchmark(artifacts_dir / "shot_point.json", benchmark_root),
            "benchmark_task": rel_to_benchmark(artifacts_dir / "benchmark_task.json", benchmark_root),
            "backend_log": rel_to_benchmark(logs_dir / "pipeline.log", benchmark_root),
            "run_log": rel_to_benchmark(logs_dir / "render.log", benchmark_root),
        },
        "error": error,
    }
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
    run_dir = results_root / run_id
    task_dir = run_dir / "task_outputs" / task_id
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CutMaster on Mashup-Benchmark tasks.")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--task-id", nargs="+", help="Task id(s), e.g. task_006.")
    group.add_argument("--all", action="store_true", help="Run all benchmark tasks.")
    parser.add_argument("--list-tasks", action="store_true", help="List available task ids and exit.")
    parser.add_argument("--benchmark-root", type=Path, default=BENCHMARK_ROOT)
    parser.add_argument("--cutmaster-root", type=Path, default=DEFAULT_CUTMASTER_ROOT)
    parser.add_argument(
        "--cutmaster-python",
        type=Path,
        default=None,
        help="Python executable for CutMaster. Defaults to <cutmaster-root>/.venv/bin/python when present.",
    )
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--run-id", default="cutmaster_benchmark")
    parser.add_argument("--method", default="CutMaster")
    parser.add_argument("--method-version", default="CutMaster")
    parser.add_argument("--video-type", choices=["film", "vlog"], default="film")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate even if task output.mp4 already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands and write metadata without executing heavy steps.")
    parser.add_argument("--no-hook-dialogue", action="store_true", help="Do not render hook dialogue intro.")
    parser.add_argument("--no-ending", action="store_true", help="Do not append resource/ending/ending.mp4.")
    parser.add_argument("--crop-ratio", default=None, help='Optional render crop ratio, e.g. "16:9" or "9:16".')
    parser.add_argument("--original-audio-volume", type=float, default=0.0)
    parser.add_argument("--notes", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    benchmark_root = args.benchmark_root.resolve()
    cutmaster_root = args.cutmaster_root.resolve()
    cutmaster_python = resolve_cutmaster_python(cutmaster_root, args.cutmaster_python)
    results_root = args.results_root.resolve()
    if not cutmaster_root.exists():
        raise SystemExit(f"CutMaster root does not exist: {cutmaster_root}")
    if not cutmaster_python.exists():
        raise SystemExit(f"CutMaster Python executable does not exist: {cutmaster_python}")
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
    adapter_metadata = {
        "name": "run_cutmaster",
        "script": "scripts/run_cutmaster.py",
        "project_root": str(cutmaster_root),
        "python": str(cutmaster_python),
        "benchmark_root": str(benchmark_root),
        "results_root": rel_to_benchmark(results_root, benchmark_root),
        "raw_output_root": str(cutmaster_root / "Output"),
        "task_selection": {
            "mode": "all" if args.all else "task_ids",
            "task_ids": [task["id"] for task in selected],
        },
        "options": {
            "overwrite": bool(args.overwrite),
            "dry_run": bool(args.dry_run),
            "video_type": args.video_type,
            "render_hook_dialogue": not args.no_hook_dialogue,
            "include_ending": not args.no_ending,
            "crop_ratio": args.crop_ratio,
            "original_audio_volume": args.original_audio_volume,
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
                cutmaster_root=cutmaster_root,
                cutmaster_python=cutmaster_python,
                results_root=results_root,
                run_id=args.run_id,
                method=args.method,
                method_version=args.method_version,
                cutmaster_video_type=args.video_type,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                include_hook_dialogue=not args.no_hook_dialogue,
                include_ending=not args.no_ending,
                crop_ratio=args.crop_ratio,
                original_audio_volume=args.original_audio_volume,
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
                results_root=results_root,
                run_id=args.run_id,
                method=args.method,
                method_version=args.method_version,
                cutmaster_root=cutmaster_root,
                cutmaster_python=cutmaster_python,
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
