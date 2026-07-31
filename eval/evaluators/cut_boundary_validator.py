from __future__ import annotations

import base64
import time
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    as_completed,
)
from pathlib import Path
from typing import Any

import cv2

from eval.evaluators.vlm_judge import VLMJudge

SYSTEM_PROMPT = """You are a strict video shot-boundary classifier.
You receive exactly two adjacent frames from a rendered video:
Image 1 is immediately before a proposed cut.
Image 2 is the first frame at or immediately after the proposed cut.
Decide whether a real editorial shot boundary occurs between them.
Return strict JSON only."""

USER_PROMPT_TEMPLATE = """Candidate cut time: {time_sec:.6f} seconds.

Return is_cut=true only when the two images show a discontinuous editorial
transition to a different shot, camera viewpoint, framing, scale, scene, or
moment in time.

Return is_cut=false when they belong to the same continuous shot. Player or
subject movement, camera tracking, panning, zooming, motion blur, lighting or
exposure changes, compression artifacts, and scoreboard or overlay updates do
not constitute a cut by themselves.

Return exactly:
{{
  "is_cut": true,
  "reason": "concise visual evidence"
}}"""


def _frame_data_url(frame: Any, *, width: int) -> str:
    if width <= 0:
        raise ValueError("BCS VLM frame width must be positive")
    height = max(2, round(frame.shape[0] * width / frame.shape[1]))
    if height % 2:
        height += 1
    resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(
        ".jpg",
        resized,
        [cv2.IMWRITE_JPEG_QUALITY, 90],
    )
    if not ok:
        raise RuntimeError("Could not encode a BCS cut-validation frame")
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def _extract_adjacent_frame_pairs(
    video_path: Path,
    candidate_cuts: list[float],
    *,
    frame_width: int,
) -> tuple[float, list[tuple[int, int, str, str]]]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video for cut validation: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if fps <= 0:
        capture.release()
        raise RuntimeError(f"Video has invalid frame rate: {video_path}")

    pairs: list[tuple[int, int, str, str]] = []
    try:
        for cut in candidate_cuts:
            after_index = max(1, round(cut * fps))
            before_index = after_index - 1
            frames = []
            for frame_index in (before_index, after_index):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError(f"Could not read frame {frame_index} around cut {cut:.6f}s from {video_path}")
                frames.append(_frame_data_url(frame, width=frame_width))
            pairs.append(
                (
                    before_index,
                    after_index,
                    frames[0],
                    frames[1],
                )
            )
    finally:
        capture.release()
    return fps, pairs


def _validate_binary_response(payload: dict[str, Any]) -> tuple[bool, str]:
    is_cut = payload.get("is_cut")
    if not isinstance(is_cut, bool):
        raise ValueError("is_cut must be a JSON boolean")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-empty string")
    return is_cut, reason.strip()


def _merge_usage(total: dict[str, float], usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    for key, value in usage.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        total[key] = total.get(key, 0.0) + float(value)


class CutBoundaryValidator:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        max_concurrency: int,
        frame_width: int,
        enable_thinking: bool,
    ):
        self.judge = VLMJudge(config)
        self.frame_width = frame_width
        self.enable_thinking = enable_thinking
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_concurrency),
            thread_name_prefix="bcs-cut-vlm",
        )

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def _classify(
        self,
        time_sec: float,
        before_data_url: str,
        after_data_url: str,
    ) -> dict[str, Any]:
        last_error: BaseException | None = None
        for attempt in range(1, self.judge.max_retries + 1):
            try:
                response = self.judge.request_image_json(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=USER_PROMPT_TEMPLATE.format(time_sec=time_sec),
                    image_data_urls=[before_data_url, after_data_url],
                    enable_thinking=self.enable_thinking,
                )
                is_cut, reason = _validate_binary_response(response["parsed"])
                return {
                    "is_cut": is_cut,
                    "reason": reason,
                    "usage": response.get("usage"),
                    "request_id": response.get("request_id"),
                }
            except Exception as exc:
                last_error = exc
                if attempt >= self.judge.max_retries:
                    break
                time.sleep(self.judge.retry_backoff_sec * attempt)
        raise RuntimeError(
            f"VLM cut classification failed after {self.judge.max_retries} attempts: {last_error}"
        ) from last_error

    def validate(
        self,
        video_path: Path,
        candidate_cuts: list[float],
    ) -> dict[str, Any]:
        if not candidate_cuts:
            return {
                "cuts": [],
                "candidates": [],
                "model": self.judge.model,
                "provider": self.judge.provider,
                "usage": {},
            }
        fps, pairs = _extract_adjacent_frame_pairs(
            video_path,
            candidate_cuts,
            frame_width=self.frame_width,
        )
        futures: dict[Future[dict[str, Any]], int] = {}
        for index, (
            _before_index,
            _after_index,
            before_url,
            after_url,
        ) in enumerate(pairs):
            futures[
                self._executor.submit(
                    self._classify,
                    candidate_cuts[index],
                    before_url,
                    after_url,
                )
            ] = index

        results: list[dict[str, Any] | None] = [None] * len(candidate_cuts)
        for future in as_completed(futures):
            index = futures[future]
            before_index, after_index, _before_url, _after_url = pairs[index]
            classification = future.result()
            results[index] = {
                "time_sec": candidate_cuts[index],
                "frame_before": before_index,
                "frame_after": after_index,
                "is_cut": classification["is_cut"],
                "reason": classification["reason"],
                "request_id": classification.get("request_id"),
                "usage": classification.get("usage"),
            }

        candidates = [result for result in results if result is not None]
        usage: dict[str, float] = {}
        for result in candidates:
            _merge_usage(usage, result.get("usage"))
        return {
            "cuts": [float(result["time_sec"]) for result in candidates if result["is_cut"]],
            "candidates": candidates,
            "model": self.judge.model,
            "provider": self.judge.provider,
            "fps": fps,
            "frame_sampling": ("frame immediately before candidate and frame at candidate"),
            "classification": "binary_is_cut",
            "enable_thinking": self.enable_thinking,
            "usage": usage,
        }
