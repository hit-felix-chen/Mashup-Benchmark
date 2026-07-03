#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
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
DEFAULT_DIRECT_CLAW_ROOT = BENCHMARK_ROOT.parent / "DIRECT-Claw"
DEFAULT_RESULTS_ROOT = BENCHMARK_ROOT / "runs"
TASK_FILE_REL = Path("data/tasks/mashup_benchmark.jsonl")
ADAPTER_DATA_ROOT = Path("benchmark_adapter")


def normalize_omp_num_threads(value: str | None) -> str:
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


os.environ["OMP_NUM_THREADS"] = normalize_omp_num_threads(os.environ.get("OMP_NUM_THREADS"))


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


def resolve_direct_claw_python(direct_claw_root: Path, explicit_python: Path | None = None) -> Path:
    if explicit_python is not None:
        explicit_python = explicit_python.expanduser()
        return explicit_python if explicit_python.is_absolute() else explicit_python.absolute()
    candidates = [
        direct_claw_root / ".venv" / "bin" / "python",
        Path("/root/miniconda3/envs/direct/bin/python"),
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


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, str):
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def symlink_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink() and dst.resolve() == src.resolve():
            return
        dst.unlink()
    try:
        dst.symlink_to(src.resolve())
    except Exception:
        shutil.copy2(src, dst)


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


def gpu_name() -> str | None:
    try:
        return subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True,
        ).strip().splitlines()[0]
    except Exception:
        return None


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
        return cv2_duration(path)


def cv2_duration(path: Path) -> float | None:
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(str(path))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        cap.release()
        if fps > 0 and frames > 0:
            return frames / fps
    except Exception:
        return None
    return None


def video_fps(path: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            text=True,
        ).strip()
        if "/" in out:
            num, den = out.split("/", 1)
            return float(num) / float(den)
        return float(out)
    except Exception:
        pass
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(str(path))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        cap.release()
        if fps > 0:
            return fps
    except Exception:
        pass
    return 24.0


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
        env["OMP_NUM_THREADS"] = normalize_omp_num_threads(env.get("OMP_NUM_THREADS"))
        env["HF_HUB_OFFLINE"] = env.get("HF_HUB_OFFLINE") or "1"
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


def ensure_ffmpeg_on_path(direct_claw_root: Path, direct_claw_python: Path) -> Path | None:
    if shutil.which("ffmpeg"):
        return None
    try:
        ffmpeg_exe = subprocess.check_output(
            [
                str(direct_claw_python),
                "-c",
                "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())",
            ],
            text=True,
        ).strip()
    except Exception:
        return None

    source = Path(ffmpeg_exe)
    if not source.exists():
        return None

    bin_dir = direct_claw_root / "output" / "benchmark_adapter" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "ffmpeg"
    if shim.exists() or shim.is_symlink():
        shim.unlink()
    try:
        shim.symlink_to(source)
    except Exception:
        shutil.copy2(source, shim)
        shim.chmod(0o755)

    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    return bin_dir


def ensure_u2net_weights(direct_claw_root: Path) -> Path:
    expected = direct_claw_root / "U-2-Net" / "saved_models" / "u2net" / "u2net.pth"
    if expected.exists():
        return expected

    candidates = [
        direct_claw_root / "U-2-Net" / "saved_models" / "u2net_portrait.pth",
        direct_claw_root / "U-2-Net" / "saved_models" / "u2net_portrait" / "u2net_portrait.pth",
    ]
    for candidate in candidates:
        if candidate.exists():
            expected.parent.mkdir(parents=True, exist_ok=True)
            try:
                expected.symlink_to(candidate.relative_to(expected.parent))
            except Exception:
                shutil.copy2(candidate, expected)
            return expected

    raise FileNotFoundError(
        "DIRECT-Claw U2NET weights not found. Expected "
        f"{expected} or one of: {', '.join(str(path) for path in candidates)}"
    )


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
    run_id: str,
    method: str,
    method_version: str,
    benchmark_root: Path,
    direct_claw_root: Path,
    direct_claw_python: Path,
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
        "code": repo_info(direct_claw_root, "DIRECT-Claw"),
        "environment": {
            "platform": platform.platform(),
            "python": str(direct_claw_python),
            "gpu": gpu_name(),
        },
        "adapter": adapter,
        "config": {
            "baseline": "DIRECT-Claw",
            "pipeline": [
                "main_preprocess",
                "Screenwriter",
                "Director",
                "Editor",
                "ffmpeg_mux",
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


def direct_rel_video_path(task: dict[str, Any], video_path: Path) -> Path:
    return ADAPTER_DATA_ROOT / "videos" / task["video"]["id"] / video_path.name


def direct_rel_audio_path(task: dict[str, Any], audio_path: Path) -> Path:
    return ADAPTER_DATA_ROOT / "audios" / task["audio"]["id"] / audio_path.name


def direct_rel_csv_path(task: dict[str, Any]) -> Path:
    return ADAPTER_DATA_ROOT / "tasks" / f"{task['video']['id']}.csv"


def direct_rel_task_yaml_path(task: dict[str, Any]) -> Path:
    return ADAPTER_DATA_ROOT / "tasks" / f"{task['id']}.yaml"


def direct_feature_path(direct_claw_root: Path, rel_video_path: Path) -> Path:
    return direct_claw_root / "output" / rel_video_path.with_suffix(".pkl")


def prepare_direct_inputs(
    *,
    task: dict[str, Any],
    benchmark_root: Path,
    direct_claw_root: Path,
    artifacts_dir: Path,
) -> dict[str, Path | float]:
    video_path, audio_path = task_paths(task, benchmark_root)
    if not video_path.exists():
        raise FileNotFoundError(f"Benchmark video not found: {video_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Benchmark audio not found: {audio_path}")

    rel_video = direct_rel_video_path(task, video_path)
    rel_audio = direct_rel_audio_path(task, audio_path)
    rel_csv = direct_rel_csv_path(task)
    rel_task_yaml = direct_rel_task_yaml_path(task)

    direct_data_dir = direct_claw_root / "data"
    symlink_or_copy(video_path, direct_data_dir / rel_video)
    symlink_or_copy(audio_path, direct_data_dir / rel_audio)

    csv_path = direct_data_dir / rel_csv
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["video_id", "filepath"])
        writer.writeheader()
        writer.writerow({"video_id": task["video"]["id"], "filepath": rel_video.as_posix()})

    fps = video_fps(video_path)
    task_yaml_path = direct_data_dir / rel_task_yaml
    write_yaml(
        task_yaml_path,
        {
            "video_csv": rel_csv.as_posix(),
            "video_fps": round(fps, 6),
            "music_path": rel_audio.as_posix(),
            "user_prompt": task["task"]["prompt"],
        },
    )

    copy_if_exists(csv_path, artifacts_dir / "source_videos.csv")
    copy_if_exists(task_yaml_path, artifacts_dir / "direct_claw_task.yaml")

    return {
        "video_path": video_path,
        "audio_path": audio_path,
        "direct_rel_video": rel_video,
        "direct_rel_audio": rel_audio,
        "direct_rel_csv": rel_csv,
        "direct_rel_task_yaml": rel_task_yaml,
        "csv_path": csv_path,
        "task_yaml_path": task_yaml_path,
        "feature_path": direct_feature_path(direct_claw_root, rel_video),
        "fps": fps,
    }


def run_one_task(
    *,
    task: dict[str, Any],
    benchmark_root: Path,
    direct_claw_root: Path,
    direct_claw_python: Path,
    results_root: Path,
    run_id: str,
    method: str,
    method_version: str,
    overwrite: bool,
    dry_run: bool,
    force_preprocess: bool,
    skip_preprocess: bool,
    cfg_path: Path,
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

    target_output = float(task["task"]["target_output_length_sec"])
    target_shot = float(task["task"]["target_shot_length_sec"])
    prompt_type = task["task"]["type"]
    started_at = now_iso()
    t0 = time.time()
    existing_record = load_existing_record(task_dir)

    write_json(artifacts_dir / "benchmark_task.json", task)
    prepared = prepare_direct_inputs(
        task=task,
        benchmark_root=benchmark_root,
        direct_claw_root=direct_claw_root,
        artifacts_dir=artifacts_dir,
    )
    feature_path = Path(prepared["feature_path"])
    task_yaml_path = Path(prepared["task_yaml_path"])
    csv_path = Path(prepared["csv_path"])
    result_raw_path = direct_claw_root / "output" / "benchmark_adapter" / run_id / task_id / "out.mp4"
    raw_log_path = direct_claw_root / "output" / "benchmark_adapter" / run_id / task_id / "out.log"

    can_reuse_success = (
        output_video.exists()
        and not overwrite
        and (existing_record is None or existing_record.get("status") == "success")
        and not (existing_record or {}).get("error")
    )
    if can_reuse_success:
        print(f"[{task_id}] success output exists, reusing: {output_video}")
    else:
        if not skip_preprocess:
            if force_preprocess or not feature_path.exists():
                preprocess_cmd = [
                    str(direct_claw_python),
                    "-m", "src.main_preprocess",
                    "--csv", str(csv_path),
                ]
                if force_preprocess:
                    preprocess_cmd.append("--recalc")
                rc = stream_command(preprocess_cmd, logs_dir / "preprocess.log", cwd=direct_claw_root, dry_run=dry_run)
                if rc != 0:
                    raise RuntimeError(f"DIRECT-Claw preprocessing failed with exit code {rc}")
            else:
                print(f"[{task_id}] feature cache exists, reusing: {feature_path}")

        if not dry_run and not feature_path.exists():
            raise FileNotFoundError(f"DIRECT-Claw feature cache not found: {feature_path}")

        result_raw_path.parent.mkdir(parents=True, exist_ok=True)
        agent_cmd = [
            str(direct_claw_python),
            "-m", "src.main_agent",
            "--yaml_path", str(task_yaml_path),
            "--cfg_path", str(cfg_path),
            "--result_path", str(result_raw_path),
            "--log_path", str(raw_log_path),
        ]
        rc = stream_command(agent_cmd, logs_dir / "pipeline.log", cwd=direct_claw_root, dry_run=dry_run)
        if rc != 0:
            raise RuntimeError(f"DIRECT-Claw main_agent failed with exit code {rc}")
        if not dry_run and not result_raw_path.exists():
            raise FileNotFoundError(f"DIRECT-Claw output not found: {result_raw_path}")
        if not dry_run:
            output_video.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result_raw_path, output_video)

    copy_if_exists(raw_log_path, logs_dir / "direct_claw.log")
    actual_duration = ffprobe_duration(output_video) if output_video.exists() else 0.0
    ended_at = now_iso()
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
        "code_commit": repo_info(direct_claw_root, "DIRECT-Claw").get("commit"),
        "config": {
            "video_path": str(prepared["video_path"]),
            "audio_path": str(prepared["audio_path"]),
            "direct_claw_root": str(direct_claw_root),
            "direct_claw_python": str(direct_claw_python),
            "cfg_path": str(cfg_path),
            "feature_path": str(feature_path),
            "video_fps": float(prepared["fps"]),
            "force_preprocess": force_preprocess,
            "skip_preprocess": skip_preprocess,
            "direct_rel_video": Path(prepared["direct_rel_video"]).as_posix(),
            "direct_rel_audio": Path(prepared["direct_rel_audio"]).as_posix(),
            "direct_rel_csv": Path(prepared["direct_rel_csv"]).as_posix(),
            "direct_rel_task_yaml": Path(prepared["direct_rel_task_yaml"]).as_posix(),
            "raw_output_video": str(result_raw_path),
        },
        "artifacts": {
            "benchmark_task": rel_to_benchmark(artifacts_dir / "benchmark_task.json", benchmark_root),
            "source_videos": rel_to_benchmark(artifacts_dir / "source_videos.csv", benchmark_root),
            "task_yaml": rel_to_benchmark(artifacts_dir / "direct_claw_task.yaml", benchmark_root),
            "backend_log": rel_to_benchmark(logs_dir / "pipeline.log", benchmark_root),
            "run_log": rel_to_benchmark(logs_dir / "direct_claw.log", benchmark_root)
            if (logs_dir / "direct_claw.log").exists()
            else rel_to_benchmark(logs_dir / "pipeline.log", benchmark_root),
        },
        "error": None,
    }
    if (logs_dir / "preprocess.log").exists():
        record["artifacts"]["preprocess_log"] = rel_to_benchmark(logs_dir / "preprocess.log", benchmark_root)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DIRECT-Claw on Mashup-Benchmark tasks.")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--task-id", nargs="+", help="Task id(s), e.g. task_001.")
    group.add_argument("--all", action="store_true", help="Run all benchmark tasks.")
    parser.add_argument("--list-tasks", action="store_true", help="List available task ids and exit.")
    parser.add_argument("--benchmark-root", type=Path, default=BENCHMARK_ROOT)
    parser.add_argument("--direct-claw-root", type=Path, default=DEFAULT_DIRECT_CLAW_ROOT)
    parser.add_argument("--direct-claw-python", type=Path, default=None)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--run-id", default="direct_claw_benchmark")
    parser.add_argument("--method", default="DIRECT-Claw")
    parser.add_argument("--method-version", default="main")
    parser.add_argument("--cfg-path", type=Path, default=None, help="DIRECT-Claw system config. Defaults to <direct-claw-root>/configs/cfg.yaml.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate even if task output.mp4 already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Write metadata and print commands without executing DIRECT-Claw.")
    parser.add_argument("--force-preprocess", action="store_true", help="Recalculate DIRECT-Claw video features even if the cache exists.")
    parser.add_argument("--skip-preprocess", action="store_true", help="Skip preprocessing and require existing feature cache.")
    parser.add_argument("--notes", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    benchmark_root = args.benchmark_root.resolve()
    direct_claw_root = args.direct_claw_root.resolve()
    direct_claw_python = resolve_direct_claw_python(direct_claw_root, args.direct_claw_python)
    results_root = args.results_root.resolve()
    cfg_path = (args.cfg_path or (direct_claw_root / "configs" / "cfg.yaml")).resolve()

    if not direct_claw_root.exists():
        raise SystemExit(f"DIRECT-Claw root does not exist: {direct_claw_root}")
    if not direct_claw_python.exists():
        raise SystemExit(f"DIRECT-Claw Python executable does not exist: {direct_claw_python}")
    if not cfg_path.exists():
        raise SystemExit(f"DIRECT-Claw cfg_path does not exist: {cfg_path}")
    try:
        results_root.relative_to(benchmark_root)
    except ValueError as exc:
        raise SystemExit("--results-root must be inside --benchmark-root so run paths remain benchmark-relative.") from exc
    if args.force_preprocess and args.skip_preprocess:
        raise SystemExit("--force-preprocess and --skip-preprocess cannot be used together.")
    ffmpeg_shim_dir = ensure_ffmpeg_on_path(direct_claw_root, direct_claw_python)
    u2net_weight_path = ensure_u2net_weights(direct_claw_root)

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
        "name": "run_direct_claw",
        "script": "scripts/run_direct_claw.py",
        "project_root": str(direct_claw_root),
        "python": str(direct_claw_python),
        "benchmark_root": str(benchmark_root),
        "results_root": rel_to_benchmark(results_root, benchmark_root),
        "raw_output_root": str(direct_claw_root / "output" / "benchmark_adapter"),
        "task_selection": {
            "mode": "all" if args.all else "task_ids",
            "task_ids": [task["id"] for task in selected],
        },
        "options": {
            "overwrite": bool(args.overwrite),
            "dry_run": bool(args.dry_run),
            "force_preprocess": bool(args.force_preprocess),
            "skip_preprocess": bool(args.skip_preprocess),
            "cfg_path": str(cfg_path),
            "ffmpeg_shim_dir": str(ffmpeg_shim_dir) if ffmpeg_shim_dir else None,
            "u2net_weight_path": str(u2net_weight_path),
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
                direct_claw_root=direct_claw_root,
                direct_claw_python=direct_claw_python,
                results_root=results_root,
                run_id=args.run_id,
                method=args.method,
                method_version=args.method_version,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                force_preprocess=args.force_preprocess,
                skip_preprocess=args.skip_preprocess,
                cfg_path=cfg_path,
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
                direct_claw_root=direct_claw_root,
                direct_claw_python=direct_claw_python,
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
