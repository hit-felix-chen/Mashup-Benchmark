from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.validate_run as validator


def _task_033() -> dict:
    return validator.load_tasks()["task_033"]


def _write_failed_run(
    run_dir: Path,
    *,
    target: float,
    record_mode: str | None,
    manifest_mode: str | None,
) -> None:
    task = _task_033()
    record = {
        "run_id": run_dir.name,
        "method": "CutMaster",
        "task_id": task["id"],
        "video_id": task["video"]["id"],
        "audio_id": task["audio"]["id"],
        "prompt_type": task["task"]["type"],
        "status": "failed",
        "output_video": f"runs/{run_dir.name}/task_outputs/{task['id']}/output.mp4",
        "target_output_length_sec": target,
        "target_shot_length_sec": task["task"]["target_shot_length_sec"],
        "actual_output_length_sec": 0.0,
        "wall_clock_sec": 1.0,
        "created_at": "2026-08-13T00:00:00+08:00",
        "error": {"type": "TestFailure", "message": "intentional fixture"},
    }
    if record_mode is not None:
        record["target_duration_mode"] = record_mode

    manifest = {
        "run_id": run_dir.name,
        "method": "CutMaster",
        "benchmark": "Mashup-Benchmark",
        "task_file": "data/tasks/mashup_benchmark.jsonl",
        "created_at": "2026-08-13T00:00:00+08:00",
        "status": "failed",
        "num_tasks": 1,
        "num_success": 0,
        "num_failed": 1,
        "run_outputs": f"runs/{run_dir.name}/run_outputs.jsonl",
        "adapter": {"options": {}},
    }
    if manifest_mode is not None:
        manifest["adapter"]["options"]["target_duration_mode"] = manifest_mode

    task_dir = run_dir / "task_outputs" / task["id"]
    task_dir.mkdir(parents=True)
    (task_dir / "run_output.json").write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run_outputs.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_validate_run_accepts_legacy_task_mode(tmp_path: Path) -> None:
    run_dir = tmp_path / "legacy_task_run"
    _write_failed_run(run_dir, target=60.0, record_mode=None, manifest_mode=None)

    assert validator.main(["validate_run.py", str(run_dir)]) == 0


def test_validate_run_accepts_music_mode_and_rounded_ffprobe_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "music_run"
    _write_failed_run(run_dir, target=111.706, record_mode="music", manifest_mode="music")
    monkeypatch.setattr(validator, "ffprobe_duration", lambda _path: 111.705896)

    assert validator.main(["validate_run.py", str(run_dir)]) == 0


def test_validate_run_rejects_invalid_or_manifest_mismatched_music_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_duration = tmp_path / "invalid_duration"
    _write_failed_run(invalid_duration, target=60.0, record_mode="music", manifest_mode="music")
    monkeypatch.setattr(validator, "ffprobe_duration", lambda _path: 111.705896)
    assert validator.main(["validate_run.py", str(invalid_duration)]) == 1

    mismatched_manifest = tmp_path / "mismatched_manifest"
    _write_failed_run(mismatched_manifest, target=111.706, record_mode="music", manifest_mode="task")
    assert validator.main(["validate_run.py", str(mismatched_manifest)]) == 1
