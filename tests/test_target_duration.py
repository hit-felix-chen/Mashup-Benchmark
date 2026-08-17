from __future__ import annotations

import copy
from pathlib import Path

import pytest

from eval.evaluators.specified_metrics_judge import TYPE_METRICS, _prompt_for_metrics
from eval.evaluators.vlm_judge import _prompt_for_run
from eval.run_evaluation import load_tasks, validate_run_target_durations
from eval.target_duration import (
    effective_target_output_length_sec,
    target_duration_mode,
    validate_target_output_length,
)

ROOT = Path(__file__).resolve().parents[1]


def _task_033() -> dict:
    return copy.deepcopy(load_tasks()["task_033"])


def _run_record(*, mode: str | None = None, target: float = 60.0) -> dict:
    record = {
        "task_id": "task_033",
        "target_output_length_sec": target,
        "actual_output_length_sec": target,
    }
    if mode is not None:
        record["target_duration_mode"] = mode
    return record


def test_legacy_record_is_strict_task_mode() -> None:
    task = _task_033()
    record = _run_record()

    assert target_duration_mode(record) == "task"
    assert effective_target_output_length_sec(task, record) == 60.0

    record["target_output_length_sec"] = 60.001
    with pytest.raises(ValueError, match="task-mode"):
        effective_target_output_length_sec(task, record)


def test_music_mode_validates_rounded_effective_target_against_canonical_bgm() -> None:
    task = _task_033()
    record = _run_record(mode="music", target=111.706)

    assert validate_target_output_length(task, record, benchmark_root=ROOT) == 111.706


def test_music_mode_rejects_asserted_duration_that_does_not_match_bgm() -> None:
    task = _task_033()
    record = _run_record(mode="music", target=112.0)

    with pytest.raises(ValueError, match="canonical BGM"):
        validate_target_output_length(task, record, benchmark_root=ROOT)


@pytest.mark.parametrize("mode", ["audio", "", None, 1])
def test_invalid_explicit_duration_mode_is_rejected(mode: object) -> None:
    record = _run_record()
    record["target_duration_mode"] = mode

    with pytest.raises(ValueError, match="target_duration_mode"):
        target_duration_mode(record)


def test_music_mode_resolves_only_the_canonical_audio_under_benchmark_root(tmp_path: Path) -> None:
    outside_audio = tmp_path.parent / "outside.mp3"
    outside_audio.write_bytes(b"not audio")
    task = _task_033()
    task["audio"]["local_path"] = "../outside.mp3"

    with pytest.raises(ValueError, match="escapes the benchmark root"):
        validate_target_output_length(
            task,
            _run_record(mode="music", target=1.0),
            benchmark_root=tmp_path,
            probe_duration=lambda _path: 1.0,
        )


def test_evaluation_preflight_rejects_invalid_music_target() -> None:
    tasks = load_tasks()
    with pytest.raises(ValueError, match="Invalid target duration for task_033"):
        validate_run_target_durations(
            [_run_record(mode="music", target=60.0)],
            tasks,
            benchmark_root=ROOT,
        )


def test_vlm_and_specified_prompts_use_run_effective_target() -> None:
    task = _task_033()
    record = _run_record(mode="music", target=111.706)

    vlm_prompt = _prompt_for_run(task, record)
    specified_prompt = _prompt_for_metrics(task, record, TYPE_METRICS["event"])

    assert "Target output length: 111.706s" in vlm_prompt
    assert "Target output length: 111.706s" in specified_prompt
    assert "Target output length: 60s" not in vlm_prompt
    assert "Target output length: 60s" not in specified_prompt
