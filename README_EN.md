# Mashup-Benchmark

[中文](README.md)

Mashup-Benchmark is a long-video automatic editing benchmark for evaluating short-form mashup, highlight, and music-driven video editing systems.

![Mashup-Benchmark Overview](docs/assets/mashup_benchmark_overview.png)

## Dataset

- 10 hour-scale source videos: 3 sports broadcasts, 3 documentary episodes, and 4 feature films.
- 40 video-prompt tasks: each source video has 4 task types: event, character, emotion, and narrative.
- 11 BGM tracks from Mixkit, assigned by task mood and genre.
- Default target output length: 60 seconds.
- Default target shot length: 4 seconds.

The canonical task file is `data/tasks/mashup_benchmark.jsonl`. Each line is one video-prompt-audio task. Task ids follow `task_<index>`, from `task_001` to `task_040`.

<details>
<summary>Videos</summary>

| ID | Category | Title | Duration | Resolution |
|---|---|---|---:|---|
| `video_001` | sports | FIFA World Cup Group A: Mexico vs South Africa<br>美加墨世界杯A组第1轮：墨西哥VS南非 | 01:38:53 | 480x270 |
| `video_002` | sports | FIFA World Cup Group H: Spain vs Cape Verde<br>美加墨世界杯H组第1轮：西班牙VS佛得角 | 02:03:58 | 1920x1080 |
| `video_003` | sports | FIFA World Cup Group E: Germany vs Curacao<br>美加墨世界杯E组第1轮：德国VS库拉索 | 02:09:00 | 1920x1080 |
| `video_004` | documentary | Planet Earth S01E01: From Pole to Pole<br>地球脉动 第一季第一集：From Pole to Pole | 49:02 | 1920x1080 |
| `video_005` | documentary | Planet Earth S01E02: Mountains<br>地球脉动 第一季第二集：Mountains | 47:52 | 1920x1080 |
| `video_006` | documentary | Planet Earth S01E03: Fresh Water<br>地球脉动 第一季第三集：Fresh Water | 49:11 | 1920x1080 |
| `video_007` | film | The Godfather (1972)<br>教父1 | 02:57:09 | 1920x1080 |
| `video_008` | film | Spirited Away (2001)<br>千与千寻 | 02:04:32 | 1920x1038 |
| `video_009` | film | La La Land (2016)<br>爱乐之城 | 02:07:48 | 1920x754 |
| `video_010` | film | Interstellar (2014)<br>星际穿越 | 02:49:04 | 1920x1080 |

</details>

<details>
<summary>Audios</summary>

| ID | Title | Artist | Duration | Mood Tags |
|---|---|---|---:|---|
| `audio_001` | Sports Highlights | Ahjay Stelino | 01:36 | sports, rock, aggressive, propulsive |
| `audio_002` | Dirty Thinkin' | Michael Ramir C. | 01:29 | funk, energetic, groove, playful |
| `audio_003` | Techno Fest Vibes | Alejandro Magana (A. M.) | 01:09 | edm, high_energy, driving, celebratory |
| `audio_004` | Fright Night | Michael Ramir C. | 01:41 | cinematic, tension, dark, suspense |
| `audio_005` | Sun and His Daughter | Eugenio Mininni | 02:48 | nature, poetic, world, expansive |
| `audio_006` | Discover | Eugenio Mininni | 02:24 | documentary, hopeful, orchestral, wonder |
| `audio_007` | Relax Beat | Arulo | 01:48 | ambient, calm, observational, soft |
| `audio_008` | Silent Descent | Eugenio Mininni | 02:40 | film_score, melancholic, reflective, dramatic |
| `audio_009` | Epical Drums 01 | Grigoriy Nuzhny | 01:46 | cinematic, drums, epic, action |
| `audio_010` | Romantic Getaway | Ahjay Stelino | 01:44 | romantic, warm, emotional, classical |
| `audio_011` | Romantic Vacation | Ahjay Stelino | 01:52 | jazz, romantic, lounge, stylish |

</details>

## Directory Layout

```text
Mashup-Benchmark/
  data/
    tasks/mashup_benchmark.jsonl # Canonical 40-task JSONL
    videos/<video_id>/             # Source long-video asset directories, ignored by Git
    audios/<audio_id>/             # BGM audio asset directories, ignored by Git
  manifests/                     # Derived indexes for videos, audio, tasks, and summary
  schemas/                       # JSON Schema files for task/run/evaluation records
  scripts/                       # Validation and utility scripts
  runs/                          # System outputs, run_output.json files, and run manifests
  outputs/                       # Temporary exported artifacts that are not submitted runs
  eval/                          # Evaluation code
  eval_results/                  # Metric outputs and VLM-as-judge scores
  reports/                       # Aggregated tables, plots, and experiment notes
  docs/                          # Benchmark spec, metric protocol, and data card
```

## Expected System Output

One `run` represents the complete output of one baseline or ablation setting on one or more benchmark tasks. Each task should produce one complete edited short video and use the following structure:

```text
runs/<run_id>/
  run_manifest.json             # Whole-run metadata, following schemas/run_manifest.schema.json
  run_outputs.jsonl             # JSONL index of all per-task run_output.json records
  task_outputs/
    <task_id>/
      output.mp4                # Final edited video for this task, consumed directly by the evaluator
      run_output.json           # Per-task metadata, following schemas/run_output.schema.json
      logs/
        backend.log             # Optional raw pipeline log
        render.log              # Optional render log
      artifacts/
        benchmark_task.json     # Optional snapshot of the benchmark task input
        shot_plan.json          # Optional method-internal editing plan
        shot_point.json         # Optional method-internal edit points or timeline
```

`<run_id>` identifies the method and experiment setting, for example `cutclaw_benchmark` or `cutmaster_embedding_v4_full`; `<task_id>` uses the canonical `task_001` to `task_040` ids. The minimum required files for evaluation are `run_manifest.json`, `run_outputs.jsonl`, and each successful task's `output.mp4` and `run_output.json`. See `docs/run_submission_format.md` for the full submission format.

## Environment Setup

This benchmark uses `uv` to manage its own Python environment, independent from any baseline project's virtual environment. From the benchmark root, run:

```bash
uv sync
```

Then use `uv run` for validation, adapters, and evaluation:

```bash
uv run python scripts/validate_benchmark.py
uv run python scripts/validate_run.py runs/<run_id>
uv run python -m eval.run_evaluation --run runs/<run_id> --config eval/config.yaml
```

Media decoding and automatic metrics rely on the system commands `ffmpeg` and `ffprobe`; they are not installed by the Python environment, so make sure both are available on `PATH`. Local VLM credentials should be placed in `eval/config.yaml`, which is ignored by Git.

## Evaluation Dimensions

The full quality score uses 7 metrics:

```text
Quality = weighted_mean(IF, BCS, AEC, VQ, TC, NC, OQ)
```

Weighting policy:

- Local automatic metrics: `BCS = 0.20`, `AEC = 0.20`.
- VLM-as-judge metrics: `IF = 0.10`, `VQ = 0.10`, `TC = 0.10`, `NC = 0.10`.
- Human evaluation metric: `OQ = 0.20`.
- If human `OQ` is unavailable, the available 6 metrics are automatically renormalized: `BCS = 0.25`, `AEC = 0.25`, and `IF/VQ/TC/NC = 0.125`.

Raw VLM-as-judge scores for `IF/VQ/TC/NC` and the human `OQ` score use a 1-5 Likert scale. For `Quality`, they are converted to the 0-100 scale with `(score - 1) / 4 * 100`.

Metrics:

- IF: Instruction Following.
- BCS: Beat-Cut Synchronization; based on full-frame visual cut detection on the final rendered video, without reading the edit timeline.
- AEC: Audio-Visual Energy Correspondence.
- VQ: Visual Quality.
- TC: Transition Continuity.
- NC: Narrative Coherence.
- OQ: Overall Quality, optional human rating on a 1-5 Likert scale.


Specified Metrics are independent from the main score and are not included in `Quality`. They are used only for prompt-type-specific failure analysis and fine-grained diagnostics:

- Event prompts: `EC — Event Coverage — 事件覆盖率`, `KMS — Key Moment Salience — 片段显著性`.
- Character prompts: `PPR — Protagonist Presence Rate — 主体出镜率`, `PPM — Protagonist Prominence — 主体显著性`.
- Emotion prompts: `ES — Emotional Specificity — 情绪特异性`, `FBAE — Facial / Body Affect Evidence — 面部/肢体情绪证据`.
- Narrative prompts: `NSC — Narrative Structure Completeness — 叙事完整性`, `TLO — Temporal / Logical Order — 时间合理性`.

Run specified metrics separately:

```bash
uv run python -m eval.run_specified_metrics --run runs/<run_id> --config eval/config.yaml
```

Specified metric results can be exported as a three-column table: `Type | Metric | <Model Name>`.

```bash
uv run python scripts/export_specified_metrics_table.py \
  --model-name <model_name> \
  --specified-metrics-id <specified_metrics_id>
```

Efficiency is reported separately as API cost and end-to-end latency. See `eval/README.md` for the runnable evaluator.

## Baseline Evaluation

This benchmark is designed to compare the following three long-video mashup/editing baselines. All baselines should write standardized outputs to `runs/<run_id>/` following `schemas/run_manifest.schema.json` and `schemas/run_output.schema.json`.

<details>
<summary>Common Baseline Adapter Configuration</summary>

Each baseline adapter should follow the same shared argument conventions wherever possible. This keeps batch experiments reproducible and lets all methods plug into the same validators and evaluator. Each method may keep its own project root, Python environment, and raw intermediate outputs, but the adapter should always export benchmark-standardized artifacts under `runs/<run_id>/`.

| Argument Pattern | Description |
|---|---|
| `--<baseline>-root` | External baseline project root, such as `--cutclaw-root`. The adapter invokes the baseline's original entrypoint from this directory. |
| `--<baseline>-python` | Python executable used by the external baseline, such as `--cutclaw-python`. The recommended default is `<baseline-root>/.venv/bin/python`, with explicit overrides for conda, uv, or other environments. |
| `--task-id` | Run one or more benchmark tasks, for example `task_006`. Task definitions come from `data/tasks/mashup_benchmark.jsonl`. |
| `--all` | Run all 40 benchmark tasks. |
| `--run-id` | Standardized result directory name, written to `runs/<run_id>/`. Prefer names that identify the method and setup, such as `cutclaw_benchmark`. |
| `--results-root` | Standardized result root. Defaults to `runs/` inside this benchmark repo and should stay under the benchmark root for schema validation and evaluation. |
| `--method` | Method name written to the manifest, such as `cutclaw`, `direct_claw`, or `videoagent`. |
| `--method-version` | Method version or experiment label written to the manifest, used to distinguish original runs, ablations, and model configurations. |
| `--overwrite` | Regenerate a task even if its `output.mp4` already exists. By default, the same run can be resumed: successful tasks with an output video are skipped, while failed or incomplete tasks are retried. |
| `--dry-run` | Print the commands and write skipped metadata without calling models or rendering, useful for checking paths and arguments. |

Method-specific options are documented in each baseline section, such as CutClaw's hook dialogue, ending video, crop ratio, and source-video audio volume.

</details>

<details>
<summary>CutClaw</summary>

CutClaw: Agentic Hours-Long Video Editing via Music Synchronization

- Project: [https://github.com/GVCLab/CutClaw](https://github.com/GVCLab/CutClaw)
- Fork: [https://github.com/hit-cxf/CutClaw](https://github.com/hit-cxf/CutClaw)
- Paper: [https://arxiv.org/abs/2603.29664](https://arxiv.org/abs/2603.29664)
- Status: benchmark adapter available.

Use the benchmark-side CutClaw adapter to run selected tasks and write evaluation-ready artifacts to `runs/<run_id>/`:

```bash
python3 scripts/run_cutclaw.py \
  --cutclaw-root /Users/xinfanchen/Project/CutClaw \
  --task-id task_006 \
  --run-id cutclaw_benchmark
```

Run all tasks in batch:

```bash
python3 scripts/run_cutclaw.py \
  --cutclaw-root /Users/xinfanchen/Project/CutClaw \
  --all \
  --run-id cutclaw_benchmark
```

CutClaw-specific arguments:

| Argument | Description |
|---|---|
| `--no-hook-dialogue` | Do not render CutClaw's hook-dialogue intro. |
| `--no-ending` | Do not append CutClaw's ending video. |
| `--crop-ratio` | Optional render crop ratio, such as `16:9`, `9:16`, or `1:1`. |
| `--original-audio-volume` | Mixed-in source-video audio volume. Defaults to `0.0`, meaning BGM only. |
| `--video-type` | Video type passed to CutClaw. The current default is `film`, kept for compatibility with CutClaw's original entrypoint. |

The same `run_id` can be executed multiple times to fill in failed tasks. By default, the adapter reuses successful task outputs; if a task was previously recorded as `failed`, or if `output.mp4` is missing, the same `run_id` will retry that task. Use `--overwrite` only when successful tasks should also be regenerated.

CutClaw's raw intermediate outputs remain in the CutClaw project's `Output/` directory; the benchmark stores only the standardized `runs/<run_id>/` structure used for evaluation. After generation, validate and evaluate the run with:

```bash
python3 scripts/validate_run.py runs/cutclaw_benchmark
python3 -m eval.run_evaluation --run runs/cutclaw_benchmark --config eval/config.yaml
```

</details>

<details>
<summary>DIRECT-Claw</summary>

DIRECT: Video Mashup Creation via Hierarchical Multi-Agent Planning and Intent-Guided Editing

- Project: [https://github.com/AK-DREAM/DIRECT-Claw](https://github.com/AK-DREAM/DIRECT-Claw)
- Fork: [https://github.com/hit-cxf/DIRECT-Claw](https://github.com/hit-cxf/DIRECT-Claw)
- Paper: [https://arxiv.org/abs/2604.04875](https://arxiv.org/abs/2604.04875)
- Status: benchmark adapter pending.

</details>

<details>
<summary>VideoAgent</summary>

VideoAgent: All-in-One Framework for Video Understanding and Editing

- Project: [https://github.com/HKUDS/VideoAgent](https://github.com/HKUDS/VideoAgent)
- Fork: [https://github.com/hit-cxf/VideoAgent](https://github.com/hit-cxf/VideoAgent)
- Paper: [https://arxiv.org/abs/2606.23327](https://arxiv.org/abs/2606.23327)
- Status: benchmark adapter available.

VideoAgent's original entrypoint is an interactive TUI launched by `python main.py`: the system first performs intent analysis, agent graph planning, graph judge/reflection, and then asks the user for missing parameters. For benchmark-scale reproducibility, the adapter fixes the most relevant music-montage sub-pipeline:

```text
VideoPreloader -> RhythmDetector -> RhythmContentGenerator -> VideoSearcher -> VideoEditor
```

Server environment used for reproduction:

| Item | Configuration |
| ---- | ------------- |
| Machine | AutoDL Ubuntu 22.04 |
| GPU | NVIDIA GeForce RTX 4090 24GB |
| VideoAgent environment | `/root/miniconda3/envs/videoagent/bin/python` |
| Benchmark environment | `uv run` from the benchmark root |
| VideoAgent root | `/root/autodl-tmp/VideoAgent` |
| Benchmark root | `/root/autodl-tmp/Mashup-Benchmark` |

Run one task:

```bash
cd /root/autodl-tmp/Mashup-Benchmark
uv run python3 scripts/run_videoagent.py \
  --task-id task_001 \
  --run-id videoagent_benchmark_smoke \
  --overwrite
```

Run all tasks:

```bash
cd /root/autodl-tmp/Mashup-Benchmark
uv run python3 scripts/run_videoagent.py \
  --all \
  --run-id videoagent_benchmark \
  --overwrite
```

Reproduction changes and rationale:

| Change | Rationale |
| ------ | --------- |
| Bypass the interactive TUI and call a fixed tool chain directly | The benchmark requires unattended batch execution; dynamic graph planning adds extra randomness and interactive inputs. |
| Run the worker with the `videoagent` conda Python interpreter | Keeps VideoAgent inside its original dependency environment and prevents the benchmark `uv` environment from contaminating the baseline. |
| Create underscore-free source-video aliases, e.g. `video001.mp4` | VideoAgent's `VideoEditor` parses segment ids with `segment_id.split("_")`; benchmark filenames contain multiple underscores and would break timestamp resolution. |
| Trim the BGM to `target_output_length_sec` by default | VideoAgent generates the timeline from audio rhythm; trimming keeps output duration aligned with the benchmark target. |
| Cache VideoRAG preprocessing results by `video_id` | Long-video indexing is expensive; each video has four tasks, so caching avoids redundant preprocessing. |
| Copy `video_scene.json`, `cut_points.json`, retrieved segments, and logs into `runs/<run_id>/task_outputs/<task_id>/artifacts/` | Stores auditable intermediate artifacts in the standardized run directory for debugging and decision review. |
| Add a `torchvision.transforms.functional_tensor` compatibility shim in the current VideoAgent environment | The environment uses `torch 2.3.1+cu121` and `torchvision 0.18.1+cu121`, while `pytorchvideo` still imports the removed private torchvision module. The shim is the smallest compatibility fix and avoids risky CUDA/PyTorch downgrades. |

The adapter only changes the engineering entrypoint and environment compatibility. It does not modify VideoAgent's core retrieval, rhythm analysis, storyboard generation, or editing algorithms. The goal is to make VideoAgent reproducible as a baseline, not to strengthen or weaken its modeling capability.

</details>

## Scripts

Runnable entrypoints are grouped into data/run validation, baseline adapters, evaluation, and export utilities. Run them from the benchmark root with `uv run` by default; baseline worker interpreters can be overridden through each adapter's arguments.

### Validation Scripts

| Script | Purpose | Example |
| --- | --- | --- |
| `scripts/validate_benchmark.py` | Validate benchmark metadata, task JSONL files, manifests, and schema consistency. | `uv run python scripts/validate_benchmark.py` |
| `scripts/validate_run.py` | Validate one submitted `runs/<run_id>` directory against the required structure and schemas. Failed tasks may omit `output.mp4`, but must record a non-null `error`. | `uv run python scripts/validate_run.py runs/<run_id>` |

### Baseline Adapter Scripts

| Script | Purpose | Example |
| --- | --- | --- |
| `scripts/run_cutclaw.py` | Run CutClaw and export standardized `runs/<run_id>/` outputs. | `uv run python scripts/run_cutclaw.py --cutclaw-root /path/to/CutClaw --task-id task_001 --run-id cutclaw_benchmark` |
| `scripts/run_direct_claw.py` | Run DIRECT-Claw and export standardized `runs/<run_id>/` outputs. | `uv run python scripts/run_direct_claw.py --task-id task_001 --run-id direct_claw_benchmark` |
| `scripts/run_videoagent.py` | Run VideoAgent's fixed music-montage pipeline and export standardized `runs/<run_id>/` outputs. | `uv run python scripts/run_videoagent.py --task-id task_001 --run-id videoagent_benchmark` |

### Evaluation Scripts

| Entrypoint | Purpose | Outputs |
| --- | --- | --- |
| `python -m eval.run_evaluation` | Compute the main score: local automatic `BCS/AEC`, VLM-as-judge `IF/VQ/TC/NC`, optional `OQ`, and `Quality`. | `eval_results/<eval_id>/evaluation_scores.jsonl`, `summary.json` |
| `python -m eval.run_specified_metrics` | Compute specified metrics separately from the main `Quality` score for prompt-type-specific failure analysis. | `eval_results/<specified_metrics_id>/specified_metric_scores.jsonl`, `specified_metric_summary.json` |

Main evaluation example:

```bash
cp eval/config.example.yaml eval/config.yaml
uv run python -m eval.run_evaluation --run runs/<run_id> --config eval/config.yaml
```

Specified metrics example:

```bash
uv run python -m eval.run_specified_metrics --run runs/<run_id> --config eval/config.yaml
```

`eval/config.yaml` configures the VLM model name, API key, base URL, timeout, and metric weights. This file contains local credentials and is ignored by Git; do not commit it.

### Export Scripts

| Script | Purpose | Example |
| --- | --- | --- |
| `scripts/export_evaluation_table.py` | Export main evaluation results to Excel, grouped by task type for `IF/BCS/AEC/VQ/TC/NC/Quality`. | `uv run python scripts/export_evaluation_table.py --model-name CutClaw --eval-id <eval_id>` |
| `scripts/export_specified_metrics_table.py` | Export specified metrics as a three-column table: `Type | Metric | <Model Name>`. | `uv run python scripts/export_specified_metrics_table.py --model-name CutClaw --specified-metrics-id <specified_metrics_id>` |

## License

- Repository-authored code, benchmark metadata, task definitions, prompts, schemas, manifests, documentation, and evaluation annotations are licensed under the Apache License 2.0. See `LICENSE`.
- This repository does not redistribute source videos or audio assets. Users must obtain all media files from lawful sources and comply with the original copyright, license, and terms of use for each asset.
- Generated videos that contain third-party copyrighted media are not covered by this repository's code or data licenses.

See `NOTICE` for third-party media and asset notes.
