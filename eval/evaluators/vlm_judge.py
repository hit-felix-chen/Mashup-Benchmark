from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SYSTEM_PROMPT = """You are a strict evaluator for short-form video editing benchmarks. Score only what is visible in the provided video and described task metadata. Return JSON only."""

USER_PROMPT_TEMPLATE = """
Evaluate this generated short video for Mashup-Benchmark.

Task prompt:
{prompt}

Task type: {task_type}
Source video title: {video_title}
BGM title: {audio_title}
Target output length: {target_output_length_sec}s
Target shot length: {target_shot_length_sec}s
Actual output length: {actual_output_length_sec}s

Score the following metrics on a 1-5 Likert scale:
Use the metric-specific anchors below. Keep metrics independent:
- Do not penalize IF for visual quality or transition quality unless they prevent judging prompt fulfillment.
- Do not score beat synchronization or audio-visual energy alignment here; those are computed separately.
- Use BGM metadata only when judging whether the requested style or emotion is supported.
- Length mismatch should affect IF only if it substantially violates the requested output length or prevents satisfying the prompt.

IF: Instruction Following. Does the edit follow the requested subject, event, style, emotion, or narrative?
1 = unrelated or contradicts the prompt.
2 = weakly related; misses most key requested elements.
3 = partially follows; covers some key elements but misses important ones.
4 = mostly follows; minor omissions or weak emphasis.
5 = strongly follows all key requested elements and constraints.

VQ: Visual Quality. Is the video clear, well-composed, subject-focused, and free of obvious technical defects?
1 = severe visual defects make the video hard to watch.
2 = frequent blur, occlusion, bad framing, or unstable subject focus.
3 = generally watchable but with noticeable quality or framing issues.
4 = clear and stable with only minor visual issues.
5 = consistently clear, well-composed, and subject-focused.

TC: Transition Continuity. Do adjacent segments feel coherent in visual semantics, motion, and composition?
1 = chaotic or jarring cuts that break comprehension.
2 = many abrupt jumps or mismatched transitions.
3 = mixed continuity; some transitions work, some feel abrupt.
4 = mostly smooth and coherent transitions with minor jumps.
5 = consistently natural, purposeful, and rhythmically coherent transitions.

NC: Narrative Coherence. Does the edit have a clear structure, progression, or story arc matching the prompt?
1 = random clips with no understandable structure.
2 = weak structure; sequence feels mostly disjointed.
3 = basic progression is present but underdeveloped or uneven.
4 = clear progression with minor gaps or pacing issues.
5 = strong beginning-middle-end or emotional/story progression.

Return a JSON object exactly like:
{{
  "scores": {{"IF": 1, "VQ": 1, "TC": 1, "NC": 1}},
  "rationale": {{
    "IF": "short reason",
    "VQ": "short reason",
    "TC": "short reason",
    "NC": "short reason"
  }},
  "diagnostics": {{
    "matched_prompt_elements": ["visible requested element"],
    "missing_prompt_elements": ["requested element not visible"],
    "visual_quality_issues": ["blur, bad framing, occlusion, or empty list"],
    "transition_issues": ["abrupt jump, mismatched motion, or empty list"],
    "narrative_issues": ["weak opening, temporal disorder, or empty list"],
    "length_issue": "none | too_short | too_long",
    "uncertain_observations": ["things that could not be verified, or empty list"]
  }}
}}
""".strip()


def _video_content(path: Path) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "video_url", "video_url": {"url": f"data:{mime_type};base64,{encoded}"}}


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


def _normalize_diagnostics(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    length_issue = str(raw.get("length_issue") or "none").strip().lower()
    if length_issue not in {"none", "too_short", "too_long"}:
        length_issue = "none"
    return {
        "matched_prompt_elements": _string_list(raw.get("matched_prompt_elements")),
        "missing_prompt_elements": _string_list(raw.get("missing_prompt_elements")),
        "visual_quality_issues": _string_list(raw.get("visual_quality_issues")),
        "transition_issues": _string_list(raw.get("transition_issues")),
        "narrative_issues": _string_list(raw.get("narrative_issues")),
        "length_issue": length_issue,
        "uncertain_observations": _string_list(raw.get("uncertain_observations")),
    }


class VLMJudge:
    def __init__(self, config: dict[str, Any]):
        vlm = config.get("vlm") or {}
        self.model = str(vlm.get("model") or "")
        self.api_key = str(vlm.get("api_key") or "")
        self.base_url = str(vlm.get("base_url") or "").rstrip("/")
        self.timeout_sec = int(vlm.get("timeout_sec") or 120)
        self.temperature = float(vlm.get("temperature") or 0)
        self.max_video_mb = float(vlm.get("max_video_mb") or 500)
        self.max_retries = int(vlm.get("max_retries") or 3)
        self.retry_backoff_sec = float(vlm.get("retry_backoff_sec") or 2)
        if not self.model or not self.api_key or not self.base_url:
            raise ValueError("vlm.model, vlm.api_key, and vlm.base_url are required in eval/config.yaml")

    def _post_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        retryable_http_codes = {408, 409, 429, 500, 502, 503, 504}
        last_error: BaseException | None = None
        for attempt in range(1, self.max_retries + 1):
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                response_body = exc.read().decode("utf-8", errors="replace")[-2000:]
                if exc.code not in retryable_http_codes or attempt >= self.max_retries:
                    raise RuntimeError(f"VLM request failed: HTTP {exc.code}: {response_body}") from exc
                print(
                    f"[VLMJudge] HTTP {exc.code} on attempt {attempt}/{self.max_retries}; retrying...",
                    flush=True,
                )
            except (urllib.error.URLError, TimeoutError, ConnectionResetError, BrokenPipeError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"VLM request failed after {self.max_retries} attempts: {exc}"
                    ) from exc
                print(
                    f"[VLMJudge] Network error on attempt {attempt}/{self.max_retries}: {exc}; retrying...",
                    flush=True,
                )
            time.sleep(self.retry_backoff_sec * attempt)
        raise RuntimeError(f"VLM request failed after {self.max_retries} attempts: {last_error}")

    def score(self, output_video: Path, task: dict[str, Any], run_record: dict[str, Any]) -> dict[str, Any]:
        video_size_bytes = output_video.stat().st_size
        max_video_bytes = int(self.max_video_mb * 1024 * 1024)
        if video_size_bytes > max_video_bytes:
            raise ValueError(
                f"Video is too large for VLM upload: {video_size_bytes / 1024 / 1024:.1f} MB "
                f"> {self.max_video_mb:.1f} MB"
            )

        user_text = USER_PROMPT_TEMPLATE.format(
            prompt=task["task"]["prompt"],
            task_type=task["task"]["type"],
            video_title=task["video"].get("title_en") or task["video"].get("title_zh") or task["video"].get("id"),
            audio_title=task["audio"].get("title") or task["audio"].get("id"),
            target_output_length_sec=task["task"]["target_output_length_sec"],
            target_shot_length_sec=task["task"]["target_shot_length_sec"],
            actual_output_length_sec=run_record.get("actual_output_length_sec"),
        )
        content: list[dict[str, Any]] = [
            _video_content(output_video),
            {"type": "text", "text": user_text},
        ]
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        }
        raw = self._post_chat_completion(payload)

        content_text = raw["choices"][0]["message"]["content"]
        parsed = _extract_json(content_text)
        scores = parsed.get("scores") or {}
        likert_scores = {}
        for key in ["IF", "VQ", "TC", "NC"]:
            value = float(scores.get(key, 1.0))
            likert_scores[key] = max(1.0, min(5.0, value))
        return {
            "scores": likert_scores,
            "rationale": parsed.get("rationale") or {},
            "diagnostics": _normalize_diagnostics(parsed.get("diagnostics")),
            "usage": raw.get("usage"),
            "model": self.model,
            "input_type": "video",
            "score_scale": "likert_1_5",
            "video_size_bytes": video_size_bytes,
        }
