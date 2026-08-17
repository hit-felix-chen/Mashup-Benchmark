#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CUTMASTER_ROOT = BENCHMARK_ROOT.parent / "CutMaster"
DEFAULT_RESULTS_ROOT = BENCHMARK_ROOT / "runs"
TASK_FILE_REL = Path("data/tasks/mashup_benchmark.jsonl")
CUTMASTER_REPOSITORY_URL = "https://github.com/hit-cxf/CutMaster"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CUTMASTER_WORKER_REL = Path("scripts/cutmaster_adapter_worker.py")
CUTMASTER_APPLICATION_ENTRYPOINT = (
    "CutMasterApplication.open(config).workflows.execute_and_wait("
    "ExecuteManagedWorkflowCommand(...))"
)
ARTIFACT_MANIFEST_MAJOR_VERSION = 1
ARTIFACT_MANIFEST_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
ARTIFACT_LOGICAL_KEY_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
REQUIRED_CUTMASTER_ARTIFACT_KEYS = frozenset(
    {
        "workflow.result",
        "workflow.model_usage",
        "analyser.video_result",
        "analyser.music_result",
        "planners.render_plan",
        "renderer.output_video",
    }
)
BENCHMARK_ARTIFACT_KEYS = {
    "analysis_result": "analyser.video_result",
    "music_analysis_result": "analyser.music_result",
    "planners_result": "planners.result",
    "render_result": "renderer.result",
    "script_raw": "planners.raw_script",
    "render_plan": "planners.render_plan",
    "dialogues_json": "analyser.dialogues",
    "processed_subtitle": "analyser.dialogue_subtitle",
    "cutmaster_result": "workflow.result",
}
TARGET_DURATION_MODES = ("task", "music")


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
            log.write(ANSI_ESCAPE_RE.sub("", line))
        return process.wait()


def ffprobe_duration(path: Path) -> float:
    output = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(output)


def resolve_target_output_length_sec(
    task: dict[str, Any],
    audio: Path,
    target_duration_mode: str,
) -> float:
    if target_duration_mode == "task":
        duration = float(task["task"]["target_output_length_sec"])
    elif target_duration_mode == "music":
        duration = ffprobe_duration(audio)
    else:
        raise ValueError(f"Unsupported target duration mode: {target_duration_mode!r}")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(
            f"Resolved target output duration must be positive and finite, got {duration!r} "
            f"from {target_duration_mode!r} mode"
        )
    return duration


def _record_matches_target(
    record: dict[str, Any],
    *,
    target_duration_mode: str,
    target_output_length_sec: float,
) -> bool:
    recorded_mode = record.get("target_duration_mode", "task")
    try:
        recorded_target = float(record["target_output_length_sec"])
    except (KeyError, TypeError, ValueError):
        return False
    return recorded_mode == target_duration_mode and math.isclose(
        recorded_target,
        target_output_length_sec,
        rel_tol=1e-9,
        abs_tol=1e-6,
    )


def reusable_success_record(
    task_dir: Path,
    *,
    overwrite: bool,
    target_duration_mode: str,
    target_output_length_sec: float,
) -> dict[str, Any] | None:
    output_video = task_dir / "output.mp4"
    existing = load_record(task_dir)
    if overwrite or not output_video.exists() or (existing or {}).get("status") != "success":
        return None
    assert existing is not None
    if _record_matches_target(
        existing,
        target_duration_mode=target_duration_mode,
        target_output_length_sec=target_output_length_sec,
    ):
        return existing
    recorded_mode = existing.get("target_duration_mode", "task")
    recorded_target = existing.get("target_output_length_sec")
    raise RuntimeError(
        "Existing successful output uses a different target duration "
        f"(mode={recorded_mode!r}, target={recorded_target!r}); requested "
        f"mode={target_duration_mode!r}, target={target_output_length_sec!r}. "
        "Use --overwrite or a new --run-id."
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _normalize_artifact_path(value: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise TypeError("CutMaster Artifact Manifest paths must be strings")
    if not value or "\\" in value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"Invalid CutMaster artifact path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Invalid CutMaster artifact path: {value!r}")
    return path


def _resolve_artifact_path(artifact_root: Path, value: str) -> Path:
    relative_path = _normalize_artifact_path(value)
    canonical_root = artifact_root.resolve(strict=True)
    if not canonical_root.is_dir():
        raise ValueError("CutMaster managed artifact root must be a directory")
    try:
        artifact = canonical_root.joinpath(*relative_path.parts).resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"CutMaster artifact is missing: {value}") from exc
    try:
        artifact.relative_to(canonical_root)
    except ValueError as exc:
        raise ValueError("CutMaster artifact path escapes its managed artifact root") from exc
    if not artifact.is_file():
        raise ValueError(f"CutMaster artifact is not a file: {value}")
    return artifact


def resolve_cutmaster_artifacts(
    artifact_root: Path,
    result: dict[str, Any],
) -> dict[str, Path]:
    version = result.get("artifact_manifest_version")
    if not isinstance(version, str):
        raise TypeError("CutMaster result has no string artifact_manifest_version")
    match = ARTIFACT_MANIFEST_VERSION_RE.fullmatch(version)
    if match is None or int(match.group(1)) != ARTIFACT_MANIFEST_MAJOR_VERSION:
        raise ValueError(f"Unsupported CutMaster Artifact Manifest version: {version!r}")
    manifest = result.get("artifacts")
    if not isinstance(manifest, dict):
        raise TypeError("CutMaster result has no Artifact Manifest mapping")
    invalid_keys = sorted(
        repr(key) for key in manifest if not isinstance(key, str) or ARTIFACT_LOGICAL_KEY_RE.fullmatch(key) is None
    )
    if invalid_keys:
        raise ValueError(f"Invalid CutMaster artifact logical keys: {invalid_keys}")
    missing = sorted(REQUIRED_CUTMASTER_ARTIFACT_KEYS - set(manifest))
    if missing:
        raise ValueError(f"CutMaster Artifact Manifest is missing keys: {missing}")
    return {
        logical_key: _resolve_artifact_path(artifact_root, value)
        for logical_key, value in manifest.items()
    }


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
    dialogue_audio: bool,
    target_duration_mode: str = "task",
    target_output_length_sec: float | None = None,
) -> dict[str, Any]:
    task_id = task["id"]
    if target_duration_mode not in TARGET_DURATION_MODES:
        raise ValueError(f"Unsupported target duration mode: {target_duration_mode!r}")
    task_dir = run_dir / "task_outputs" / task_id
    logs_dir = task_dir / "logs"
    artifacts_dir = task_dir / "artifacts"
    work_dir = artifacts_dir / "cutmaster"
    adapter_result = work_dir / "adapter_result.json"
    output_video = task_dir / "output.mp4"
    video = benchmark_root / task["video"]["local_path"]
    audio = benchmark_root / task["audio"]["local_path"]
    if not video.is_file() or not audio.is_file():
        raise FileNotFoundError(f"Missing benchmark media: video={video.is_file()}, audio={audio.is_file()}")
    effective_target = (
        resolve_target_output_length_sec(task, audio, target_duration_mode)
        if target_output_length_sec is None
        else float(target_output_length_sec)
    )
    if not math.isfinite(effective_target) or effective_target <= 0:
        raise ValueError(f"target_output_length_sec must be positive and finite, got {effective_target!r}")
    existing = reusable_success_record(
        task_dir,
        overwrite=overwrite,
        target_duration_mode=target_duration_mode,
        target_output_length_sec=effective_target,
    )
    if existing is not None:
        print(f"[{task_id}] reusing successful output: {output_video}")
        return existing

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    write_json(artifacts_dir / "benchmark_task.json", task)
    started_at = now_iso()
    started = time.monotonic()
    worker = benchmark_root / CUTMASTER_WORKER_REL
    command = [
        str(python),
        str(worker),
        "--video",
        str(video),
        "--audio",
        str(audio),
        "--prompt",
        task["task"]["prompt"],
        "--result-file",
        str(adapter_result),
        "--config",
        str(config),
        "--target-duration",
        str(effective_target),
        "--target-shot-length",
        str(task["task"]["target_shot_length_sec"]),
        "--prompt-type",
        task["task"]["type"],
        "--video-title",
        task["video"].get("title_zh") or task["video"].get("title_en") or "",
        "--video-material-name",
        (task["video"].get("material_name") or Path(task["video"]["local_path"]).stem),
        "--music-material-name",
        (task["audio"].get("material_name") or Path(task["audio"]["local_path"]).stem),
        "--project-name",
        f"Benchmark · {run_id} · {task_id}",
        "--dialogue-audio" if dialogue_audio else "--no-dialogue-audio",
    ]
    if subtitle:
        command += ["--subtitle", str(subtitle)]
    return_code = stream_command(command, logs_dir / "backend.log", project_root)
    if return_code:
        raise RuntimeError(f"CutMaster exited with code {return_code}")
    result_path = adapter_result
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != "success":
        raise ValueError("CutMaster returned a non-success WorkflowResult")
    raw_artifact_root = result.get("artifact_root")
    if not isinstance(raw_artifact_root, str):
        raise TypeError("CutMaster managed result has no artifact_root")
    artifact_root = Path(raw_artifact_root)
    if not artifact_root.is_absolute():
        raise ValueError("CutMaster managed artifact_root must be absolute")
    cutmaster_artifacts = resolve_cutmaster_artifacts(artifact_root, result)
    shutil.copy2(cutmaster_artifacts["renderer.output_video"], output_video)
    exported_artifacts: dict[str, Path] = {}
    for logical_key, source in cutmaster_artifacts.items():
        destination = (
            work_dir
            / "managed_artifacts"
            / Path(*logical_key.split("."))
            / source.name
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        exported_artifacts[logical_key] = destination
    artifact_map = {
        "benchmark_task": relative(artifacts_dir / "benchmark_task.json", benchmark_root),
        "backend_log": relative(logs_dir / "backend.log", benchmark_root),
        "adapter_result": relative(adapter_result, benchmark_root),
    }
    artifact_map.update(
        {
            benchmark_key: relative(exported_artifacts[logical_key], benchmark_root)
            for benchmark_key, logical_key in BENCHMARK_ARTIFACT_KEYS.items()
            if logical_key in exported_artifacts
        }
    )
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
        "target_duration_mode": target_duration_mode,
        "target_output_length_sec": effective_target,
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
            "dialogue_audio_included": bool(result.get("dialogue_audio_included", dialogue_audio)),
            "stage_timings_sec": result.get("stage_timings_sec", {}),
            "num_raw_clips": result.get("num_raw_clips"),
            "num_planned_clips": result.get("num_planned_clips"),
            "cutmaster_project_id": result.get("project_id"),
            "cutmaster_run_id": result.get("run_id"),
            "cutmaster_frozen_edit_id": result.get("frozen_edit_id"),
            "cutmaster_render_variant_id": result.get("render_variant_id"),
        },
        "artifacts": artifact_map,
        "error": None,
    }
    write_json(task_dir / "run_output.json", record)
    return record


def write_failure(
    task: dict[str, Any],
    benchmark_root: Path,
    run_dir: Path,
    run_id: str,
    method: str,
    method_version: str,
    started_at: str,
    exc: BaseException,
    *,
    target_duration_mode: str = "task",
    target_output_length_sec: float | None = None,
) -> None:
    task_dir = run_dir / "task_outputs" / task["id"]
    output = task_dir / "output.mp4"
    ended_at = now_iso()
    effective_target = (
        float(task["task"]["target_output_length_sec"])
        if target_output_length_sec is None
        else float(target_output_length_sec)
    )
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
            "target_duration_mode": target_duration_mode,
            "target_output_length_sec": effective_target,
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
    parser.add_argument("--method-version", default="master-team-v1")
    parser.add_argument(
        "--target-duration-mode",
        choices=TARGET_DURATION_MODES,
        default="task",
        help=(
            "Choose the effective output target: 'task' uses the benchmark task value; "
            "'music' probes and uses the full input BGM duration."
        ),
    )
    parser.add_argument(
        "--subtitle-path", type=Path, help="Optional SRT for a single selected task; otherwise run Fun-ASR."
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--dialogue-audio",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=("Include selected original-dialogue anchors. The default benchmark output is BGM-only."),
    )
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
    worker = benchmark_root / CUTMASTER_WORKER_REL
    if not worker.is_file():
        raise SystemExit(f"CutMaster adapter worker not found: {worker}")
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

    effective_targets: dict[str, float] = {}
    for task in selected:
        audio = benchmark_root / task["audio"]["local_path"]
        if not audio.is_file():
            raise SystemExit(f"Audio not found for {task['id']}: {audio}")
        effective_targets[task["id"]] = resolve_target_output_length_sec(
            task,
            audio,
            args.target_duration_mode,
        )

    run_dir = results_root / args.run_id
    for task in selected:
        try:
            reusable_success_record(
                run_dir / "task_outputs" / task["id"],
                overwrite=args.overwrite,
                target_duration_mode=args.target_duration_mode,
                target_output_length_sec=effective_targets[task["id"]],
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    adapter = {
        "name": "run_cutmaster",
        "script": "scripts/run_cutmaster.py",
        "worker": CUTMASTER_WORKER_REL.as_posix(),
        "entrypoint": CUTMASTER_APPLICATION_ENTRYPOINT,
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
            "dialogue_audio": bool(args.dialogue_audio),
            "target_duration_mode": args.target_duration_mode,
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
                dialogue_audio=args.dialogue_audio,
                target_duration_mode=args.target_duration_mode,
                target_output_length_sec=effective_targets[task["id"]],
            )
        except Exception as exc:
            failures += 1
            print(f"[{task['id']}] FAILED: {exc}")
            write_failure(
                task,
                benchmark_root,
                run_dir,
                args.run_id,
                args.method,
                args.method_version,
                task_started,
                exc,
                target_duration_mode=args.target_duration_mode,
                target_output_length_sec=effective_targets[task["id"]],
            )
        finally:
            write_run_index(
                run_dir,
                benchmark_root,
                args.run_id,
                args.method,
                args.method_version,
                started_at,
                project_root,
                python,
                adapter,
            )
    print(f"Run directory: {run_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
