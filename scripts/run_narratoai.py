#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
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
DEFAULT_NARRATOAI_ROOT = BENCHMARK_ROOT.parent / "NarratoAI"
DEFAULT_RESULTS_ROOT = BENCHMARK_ROOT / "runs"
TASK_FILE_REL = Path("data/tasks/mashup_benchmark.jsonl")


WORKER_SOURCE = r'''
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def parse_timestamp(value: str) -> tuple[float, float]:
    start_raw, end_raw = str(value).split("-", 1)
    return parse_time(start_raw), parse_time(end_raw)


def parse_time(value: str) -> float:
    value = str(value).strip().replace(".", ",")
    main, ms_raw = value.split(",", 1) if "," in value else (value, "0")
    hours, minutes, seconds = [int(part) for part in main.split(":")]
    return hours * 3600 + minutes * 60 + seconds + int(ms_raw[:3].ljust(3, "0")) / 1000.0


def format_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    ms_total = int(round(seconds * 1000))
    hours, rem = divmod(ms_total, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def clamp_timestamp(timestamp: str, max_duration_sec: float, remaining_sec: float | None = None) -> str:
    start_sec, end_sec = parse_timestamp(timestamp)
    duration = max(0.001, end_sec - start_sec)
    cap = max(0.001, min(duration, float(max_duration_sec)))
    if remaining_sec is not None:
        cap = max(0.001, min(cap, float(remaining_sec)))
    return f"{format_time(start_sec)}-{format_time(start_sec + cap)}"


def script_duration(items: list[dict]) -> float:
    total = 0.0
    for item in items:
        try:
            start, end = parse_timestamp(item["timestamp"])
            total += max(0.0, end - start)
        except Exception:
            continue
    return total


def adapt_script(
    raw_script: list[dict],
    *,
    video_path: str,
    target_output_length_sec: float,
    target_shot_length_sec: float,
    max_clip_duration_sec: float,
) -> list[dict]:
    video_name = os.path.basename(video_path)
    adapted: list[dict] = []
    total = 0.0
    clip_cap = float(max_clip_duration_sec or target_shot_length_sec or 4.0)
    target_total = float(target_output_length_sec or 60.0)

    for raw in raw_script:
        if not isinstance(raw, dict):
            continue
        timestamp = str(raw.get("timestamp", "")).strip()
        if not timestamp:
            continue

        remaining = target_total - total
        if remaining <= 0.2:
            break
        try:
            timestamp = clamp_timestamp(timestamp, clip_cap, remaining_sec=remaining)
            start_sec, end_sec = parse_timestamp(timestamp)
            duration = max(0.0, end_sec - start_sec)
        except Exception:
            continue
        if duration <= 0:
            continue

        new_id = len(adapted) + 1
        item = {
            "_id": new_id,
            "video_id": int(raw.get("video_id") or 1),
            "video_name": str(raw.get("video_name") or video_name),
            "timestamp": timestamp,
            "picture": str(raw.get("picture") or raw.get("content") or "Benchmark selected source-video segment"),
            "narration": f"播放原片{new_id}",
            "OST": 1,
        }
        adapted.append(item)
        total += duration

    return adapted


def get_text_llm_config(config, overrides: dict) -> tuple[str, str, str, str]:
    provider = str(overrides.get("text_provider") or config.app.get("text_llm_provider", "openai")).strip() or "openai"
    model = str(overrides.get("text_model") or config.app.get(f"text_{provider}_model_name", "")).strip()
    api_key = str(overrides.get("text_api_key") or config.app.get(f"text_{provider}_api_key", "")).strip()
    base_url = str(overrides.get("text_base_url") or config.app.get(f"text_{provider}_base_url", "")).strip()
    if not model:
        raise ValueError(f"Missing text model config: text_{provider}_model_name")
    if not api_key:
        raise ValueError(f"Missing text API key config: text_{provider}_api_key")
    return provider, model, api_key, base_url


def prepare_asr_audio(payload: dict) -> str:
    asr_audio_path = Path(payload.get("asr_audio_path") or "").resolve()
    if asr_audio_path.exists() and asr_audio_path.stat().st_size > 0:
        return str(asr_audio_path)
    asr_audio_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = asr_audio_path.with_name(f"{asr_audio_path.stem}.tmp{asr_audio_path.suffix}")
    if tmp_path.exists():
        tmp_path.unlink()
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        payload["video_path"],
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "64k",
        str(tmp_path),
    ]
    subprocess.run(cmd, check=True)
    tmp_path.replace(asr_audio_path)
    return str(asr_audio_path)


def transcribe_video(payload: dict, config, srt_path: Path) -> str:
    from app.services import fun_asr_subtitle

    backend = str(payload.get("asr_backend") or config.fun_asr.get("backend", "bailian")).strip().lower()
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    if backend == "bailian":
        asr_input = prepare_asr_audio(payload)
        api_key = str(payload.get("asr_api_key") or config.fun_asr.get("api_key", "")).strip()
        return fun_asr_subtitle.create_with_fun_asr(
            local_file=asr_input,
            subtitle_file=str(srt_path),
            api_key=api_key,
            timeout=float(payload.get("asr_timeout_sec") or 1800.0),
        )
    if backend == "local":
        api_url = str(payload.get("asr_api_url") or config.fun_asr.get("api_url", "")).strip()
        return fun_asr_subtitle.create_with_local_fun_asr(
            local_file=payload["video_path"],
            subtitle_file=str(srt_path),
            api_url=api_url,
            hotword=str(config.fun_asr.get("hotword", "")),
            enable_spk=bool(config.fun_asr.get("enable_spk", False)),
        )
    if backend == "firered":
        api_url = str(payload.get("asr_firered_api_url") or config.fun_asr.get("firered_api_url", "")).strip()
        return fun_asr_subtitle.create_with_local_firered_asr(
            local_file=payload["video_path"],
            subtitle_file=str(srt_path),
            api_url=api_url,
        )
    raise ValueError(f"Unsupported ASR backend: {backend}")


def mirror_srt_to_artifacts(shared_srt: Path, artifact_srt: Path) -> None:
    if shared_srt.resolve() == artifact_srt.resolve():
        return
    artifact_srt.parent.mkdir(parents=True, exist_ok=True)
    if artifact_srt.exists():
        artifact_srt.unlink()
    shutil.copy2(shared_srt, artifact_srt)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    args = parser.parse_args()

    payload_path = Path(args.payload)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    narratoai_root = Path(payload["narratoai_root"]).resolve()
    sys.path.insert(0, str(narratoai_root))
    os.chdir(narratoai_root)

    from app.config import config
    from app.models.schema import VideoClipParams
    from app.services.llm.providers import register_all_providers
    from app.services.SDP.generate_script_short import generate_script_result
    from app.services.task import start_subclip_unified

    register_all_providers()

    artifacts_dir = Path(payload["artifacts_dir"]).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_source_srt = artifacts_dir / "source.srt"
    source_srt = Path(payload.get("source_srt_path") or artifact_source_srt).resolve()
    raw_script_path = artifacts_dir / "narrato_script_raw.json"
    adapted_script_path = artifacts_dir / "narrato_script_adapted.json"
    result_path = artifacts_dir / "narrato_worker_result.json"

    t0 = time.time()
    if (
        payload.get("reuse_asr", True)
        and not source_srt.exists()
        and artifact_source_srt.exists()
        and artifact_source_srt.stat().st_size > 0
    ):
        source_srt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact_source_srt, source_srt)
    if payload.get("reuse_asr", True) and source_srt.exists() and source_srt.stat().st_size > 0:
        generated_srt = str(source_srt)
    else:
        generated_srt = transcribe_video(payload, config, source_srt)
    mirror_srt_to_artifacts(Path(generated_srt), artifact_source_srt)

    provider, model, api_key, base_url = get_text_llm_config(config, payload)
    target_output = float(payload["target_output_length_sec"])
    target_shot = float(payload["target_shot_length_sec"])
    custom_clips = int(payload.get("custom_clips") or max(1, math.ceil(target_output / max(target_shot, 1.0))))
    prompt = str(payload["prompt"]).strip()
    plot_analysis = (
        "Mashup-Benchmark adaptation task.\n"
        "Select source-video clips strictly according to the user prompt below. "
        "Prefer moments that can form a concise music-video montage rather than narration.\n"
        f"User prompt: {prompt}\n"
        f"Task type: {payload.get('prompt_type')}\n"
        f"Video category: {payload.get('video_category')}\n"
        f"Target output duration: {target_output:.1f}s. Target shot duration: {target_shot:.1f}s."
    )
    script_result = generate_script_result(
        api_key=api_key,
        model_name=model,
        output_path=str(raw_script_path),
        base_url=base_url or None,
        custom_clips=custom_clips,
        provider=provider,
        video_paths=[payload["video_path"]],
        plot_analysis=plot_analysis,
        short_name=payload.get("video_title") or payload.get("video_id") or "",
        drama_genre=prompt,
        subtitle_file_path=generated_srt,
    )
    if script_result.get("status") != "success":
        raise RuntimeError(script_result.get("message") or "NarratoAI script generation failed")
    raw_script = script_result.get("script") or []
    raw_script_path.write_text(json.dumps(raw_script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    adapted_script = adapt_script(
        raw_script,
        video_path=payload["video_path"],
        target_output_length_sec=target_output,
        target_shot_length_sec=target_shot,
        max_clip_duration_sec=float(payload.get("max_clip_duration_sec") or target_shot),
    )
    if not adapted_script:
        raise RuntimeError("NarratoAI produced no usable script items after adaptation")
    adapted_script_path.write_text(json.dumps(adapted_script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    params = VideoClipParams(
        video_clip_json_path=str(adapted_script_path),
        video_origin_path=payload["video_path"],
        video_origin_paths=[payload["video_path"]],
        original_subtitle_path=generated_srt,
        original_subtitle_paths=[generated_srt],
        video_aspect=payload.get("video_aspect", "16:9"),
        bgm_type="custom",
        bgm_file=payload["audio_path"],
        subtitle_enabled=bool(payload.get("subtitle_enabled", False)),
        subtitle_auto_transcribe_enabled=False,
        n_threads=int(payload.get("n_threads") or 16),
        bgm_volume=float(payload.get("bgm_volume") or 0.3),
        original_volume=float(payload.get("original_volume") or 1.0),
    )
    render_result = start_subclip_unified(task_id=payload["narrato_task_id"], params=params)
    videos = render_result.get("videos") or []
    if not videos:
        raise RuntimeError("NarratoAI render returned no video path")

    result = {
        "status": "success",
        "source_srt": str(source_srt),
        "raw_script": str(raw_script_path),
        "adapted_script": str(adapted_script_path),
        "narrato_output_video": videos[0],
        "narrato_combined_video": (render_result.get("combined_videos") or [""])[0],
        "raw_script_duration_sec": script_duration(raw_script),
        "adapted_script_duration_sec": script_duration(adapted_script),
        "num_raw_clips": len(raw_script),
        "num_adapted_clips": len(adapted_script),
        "wall_clock_sec": time.time() - t0,
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


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


def resolve_narratoai_python(narratoai_root: Path, explicit_python: Path | None = None) -> Path:
    if explicit_python is not None:
        explicit_python = explicit_python.expanduser()
        return explicit_python if explicit_python.is_absolute() else explicit_python.absolute()
    venv_python = narratoai_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable).absolute()


def repo_info(repo_root: Path, repo_name: str = "NarratoAI") -> dict[str, Any]:
    def git(args: list[str]) -> str | None:
        try:
            return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()
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
    run_id: str,
    method: str,
    method_version: str,
    benchmark_root: Path,
    narratoai_root: Path,
    narratoai_python: Path,
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
        "code": repo_info(narratoai_root),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "adapter": adapter,
        "config": {
            "baseline": "NarratoAI",
            "pipeline": "ASR -> short_mix_script -> force_OST_1 -> benchmark_BGM_render",
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
    narratoai_root: Path,
    narratoai_python: Path,
    results_root: Path,
    run_id: str,
    method: str,
    method_version: str,
    overwrite: bool,
    dry_run: bool,
    asr_backend: str,
    custom_clips: int | None,
    max_clip_duration_sec: float | None,
    bgm_volume: float,
    original_volume: float,
    video_aspect: str,
    n_threads: int,
    subtitle_enabled: bool,
    reuse_asr: bool,
) -> dict[str, Any]:
    task_id = task["id"]
    run_dir = results_root / run_id
    task_dir = run_dir / "task_outputs" / task_id
    logs_dir = task_dir / "logs"
    artifacts_dir = task_dir / "artifacts"
    output_video = task_dir / "output.mp4"
    existing_record = load_existing_record(task_dir)

    video_path, audio_path = task_paths(task, benchmark_root)
    prompt = task["task"]["prompt"]
    target_output = float(task["task"]["target_output_length_sec"])
    target_shot = float(task["task"]["target_shot_length_sec"])
    prompt_type = task["task"]["type"]

    started_at = now_iso()
    t0 = time.time()
    status = "skipped" if dry_run else "success"

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    write_json(artifacts_dir / "benchmark_task.json", task)

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
        if not narratoai_root.exists():
            raise FileNotFoundError(f"NarratoAI root not found: {narratoai_root}")

        worker_path = artifacts_dir / "narratoai_worker.py"
        payload_path = artifacts_dir / "narratoai_payload.json"
        shared_asr_dir = run_dir / "shared_cache" / "asr" / task["video"]["id"] / asr_backend
        shared_srt_path = shared_asr_dir / "source.srt"
        shared_asr_audio_path = shared_asr_dir / "source_audio.m4a"
        worker_path.write_text(WORKER_SOURCE, encoding="utf-8")
        payload = {
            "narratoai_root": str(narratoai_root),
            "artifacts_dir": str(artifacts_dir),
            "source_srt_path": str(shared_srt_path),
            "asr_audio_path": str(shared_asr_audio_path),
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "video_id": task["video"]["id"],
            "video_title": task["video"].get("title_zh") or task["video"].get("title_en") or task["video"]["id"],
            "video_category": task["video"].get("category"),
            "prompt": prompt,
            "prompt_type": prompt_type,
            "target_output_length_sec": target_output,
            "target_shot_length_sec": target_shot,
            "custom_clips": custom_clips,
            "max_clip_duration_sec": max_clip_duration_sec or target_shot,
            "narrato_task_id": f"{run_id}_{task_id}",
            "asr_backend": asr_backend,
            "reuse_asr": reuse_asr,
            "video_aspect": video_aspect,
            "n_threads": n_threads,
            "subtitle_enabled": subtitle_enabled,
            "bgm_volume": bgm_volume,
            "original_volume": original_volume,
        }
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        cmd = [str(narratoai_python), str(worker_path), "--payload", str(payload_path)]
        rc = stream_command(cmd, logs_dir / "narratoai_worker.log", cwd=narratoai_root, dry_run=dry_run)
        if rc != 0:
            raise RuntimeError(f"NarratoAI worker failed with exit code {rc}")

        worker_result_path = artifacts_dir / "narrato_worker_result.json"
        if not dry_run and not worker_result_path.exists():
            raise FileNotFoundError(f"NarratoAI worker result not found: {worker_result_path}")
        if not dry_run:
            worker_result = json.loads(worker_result_path.read_text(encoding="utf-8"))
            raw_output = Path(worker_result["narrato_output_video"])
            if not raw_output.exists():
                raise FileNotFoundError(f"NarratoAI output not found: {raw_output}")
            output_video.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(raw_output, output_video)

    actual_duration = ffprobe_duration(output_video) if output_video.exists() else 0.0
    if not output_video.exists() and not dry_run:
        raise FileNotFoundError(f"Rendered output not found: {output_video}")

    ended_at = now_iso()
    wall_clock = time.time() - t0
    artifacts = {
        "benchmark_task": rel_to_benchmark(artifacts_dir / "benchmark_task.json", benchmark_root),
        "source_srt": rel_to_benchmark(artifacts_dir / "source.srt", benchmark_root),
        "narrato_script_raw": rel_to_benchmark(artifacts_dir / "narrato_script_raw.json", benchmark_root),
        "narrato_script_adapted": rel_to_benchmark(artifacts_dir / "narrato_script_adapted.json", benchmark_root),
        "worker_payload": rel_to_benchmark(artifacts_dir / "narratoai_payload.json", benchmark_root),
        "worker_result": rel_to_benchmark(artifacts_dir / "narrato_worker_result.json", benchmark_root),
        "run_log": rel_to_benchmark(logs_dir / "narratoai_worker.log", benchmark_root),
    }
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
        "code_commit": repo_info(narratoai_root).get("commit"),
        "config": {
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "narratoai_root": str(narratoai_root),
            "narratoai_python": str(narratoai_python),
            "script_mode": "short",
            "asr_backend": asr_backend,
            "force_ost": 1,
            "custom_clips": custom_clips,
            "max_clip_duration_sec": max_clip_duration_sec or target_shot,
            "bgm_source": "benchmark_task_audio",
            "bgm_volume": bgm_volume,
            "original_volume": original_volume,
            "video_aspect": video_aspect,
            "subtitle_enabled": subtitle_enabled,
            "n_threads": n_threads,
        },
        "artifacts": artifacts,
        "error": None,
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
    parser = argparse.ArgumentParser(description="Run NarratoAI on Mashup-Benchmark tasks.")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--task-id", nargs="+", help="Task id(s), e.g. task_001.")
    group.add_argument("--all", action="store_true", help="Run all benchmark tasks.")
    parser.add_argument("--list-tasks", action="store_true", help="List available task ids and exit.")
    parser.add_argument("--benchmark-root", type=Path, default=BENCHMARK_ROOT)
    parser.add_argument("--narratoai-root", type=Path, default=DEFAULT_NARRATOAI_ROOT)
    parser.add_argument(
        "--narratoai-python",
        type=Path,
        default=None,
        help="Python executable for NarratoAI. Defaults to <narratoai-root>/.venv/bin/python when present.",
    )
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--run-id", default="narratoai_benchmark")
    parser.add_argument("--method", default="NarratoAI")
    parser.add_argument("--method-version", default="0.8.4-adapted")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate even if task output.mp4 already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands and write metadata without executing heavy steps.")
    parser.add_argument("--asr-backend", choices=["bailian", "local", "firered"], default="bailian")
    parser.add_argument("--no-reuse-asr", action="store_true", help="Regenerate SRT even when artifacts/source.srt exists.")
    parser.add_argument("--custom-clips", type=int, default=None, help="Number of script clips requested from NarratoAI. Defaults to target_output/target_shot.")
    parser.add_argument("--max-clip-duration-sec", type=float, default=None, help="Cap each adapted clip duration. Defaults to task target_shot_length_sec.")
    parser.add_argument("--bgm-volume", type=float, default=0.3)
    parser.add_argument("--original-volume", type=float, default=1.0)
    parser.add_argument("--video-aspect", default="16:9")
    parser.add_argument("--n-threads", type=int, default=16)
    parser.add_argument("--subtitle-enabled", action="store_true", help="Burn subtitles in final output. Default is off for benchmark runs.")
    parser.add_argument("--notes", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    benchmark_root = args.benchmark_root.resolve()
    narratoai_root = args.narratoai_root.resolve()
    narratoai_python = resolve_narratoai_python(narratoai_root, args.narratoai_python)
    results_root = args.results_root.resolve()
    if not narratoai_root.exists():
        raise SystemExit(f"NarratoAI root does not exist: {narratoai_root}")
    if not narratoai_python.exists():
        raise SystemExit(f"NarratoAI Python executable does not exist: {narratoai_python}")
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
        "name": "run_narratoai",
        "script": "scripts/run_narratoai.py",
        "project_root": str(narratoai_root),
        "python": str(narratoai_python),
        "benchmark_root": str(benchmark_root),
        "results_root": rel_to_benchmark(results_root, benchmark_root),
        "raw_output_root": str(narratoai_root / "storage" / "tasks"),
        "task_selection": {
            "mode": "all" if args.all else "task_ids",
            "task_ids": [task["id"] for task in selected],
        },
        "options": {
            "overwrite": bool(args.overwrite),
            "dry_run": bool(args.dry_run),
            "pipeline": "ASR -> short_mix -> force_OST_1 -> benchmark_BGM_render",
            "asr_backend": args.asr_backend,
            "reuse_asr": not args.no_reuse_asr,
            "custom_clips": args.custom_clips,
            "max_clip_duration_sec": args.max_clip_duration_sec,
            "bgm_volume": args.bgm_volume,
            "original_volume": args.original_volume,
            "video_aspect": args.video_aspect,
            "subtitle_enabled": bool(args.subtitle_enabled),
            "n_threads": args.n_threads,
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
                narratoai_root=narratoai_root,
                narratoai_python=narratoai_python,
                results_root=results_root,
                run_id=args.run_id,
                method=args.method,
                method_version=args.method_version,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                asr_backend=args.asr_backend,
                custom_clips=args.custom_clips,
                max_clip_duration_sec=args.max_clip_duration_sec,
                bgm_volume=args.bgm_volume,
                original_volume=args.original_volume,
                video_aspect=args.video_aspect,
                n_threads=args.n_threads,
                subtitle_enabled=args.subtitle_enabled,
                reuse_asr=not args.no_reuse_asr,
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
                narratoai_root=narratoai_root,
                narratoai_python=narratoai_python,
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
