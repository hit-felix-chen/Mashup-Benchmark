from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from eval.media import audio_rms_series, detect_audio_beats, detect_visual_cuts, pearson, video_motion_series


def beat_cut_synchronization(
    output_video: Path,
    *,
    adaptive_threshold: float = 2.0,
    adaptive_min_content_val: float = 15.0,
    adaptive_min_scene_len: int = 5,
    beat_window_sec: float = 0.05,
    tau_sec: float = 0.196,
) -> dict[str, Any]:
    cuts = detect_visual_cuts(
        output_video,
        adaptive_threshold=adaptive_threshold,
        adaptive_min_content_val=adaptive_min_content_val,
        adaptive_min_scene_len=adaptive_min_scene_len,
    )
    beats = detect_audio_beats(output_video, window_sec=beat_window_sec)
    if not cuts or not beats:
        return {
            "score": 0.0,
            "cut_detection": "pyscenedetect_adaptive_full_frame",
            "adaptive_threshold": adaptive_threshold,
            "adaptive_min_content_val": adaptive_min_content_val,
            "adaptive_min_scene_len": adaptive_min_scene_len,
            "num_cuts": len(cuts),
            "num_beats": len(beats),
            "mean_nearest_beat_distance_sec": None,
            "details": "No cuts or beats detected.",
        }
    distances = [min(abs(cut - beat) for beat in beats) for cut in cuts]
    raw = sum(math.exp(-d / tau_sec) for d in distances) / len(distances)
    return {
        "score": max(0.0, min(100.0, raw * 100.0)),
        "cut_detection": "pyscenedetect_adaptive_full_frame",
        "adaptive_threshold": adaptive_threshold,
        "adaptive_min_content_val": adaptive_min_content_val,
        "adaptive_min_scene_len": adaptive_min_scene_len,
        "num_cuts": len(cuts),
        "num_beats": len(beats),
        "mean_nearest_beat_distance_sec": sum(distances) / len(distances),
    }


def audio_visual_energy_correspondence(output_video: Path, *, video_fps: float = 2.0, audio_window_sec: float = 0.5) -> dict[str, Any]:
    visual = video_motion_series(output_video, fps=video_fps)
    audio = audio_rms_series(output_video, window_sec=audio_window_sec)
    corr = pearson(visual, audio)
    if corr is None:
        return {
            "score": 0.0,
            "correlation": None,
            "num_visual_windows": len(visual),
            "num_audio_windows": len(audio),
            "details": "Insufficient variance or samples for correlation.",
        }
    # Negative correlation means energy actively conflicts; map [-1, 1] to [0, 100].
    score = (corr + 1.0) * 50.0
    return {
        "score": max(0.0, min(100.0, score)),
        "correlation": corr,
        "num_visual_windows": len(visual),
        "num_audio_windows": len(audio),
    }
