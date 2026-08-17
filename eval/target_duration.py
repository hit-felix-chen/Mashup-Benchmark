from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from eval.media import ffprobe_duration

TARGET_DURATION_MODES = frozenset({"task", "music"})
MUSIC_DURATION_TOLERANCE_SEC = 0.001


def target_duration_mode(run_record: Mapping[str, Any]) -> str:
    """Return the declared duration mode, preserving legacy records as task mode."""
    mode = run_record.get("target_duration_mode", "task")
    if mode not in TARGET_DURATION_MODES:
        raise ValueError("target_duration_mode must be 'task' or 'music'")
    return str(mode)


def _positive_finite_duration(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a positive finite number")
    duration = float(value)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"{field} must be a positive finite number")
    return duration


def effective_target_output_length_sec(
    task: Mapping[str, Any],
    run_record: Mapping[str, Any],
) -> float:
    """Resolve the effective target consumed by evaluators and VLM prompts.

    A task-mode record must retain the canonical task target. A music-mode
    record carries its effective target in ``target_output_length_sec``; the
    media-backed consistency check is performed by
    :func:`validate_target_output_length`.
    """
    mode = target_duration_mode(run_record)
    effective = _positive_finite_duration(
        run_record.get("target_output_length_sec"),
        field="target_output_length_sec",
    )
    if mode == "task":
        canonical = _positive_finite_duration(
            task["task"]["target_output_length_sec"],
            field="task.target_output_length_sec",
        )
        if effective != canonical:
            raise ValueError(
                "task-mode target_output_length_sec does not match the benchmark task "
                f"({effective:g} vs {canonical:g})"
            )
    return effective


def _canonical_audio_path(task: Mapping[str, Any], benchmark_root: Path) -> Path:
    raw_path = task["audio"].get("local_path")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("benchmark task has no valid audio.local_path")
    relative_path = Path(raw_path)
    if relative_path.is_absolute():
        raise ValueError("benchmark task audio.local_path must be relative")

    canonical_root = benchmark_root.resolve()
    audio_path = (canonical_root / relative_path).resolve()
    try:
        audio_path.relative_to(canonical_root)
    except ValueError as exc:
        raise ValueError("benchmark task audio.local_path escapes the benchmark root") from exc
    if not audio_path.is_file():
        raise ValueError(f"benchmark task audio file is missing: {raw_path}")
    return audio_path


def validate_target_output_length(
    task: Mapping[str, Any],
    run_record: Mapping[str, Any],
    *,
    benchmark_root: Path,
    probe_duration: Callable[[Path], float | None] = ffprobe_duration,
    music_tolerance_sec: float = MUSIC_DURATION_TOLERANCE_SEC,
) -> float:
    """Validate and return a run record's effective target duration.

    Music mode is checked against the canonical audio file bound to the
    benchmark task, not against a path or duration supplied by the run.
    """
    effective = effective_target_output_length_sec(task, run_record)
    if target_duration_mode(run_record) == "task":
        return effective

    audio_path = _canonical_audio_path(task, benchmark_root)
    try:
        music_duration = _positive_finite_duration(
            probe_duration(audio_path),
            field="canonical music duration",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"could not determine canonical music duration: {exc}") from exc
    if abs(effective - music_duration) > music_tolerance_sec:
        raise ValueError(
            "music-mode target_output_length_sec does not match the canonical BGM "
            f"({effective:.6f} vs {music_duration:.6f}, tolerance {music_tolerance_sec:.3f}s)"
        )
    return effective
