from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from eval.evaluators.vlm_judge import VLMJudge, _extract_json
from eval.target_duration import effective_target_output_length_sec

SYSTEM_PROMPT = """You are a strict evaluator for prompt-specified short-form video editing metrics. Score only what is visible in the provided video and described task metadata. Return JSON only."""

TYPE_METRICS: dict[str, list[dict[str, Any]]] = {
    "event": [
        {
            "code": "EC",
            "name_en": "Event Coverage",
            "name_zh": "事件覆盖率",
            "description": "Whether the final edit covers the key events explicitly requested by the prompt.",
            "anchors": {
                1: "Almost none of the requested key events are visible, or the edit focuses on unrelated content.",
                2: "Only one or a small minority of requested events are visible; most required event categories are missing.",
                3: "Some requested events are covered, but important event categories or decisive moments are missing.",
                4: "Most requested key events are covered, with only minor omissions or weak emphasis on a few events.",
                5: "All or nearly all requested key events are clearly represented and easy to identify in the final edit.",
            },
        },
        {
            "code": "KMS",
            "name_en": "Key Moment Salience",
            "name_zh": "片段显著性",
            "description": "Whether the selected clips are salient highlights or decisive moments rather than merely related footage.",
            "anchors": {
                1: "Clips are mostly ordinary, filler, or unrelated, with little sense of highlight value.",
                2: "A few clips are mildly relevant, but most lack decisive action, tension, consequence, or highlight salience.",
                3: "The edit includes some salient moments, mixed with ordinary or weakly consequential footage.",
                4: "Most clips are clear highlights or important moments, with only occasional lower-salience segments.",
                5: "The edit consistently selects decisive, high-impact, highlight-worthy moments matching the event prompt.",
            },
        },
    ],
    "character": [
        {
            "code": "PPR",
            "name_en": "Protagonist Presence Rate",
            "name_zh": "主体出镜率",
            "description": "How much of the final edit visibly contains the target protagonist, character, or character group requested by the prompt.",
            "anchors": {
                1: "The requested protagonist or character group is rarely or never visible.",
                2: "The protagonist appears only briefly or ambiguously; much of the edit focuses on other subjects.",
                3: "The protagonist appears in a meaningful portion of the edit, but presence is inconsistent.",
                4: "The protagonist is visible through most of the edit, with only minor detours to supporting context.",
                5: "The requested protagonist or character group is consistently visible and remains the dominant subject of the edit.",
            },
        },
        {
            "code": "PPM",
            "name_en": "Protagonist Prominence",
            "name_zh": "主体显著性",
            "description": "Whether the requested protagonist is visually prominent, clear, and central rather than distant, obscured, or peripheral.",
            "anchors": {
                1: "The protagonist is not identifiable, extremely small, obscured, or visually peripheral in most relevant shots.",
                2: "The protagonist is sometimes identifiable but often distant, blurry, occluded, or not visually emphasized.",
                3: "The protagonist is reasonably visible in several shots, but prominence and clarity are uneven.",
                4: "The protagonist is usually clear, identifiable, and visually emphasized, with minor framing or clarity issues.",
                5: "The protagonist is consistently clear, central, and visually prominent in the selected shots.",
            },
        },
    ],
    "emotion": [
        {
            "code": "ES",
            "name_en": "Emotional Specificity",
            "name_zh": "情绪特异性",
            "description": "Whether the edit expresses the specific target emotion requested by the prompt instead of a generic energetic or atmospheric mood.",
            "anchors": {
                1: "The expressed mood contradicts the prompt or is not emotionally legible.",
                2: "The edit conveys only a vague or generic mood and misses the specific requested emotion.",
                3: "The requested emotion is partially present, but mixed with generic or inconsistent emotional signals.",
                4: "The edit mostly expresses the specific requested emotion, with minor ambiguity or occasional drift.",
                5: "The edit clearly and consistently expresses the specific target emotion requested by the prompt.",
            },
        },
        {
            "code": "FBAE",
            "name_en": "Facial / Body Affect Evidence",
            "name_zh": "面部/肢体情绪证据",
            "description": "Whether visible facial expressions, body language, interactions, or crowd reactions provide evidence for the target emotion.",
            "anchors": {
                1: "There is almost no visible facial, body, interaction, or crowd evidence supporting the requested emotion.",
                2: "A few weak affective cues are visible, but the emotion is mostly carried by music or context rather than visual evidence.",
                3: "Some visible affective evidence supports the target emotion, but it is intermittent or not very strong.",
                4: "Clear facial expressions, body language, interactions, or crowd reactions support the target emotion in most key moments.",
                5: "Strong and repeated visible affective evidence makes the target emotion immediately legible throughout the edit.",
            },
        },
    ],
    "narrative": [
        {
            "code": "NSC",
            "name_en": "Narrative Structure Completeness",
            "name_zh": "叙事完整性",
            "description": "Whether the edit forms a complete narrative structure rather than a loose collection of related clips.",
            "anchors": {
                1: "The edit feels like random or disconnected clips with no recognizable narrative structure.",
                2: "A weak topic is present, but setup, development, climax, or resolution are mostly missing.",
                3: "A basic narrative is understandable, but one or more major stages are missing or underdeveloped.",
                4: "The edit has a mostly complete narrative structure with minor gaps or uneven emphasis.",
                5: "The edit presents a clear and complete narrative arc with coherent setup, development, climax, and resolution.",
            },
        },
        {
            "code": "TLO",
            "name_en": "Temporal / Logical Order",
            "name_zh": "时间合理性",
            "description": "Whether the clip order follows a reasonable temporal, causal, or thematic progression.",
            "anchors": {
                1: "The order is confusing, contradictory, or breaks basic temporal/causal understanding.",
                2: "Several clips appear out of order or logically disconnected, making progression hard to follow.",
                3: "The order is partly reasonable, but some transitions or event placements feel confusing or weakly motivated.",
                4: "The clip order mostly follows a sensible temporal, causal, or thematic progression with minor issues.",
                5: "The order is consistently clear, logical, and purposeful, supporting the intended narrative progression.",
            },
        },
    ],
}

METRIC_REFERENCES: dict[str, list[str]] = {
    "EC": ["CutClaw", "Less is More: Learning Highlight Detection from Video Duration", "Weakly-Supervised Movie Trailer Generation"],
    "KMS": ["DIRECT", "Less is More: Learning Highlight Detection from Video Duration", "Weakly-Supervised Movie Trailer Generation"],
    "PPR": ["Crayotter", "VideoAgent", "CutClaw"],
    "PPM": ["Crayotter", "CutClaw"],
    "ES": ["Weakly-Supervised Movie Trailer Generation", "Crayotter", "CutClaw"],
    "FBAE": ["Crayotter", "VideoAgent", "Weakly-Supervised Movie Trailer Generation"],
    "NSC": ["CutClaw", "Crayotter", "DIRECT"],
    "TLO": ["Weakly-Supervised Movie Trailer Generation", "Crayotter", "DIRECT"],
}


def metric_label(metric: dict[str, str]) -> str:
    return f"{metric['code']} — {metric['name_en']} — {metric['name_zh']}"


def metrics_for_task_type(task_type: str) -> list[dict[str, Any]]:
    normalized = task_type.strip().lower()
    if normalized not in TYPE_METRICS:
        raise ValueError(f"Unsupported task type for type diagnostics: {task_type}")
    return TYPE_METRICS[normalized]


def _video_content(path: Path) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "video_url", "video_url": {"url": f"data:{mime_type};base64,{encoded}"}}


def _video_content_dashscope(path: Path, fps: float, max_frames: int | None) -> dict[str, Any]:
    content: dict[str, Any] = {"video": f"file://{path.resolve()}", "fps": fps}
    if max_frames is not None:
        content["max_frames"] = max_frames
    return content


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


def _anchor_lines(metric: dict[str, Any]) -> str:
    anchors = metric["anchors"]
    return "\n".join(f"  {score} = {anchors[score]}" for score in range(1, 6))


def _prompt_for_metrics(task: dict[str, Any], run_record: dict[str, Any], metrics: list[dict[str, Any]]) -> str:
    metric_sections = "\n\n".join(
        f"{metric_label(metric)}\n"
        f"Definition: {metric['description']}\n"
        f"Rating anchors:\n{_anchor_lines(metric)}"
        for metric in metrics
    )
    score_keys = ", ".join(f'"{metric["code"]}": 1' for metric in metrics)
    rationale_keys = ", ".join(f'"{metric["code"]}": "short reason"' for metric in metrics)
    metric_codes = ", ".join(metric["code"] for metric in metrics)

    return f"""
Evaluate this generated short video using only the specified metrics for its prompt type.

These metrics are independent from the benchmark's main Quality score. Keep scores independent:
- Do not score generic visual quality, beat synchronization, audio-visual energy, or overall instruction following unless they directly affect the requested specified metric.
- Use only the metric sections shown below. Do not infer or score metrics from other prompt types.
- Score only what is visible in the provided final video and described task metadata.

Task prompt:
{task['task']['prompt']}

Task type: {task['task']['type']} ({task['task'].get('type_zh', '')})
Source video title: {task['video'].get('title_en') or task['video'].get('title_zh') or task['video'].get('id')}
BGM title: {task['audio'].get('title') or task['audio'].get('id')}
BGM mood tags: {', '.join(task['audio'].get('mood_tags') or [])}
Target output length: {effective_target_output_length_sec(task, run_record)}s
Actual output length: {run_record.get('actual_output_length_sec')}s

Score only these metrics on a 1-5 Likert scale using their metric-specific anchors:

{metric_sections}

Return a JSON object exactly like:
{{
  "scores": {{{score_keys}}},
  "rationale": {{{rationale_keys}}},
  "diagnostics": {{
    "visible_evidence": ["brief evidence supporting {metric_codes}"],
    "missing_or_weak_evidence": ["brief missing/weak evidence, or empty list"],
    "uncertain_observations": ["things that could not be verified, or empty list"]
  }}
}}
""".strip()


class SpecifiedMetricsJudge(VLMJudge):
    def score_specified_metrics(self, output_video: Path, task: dict[str, Any], run_record: dict[str, Any]) -> dict[str, Any]:
        video_size_bytes = output_video.stat().st_size
        max_video_bytes = int(self.max_video_mb * 1024 * 1024)
        if video_size_bytes > max_video_bytes:
            raise ValueError(
                f"Video is too large for VLM upload: {video_size_bytes / 1024 / 1024:.1f} MB "
                f"> {self.max_video_mb:.1f} MB"
            )

        task_type = str(task["task"]["type"]).strip().lower()
        metrics = metrics_for_task_type(task_type)
        user_text = _prompt_for_metrics(task, run_record, metrics)

        if self.provider == "dashscope":
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        _video_content_dashscope(output_video, self.video_fps, self.max_video_frames),
                        {"text": user_text},
                    ],
                },
            ]
            raw = self._post_multimodal_conversation(messages)
        else:
            payload = {
                "model": self.model,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            _video_content(output_video),
                            {"type": "text", "text": user_text},
                        ],
                    },
                ],
            }
            raw = self._post_chat_completion(payload)

        content_text = raw["choices"][0]["message"]["content"]
        parsed = _extract_json(content_text)
        raw_scores = parsed.get("scores") or {}
        scores: dict[str, float] = {}
        metric_details: dict[str, Any] = {}
        for metric in metrics:
            code = metric["code"]
            value = float(raw_scores.get(code, 1.0))
            value = max(1.0, min(5.0, value))
            scores[code] = value
            metric_details[code] = {
                "label": metric_label(metric),
                "name_en": metric["name_en"],
                "name_zh": metric["name_zh"],
                "description": metric["description"],
                "references": METRIC_REFERENCES.get(code, []),
                "scale": "likert_1_5",
                "raw_score": value,
            }

        diagnostics = parsed.get("diagnostics") if isinstance(parsed.get("diagnostics"), dict) else {}
        return {
            "task_type": task_type,
            "scores": scores,
            "metric_details": metric_details,
            "rationale": parsed.get("rationale") or {},
            "diagnostics": {
                "visible_evidence": _string_list(diagnostics.get("visible_evidence")),
                "missing_or_weak_evidence": _string_list(diagnostics.get("missing_or_weak_evidence")),
                "uncertain_observations": _string_list(diagnostics.get("uncertain_observations")),
            },
            "usage": raw.get("usage"),
            "model": self.model,
            "input_type": "video",
            "vlm_provider": self.provider,
            "score_scale": "likert_1_5",
            "video_size_bytes": video_size_bytes,
        }
