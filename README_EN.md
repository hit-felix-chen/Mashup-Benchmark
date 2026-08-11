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
<summary><strong>Videos</strong></summary>

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
<summary><strong>Audios</strong></summary>

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

<details>
<summary><strong>Tasks</strong></summary>

| ID | Type | Video | Audio | Prompt |
| --- | --- | --- | --- | --- |
| `task_001` | event | `video_001` | `audio_001` | 剪出墨西哥对南非这场比赛的关键事件合集，重点包括赛前仪式、快速攻防、射门机会、进球和比分转折。 |
| `task_002` | character | `video_001` | `audio_002` | 围绕南非队球员和主场球迷，剪一个既有人物表情又有现场氛围的主队高光短片。 |
| `task_003` | emotion | `video_001` | `audio_003` | 剪一个有开幕战仪式感的高燃足球短片，突出欢呼、冲刺、对抗和临门一脚的紧张释放。 |
| `task_004` | narrative | `video_001` | `audio_001` | 剪出这场比赛从赛前期待、南非率先点燃主场，到墨西哥追赶回应的完整比赛故事。 |
| `task_005` | event | `video_002` | `audio_001` | 剪出西班牙对佛得角比赛中的门前险情、关键扑救、封堵和反击机会，突出爆冷比赛的关键节点。 |
| `task_006` | character | `video_002` | `audio_002` | 做佛得角门将的个人高光合集，突出反应速度、扑救动作、指挥防线和顶住压力后的情绪。 |
| `task_007` | emotion | `video_002` | `audio_004` | 剪一个弱队爆冷的紧张爽感短片，前半段强调压迫和险情，后半段强调坚持后的情绪释放。 |
| `task_008` | narrative | `video_002` | `audio_003` | 剪出佛得角如何在西班牙持续进攻下稳住防线，并一步步把比赛拖向爆冷结果的叙事线。 |
| `task_009` | event | `video_003` | `audio_001` | 德国7:1大胜库拉索，剪出所有进球、关键助攻和连续压制的精彩合集。 |
| `task_010` | character | `video_003` | `audio_002` | 围绕德国队进攻群像，剪出传跑配合、门前终结、庆祝互动和球员自信状态。 |
| `task_011` | emotion | `video_003` | `audio_003` | 剪一个火力全开、比分不断扩大、节拍密集的进球盛宴短片。 |
| `task_012` | narrative | `video_003` | `audio_001` | 剪出德国队从试探进攻到彻底打开局面、优势不断滚大的比赛走势。 |
| `task_013` | event | `video_004` | `audio_005` | 从地球脉动第一集剪出跨越地球不同区域的自然事件合集，突出季节变化、迁徙、捕猎和生存压力。 |
| `task_014` | character | `video_004` | `audio_006` | 选择片中最有代表性的动物个体或族群，剪一个展示它们觅食、迁徙、求生和亲缘关系的短片。 |
| `task_015` | emotion | `video_004` | `audio_005` | 剪一个宏大、敬畏、充满地球尺度感的自然奇观短片，强调从两极到赤道的生命张力。 |
| `task_016` | narrative | `video_004` | `audio_006` | 剪出一条从环境铺垫、生命挑战、行动展开到结果揭晓的自然故事线。 |
| `task_017` | event | `video_005` | `audio_006` | 从地球脉动第二集剪出高山环境中的关键自然事件，突出雪线、峭壁、风暴、捕猎和动物攀爬。 |
| `task_018` | character | `video_005` | `audio_005` | 围绕高山动物作为主角，剪一个展示孤独、敏捷、耐力和生存策略的短片。 |
| `task_019` | emotion | `video_005` | `audio_004` | 剪一个冷峻、壮阔、危险又诗意的高山自然短片，突出海拔带来的压迫感。 |
| `task_020` | narrative | `video_005` | `audio_006` | 剪出从山脚到雪峰、从宁静风景到生存冲突的垂直空间叙事。 |
| `task_021` | event | `video_006` | `audio_007` | 从地球脉动第三集剪出淡水系统中的关键事件，突出河流、瀑布、湖泊、洪水和动物围绕水源的行动。 |
| `task_022` | character | `video_006` | `audio_006` | 选择一种依赖淡水生态的动物作为主角，剪出它寻找水源、捕食、躲避危险或繁衍的过程。 |
| `task_023` | emotion | `video_006` | `audio_005` | 剪一个流动、清澈、生命感强的自然短片，让画面节奏随着水流和音乐起伏。 |
| `task_024` | narrative | `video_006` | `audio_007` | 剪出水从源头、河道、瀑布到湖泊湿地的旅程，并串联不同生命如何依水而生。 |
| `task_025` | event | `video_007` | `audio_004` | 从教父1中剪出黑帮权力交接的关键事件，包括家族会议、暗杀危机、复仇安排和权力确认。 |
| `task_026` | character | `video_007` | `audio_008` | 围绕迈克尔·柯里昂，剪一个从局外人到家族继承者的角色转变短片。 |
| `task_027` | emotion | `video_007` | `audio_004` | 剪一个阴郁、克制、压迫感强的黑帮电影短片，突出沉默、眼神、谈判和暴力爆发前的张力。 |
| `task_028` | narrative | `video_007` | `audio_008` | 剪出迈克尔如何被家族危机一步步推入权力中心，并完成身份转变的叙事线。 |
| `task_029` | event | `video_008` | `audio_009` | 从千与千寻中剪出进入异世界、签约浴屋、无脸男失控、拯救白龙和最终离开的关键事件。 |
| `task_030` | character | `video_008` | `audio_010` | 围绕千寻，剪一个从害怕迷失到勇敢承担、主动拯救他人的成长短片。 |
| `task_031` | emotion | `video_008` | `audio_006` | 剪一个奇幻、神秘、温暖又略带不安的动画短片，突出异世界的规则感和童话感。 |
| `task_032` | narrative | `video_008` | `audio_008` | 剪出千寻从误入异界、适应浴屋、面对诱惑和危险，到找回名字与自我的完整旅程。 |
| `task_033` | event | `video_009` | `audio_011` | 从爱乐之城中剪出相遇、歌舞、试镜、演出和梦想选择的关键事件合集。 |
| `task_034` | character | `video_009` | `audio_010` | 围绕米娅，剪一个追梦、受挫、坚持试镜并最终绽放的人物短片。 |
| `task_035` | emotion | `video_009` | `audio_011` | 剪一个浪漫、爵士、梦幻又带遗憾感的音乐电影短片，强调色彩、舞蹈和城市夜景。 |
| `task_036` | narrative | `video_009` | `audio_008` | 剪出米娅和塞巴斯蒂安从相遇、相爱、互相鼓励到为了梦想错过彼此的情感线。 |
| `task_037` | event | `video_010` | `audio_009` | 从星际穿越中剪出地球危机、离家升空、穿越虫洞、极端星球任务、对接和父女重逢线索的关键事件。 |
| `task_038` | character | `video_010` | `audio_008` | 围绕库珀，剪一个父亲、宇航员和拯救者三重身份交织的人物短片。 |
| `task_039` | emotion | `video_010` | `audio_009` | 剪一个宇宙尺度宏大、孤独、紧张又充满亲情牵引的科幻短片。 |
| `task_040` | narrative | `video_010` | `audio_008` | 剪出库珀离开女儿、穿越星际、经历时间代价，并通过爱和引力完成回响的叙事线。 |

</details>

## System Format Specification

<details>
<summary><strong>Directory Layout</strong></summary>

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
  eval/                          # Evaluation code
  eval_results/                  # Metric outputs and VLM-as-judge scores
  reports/                       # Aggregated tables, plots, and experiment notes
  docs/                          # Benchmark spec, metric protocol, and data card
```

</details>

<details>
<summary><strong>Expected System Output</strong></summary>

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

`<run_id>` identifies the method and experiment setting, for example `cutclaw_benchmark` or `cutmaster_agentic_task034_v1`; `<task_id>` uses the canonical `task_001` to `task_040` ids. The minimum required files for evaluation are `run_manifest.json`, `run_outputs.jsonl`, and each successful task's `output.mp4` and `run_output.json`. See `docs/run_submission_format.md` for the full submission format.

</details>

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

### General Metrics

The automatic `Quality` score uses six metrics:

```text
Quality = weighted_mean(IF, BCS, AEC, VQ, TC, NC)
```

Weighting policy:

- Local automatic metrics: `BCS = 0.25`, `AEC = 0.25`.
- VLM-as-judge metrics: `IF = 0.125`, `VQ = 0.125`, `TC = 0.125`, `NC = 0.125`.
- If an automatic metric is missing, weights are renormalized over the remaining automatic metrics only.

Raw VLM-as-judge scores for `IF/VQ/TC/NC` use a 1-5 Likert scale. For `Quality`, they are converted to the 0-100 scale with `(score - 1) / 4 * 100`.

Metrics:

- IF: Instruction Following.
- BCS: Beat-Cut Synchronization; PySceneDetect AdaptiveDetector first proposes high-recall cut candidates on the final rendered video, then a VLM classifies each adjacent before/after frame pair and only confirmed cuts are compared with beats. The edit timeline is not read.
- AEC: Audio-Visual Energy Correspondence.
- VQ: Visual Quality.
- TC: Transition Continuity.
- NC: Narrative Coherence.
- OQ: Overall Quality, a human rating stored and analyzed by a separate human-evaluation workflow; it is never written to automatic evaluation results or included in `Quality`.


### Specified Metrics

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

## Our Method and Baseline Evaluation

This benchmark evaluates our CutMaster method and compares it against five long-video mashup/editing baselines. All methods should write standardized outputs to `runs/<run_id>/` following `schemas/run_manifest.schema.json` and `schemas/run_output.schema.json`.

Reproduction environment overview:

| Environment | Hardware / OS | Method / Baselines | Notes |
| --- | --- | --- | --- |
| Mac mini M4 | macOS 26.5.1, Build 25F80, arm64; Mac mini `Mac16,10`; Apple M4, 10-core CPU (4 performance + 6 efficiency cores); 16 GB memory | CutMaster (our method), CutClaw, NarratoAI, OpenMontage | Local Mac mini reproduction environment. CutMaster is the method currently being optimized; OpenMontage uses Claude Code as the agent and calls Qwen3.7-Plus through an Anthropic-compatible endpoint. |
| AutoDL server | Ubuntu 22.04, NVIDIA GeForce RTX 4090 24GB | VideoAgent, DIRECT-Claw | DIRECT-Claw and VideoAgent use the same server environment and model/API configuration; each baseline still uses its own conda/Python environment. |

<details>
<summary><strong>Common Baseline Adapter Configuration</strong></summary>

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

Method-specific options are documented in each method section, such as CutMaster's config file and optional subtitle input, and CutClaw's hook dialogue, ending video, crop ratio, and source-video audio volume.

</details>


<details>
<summary><strong>CutMaster (Our Method)</strong></summary>

CutMaster edits long-form video through its MASTER Editing Team. Material Analyst builds reusable Shot, Segment, dialogue, and story Material Memory; the ASTER team—Arrangement Architect, Story Editor, Timeline Scout, Edit Composer, and Revision Editor—then arranges pacing, anchors the story, builds a validated Candidate Space, performs lazy VLM transition scoring and Beam Search composition, and completes candidate-constrained revision. Source windows are finally optimized around real visual cuts and assembled as hard cuts with FFmpeg.

The benchmark adapter, `scripts/run_cutmaster.py`, uses an isolated worker to map each benchmark task to a `WorkflowRequest`, directly calls the public `Orchestrator(config).run(request)` entry point, and exports videos, scripts, logs, and run metadata into the standard `runs/<run_id>/` structure.

Setup:

```bash
cd /Users/xinfanchen/Project/CutMaster
uv sync
cp .env.example .env
# Set DASHSCOPE_API_KEY in .env; edit workflow parameters directly in config.toml.

cd /Users/xinfanchen/Project/Mashup-Benchmark
uv sync
```

Python 3.12 and working `ffmpeg` and `ffprobe` executables on `PATH` are required. LLM and VLM model names, endpoints, API keys, thinking switches, and concurrency limits can be configured independently. The adapter reads `<cutmaster-root>/config.toml` by default.

Run the current development and regression task, `task_034`:

```bash
uv run python scripts/run_cutmaster.py \
  --cutmaster-root /Users/xinfanchen/Project/CutMaster \
  --cutmaster-python /Users/xinfanchen/Project/CutMaster/.venv/bin/python \
  --cutmaster-config /Users/xinfanchen/Project/CutMaster/config.toml \
  --task-id task_034 \
  --run-id cutmaster_agentic_task034_v1 \
  --method-version master-team-v1 \
  --overwrite
```

Run the command from the Mashup-Benchmark repository root. It makes real calls to the configured ASR, LLM, and VLM services. Use `uv run python scripts/run_cutmaster.py --list-tasks` to inspect tasks. `--task-id` also accepts multiple IDs.

Run all tasks in batch:

```bash
uv run python scripts/run_cutmaster.py \
  --cutmaster-root /Users/xinfanchen/Project/CutMaster \
  --cutmaster-python /Users/xinfanchen/Project/CutMaster/.venv/bin/python \
  --cutmaster-config /Users/xinfanchen/Project/CutMaster/config.toml \
  --all \
  --run-id cutmaster_agentic_full \
  --method-version master-team-v1
```

CutMaster-specific arguments and recommendations:

| Argument | Description |
| --- | --- |
| `--cutmaster-root` | CutMaster project root. |
| `--cutmaster-python` | Python executable used by CutMaster; explicitly pointing to `.venv/bin/python` is recommended. |
| `--cutmaster-config` | CutMaster TOML config; defaults to `<cutmaster-root>/config.toml`. |
| `--subtitle-path` | Explicitly reuse an SRT for a single task; if omitted, Fun-ASR is called. |
| `--method-version` | CutMaster experiment label written to the manifest; defaults to `master-team-v1`. |
| `--dialogue-audio` | Include selected original-dialogue anchors in benchmark output. Disabled by default, so a full run directly produces the standard AAC BGM-only evaluation version. |
| `--overwrite` | Regenerate task outputs without deleting CutMaster's source-analysis cache. Use for development and failed reruns. |

Without `--overwrite`, a successful task with an existing `output.mp4` is skipped; failed or incomplete tasks are executed again. With `--overwrite`, task-level ASTER coordination and rendering are rebuilt, but the `.cutmaster/media/` Material Library under the CutMaster project is preserved. Video or music whose Material Type, exact name, and bound content fingerprint all match idempotently reuses the managed source and completed analysis; the same name with different bytes raises a collision instead of receiving an automatic suffix. An interrupted video analysis also resumes its existing checkpoints when the subtitle and analysis specification are unchanged.

Main output locations:

```text
runs/<run_id>/task_outputs/<task_id>/output.mp4
runs/<run_id>/task_outputs/<task_id>/run_output.json
runs/<run_id>/task_outputs/<task_id>/logs/backend.log
runs/<run_id>/task_outputs/<task_id>/artifacts/cutmaster/
/Users/xinfanchen/Project/CutMaster/.cutmaster/media/
```

`artifacts/cutmaster/` stores the three stage outputs under `analyser/`, `planners/`, and `renderer/`, including Material Memory indexes, `planners_result.json`, `script_raw.json`, `render_plan.json`, diagnostics, and `renderer/output.mp4`. Video and music analysis is cached per Material rather than per benchmark task. Terminal logs use level colors, while `logs/backend.log` and `artifacts/cutmaster/cutmaster.log` remain ANSI-free plain text.

After generation, validate and evaluate with:

```bash
uv run python scripts/validate_run.py runs/cutmaster_agentic_task034_v1
uv run python -m eval.run_evaluation \
  --run runs/cutmaster_agentic_task034_v1 \
  --config eval/config.yaml
```

</details>

<details>
<summary><strong>CutClaw</strong></summary>

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
<summary><strong>DIRECT-Claw</strong></summary>

DIRECT: Video Mashup Creation via Hierarchical Multi-Agent Planning and Intent-Guided Editing

- Project: [https://github.com/AK-DREAM/DIRECT-Claw](https://github.com/AK-DREAM/DIRECT-Claw)
- Fork: [https://github.com/hit-cxf/DIRECT-Claw](https://github.com/hit-cxf/DIRECT-Claw)
- Paper: [https://arxiv.org/abs/2604.04875](https://arxiv.org/abs/2604.04875)
- Status: benchmark adapter available; server run in progress.

Server environment used for reproduction:

| Item | Configuration |
| ---- | ------------- |
| Machine | AutoDL Ubuntu 22.04 |
| GPU | NVIDIA GeForce RTX 4090 24GB |
| DIRECT-Claw environment | `/root/miniconda3/envs/direct/bin/python` |
| Benchmark environment | Python/uv from the benchmark root |
| DIRECT-Claw root | `/root/autodl-tmp/DIRECT-Claw` |
| Benchmark root | `/root/autodl-tmp/Mashup-Benchmark` |
| Model/API configuration | Same server environment and configuration as the VideoAgent reproduction run |

</details>

<details>
<summary><strong>NarratoAI</strong></summary>

NarratoAI: all-in-one AI-powered film commentary and automated video editing tool.

- Project: [https://github.com/linyqh/NarratoAI](https://github.com/linyqh/NarratoAI)
- Status: benchmark adapter available.

NarratoAI's native entrypoint is a Streamlit WebUI. For Mashup-Benchmark, the adapter fixes a reproducible batch pipeline:

```text
ASR to SRT -> short-mix script generation -> force OST=1 -> render with benchmark-specified BGM
```

`OST=1` means preserving source-video audio and disabling TTS generation. The adapter passes each task's `audio.local_path` as the BGM file for NarratoAI's final render stage, rather than letting NarratoAI randomly choose music.

Run one task:

```bash
uv run python scripts/run_narratoai.py \
  --narratoai-root /Users/xinfanchen/Project/NarratoAI \
  --task-id task_001 \
  --run-id narratoai_benchmark
```

Run all tasks:

```bash
uv run python scripts/run_narratoai.py \
  --narratoai-root /Users/xinfanchen/Project/NarratoAI \
  --all \
  --run-id narratoai_benchmark
```

NarratoAI-specific arguments:

| Argument | Description |
| --- | --- |
| `--asr-backend` | Subtitle transcription backend: `bailian`, `local`, or `firered`. Defaults to `bailian`. |
| `--no-reuse-asr` | Regenerate subtitles even when `artifacts/source.srt` already exists. Existing SRT files are reused by default. |
| `--custom-clips` | Number of candidate clips requested from NarratoAI. Defaults to `target_output_length_sec / target_shot_length_sec`. |
| `--max-clip-duration-sec` | Maximum duration of each adapted clip. Defaults to the task's `target_shot_length_sec`. |
| `--bgm-volume` | Mixed-in volume for the benchmark-specified BGM. |
| `--original-volume` | Source-video audio volume passed to NarratoAI. NarratoAI tends to preserve source audio for `OST=1` clips. |
| `--subtitle-enabled` | Burn subtitles into the final video. Disabled by default for benchmark runs to avoid affecting visual evaluation. |

Per-task intermediate artifacts are stored under:

```text
runs/<run_id>/task_outputs/<task_id>/artifacts/
  source.srt
  narrato_script_raw.json
  narrato_script_adapted.json
  narratoai_payload.json
  narrato_worker_result.json
```

This adapter does not modify NarratoAI's core code. It invokes NarratoAI's ASR, short-mix script generation, and video rendering services through an external worker, then normalizes the output into the benchmark-standard `runs/<run_id>/` structure.

</details>

<details>
<summary><strong>VideoAgent</strong></summary>

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
uv run python3 scripts/run_videoagent.py \
  --task-id task_001 \
  --run-id videoagent_benchmark_smoke \
  --overwrite
```

Run all tasks:

```bash
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

<details>
<summary><strong>OpenMontage</strong></summary>

OpenMontage: agent-driven video production harness.

- Status: benchmark adapter available.
- Adaptation: Claude Code acts as the coding agent and follows OpenMontage's `AGENT_GUIDE.md`, pipeline manifests, and tool protocol. The local Claude Code setup can route to Qwen3.7-Plus through an Anthropic-compatible endpoint.

OpenMontage is not a traditional one-command pipeline; it is a harness where the agent is the orchestrator. For reproducible benchmark runs, the adapter fixes the following constrained path:

```text
Claude Code/Qwen agent -> OpenMontage hybrid/source-footage-led -> FFmpeg compose
```

For each task, the adapter creates an isolated OpenMontage project and writes the benchmark task, source video, specified BGM, and agent prompt. The agent must use only the benchmark-provided video and audio, with no downloaded assets, generated assets, TTS, or narration. The final output is rendered through OpenMontage's `video_compose` / FFmpeg path as `renders/final.mp4`, then copied into the benchmark-standard `runs/<run_id>/task_outputs/<task_id>/output.mp4`.

Generate a dry-run project and prompt first:

```bash
uv run python scripts/run_openmontage.py \
  --task-id task_001 \
  --run-id openmontage_dryrun \
  --dry-run \
  --overwrite-project
```

Run one task:

```bash
uv run python scripts/run_openmontage.py \
  --task-id task_001 \
  --run-id openmontage_benchmark \
  --bypass-permissions \
  --overwrite-project
```

Run all tasks:

```bash
uv run python scripts/run_openmontage.py \
  --all \
  --run-id openmontage_benchmark \
  --bypass-permissions
```

OpenMontage-specific arguments:

| Argument | Description |
| --- | --- |
| `--openmontage-root` | OpenMontage project root. Defaults to an `OpenMontage` directory next to this benchmark repo. |
| `--agent-cmd` | Claude Code executable path. Defaults to `/Users/xinfanchen/.local/bin/claude`. |
| `--agent-model` | Optional model name passed to Claude Code. Omit it to use the current Claude Code configuration. |
| `--agent-output-format` | Claude Code output format. Defaults to `stream-json` for complete agent logs. |
| `--permission-mode` | Claude Code permission mode. Defaults to `acceptEdits`; combine with `--bypass-permissions` if non-interactive permissions still block execution. |
| `--bypass-permissions` | Pass `--dangerously-skip-permissions` to Claude Code; recommended only in a trusted local benchmark environment. |
| `--max-budget-usd` | Optional maximum API budget per task for Claude Code. |
| `--timeout-sec` | Optional timeout for one task's agent run. |
| `--overwrite-project` | Delete and recreate the OpenMontage project for the selected task. |
| `--max-cuts` | Maximum number of cuts communicated to the agent. Defaults to `24`. |
| `--bgm-volume` | Target BGM volume hint. Defaults to `0.75`. |
| `--original-volume` | Source-audio mix-in hint. Defaults to `0.15`. |

Per-task standardized artifacts are stored under:

```text
runs/<run_id>/task_outputs/<task_id>/artifacts/
  benchmark_task.json
  openmontage_agent_prompt.md
  brief.json                         # if written by the agent
  edit_decisions.json                # if written by the agent
  render_report.json                 # if written by the agent
  openmontage_agent_result.json      # if written by the agent
```

This adapter does not modify OpenMontage's core code. It creates the benchmark project, generates a non-interactive agent prompt, invokes Claude Code, and normalizes OpenMontage outputs into the benchmark-standard `runs/<run_id>/` structure.

</details>

## Scripts

Runnable entrypoints are grouped into validation, baseline adapters, evaluation, and export utilities. Run them from the benchmark root with `uv run` by default; baseline worker interpreters can be overridden through each adapter's arguments.

<details>
<summary><strong>Validation Scripts</strong></summary>

#### `scripts/validate_benchmark.py`

Validate benchmark metadata, task JSONL files, manifests, and schema consistency.

```bash
uv run python scripts/validate_benchmark.py
```

#### `scripts/validate_run.py`

Validate one submitted `runs/<run_id>` directory against the required structure and schemas. Failed tasks may omit `output.mp4`, but must record a non-null `error`.

```bash
uv run python scripts/validate_run.py runs/<run_id>
```

</details>

<details>
<summary><strong>Baseline Adapter Scripts</strong></summary>

#### `scripts/run_cutmaster.py`

Run CutMaster (our method) and export standardized `runs/<run_id>/` outputs.

```bash
uv run python scripts/run_cutmaster.py \
  --cutmaster-root /path/to/CutMaster \
  --cutmaster-python /path/to/CutMaster/.venv/bin/python \
  --cutmaster-config /path/to/CutMaster/config.toml \
  --task-id task_034 \
  --run-id cutmaster_agentic_task034_v1 \
  --method-version master-team-v1 \
  --overwrite
```

#### `scripts/run_cutclaw.py`

Run CutClaw and export standardized `runs/<run_id>/` outputs.

```bash
uv run python scripts/run_cutclaw.py --cutclaw-root /path/to/CutClaw --task-id task_001 --run-id cutclaw_benchmark
```

#### `scripts/run_direct_claw.py`

Run DIRECT-Claw and export standardized `runs/<run_id>/` outputs.

```bash
uv run python scripts/run_direct_claw.py --task-id task_001 --run-id direct_claw_benchmark
```

#### `scripts/run_narratoai.py`

Run NarratoAI with the `ASR -> short mix -> OST=1 -> benchmark BGM render` adaptation pipeline and export standardized outputs.

```bash
uv run python scripts/run_narratoai.py --narratoai-root /path/to/NarratoAI --task-id task_001 --run-id narratoai_benchmark
```

#### `scripts/run_videoagent.py`

Run VideoAgent's fixed music-montage pipeline and export standardized `runs/<run_id>/` outputs.

```bash
uv run python scripts/run_videoagent.py --task-id task_001 --run-id videoagent_benchmark
```

#### `scripts/run_openmontage.py`

Run the OpenMontage agent harness through Claude Code/Qwen and export standardized outputs.

```bash
uv run python scripts/run_openmontage.py --task-id task_001 --run-id openmontage_benchmark --bypass-permissions --overwrite-project
```

</details>

<details>
<summary><strong>Evaluation Scripts</strong></summary>

#### `python -m eval.run_evaluation`

Compute the main score: local automatic `BCS/AEC`, VLM-as-judge `IF/VQ/TC/NC`, and the automatic `Quality` derived from those six metrics. Outputs are written to `eval_results/<eval_id>/evaluation_scores.jsonl` and `summary.json`. Human ratings are stored and analyzed separately.

```bash
uv run python -m eval.run_evaluation --run runs/<run_id> --config eval/config.yaml
```

The default concurrency is 10 and can be changed with `--concurrency <N>`; output files are still written in the original task order.

Partial reevaluation can reuse an existing result. `--task-ids` selects tasks, `--metrics` selects metrics to recompute, and all unselected tasks and metrics are copied from `--reuse-eval-id`. `Quality` is always recomputed from the merged scores:

```bash
uv run python -m eval.run_evaluation \
  --run runs/cutclaw_benchmark \
  --config eval/config.yaml \
  --reuse-eval-id <existing_eval_id> \
  --task-id task_022 \
  --metrics BCS
```

`--task-id` (alias `--task-ids`) and `--metrics` accept comma-separated or repeated values. Supported metrics are `BCS/AEC/IF/VQ/TC/NC`. Selecting any VLM metric still performs one joint VLM request, but only the requested fields are replaced.

If a generated video triggers server-side VLM content inspection, the evaluator skips that task's VLM-as-judge metrics and continues with the remaining tasks. The task still keeps local automatic metrics, `Quality` is renormalized over available metrics, and the skip reason is recorded under `judge.status = skipped` and the `vlm_judge` field in `summary.json`.

#### `python -m eval.run_specified_metrics`

Compute specified metrics separately from the main `Quality` score for prompt-type-specific failure analysis. Outputs are written to `eval_results/<specified_metrics_id>/specified_metric_scores.jsonl` and `specified_metric_summary.json`.

```bash
uv run python -m eval.run_specified_metrics --run runs/<run_id> --config eval/config.yaml
```

The default concurrency is 10 and can be changed with `--concurrency <N>`; output files are still written in the original task order.

Specified metrics also skip tasks that trigger VLM content inspection and record the reason under `judge.status = skipped`; that task is excluded from specified-metric averages.

`eval/config.yaml` configures the VLM model name, API key, base URL, timeout, and metric weights. This file contains local credentials and is ignored by Git; do not commit it.

</details>

<details>
<summary><strong>Export Scripts</strong></summary>

#### `scripts/export_evaluation_table.py`

Export main evaluation results to Excel, grouped by task type for `IF/BCS/AEC/VQ/TC/NC/Quality`.

```bash
uv run python scripts/export_evaluation_table.py --model-name CutClaw --eval-id <eval_id>
```

#### `scripts/export_specified_metrics_table.py`

Export specified metrics to Excel, grouped by prompt type and metric.

```bash
uv run python scripts/export_specified_metrics_table.py --model-name CutClaw --specified-metrics-id <specified_metrics_id>
```

#### `scripts/export_evaluation_detail_table.py`

Export task-level details by merging main scores and specified metrics; specified metrics outside the task's prompt type are left blank.

```bash
uv run python scripts/export_evaluation_detail_table.py --model-name CutClaw --eval-id <eval_id> --specified-metrics-id <specified_metrics_id>
```

</details>

## License

- Repository-authored code, benchmark metadata, task definitions, prompts, schemas, manifests, documentation, and evaluation annotations are licensed under the Apache License 2.0. See `LICENSE`.
- This repository does not redistribute source videos or audio assets. Users must obtain all media files from lawful sources and comply with the original copyright, license, and terms of use for each asset.
- Generated videos that contain third-party copyrighted media are not covered by this repository's code or data licenses.

See `NOTICE` for third-party media and asset notes.
