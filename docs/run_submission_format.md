# Run Submission Format

This document defines where baseline outputs go and which metadata each method must provide.

## Directory Convention

Each baseline or ablation should write one run directory:

```text
runs/<run_id>/
  run_manifest.json
  run_outputs.jsonl
  task_outputs/
    <task_id>/
      output.mp4
      run_output.json
      logs/
        backend.log
      artifacts/
        shot_plan.json
```

`run_id` should identify the method and experiment setting, for example:

```text
cutclaw_original
cutmaster_embedding_v4_full
cutmaster_local_embedding
baseline_random
```

Use stable names for comparison runs. Add a date only when the same method/config is intentionally rerun and both results need to be kept.

## Per-Task `run_output.json`

`task_outputs/<task_id>/run_output.json` is the canonical per-task record and must follow `schemas/run_output.schema.json`.

Task ids use the canonical format `task_<index>`, for example `task_001`.

Required fields:

- `run_id`: run directory name.
- `method`: system or baseline name.
- `method_version`: optional method variant, model setting, or ablation name.
- `task_id`: benchmark task id from `data/tasks/mashup_benchmark.jsonl`.
- `video_id`, `audio_id`, `prompt_type`: copied from the task for easier joins.
- `status`: `success`, `failed`, or `skipped`.
- `output_video`: path to the generated video relative to benchmark root.
- `target_output_length_sec`: effective output target used by the method. Its meaning is selected by `target_duration_mode` below.
- `target_shot_length_sec`: target average shot length used by the method.
- `actual_output_length_sec`: measured final video duration.
- `wall_clock_sec`: end-to-end generation time for this task.
- `created_at`: ISO-8601 timestamp.

Recommended optional fields:

- `target_duration_mode`: `task` for the canonical task target or `music` for the full duration of the task's canonical BGM. Missing is interpreted as `task` for backward compatibility.
- `api_cost_usd`: total API cost for the task.
- `code_commit`: source code commit used for the method.
- `config`: key model and algorithm settings.
- `artifacts`: paths to logs, shot plans, intermediate plans, or traces.
- `error`: structured failure information when `status != success`.

Human ratings such as `OQ` must be stored by the separate human-evaluation
workflow. Do not embed `human_scores` or `scores` in run output records.

Example:

```json
{
  "run_id": "cutmaster_embedding_v4_full",
  "method": "CutMaster",
  "method_version": "embedding_v4",
  "task_id": "task_001",
  "video_id": "video_001",
  "audio_id": "audio_001",
  "prompt_type": "event",
  "status": "success",
  "output_video": "runs/cutmaster_embedding_v4_full/task_outputs/task_001/output.mp4",
  "target_output_length_sec": 60,
  "target_duration_mode": "task",
  "target_shot_length_sec": 4.0,
  "actual_output_length_sec": 58.7,
  "wall_clock_sec": 1234.5,
  "api_cost_usd": 0.42,
  "created_at": "2026-06-29T12:00:00+08:00",
  "code_commit": "git_sha",
  "config": {
    "embedding_model": "text-embedding-v4",
    "vlm_model": "qwen-vl-plus",
    "llm_model": "qwen-max"
  },
  "artifacts": {
    "shot_plan": "runs/cutmaster_embedding_v4_full/task_outputs/task_001/artifacts/shot_plan.json",
    "backend_log": "runs/cutmaster_embedding_v4_full/task_outputs/task_001/logs/backend.log"
  },
  "error": null
}
```

### Target-duration modes

The standard benchmark setting is `task`: `target_output_length_sec` must
strictly equal the value in `data/tasks/mashup_benchmark.jsonl` (currently 60
seconds). Legacy records without `target_duration_mode` are validated as
`task` records.

The `music` variant allows an experiment to use the complete BGM as its target.
In that case, `target_duration_mode` must be explicitly set to `music`, and
`target_output_length_sec` must equal the `ffprobe` duration of the canonical
audio file bound to that task, within 0.001 seconds. The validator resolves the
audio through the benchmark task metadata; a submission cannot choose its own
audio path or asserted duration. Evaluators and both VLM judge prompts use this
effective run-record target instead of the canonical 60-second task target.

Report and compare `task` and `music` runs as separate experiment variants.

## `run_outputs.jsonl`

`run_outputs.jsonl` duplicates the per-task `run_output.json` records as JSONL so evaluation scripts can stream a whole run without walking directories.

Every successful task should have both:

```text
task_outputs/<task_id>/run_output.json
one matching line in run_outputs.jsonl
```

Failed tasks are allowed in a partial run. A failed task does not need `output.mp4`, but its `run_output.json` record must set `status` to `failed` and include a non-null `error` object. Adapters may reuse the same `run_id` to resume a run: existing successful tasks can be skipped, while failed or incomplete tasks are retried and their records are replaced.

## `run_manifest.json`

`run_manifest.json` stores global metadata for the whole baseline execution and must follow `schemas/run_manifest.schema.json`.

Adapters that support duration variants should also write
`adapter.options.target_duration_mode`. When present, it must agree with every
per-task record in the run; use separate run ids rather than mixing `task` and
`music` records.

Example:

```json
{
  "run_id": "cutmaster_embedding_v4_full",
  "method": "CutMaster",
  "method_version": "embedding_v4",
  "benchmark": "Mashup-Benchmark",
  "task_file": "data/tasks/mashup_benchmark.jsonl",
  "created_at": "2026-06-29T12:00:00+08:00",
  "status": "success",
  "num_tasks": 40,
  "num_success": 40,
  "num_failed": 0,
  "run_outputs": "runs/cutmaster_embedding_v4_full/run_outputs.jsonl",
  "code": {
    "repo": "CutMaster",
    "repo_url": "https://github.com/hit-cxf/CutMaster",
    "branch": "main",
    "commit": "git_sha",
    "dirty": false
  },
  "adapter": {
    "name": "run_cutmaster",
    "script": "scripts/run_cutmaster.py",
    "project_root": "/path/to/CutMaster",
    "python": "/path/to/CutMaster/.venv/bin/python",
    "benchmark_root": "/path/to/Mashup-Benchmark",
    "results_root": "runs",
    "task_selection": {
      "mode": "all",
      "task_ids": ["task_001", "task_002"]
    },
    "options": {
      "overwrite": false,
      "config": "/path/to/CutMaster/config.toml",
      "subtitle_path": null
    }
  },
  "config": {
    "embedding_model": "text-embedding-v4",
    "target_output_length_sec": 60,
    "target_shot_length_sec": 4.0
  },
  "aggregate": {
    "total_wall_clock_sec": 49320.1,
    "total_api_cost_usd": 16.8
  }
}
```

## Evaluation Outputs

Evaluation outputs are separate from generated videos:

```text
eval_results/<eval_id>/
  evaluation_scores.jsonl
  summary.json
```

A score record should reference `run_id` and `task_id`, not copy the generated video.
