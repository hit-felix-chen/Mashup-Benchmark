#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
DEFAULT_OPENMONTAGE_ROOT = BENCHMARK_ROOT.parent / "OpenMontage"
DEFAULT_RESULTS_ROOT = BENCHMARK_ROOT / "runs"
DEFAULT_CLAUDE_CMD = Path.home() / ".local" / "bin" / "claude"
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


def rel_to_benchmark(path: Path, benchmark_root: Path) -> str:
    return path.resolve().relative_to(benchmark_root.resolve()).as_posix()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def slugify(value: str, *, max_len: int = 80) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_.-")
    return (value or "item")[:max_len]


def task_paths(task: dict[str, Any], benchmark_root: Path) -> tuple[Path, Path]:
    return benchmark_root / task["video"]["local_path"], benchmark_root / task["audio"]["local_path"]


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


def symlink_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        try:
            if dst.is_symlink() and dst.resolve() == src.resolve():
                return
        except Exception:
            pass
        dst.unlink()
    try:
        dst.symlink_to(src.resolve())
    except Exception:
        shutil.copy2(src, dst)


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return True


def stream_command(
    cmd: list[str],
    log_path: Path,
    *,
    cwd: Path,
    dry_run: bool = False,
    timeout_sec: float | None = None,
    stdin_text: str | None = None,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    display = shlex.join(cmd)
    print(f"$ {display}")
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {display}\n\n")
        if stdin_text:
            log.write("[stdin]\n")
            log.write(stdin_text)
            if not stdin_text.endswith("\n"):
                log.write("\n")
            log.write("\n")
        log.flush()
        if dry_run:
            log.write("[dry-run] command not executed\n")
            return 0

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PATH"] = str(Path.home() / ".local" / "bin") + os.pathsep + env.get("PATH", "")
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE if stdin_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if stdin_text is not None:
            assert proc.stdin is not None
            proc.stdin.write(stdin_text)
            if not stdin_text.endswith("\n"):
                proc.stdin.write("\n")
            proc.stdin.close()
        assert proc.stdout is not None
        start = time.time()
        try:
            for line in proc.stdout:
                print(line, end="")
                log.write(line)
                log.flush()
                if timeout_sec is not None and time.time() - start > timeout_sec:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    log.write(f"\n[timeout] command exceeded {timeout_sec:.1f}s\n")
                    return 124
            return proc.wait()
        finally:
            if proc.poll() is None:
                proc.terminate()


def load_existing_records(run_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((run_dir / "task_outputs").glob("task_*/run_output.json")):
        try:
            records.append(read_json(path))
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


def build_agent_prompt(
    *,
    task: dict[str, Any],
    project_dir: Path,
    video_path: Path,
    audio_path: Path,
    final_video_path: Path,
    result_path: Path,
    target_output: float,
    target_shot: float,
    max_cuts: int,
    original_volume: float,
    bgm_volume: float,
) -> str:
    task_json = json.dumps(task, ensure_ascii=False, indent=2)
    return f"""You are running an OpenMontage baseline task for Mashup-Benchmark.

This is a non-interactive benchmark run. Do not ask follow-up questions. All approvals needed for the narrow benchmark plan below are pre-granted.

MANDATORY CONTEXT
- Repository root: {project_dir.parents[1]}
- OpenMontage project directory for this task: {project_dir}
- Benchmark task JSON:
```json
{task_json}
```

SOURCE ASSETS
- Source video: {video_path}
- Benchmark BGM/audio: {audio_path}
- Final video output MUST be written to: {final_video_path}
- Status/result JSON MUST be written to: {result_path}

BENCHMARK CONSTRAINTS
1. Use only the provided source video and provided BGM/audio. Do not download stock media, do not generate images, do not generate video, do not generate TTS, and do not add narration.
2. Produce exactly one landscape/source-aspect short montage MP4.
3. Target duration: {target_output:.1f}s. Stay as close as possible; acceptable tolerance is +/- 5 seconds.
4. Target shot length: {target_shot:.1f}s. Prefer cuts around this length unless the prompt demands a longer continuous moment.
5. Maximum number of cuts: {max_cuts}.
6. Use benchmark BGM as the final audio bed. Original source audio may be retained quietly only if helpful; otherwise benchmark BGM should dominate.
7. Do not burn subtitles by default.
8. Prefer instruction relevance and visual quality over decorative effects.

OPENMONTAGE OPERATING RULES
1. First read AGENT_GUIDE.md and PROJECT_CONTEXT.md.
2. Use the OpenMontage pipeline system. For this benchmark, use the hybrid/source-footage-led interpretation with these pre-approved decisions:
   - pipeline: hybrid
   - render_runtime: ffmpeg
   - composition mode: source-only montage
   - no support assets
   - no human review pauses
3. You may use OpenMontage analysis tools such as scene detection, frame sampling, video analysis, source media review, or transcription if available locally.
4. Final composition should use OpenMontage's `tools.video.video_compose.VideoCompose` with operation `compose`, or an equivalent OpenMontage-approved FFmpeg compose path, using an `edit_decisions` artifact with video cuts.

REQUIRED ARTIFACTS
Create these files inside `{project_dir / "artifacts"}`:
- benchmark_task.json
- brief.json
- edit_decisions.json
- render_report.json
- openmontage_agent_result.json

The `edit_decisions.json` must follow OpenMontage's edit decision schema as closely as possible:
```json
{{
  "version": "1.0",
  "render_runtime": "ffmpeg",
  "cuts": [
    {{
      "id": "cut_001",
      "source": "{video_path}",
      "in_seconds": 0.0,
      "out_seconds": 4.0,
      "reason": "why this clip matches the benchmark prompt"
    }}
  ],
  "audio": {{
    "music": {{
      "asset_id": "{audio_path}",
      "volume": {bgm_volume}
    }}
  }},
  "metadata": {{
    "target_duration_seconds": {target_output:.1f},
    "target_shot_length_seconds": {target_shot:.1f},
    "compose_target": {{"width": 1920, "height": 1080, "fit": "pad"}}
  }}
}}
```

The result JSON at `{result_path}` must be a single JSON object:
```json
{{
  "status": "success",
  "final_video": "{final_video_path}",
  "edit_decisions": "{project_dir / "artifacts" / "edit_decisions.json"}",
  "render_report": "{project_dir / "artifacts" / "render_report.json"}",
  "num_cuts": 0,
  "actual_duration_sec": 0.0,
  "notes": "short summary"
}}
```

If the task fails, still write `{result_path}` with:
```json
{{
  "status": "failed",
  "error": "short error message",
  "notes": "what was attempted"
}}
```

EXECUTION HINT
After selecting cuts, a direct Python snippet like this is acceptable when used as the OpenMontage tool invocation:

```python
import json
from pathlib import Path
from tools.video.video_compose import VideoCompose

project_dir = Path("{project_dir}")
edit_decisions = json.loads((project_dir / "artifacts" / "edit_decisions.json").read_text())
result = VideoCompose().execute({{
    "operation": "compose",
    "edit_decisions": edit_decisions,
    "audio_path": "{audio_path}",
    "output_path": "{final_video_path}",
    "codec": "libx264",
    "crf": 21,
    "preset": "medium",
}})
print(result)
```

Now execute the complete OpenMontage benchmark task and produce the required files.
"""


def prepare_openmontage_project(
    *,
    task: dict[str, Any],
    benchmark_root: Path,
    openmontage_root: Path,
    run_id: str,
    artifacts_dir: Path,
    overwrite_project: bool,
    max_cuts: int,
    original_volume: float,
    bgm_volume: float,
) -> dict[str, Path]:
    task_id = task["id"]
    video_path, audio_path = task_paths(task, benchmark_root)
    target_output = float(task["task"]["target_output_length_sec"])
    target_shot = float(task["task"]["target_shot_length_sec"])

    project_name = slugify(f"mashup_{run_id}_{task_id}")
    project_dir = openmontage_root / "projects" / project_name
    if overwrite_project and project_dir.exists():
        shutil.rmtree(project_dir)
    (project_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (project_dir / "assets").mkdir(parents=True, exist_ok=True)
    (project_dir / "renders").mkdir(parents=True, exist_ok=True)

    local_video = project_dir / "assets" / f"source_video{video_path.suffix.lower()}"
    local_audio = project_dir / "assets" / f"benchmark_audio{audio_path.suffix.lower()}"
    symlink_or_copy(video_path, local_video)
    symlink_or_copy(audio_path, local_audio)

    final_video = project_dir / "renders" / "final.mp4"
    result_path = project_dir / "artifacts" / "openmontage_agent_result.json"
    benchmark_task_path = project_dir / "artifacts" / "benchmark_task.json"
    prompt_path = artifacts_dir / "openmontage_agent_prompt.md"
    write_json(benchmark_task_path, task)
    prompt = build_agent_prompt(
        task=task,
        project_dir=project_dir,
        video_path=local_video,
        audio_path=local_audio,
        final_video_path=final_video,
        result_path=result_path,
        target_output=target_output,
        target_shot=target_shot,
        max_cuts=max_cuts,
        original_volume=original_volume,
        bgm_volume=bgm_volume,
    )
    prompt_path.write_text(prompt, encoding="utf-8")

    return {
        "project_dir": project_dir,
        "local_video": local_video,
        "local_audio": local_audio,
        "final_video": final_video,
        "result_path": result_path,
        "prompt_path": prompt_path,
        "benchmark_task_path": benchmark_task_path,
    }


def copy_openmontage_artifacts(paths: dict[str, Path], artifacts_dir: Path) -> dict[str, Path]:
    copied: dict[str, Path] = {}
    project_artifacts = paths["project_dir"] / "artifacts"
    mapping = {
        "openmontage_benchmark_task": project_artifacts / "benchmark_task.json",
        "openmontage_brief": project_artifacts / "brief.json",
        "openmontage_edit_decisions": project_artifacts / "edit_decisions.json",
        "openmontage_render_report": project_artifacts / "render_report.json",
        "openmontage_agent_result": project_artifacts / "openmontage_agent_result.json",
    }
    for key, src in mapping.items():
        dst = artifacts_dir / src.name
        if copy_if_exists(src, dst):
            copied[key] = dst
    return copied


def build_claude_command(
    *,
    agent_cmd: Path,
    openmontage_root: Path,
    benchmark_root: Path,
    output_format: str,
    permission_mode: str,
    agent_model: str | None,
    max_budget_usd: float | None,
    bypass_permissions: bool,
) -> list[str]:
    cmd = [
        str(agent_cmd),
        "-p",
        "--output-format", output_format,
        "--permission-mode", permission_mode,
        "--add-dir", str(openmontage_root),
        "--add-dir", str(benchmark_root),
    ]
    if output_format == "stream-json":
        cmd.append("--verbose")
    if agent_model:
        cmd.extend(["--model", agent_model])
    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])
    if bypass_permissions:
        cmd.append("--dangerously-skip-permissions")
    return cmd


def run_one_task(
    *,
    task: dict[str, Any],
    benchmark_root: Path,
    openmontage_root: Path,
    agent_cmd: Path,
    results_root: Path,
    run_id: str,
    method: str,
    method_version: str,
    overwrite: bool,
    overwrite_project: bool,
    dry_run: bool,
    output_format: str,
    permission_mode: str,
    agent_model: str | None,
    max_budget_usd: float | None,
    bypass_permissions: bool,
    timeout_sec: float | None,
    max_cuts: int,
    original_volume: float,
    bgm_volume: float,
) -> dict[str, Any]:
    task_id = task["id"]
    run_dir = results_root / run_id
    task_dir = run_dir / "task_outputs" / task_id
    logs_dir = task_dir / "logs"
    artifacts_dir = task_dir / "artifacts"
    output_video = task_dir / "output.mp4"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    video_path, audio_path = task_paths(task, benchmark_root)
    if not video_path.exists():
        raise FileNotFoundError(f"Benchmark video not found: {video_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Benchmark audio not found: {audio_path}")

    target_output = float(task["task"]["target_output_length_sec"])
    target_shot = float(task["task"]["target_shot_length_sec"])
    prompt_type = task["task"]["type"]
    started_at = now_iso()
    t0 = time.time()

    write_json(artifacts_dir / "benchmark_task.json", task)
    paths = prepare_openmontage_project(
        task=task,
        benchmark_root=benchmark_root,
        openmontage_root=openmontage_root,
        run_id=run_id,
        artifacts_dir=artifacts_dir,
        overwrite_project=overwrite_project,
        max_cuts=max_cuts,
        original_volume=original_volume,
        bgm_volume=bgm_volume,
    )

    if output_video.exists() and not overwrite:
        print(f"[{task_id}] output exists, reusing: {output_video}")
    else:
        cmd = build_claude_command(
            agent_cmd=agent_cmd,
            openmontage_root=openmontage_root,
            benchmark_root=benchmark_root,
            output_format=output_format,
            permission_mode=permission_mode,
            agent_model=agent_model,
            max_budget_usd=max_budget_usd,
            bypass_permissions=bypass_permissions,
        )
        stdin_text = f"Read and execute this benchmark instruction file exactly: {paths['prompt_path']}"
        rc = stream_command(
            cmd,
            logs_dir / "openmontage_agent.log",
            cwd=openmontage_root,
            dry_run=dry_run,
            timeout_sec=timeout_sec,
            stdin_text=stdin_text,
        )
        if rc != 0:
            raise RuntimeError(f"OpenMontage agent failed with exit code {rc}")
        if not dry_run and not paths["final_video"].exists():
            raise FileNotFoundError(f"OpenMontage final video not found: {paths['final_video']}")
        if not dry_run:
            output_video.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(paths["final_video"], output_video)

    copied = copy_openmontage_artifacts(paths, artifacts_dir)
    actual_duration = ffprobe_duration(output_video) if output_video.exists() else 0.0
    ended_at = now_iso()
    status = "skipped" if dry_run else "success"

    agent_result: dict[str, Any] = {}
    result_copy = copied.get("openmontage_agent_result")
    if result_copy and result_copy.exists():
        try:
            agent_result = read_json(result_copy)
        except Exception:
            agent_result = {}

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
        "wall_clock_sec": time.time() - t0,
        "api_cost_usd": 0.0,
        "created_at": ended_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "code_commit": repo_info(openmontage_root, "OpenMontage").get("commit"),
        "config": {
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "openmontage_root": str(openmontage_root),
            "openmontage_project_dir": str(paths["project_dir"]),
            "agent_cmd": str(agent_cmd),
            "agent_model": agent_model or "configured_default",
            "agent_output_format": output_format,
            "permission_mode": permission_mode,
            "bypass_permissions": bypass_permissions,
            "pipeline": "hybrid/source-footage-led",
            "render_runtime": "ffmpeg",
            "source_policy": "benchmark_source_video_and_bgm_only",
            "max_cuts": max_cuts,
            "bgm_volume": bgm_volume,
            "original_volume": original_volume,
            "agent_result": agent_result,
        },
        "artifacts": {
            "benchmark_task": rel_to_benchmark(artifacts_dir / "benchmark_task.json", benchmark_root),
            "agent_prompt": rel_to_benchmark(paths["prompt_path"], benchmark_root),
            "run_log": rel_to_benchmark(logs_dir / "openmontage_agent.log", benchmark_root),
            "backend_log": rel_to_benchmark(logs_dir / "openmontage_agent.log", benchmark_root),
        },
        "error": None,
    }
    for key, path in copied.items():
        record["artifacts"][key] = rel_to_benchmark(path, benchmark_root)
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


def write_run_index(
    *,
    run_dir: Path,
    run_id: str,
    method: str,
    method_version: str,
    benchmark_root: Path,
    openmontage_root: Path,
    agent_cmd: Path,
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
        "code": repo_info(openmontage_root, "OpenMontage"),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "agent_cmd": str(agent_cmd),
            "gpu": gpu_name(),
        },
        "adapter": adapter,
        "config": {
            "baseline": "OpenMontage",
            "pipeline": "Claude Code/Qwen agent harness -> OpenMontage hybrid/source-footage-led -> FFmpeg compose",
        },
        "aggregate": {
            "total_wall_clock_sec": sum(float(r.get("wall_clock_sec") or 0.0) for r in records),
            "total_api_cost_usd": sum(float(r.get("api_cost_usd") or 0.0) for r in records),
        },
    }
    if notes:
        manifest["notes"] = notes
    write_json(run_dir / "run_manifest.json", manifest)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenMontage with Claude Code on Mashup-Benchmark tasks.")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--task-id", nargs="+", help="Task id(s), e.g. task_001.")
    group.add_argument("--all", action="store_true", help="Run all benchmark tasks.")
    parser.add_argument("--list-tasks", action="store_true", help="List available task ids and exit.")
    parser.add_argument("--benchmark-root", type=Path, default=BENCHMARK_ROOT)
    parser.add_argument("--openmontage-root", type=Path, default=DEFAULT_OPENMONTAGE_ROOT)
    parser.add_argument("--agent-cmd", type=Path, default=DEFAULT_CLAUDE_CMD)
    parser.add_argument("--agent-model", default=None, help="Optional Claude Code model argument. Omit to use configured default.")
    parser.add_argument("--agent-output-format", choices=["text", "json", "stream-json"], default="stream-json")
    parser.add_argument("--permission-mode", choices=["acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"], default="acceptEdits")
    parser.add_argument("--bypass-permissions", action="store_true", help="Pass --dangerously-skip-permissions to Claude Code.")
    parser.add_argument("--max-budget-usd", type=float, default=None)
    parser.add_argument("--timeout-sec", type=float, default=None)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--run-id", default="openmontage_benchmark")
    parser.add_argument("--method", default="OpenMontage")
    parser.add_argument("--method-version", default="agent-harness-ffmpeg")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate even if task output.mp4 already exists.")
    parser.add_argument("--overwrite-project", action="store_true", help="Delete and recreate the OpenMontage project directory for each selected task.")
    parser.add_argument("--dry-run", action="store_true", help="Write task prompt/project metadata without executing Claude Code.")
    parser.add_argument("--max-cuts", type=int, default=24)
    parser.add_argument("--bgm-volume", type=float, default=0.75)
    parser.add_argument("--original-volume", type=float, default=0.15)
    parser.add_argument("--notes", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    benchmark_root = args.benchmark_root.resolve()
    openmontage_root = args.openmontage_root.resolve()
    agent_cmd = args.agent_cmd.expanduser()
    if not agent_cmd.is_absolute():
        resolved = shutil.which(str(agent_cmd))
        agent_cmd = Path(resolved).resolve() if resolved else agent_cmd.resolve()
    results_root = args.results_root.resolve()

    if not openmontage_root.exists():
        raise SystemExit(f"OpenMontage root does not exist: {openmontage_root}")
    if not agent_cmd.exists():
        raise SystemExit(f"Claude Code executable does not exist: {agent_cmd}")
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
        "name": "run_openmontage",
        "script": "scripts/run_openmontage.py",
        "project_root": str(openmontage_root),
        "benchmark_root": str(benchmark_root),
        "results_root": rel_to_benchmark(results_root, benchmark_root),
        "raw_output_root": str(openmontage_root / "projects"),
        "task_selection": {
            "mode": "all" if args.all else "task_ids",
            "task_ids": [task["id"] for task in selected],
        },
        "options": {
            "overwrite": bool(args.overwrite),
            "overwrite_project": bool(args.overwrite_project),
            "dry_run": bool(args.dry_run),
            "agent_cmd": str(agent_cmd),
            "agent_model": args.agent_model or "configured_default",
            "agent_output_format": args.agent_output_format,
            "permission_mode": args.permission_mode,
            "bypass_permissions": bool(args.bypass_permissions),
            "max_budget_usd": args.max_budget_usd,
            "timeout_sec": args.timeout_sec,
            "pipeline": "hybrid/source-footage-led",
            "render_runtime": "ffmpeg",
            "max_cuts": args.max_cuts,
            "bgm_volume": args.bgm_volume,
            "original_volume": args.original_volume,
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
                openmontage_root=openmontage_root,
                agent_cmd=agent_cmd,
                results_root=results_root,
                run_id=args.run_id,
                method=args.method,
                method_version=args.method_version,
                overwrite=args.overwrite,
                overwrite_project=args.overwrite_project,
                dry_run=args.dry_run,
                output_format=args.agent_output_format,
                permission_mode=args.permission_mode,
                agent_model=args.agent_model,
                max_budget_usd=args.max_budget_usd,
                bypass_permissions=args.bypass_permissions,
                timeout_sec=args.timeout_sec,
                max_cuts=args.max_cuts,
                original_volume=args.original_volume,
                bgm_volume=args.bgm_volume,
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
                openmontage_root=openmontage_root,
                agent_cmd=agent_cmd,
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
