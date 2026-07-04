#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


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

ROOT = Path(__file__).resolve().parents[1]
TASK_FILE = ROOT / "data" / "tasks" / "mashup_benchmark.jsonl"
REQUIRED_MANIFEST = {
    "run_id", "method", "benchmark", "task_file", "created_at",
    "status", "num_tasks", "run_outputs",
}
REQUIRED_RUN = {
    "run_id", "method", "task_id", "video_id", "audio_id", "prompt_type",
    "status", "output_video", "target_output_length_sec", "target_shot_length_sec",
    "actual_output_length_sec", "wall_clock_sec", "created_at",
}
STATUSES = {"success", "failed", "skipped"}
PROMPT_TYPES = {"event", "character", "emotion", "narrative"}


def load_tasks():
    rows = []
    with TASK_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return {row["id"]: row for row in rows}


def ffprobe_duration(path: Path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    try:
        return float(subprocess.check_output(cmd, text=True).strip())
    except Exception:
        return None


def read_json(path: Path, errors):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing file: {path}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid json: {path}: {exc}")
    return None


def main(argv):
    if len(argv) != 2:
        print("Usage: python3 scripts/validate_run.py runs/<run_id>")
        return 2

    run_dir = Path(argv[1])
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    errors = []
    tasks = load_tasks()

    manifest_path = run_dir / "run_manifest.json"
    manifest = read_json(manifest_path, errors)
    if manifest:
        missing = REQUIRED_MANIFEST - set(manifest)
        if missing:
            errors.append(f"run_manifest.json missing keys: {sorted(missing)}")
        if manifest.get("benchmark") != "Mashup-Benchmark":
            errors.append("run_manifest.json benchmark must be Mashup-Benchmark")
        if manifest.get("run_id") and manifest.get("run_id") != run_dir.name:
            errors.append(f"run_id {manifest.get('run_id')} does not match directory {run_dir.name}")

    run_outputs_path = run_dir / "run_outputs.jsonl"
    records = []
    records_with_error = []
    failed_records = []
    if not run_outputs_path.exists():
        errors.append(f"missing file: {run_outputs_path}")
    else:
        with run_outputs_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    errors.append(f"run_outputs.jsonl line {line_no}: invalid json: {exc}")

    seen = set()
    for i, record in enumerate(records, 1):
        missing = REQUIRED_RUN - set(record)
        if missing:
            errors.append(f"record {i}: missing keys {sorted(missing)}")
            continue
        task_id = record["task_id"]
        if task_id in seen:
            errors.append(f"record {i}: duplicate task_id {task_id}")
        seen.add(task_id)
        task = tasks.get(task_id)
        if not task:
            errors.append(f"record {i}: unknown task_id {task_id}")
            continue
        if record["run_id"] != run_dir.name:
            errors.append(f"record {i}: run_id {record['run_id']} does not match directory {run_dir.name}")
        if record["status"] not in STATUSES:
            errors.append(f"record {i}: invalid status {record['status']}")
        error_obj = record.get("error")
        if error_obj:
            records_with_error.append((i, task_id, record["status"], error_obj))
        if record["status"] == "failed":
            failed_records.append((i, task_id, error_obj))
            if not error_obj:
                errors.append(f"record {i}: failed task {task_id} must include a non-null error field")
        elif error_obj:
            errors.append(f"record {i}: non-failed task {task_id} has non-null error field")
        if record["prompt_type"] not in PROMPT_TYPES:
            errors.append(f"record {i}: invalid prompt_type {record['prompt_type']}")
        if record["video_id"] != task["video"]["id"]:
            errors.append(f"record {i}: video_id does not match task {task_id}")
        if record["audio_id"] != task["audio"]["id"]:
            errors.append(f"record {i}: audio_id does not match task {task_id}")
        if record["prompt_type"] != task["task"]["type"]:
            errors.append(f"record {i}: prompt_type does not match task {task_id}")
        if record["target_output_length_sec"] != task["task"]["target_output_length_sec"]:
            errors.append(f"record {i}: target_output_length_sec does not match task {task_id}")
        if record["target_shot_length_sec"] != task["task"]["target_shot_length_sec"]:
            errors.append(f"record {i}: target_shot_length_sec does not match task {task_id}")

        per_task_json = run_dir / "task_outputs" / task_id / "run_output.json"
        per_task_record = read_json(per_task_json, errors)
        if per_task_record and per_task_record != record:
            errors.append(f"record {i}: task_outputs/{task_id}/run_output.json differs from run_outputs.jsonl")

        if record["status"] == "success":
            video_path = ROOT / record["output_video"]
            if not video_path.exists():
                errors.append(f"record {i}: missing output video {video_path}")
            else:
                duration = ffprobe_duration(video_path)
                if duration is None:
                    errors.append(f"record {i}: ffprobe could not read output video {video_path}")
                elif abs(duration - float(record["actual_output_length_sec"])) > 1.0:
                    errors.append(
                        f"record {i}: actual_output_length_sec differs from ffprobe "
                        f"({record['actual_output_length_sec']} vs {duration:.2f})"
                    )

    if manifest and records:
        expected_task_ids = (
            manifest.get("adapter", {})
            .get("task_selection", {})
            .get("task_ids")
        )
        if expected_task_ids:
            missing_expected = sorted(set(expected_task_ids) - seen)
            if missing_expected:
                errors.append(f"manifest task_selection has missing task records: {missing_expected}")
        if manifest.get("num_tasks") != len(records):
            errors.append(f"manifest num_tasks {manifest.get('num_tasks')} != records {len(records)}")
        if manifest.get("num_success") is not None:
            success_count = sum(1 for r in records if r.get("status") == "success")
            if manifest.get("num_success") != success_count:
                errors.append(f"manifest num_success {manifest.get('num_success')} != {success_count}")
        if manifest.get("num_failed") is not None:
            failed_count = sum(1 for r in records if r.get("status") == "failed")
            if manifest.get("num_failed") != failed_count:
                errors.append(f"manifest num_failed {manifest.get('num_failed')} != {failed_count}")

    print(f"run_dir: {run_dir}")
    print(f"records: {len(records)}")
    print(f"known benchmark tasks: {len(tasks)}")
    if records_with_error:
        print("\nTASKS WITH ERROR:")
        for _, task_id, status, error_obj in records_with_error:
            error_type = error_obj.get("type", "UnknownError") if isinstance(error_obj, dict) else type(error_obj).__name__
            message = error_obj.get("message", str(error_obj)) if isinstance(error_obj, dict) else str(error_obj)
            print(f"- {task_id} [{status}] {error_type}: {message}")
    elif failed_records:
        print("\nFAILED TASKS:")
        for _, task_id, _ in failed_records:
            print(f"- {task_id} [failed]")
    if errors:
        print("\nERRORS:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("\nOK: run output structure validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
