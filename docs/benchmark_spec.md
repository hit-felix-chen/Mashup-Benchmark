# Benchmark Specification

## Unit of Evaluation

One benchmark item is a tuple:

```text
(source_video, user_prompt, audio_track, target_output_length, target_shot_length)
```

The system output is one complete short video for that item. Canonical task ids follow `task_<index>`, from `task_001` to `task_040`.

The canonical benchmark uses `target_duration_mode: task`. A run may explicitly
declare the optional `music` duration variant, in which the effective target is
the full duration of the canonical BGM bound to the task. The run record stores
that effective value in `target_output_length_sec`; validators verify it against
the canonical audio file, and evaluators use it for length-sensitive judging.
Results from the two duration modes should not be pooled as the same setting.

## Task Types

- Event: asks for salient events or action moments.
- Character: asks for a person/team/entity-centered edit.
- Emotion: asks for a mood-driven edit.
- Narrative: asks for a structured story or progression.

## Canonical File

`data/tasks/mashup_benchmark.jsonl` is the source of truth. Files in `manifests/` are derived convenience indexes. Source media files are stored in per-asset directories: `data/videos/<video_id>/...` and `data/audios/<audio_id>/...`.

## Run Record

A run should write generated videos and metadata under `runs/<run_id>/`. The whole run follows `schemas/run_manifest.schema.json`; each task follows `schemas/run_output.schema.json`.

Recommended output layout:

```text
runs/<run_id>/run_manifest.json
runs/<run_id>/run_outputs.jsonl
runs/<run_id>/task_outputs/<task_id>/output.mp4
runs/<run_id>/task_outputs/<task_id>/run_output.json
runs/<run_id>/task_outputs/<task_id>/logs/backend.log
runs/<run_id>/task_outputs/<task_id>/artifacts/shot_plan.json
eval_results/<eval_id>/evaluation_scores.jsonl
```

See `docs/run_submission_format.md` for the exact submission contract.

## Reproducibility Fields

Each per-task run record should include:

- method name and optional method version
- target task id plus copied `video_id`, `audio_id`, and `prompt_type`
- output video path relative to benchmark root
- target and actual output durations
- wall-clock latency
- API cost if available
- code commit and major model/config settings when available
- status and failure reason if failed

Each run manifest should include global method metadata, code version, task file, aggregate cost/latency, and the path to `run_outputs.jsonl`.
