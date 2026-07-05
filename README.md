# Mashup-Benchmark

[English](README_EN.md)

Mashup-Benchmark 是一个面向长视频自动剪辑的 benchmark，用于评估短视频混剪、精彩集锦和音乐驱动剪辑系统的生成质量与效率。

![Mashup-Benchmark Overview](docs/assets/mashup_benchmark_overview.png)

## 数据集

- 10 个小时级长视频源：3 场体育赛事、3 集纪录片、4 部电影。
- 40 个视频-提示词任务：每个长视频对应 4 类任务，分别是事件型、人物型、情绪型和叙事型。
- 11 首 Mixkit BGM，根据任务情绪和风格进行分配。
- 默认目标成片时长：60 秒。
- 默认目标 shot 时长：4 秒。

标准任务文件是 `data/tasks/mashup_benchmark.jsonl`，其中每一行对应一个视频-提示词-音频任务。媒体文件按 `data/videos/<video_id>/...` 和 `data/audios/<audio_id>/...` 组织。任务 id 命名为 `task_<index>`，范围为 `task_001` 到 `task_040`。

<details>
<summary>视频</summary>

| 编号          | 类型     | 名称                                                                             |     时长 | 分辨率    |
| ------------- | -------- | -------------------------------------------------------------------------------- | -------: | --------- |
| `video_001` | 体育赛事 | 美加墨世界杯A组第1轮：墨西哥VS南非FIFA World Cup Group A: Mexico vs South Africa | 01:38:53 | 480x270   |
| `video_002` | 体育赛事 | 美加墨世界杯H组第1轮：西班牙VS佛得角FIFA World Cup Group H: Spain vs Cape Verde  | 02:03:58 | 1920x1080 |
| `video_003` | 体育赛事 | 美加墨世界杯E组第1轮：德国VS库拉索FIFA World Cup Group E: Germany vs Curacao     | 02:09:00 | 1920x1080 |
| `video_004` | 纪录片   | 地球脉动 第一季第一集：From Pole to PolePlanet Earth S01E01: From Pole to Pole   |    49:02 | 1920x1080 |
| `video_005` | 纪录片   | 地球脉动 第一季第二集：MountainsPlanet Earth S01E02: Mountains                   |    47:52 | 1920x1080 |
| `video_006` | 纪录片   | 地球脉动 第一季第三集：Fresh WaterPlanet Earth S01E03: Fresh Water               |    49:11 | 1920x1080 |
| `video_007` | 电影     | 教父1The Godfather (1972)                                                        | 02:57:09 | 1920x1080 |
| `video_008` | 电影     | 千与千寻Spirited Away (2001)                                                     | 02:04:32 | 1920x1038 |
| `video_009` | 电影     | 爱乐之城La La Land (2016)                                                        | 02:07:48 | 1920x754  |
| `video_010` | 电影     | 星际穿越Interstellar (2014)                                                      | 02:49:04 | 1920x1080 |

</details>

<details>
<summary>音频</summary>

| 编号          | 曲名                 | 作者                     |  时长 | 风格标签                                      |
| ------------- | -------------------- | ------------------------ | ----: | --------------------------------------------- |
| `audio_001` | Sports Highlights    | Ahjay Stelino            | 01:36 | sports, rock, aggressive, propulsive          |
| `audio_002` | Dirty Thinkin'       | Michael Ramir C.         | 01:29 | funk, energetic, groove, playful              |
| `audio_003` | Techno Fest Vibes    | Alejandro Magana (A. M.) | 01:09 | edm, high_energy, driving, celebratory        |
| `audio_004` | Fright Night         | Michael Ramir C.         | 01:41 | cinematic, tension, dark, suspense            |
| `audio_005` | Sun and His Daughter | Eugenio Mininni          | 02:48 | nature, poetic, world, expansive              |
| `audio_006` | Discover             | Eugenio Mininni          | 02:24 | documentary, hopeful, orchestral, wonder      |
| `audio_007` | Relax Beat           | Arulo                    | 01:48 | ambient, calm, observational, soft            |
| `audio_008` | Silent Descent       | Eugenio Mininni          | 02:40 | film_score, melancholic, reflective, dramatic |
| `audio_009` | Epical Drums 01      | Grigoriy Nuzhny          | 01:46 | cinematic, drums, epic, action                |
| `audio_010` | Romantic Getaway     | Ahjay Stelino            | 01:44 | romantic, warm, emotional, classical          |
| `audio_011` | Romantic Vacation    | Ahjay Stelino            | 01:52 | jazz, romantic, lounge, stylish               |

</details>

<details>
<summary>任务</summary>

| 编号 | 类型 | 视频 | 音频 | Prompt |
| --- | --- | --- | --- | --- |
| `task_001` | 事件型 | `video_001` | `audio_001` | 剪出墨西哥对南非这场比赛的关键事件合集，重点包括赛前仪式、快速攻防、射门机会、进球和比分转折。 |
| `task_002` | 人物型 | `video_001` | `audio_002` | 围绕南非队球员和主场球迷，剪一个既有人物表情又有现场氛围的主队高光短片。 |
| `task_003` | 情绪型 | `video_001` | `audio_003` | 剪一个有开幕战仪式感的高燃足球短片，突出欢呼、冲刺、对抗和临门一脚的紧张释放。 |
| `task_004` | 叙事型 | `video_001` | `audio_001` | 剪出这场比赛从赛前期待、南非率先点燃主场，到墨西哥追赶回应的完整比赛故事。 |
| `task_005` | 事件型 | `video_002` | `audio_001` | 剪出西班牙对佛得角比赛中的门前险情、关键扑救、封堵和反击机会，突出爆冷比赛的关键节点。 |
| `task_006` | 人物型 | `video_002` | `audio_002` | 做佛得角门将的个人高光合集，突出反应速度、扑救动作、指挥防线和顶住压力后的情绪。 |
| `task_007` | 情绪型 | `video_002` | `audio_004` | 剪一个弱队爆冷的紧张爽感短片，前半段强调压迫和险情，后半段强调坚持后的情绪释放。 |
| `task_008` | 叙事型 | `video_002` | `audio_003` | 剪出佛得角如何在西班牙持续进攻下稳住防线，并一步步把比赛拖向爆冷结果的叙事线。 |
| `task_009` | 事件型 | `video_003` | `audio_001` | 德国7:1大胜库拉索，剪出所有进球、关键助攻和连续压制的精彩合集。 |
| `task_010` | 人物型 | `video_003` | `audio_002` | 围绕德国队进攻群像，剪出传跑配合、门前终结、庆祝互动和球员自信状态。 |
| `task_011` | 情绪型 | `video_003` | `audio_003` | 剪一个火力全开、比分不断扩大、节拍密集的进球盛宴短片。 |
| `task_012` | 叙事型 | `video_003` | `audio_001` | 剪出德国队从试探进攻到彻底打开局面、优势不断滚大的比赛走势。 |
| `task_013` | 事件型 | `video_004` | `audio_005` | 从地球脉动第一集剪出跨越地球不同区域的自然事件合集，突出季节变化、迁徙、捕猎和生存压力。 |
| `task_014` | 人物型 | `video_004` | `audio_006` | 选择片中最有代表性的动物个体或族群，剪一个展示它们觅食、迁徙、求生和亲缘关系的短片。 |
| `task_015` | 情绪型 | `video_004` | `audio_005` | 剪一个宏大、敬畏、充满地球尺度感的自然奇观短片，强调从两极到赤道的生命张力。 |
| `task_016` | 叙事型 | `video_004` | `audio_006` | 剪出一条从环境铺垫、生命挑战、行动展开到结果揭晓的自然故事线。 |
| `task_017` | 事件型 | `video_005` | `audio_006` | 从地球脉动第二集剪出高山环境中的关键自然事件，突出雪线、峭壁、风暴、捕猎和动物攀爬。 |
| `task_018` | 人物型 | `video_005` | `audio_005` | 围绕高山动物作为主角，剪一个展示孤独、敏捷、耐力和生存策略的短片。 |
| `task_019` | 情绪型 | `video_005` | `audio_004` | 剪一个冷峻、壮阔、危险又诗意的高山自然短片，突出海拔带来的压迫感。 |
| `task_020` | 叙事型 | `video_005` | `audio_006` | 剪出从山脚到雪峰、从宁静风景到生存冲突的垂直空间叙事。 |
| `task_021` | 事件型 | `video_006` | `audio_007` | 从地球脉动第三集剪出淡水系统中的关键事件，突出河流、瀑布、湖泊、洪水和动物围绕水源的行动。 |
| `task_022` | 人物型 | `video_006` | `audio_006` | 选择一种依赖淡水生态的动物作为主角，剪出它寻找水源、捕食、躲避危险或繁衍的过程。 |
| `task_023` | 情绪型 | `video_006` | `audio_005` | 剪一个流动、清澈、生命感强的自然短片，让画面节奏随着水流和音乐起伏。 |
| `task_024` | 叙事型 | `video_006` | `audio_007` | 剪出水从源头、河道、瀑布到湖泊湿地的旅程，并串联不同生命如何依水而生。 |
| `task_025` | 事件型 | `video_007` | `audio_004` | 从教父1中剪出黑帮权力交接的关键事件，包括家族会议、暗杀危机、复仇安排和权力确认。 |
| `task_026` | 人物型 | `video_007` | `audio_008` | 围绕迈克尔·柯里昂，剪一个从局外人到家族继承者的角色转变短片。 |
| `task_027` | 情绪型 | `video_007` | `audio_004` | 剪一个阴郁、克制、压迫感强的黑帮电影短片，突出沉默、眼神、谈判和暴力爆发前的张力。 |
| `task_028` | 叙事型 | `video_007` | `audio_008` | 剪出迈克尔如何被家族危机一步步推入权力中心，并完成身份转变的叙事线。 |
| `task_029` | 事件型 | `video_008` | `audio_009` | 从千与千寻中剪出进入异世界、签约浴屋、无脸男失控、拯救白龙和最终离开的关键事件。 |
| `task_030` | 人物型 | `video_008` | `audio_010` | 围绕千寻，剪一个从害怕迷失到勇敢承担、主动拯救他人的成长短片。 |
| `task_031` | 情绪型 | `video_008` | `audio_006` | 剪一个奇幻、神秘、温暖又略带不安的动画短片，突出异世界的规则感和童话感。 |
| `task_032` | 叙事型 | `video_008` | `audio_008` | 剪出千寻从误入异界、适应浴屋、面对诱惑和危险，到找回名字与自我的完整旅程。 |
| `task_033` | 事件型 | `video_009` | `audio_011` | 从爱乐之城中剪出相遇、歌舞、试镜、演出和梦想选择的关键事件合集。 |
| `task_034` | 人物型 | `video_009` | `audio_010` | 围绕米娅，剪一个追梦、受挫、坚持试镜并最终绽放的人物短片。 |
| `task_035` | 情绪型 | `video_009` | `audio_011` | 剪一个浪漫、爵士、梦幻又带遗憾感的音乐电影短片，强调色彩、舞蹈和城市夜景。 |
| `task_036` | 叙事型 | `video_009` | `audio_008` | 剪出米娅和塞巴斯蒂安从相遇、相爱、互相鼓励到为了梦想错过彼此的情感线。 |
| `task_037` | 事件型 | `video_010` | `audio_009` | 从星际穿越中剪出地球危机、离家升空、穿越虫洞、极端星球任务、对接和父女重逢线索的关键事件。 |
| `task_038` | 人物型 | `video_010` | `audio_008` | 围绕库珀，剪一个父亲、宇航员和拯救者三重身份交织的人物短片。 |
| `task_039` | 情绪型 | `video_010` | `audio_009` | 剪一个宇宙尺度宏大、孤独、紧张又充满亲情牵引的科幻短片。 |
| `task_040` | 叙事型 | `video_010` | `audio_008` | 剪出库珀离开女儿、穿越星际、经历时间代价，并通过爱和引力完成回响的叙事线。 |

</details>

## 系统格式规范

<details>
<summary>目录结构</summary>

```text
Mashup-Benchmark/
  data/
    tasks/mashup_benchmark.jsonl # 标准 40 任务 JSONL
    videos/<video_id>/             # 长视频源文件目录，Git 忽略
    audios/<audio_id>/             # BGM 音频文件目录，Git 忽略
  manifests/                     # 视频、音频、任务和统计摘要索引
  schemas/                       # task/run/evaluation 记录的 JSON Schema
  scripts/                       # 校验脚本和工具脚本
  runs/                          # 待测系统输出、run_output.json 和 run_manifest.json
  outputs/                       # 非正式提交 run 的临时导出结果
  eval/                          # 评测代码
  eval_results/                  # 指标结果和 VLM-as-judge 打分结果
  reports/                       # 汇总表格、图表和实验记录
  docs/                          # benchmark 规范、指标协议和数据说明
```

</details>

<details>
<summary>系统输出格式</summary>

一个 `run` 表示某个 baseline 或消融配置在一个或多个 benchmark task 上的完整输出。每个任务需要生成一个完整的短视频成片，并按下面的结构保存：

```text
runs/<run_id>/
  run_manifest.json             # 整次运行的全局元数据，符合 schemas/run_manifest.schema.json
  run_outputs.jsonl             # 每个 task 的 run_output.json 记录汇总，每行一个 JSON
  task_outputs/
    <task_id>/
      output.mp4                # 该 task 的最终成片，评测器直接读取这个视频
      run_output.json           # 该 task 的元数据，符合 schemas/run_output.schema.json
      logs/
        backend.log             # 可选，原始 pipeline 日志
        render.log              # 可选，渲染日志
      artifacts/
        benchmark_task.json     # 可选，该 task 的输入定义快照
        shot_plan.json          # 可选，方法内部生成的剪辑计划
        shot_point.json         # 可选，方法内部生成的剪辑点或时间线
```

其中 `<run_id>` 用于标识方法和实验设置，例如 `cutclaw_benchmark` 或 `cutmaster_embedding_v4_full`；`<task_id>` 使用 `task_001` 到 `task_040` 的规范编号。评测时最小必需文件是 `run_manifest.json`、`run_outputs.jsonl`，以及每个成功 task 下的 `output.mp4` 和 `run_output.json`。详细提交格式见 `docs/run_submission_format.md`。

</details>

## 环境配置

本 benchmark 使用 `uv` 管理自己的 Python 环境，避免依赖任何 baseline 项目的虚拟环境。首次使用时在 benchmark 根目录运行：

```bash
uv sync
```

之后推荐通过 `uv run` 执行校验、adapter 和评测脚本：

```bash
uv run python scripts/validate_benchmark.py
uv run python scripts/validate_run.py runs/<run_id>
uv run python -m eval.run_evaluation --run runs/<run_id> --config eval/config.yaml
```

媒体解码和自动指标计算依赖系统命令 `ffmpeg` 与 `ffprobe`，它们不由 Python 环境安装；请确保二者在 `PATH` 中可用。VLM 密钥等本地配置写入 `eval/config.yaml`，该文件已被 Git 忽略。

## 评测维度

### 通用指标

完整质量分包含 7 个指标：

```text
Quality = weighted_mean(IF, BCS, AEC, VQ, TC, NC, OQ)
```

权重规则：

- 本地自动指标：`BCS = 0.20`，`AEC = 0.20`。
- VLM-as-judge 指标：`IF = 0.10`，`VQ = 0.10`，`TC = 0.10`，`NC = 0.10`。
- 人类评估指标：`OQ = 0.20`。
- 如果没有人类 `OQ` 分数，则对可用的 6 个指标自动归一化：`BCS = 0.25`，`AEC = 0.25`，`IF/VQ/TC/NC = 0.125`。

VLM-as-judge 的 `IF/VQ/TC/NC` 和人类评估的 `OQ` 原始分数采用 1-5 Likert 量表；计算 `Quality` 时会按 `(score - 1) / 4 * 100` 转换为 0-100 尺度。

指标含义：

- IF：Instruction Following，指令遵循。
- BCS：Beat-Cut Synchronization，节拍-切点同步；基于最终成片的全帧视觉切换检测，不读取编辑 timeline。
- AEC：Audio-Visual Energy Correspondence，音画能量对应。
- VQ：Visual Quality，视觉质量。
- TC：Transition Continuity，片段和转场连续性。
- NC：Narrative Coherence，叙事连贯性。
- OQ：Overall Quality，人类整体质量评分，可选，1-5 Likert 量表。


### 专用指标

专用指标（Specified Metrics）与主评分独立，不参与 `Quality` 计算，仅用于按 prompt 类型做失败归因和细粒度分析：

- 事件型：`EC — Event Coverage — 事件覆盖率`，`KMS — Key Moment Salience — 片段显著性`。
- 人物型：`PPR — Protagonist Presence Rate — 主体出镜率`，`PPM — Protagonist Prominence — 主体显著性`。
- 情绪型：`ES — Emotional Specificity — 情绪特异性`，`FBAE — Facial / Body Affect Evidence — 面部/肢体情绪证据`。
- 叙事型：`NSC — Narrative Structure Completeness — 叙事完整性`，`TLO — Temporal / Logical Order — 时间合理性`。

专用指标单独运行：

```bash
uv run python -m eval.run_specified_metrics --run runs/<run_id> --config eval/config.yaml
```

专用指标结果可导出为三列表格：`类型 | 指标 | <模型名>`。

```bash
uv run python scripts/export_specified_metrics_table.py \
  --model-name <model_name> \
  --specified-metrics-id <specified_metrics_id>
```

效率单独报告，包括 API 成本和端到端耗时。可运行评测器的说明见 `eval/README.md`。

## Baseline 评测

本 benchmark 计划对比以下五个长视频 mashup/editing baseline。所有 baseline 的标准化输出均写入 `runs/<run_id>/`，并遵循 `schemas/run_manifest.schema.json` 与 `schemas/run_output.schema.json`。

复现实验环境总览：

| 环境 | 硬件 / 系统 | Baseline | 说明 |
| --- | --- | --- | --- |
| Mac mini M4 | macOS 26.5.1，Build 25F80，arm64；Mac mini `Mac16,10`；Apple M4，10 核 CPU（4 个性能核心 + 6 个能效核心）；16 GB 内存 | CutClaw、NarratoAI、OpenMontage | 本地 Mac mini 复现实验环境。OpenMontage 使用 Claude Code 作为 agent，并通过 Anthropic-compatible endpoint 调用 Qwen3.7-Plus。 |
| AutoDL 服务器 | Ubuntu 22.04，NVIDIA GeForce RTX 4090 24GB | VideoAgent、DIRECT-Claw | DIRECT-Claw 与 VideoAgent 使用同一台服务器环境和同一组模型/API 配置；二者各自使用对应 baseline 的 conda/Python 环境。 |

<details>
<summary>Baseline Adapter 通用配置</summary>

每个 baseline adapter 都应尽量遵循同一组通用参数，方便批量实验、复现和接入统一评测器。不同方法的项目根目录、Python 环境和原始输出可以各自独立，但最终都需要写出 benchmark 标准化的 `runs/<run_id>/` 结构。

| 参数模式                | 说明                                                                                                                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--<baseline>-root`   | 外部 baseline 项目根目录，例如`--cutclaw-root`。adapter 会在该目录中调用 baseline 原始入口脚本。                                                                       |
| `--<baseline>-python` | 外部 baseline 使用的 Python 解释器，例如`--cutclaw-python`。默认建议优先使用 `<baseline-root>/.venv/bin/python`，也可以显式指定 conda、uv 或其他虚拟环境中的解释器。 |
| `--task-id`           | 指定一个或多个 benchmark task，例如`task_006`。task 定义来自 `data/tasks/mashup_benchmark.jsonl`。                                                                   |
| `--all`               | 批量运行全部 40 个 benchmark task。                                                                                                                                      |
| `--run-id`            | 标准化结果目录名，输出到`runs/<run_id>/`。建议用方法名和实验设置命名，例如 `cutclaw_benchmark`。                                                                     |
| `--results-root`      | 标准化结果根目录，默认是 benchmark 仓库内的`runs/`。该目录应保持在 benchmark 根目录下，便于 schema 校验和评测器读取。                                                  |
| `--method`            | 写入 manifest 的方法名，例如`cutclaw`、`direct_claw`、`videoagent`。                                                                                               |
| `--method-version`    | 写入 manifest 的方法版本或实验标识，用于区分原版、消融实验和不同模型配置。                                                                                               |
| `--overwrite`         | 即使该 task 的`output.mp4` 已存在，也重新生成。默认行为是同名 run 可继续补跑：已成功且有成片的 task 会跳过，失败或不完整 task 会重试。                                  |
| `--dry-run`           | 只打印将要执行的命令并写入跳过元数据，不调用模型或渲染，适合检查路径和参数。                                                                                             |

方法独有的开关放在各 baseline 小节中说明，例如 CutClaw 的 hook dialogue、ending video、裁剪比例和原视频音量。

</details>

<details>
<summary>CutClaw</summary>

CutClaw: Agentic Hours-Long Video Editing via Music Synchronization

- 项目：[https://github.com/GVCLab/CutClaw](https://github.com/GVCLab/CutClaw)
- Fork：[https://github.com/hit-cxf/CutClaw](https://github.com/hit-cxf/CutClaw)
- 论文：[https://arxiv.org/abs/2603.29664](https://arxiv.org/abs/2603.29664)
- 当前状态：已提供 benchmark adapter。

使用 benchmark 侧的 CutClaw adapter 运行指定任务，并将可评测产物写入 `runs/<run_id>/`：

```bash
python3 scripts/run_cutclaw.py \
  --cutclaw-root /Users/xinfanchen/Project/CutClaw \
  --task-id task_006 \
  --run-id cutclaw_benchmark
```

批量运行全部任务：

```bash
python3 scripts/run_cutclaw.py \
  --cutclaw-root /Users/xinfanchen/Project/CutClaw \
  --all \
  --run-id cutclaw_benchmark
```

CutClaw 特有参数：

| 参数                        | 说明                                                                           |
| --------------------------- | ------------------------------------------------------------------------------ |
| `--no-hook-dialogue`      | 渲染时不添加 CutClaw 的 hook dialogue 开场。                                   |
| `--no-ending`             | 渲染时不追加 CutClaw 的 ending video。                                         |
| `--crop-ratio`            | 可选裁剪比例，例如`16:9`、`9:16`、`1:1`。                                |
| `--original-audio-volume` | 原视频声音混入音量，默认`0.0`，即只保留 BGM。                                |
| `--video-type`            | 传给 CutClaw 的视频类型参数，当前默认使用`film`，用于兼容 CutClaw 原始入口。 |

同一个 `run_id` 可以重复运行来补齐失败任务。默认情况下，adapter 会复用已有的成功任务输出；如果某个 task 之前记录为 `failed`，或者没有生成 `output.mp4`，再次运行同名 `run_id` 时会重试该 task。需要强制重跑所有已成功任务时再使用 `--overwrite`。

CutClaw 的原始中间结果仍保存在 CutClaw 项目的 `Output/` 中；benchmark 只保存用于评测的标准化 `runs/<run_id>/` 结构。运行完成后可用以下命令校验并评测：

```bash
python3 scripts/validate_run.py runs/cutclaw_benchmark
python3 -m eval.run_evaluation --run runs/cutclaw_benchmark --config eval/config.yaml
```

</details>

<details>
<summary>NarratoAI</summary>

NarratoAI: all-in-one AI-powered film commentary and automated video editing tool.

- 项目：[https://github.com/linyqh/NarratoAI](https://github.com/linyqh/NarratoAI)
- 当前状态：已提供 benchmark adapter。

NarratoAI 原生入口是 Streamlit WebUI。为适配 Mashup-Benchmark，当前 adapter 固定使用统一的、可批量复现的流程：

```text
ASR 转写 SRT -> 短剧混剪脚本生成 -> 强制 OST=1 后处理 -> 使用 benchmark 指定 BGM 合成
```

其中 `OST=1` 表示保留原视频原声、不生成 TTS。adapter 会把每个 task 指定的 `audio.local_path` 作为 NarratoAI 最终合成阶段的 BGM 输入，而不是让 NarratoAI 随机选择音乐。

运行单个任务：

```bash
uv run python scripts/run_narratoai.py \
  --narratoai-root /Users/xinfanchen/Project/NarratoAI \
  --task-id task_001 \
  --run-id narratoai_benchmark
```

批量运行全部任务：

```bash
uv run python scripts/run_narratoai.py \
  --narratoai-root /Users/xinfanchen/Project/NarratoAI \
  --all \
  --run-id narratoai_benchmark
```

NarratoAI 特有参数：

| 参数 | 说明 |
| --- | --- |
| `--asr-backend` | 字幕转写后端，支持 `bailian`、`local`、`firered`；默认 `bailian`。 |
| `--no-reuse-asr` | 即使已有 `artifacts/source.srt`，也重新转写字幕。默认复用已生成字幕。 |
| `--custom-clips` | 请求 NarratoAI 生成的候选片段数；默认按 `target_output_length_sec / target_shot_length_sec` 估算。 |
| `--max-clip-duration-sec` | adapter 后处理时每个片段的最长时长；默认使用 task 的 `target_shot_length_sec`。 |
| `--bgm-volume` | benchmark 指定 BGM 的混入音量。 |
| `--original-volume` | 传给 NarratoAI 的原声音量参数。注意 NarratoAI 对 `OST=1` 片段内部会倾向保留原声。 |
| `--subtitle-enabled` | 最终视频中烧录字幕。benchmark 默认关闭，避免字幕影响视觉评测。 |

每个 task 的中间产物会保存到：

```text
runs/<run_id>/task_outputs/<task_id>/artifacts/
  source.srt
  narrato_script_raw.json
  narrato_script_adapted.json
  narratoai_payload.json
  narrato_worker_result.json
```

该 adapter 不修改 NarratoAI 核心代码，只通过外部 worker 调用 NarratoAI 的 ASR、短剧混剪脚本生成和视频合成服务，并把输出归一化到 benchmark 的 `runs/<run_id>/` 结构。

</details>

<details>
<summary>DIRECT-Claw</summary>

DIRECT: Video Mashup Creation via Hierarchical Multi-Agent Planning and Intent-Guided Editing

- 项目：[https://github.com/AK-DREAM/DIRECT-Claw](https://github.com/AK-DREAM/DIRECT-Claw)
- Fork：[https://github.com/hit-cxf/DIRECT-Claw](https://github.com/hit-cxf/DIRECT-Claw)
- 论文：[https://arxiv.org/abs/2604.04875](https://arxiv.org/abs/2604.04875)
- 当前状态：已提供 benchmark adapter。

服务器复现实验环境：

| 项目 | 配置 |
| ---- | ---- |
| 机器 | AutoDL Ubuntu 22.04 |
| GPU | NVIDIA GeForce RTX 4090 24GB |
| DIRECT-Claw 环境 | `/root/miniconda3/envs/direct/bin/python` |
| Benchmark 环境 | benchmark 根目录下使用 Python/uv |
| DIRECT-Claw 根目录 | `/root/autodl-tmp/DIRECT-Claw` |
| Benchmark 根目录 | `/root/autodl-tmp/Mashup-Benchmark` |
| 模型/API 配置 | 与 VideoAgent 复现实验使用同一组服务器环境和配置 |

运行单个任务：

```bash
/root/miniconda3/envs/direct/bin/python scripts/run_direct_claw.py \
  --task-id task_001 \
  --run-id direct_claw_benchmark_smoke \
  --overwrite
```

批量运行全部任务：

```bash
/root/miniconda3/envs/direct/bin/python scripts/run_direct_claw.py \
  --all \
  --run-id direct_claw_benchmark
```

DIRECT-Claw adapter 会把 benchmark 媒体软链到 DIRECT-Claw 自己的 `data/benchmark_adapter/` 目录，为每个视频生成 `source_videos.csv`，为每个任务生成 DIRECT-Claw 原生 `task.yaml`，再调用：

```bash
python -m src.main_preprocess --csv ...
python -m src.main_agent --yaml_path ... --result_path ... --log_path ...
```

视频特征缓存保存在 DIRECT-Claw 的 `output/benchmark_adapter/` 和 `output/benchmark_adapter/videos/` 相关路径中；默认复用已有特征缓存，需要强制重算时使用 `--force-preprocess`。如果当前 shell 中没有 `ffmpeg`，adapter 会优先使用 `imageio_ffmpeg` 自带二进制创建私有 shim，不修改系统环境。

</details>

<details>
<summary>VideoAgent</summary>

VideoAgent: All-in-One Framework for Video Understanding and Editing

- 项目：[https://github.com/HKUDS/VideoAgent](https://github.com/HKUDS/VideoAgent)
- Fork：[https://github.com/hit-cxf/VideoAgent](https://github.com/hit-cxf/VideoAgent)
- 论文：[https://arxiv.org/abs/2606.23327](https://arxiv.org/abs/2606.23327)
- 当前状态：已提供 benchmark adapter。

VideoAgent 原始入口是 `python main.py` 的交互式 TUI：系统先用 LLM 做 intent analysis、agent graph planning、graph judge/reflection，再向用户询问缺失参数。为保证 benchmark 可批量、可复现、可校验，当前 adapter 固定使用 VideoAgent 中与音乐混剪最直接相关的子流程：

```text
VideoPreloader -> RhythmDetector -> RhythmContentGenerator -> VideoSearcher -> VideoEditor
```

服务器复现实验环境：

| 项目 | 配置 |
| ---- | ---- |
| 机器 | AutoDL Ubuntu 22.04 |
| GPU | NVIDIA GeForce RTX 4090 24GB |
| VideoAgent 环境 | `/root/miniconda3/envs/videoagent/bin/python` |
| Benchmark 环境 | benchmark 根目录下使用 `uv run` |
| VideoAgent 根目录 | `/root/autodl-tmp/VideoAgent` |
| Benchmark 根目录 | `/root/autodl-tmp/Mashup-Benchmark` |

运行单个任务：

```bash
uv run python3 scripts/run_videoagent.py \
  --task-id task_001 \
  --run-id videoagent_benchmark_smoke \
  --overwrite
```

批量运行全部任务：

```bash
uv run python3 scripts/run_videoagent.py \
  --all \
  --run-id videoagent_benchmark \
  --overwrite
```

VideoAgent adapter 复现改动与理由：

| 改动 | 理由 |
| ---- | ---- |
| 绕过交互式 TUI，直接调用固定工具链 | benchmark 需要无人值守批量运行；动态 graph planning 会引入额外随机性和交互输入。 |
| 使用 `videoagent` conda 环境的 Python 解释器执行 worker | 保持 VideoAgent 原依赖环境，避免 benchmark 的 `uv` 环境污染 baseline。 |
| 为源视频创建无下划线别名，例如 `video001.mp4` | VideoAgent 的 `VideoEditor` 用 `segment_id.split("_")` 解析片段名，原始 benchmark 文件名包含多个下划线，会导致时间片解析失败。 |
| 默认把 BGM 裁剪到 `target_output_length_sec` | VideoAgent 按音频节奏生成时间线；裁剪音频可以让输出时长与 benchmark 目标时长一致。 |
| 为每个 `video_id` 缓存 VideoRAG 预处理结果 | 长视频索引成本高；同一视频对应 4 个任务，缓存能显著减少重复预处理。 |
| 将 `video_scene.json`、`cut_points.json`、检索片段和日志复制到 `runs/<run_id>/task_outputs/<task_id>/artifacts/` | 统一保存可审计中间结果，便于定位失败和复查剪辑决策。 |
| 在当前 VideoAgent 环境中补充 `torchvision.transforms.functional_tensor` 兼容 shim | 当前环境为 `torch 2.3.1+cu121`、`torchvision 0.18.1+cu121`，而 `pytorchvideo` 仍引用旧的 torchvision 私有模块；shim 是最小兼容修复，避免降级 CUDA/PyTorch 造成更大环境风险。 |

该 adapter 只改变工程入口和环境兼容性，不修改 VideoAgent 的核心检索、节奏分析、storyboard 生成或编辑算法。这样做的目标是让 VideoAgent 作为 baseline 可重复运行，而不是提高或削弱其模型能力。

</details>

<details>
<summary>OpenMontage</summary>

OpenMontage: agent-driven video production harness.

- 当前状态：已提供 benchmark adapter。
- 适配方式：Claude Code 作为 coding agent，按 OpenMontage 的 `AGENT_GUIDE.md`、pipeline manifest 和工具协议执行；本地 Claude Code 可通过 Anthropic-compatible 路由使用 Qwen3.7-Plus。

OpenMontage 不是传统的单命令 pipeline，而是“agent 即 orchestrator”的 harness。为保证 benchmark 可批量复现，当前 adapter 固定使用如下约束：

```text
Claude Code/Qwen agent -> OpenMontage hybrid/source-footage-led -> FFmpeg compose
```

adapter 会为每个 task 创建独立的 OpenMontage project，写入 benchmark task、源视频、指定 BGM 和 agent prompt。agent 必须只使用 benchmark 提供的视频和音频，不下载素材、不生成素材、不生成 TTS/旁白，最终通过 OpenMontage 的 `video_compose` / FFmpeg 路径输出一个 `renders/final.mp4`，再由 adapter 复制为 benchmark 标准的 `runs/<run_id>/task_outputs/<task_id>/output.mp4`。

先生成 dry-run 任务包和 prompt：

```bash
uv run python scripts/run_openmontage.py \
  --task-id task_001 \
  --run-id openmontage_dryrun \
  --dry-run \
  --overwrite-project
```

真实运行单个任务：

```bash
uv run python scripts/run_openmontage.py \
  --task-id task_001 \
  --run-id openmontage_benchmark \
  --bypass-permissions \
  --overwrite-project
```

批量运行全部任务：

```bash
uv run python scripts/run_openmontage.py \
  --all \
  --run-id openmontage_benchmark \
  --bypass-permissions
```

OpenMontage 特有参数：

| 参数 | 说明 |
| --- | --- |
| `--openmontage-root` | OpenMontage 项目根目录，默认使用 benchmark 同级目录下的 `OpenMontage`。 |
| `--agent-cmd` | Claude Code 可执行文件路径，默认 `/Users/xinfanchen/.local/bin/claude`。 |
| `--agent-model` | 可选，显式传给 Claude Code 的模型名；默认不传，使用当前 Claude Code 配置。 |
| `--agent-output-format` | Claude Code 输出格式，默认 `stream-json`，便于记录完整 agent 日志。 |
| `--permission-mode` | Claude Code 权限模式，默认 `acceptEdits`。如果非交互权限仍阻塞，可配合 `--bypass-permissions`。 |
| `--bypass-permissions` | 向 Claude Code 传入 `--dangerously-skip-permissions`；只建议在可信本地 benchmark 环境中使用。 |
| `--max-budget-usd` | Claude Code 单次任务的最大 API 预算，可选。 |
| `--timeout-sec` | 单个 task 的 agent 执行超时时间，可选。 |
| `--overwrite-project` | 删除并重建该 task 对应的 OpenMontage project。 |
| `--max-cuts` | prompt 中给 agent 的最大剪辑片段数约束，默认 `24`。 |
| `--bgm-volume` | 指定 BGM 的目标音量提示，默认 `0.75`。 |
| `--original-volume` | 原视频声音混入提示，默认 `0.15`。 |

每个 task 的标准化中间产物会保存到：

```text
runs/<run_id>/task_outputs/<task_id>/artifacts/
  benchmark_task.json
  openmontage_agent_prompt.md
  brief.json                         # 如果 agent 成功写出
  edit_decisions.json                # 如果 agent 成功写出
  render_report.json                 # 如果 agent 成功写出
  openmontage_agent_result.json      # 如果 agent 成功写出
```

该 adapter 不修改 OpenMontage 核心代码；它只创建 benchmark project、生成非交互 agent prompt、调用 Claude Code，并把 OpenMontage 输出归一化到 benchmark 的 `runs/<run_id>/` 结构。

</details>

## 脚本说明

本仓库的可运行入口分为四类：数据/run 校验、baseline adapter、评测和导出。推荐全部在 benchmark 根目录通过 `uv run` 执行；外部 baseline 的 worker 解释器可通过对应参数显式指定。

### 校验脚本

#### `scripts/validate_benchmark.py`

校验 benchmark 元数据、任务 JSONL、manifest 和 schema 是否一致。

```bash
uv run python scripts/validate_benchmark.py
```

#### `scripts/validate_run.py`

校验某个 `runs/<run_id>` 是否符合提交结构和 schema。失败 task 可以没有 `output.mp4`，但必须记录非空 `error`。

```bash
uv run python scripts/validate_run.py runs/<run_id>
```

### Baseline Adapter 脚本

#### `scripts/run_cutclaw.py`

调用 CutClaw，生成标准化 `runs/<run_id>/` 输出。

```bash
uv run python scripts/run_cutclaw.py --cutclaw-root /path/to/CutClaw --task-id task_001 --run-id cutclaw_benchmark
```

#### `scripts/run_direct_claw.py`

调用 DIRECT-Claw，生成标准化 `runs/<run_id>/` 输出。

```bash
uv run python scripts/run_direct_claw.py --task-id task_001 --run-id direct_claw_benchmark
```

#### `scripts/run_narratoai.py`

调用 NarratoAI，按 `ASR -> 短剧混剪 -> OST=1 -> 指定 BGM 合成` 流程生成标准化输出。

```bash
uv run python scripts/run_narratoai.py --narratoai-root /path/to/NarratoAI --task-id task_001 --run-id narratoai_benchmark
```

#### `scripts/run_videoagent.py`

调用 VideoAgent 固定音乐混剪流程，生成标准化 `runs/<run_id>/` 输出。

```bash
uv run python scripts/run_videoagent.py --task-id task_001 --run-id videoagent_benchmark
```

#### `scripts/run_openmontage.py`

调用 OpenMontage agent harness，通过 Claude Code/Qwen 驱动 OpenMontage 工具生成标准化输出。

```bash
uv run python scripts/run_openmontage.py --task-id task_001 --run-id openmontage_benchmark --bypass-permissions --overwrite-project
```

### 评测脚本

#### `python -m eval.run_evaluation`

计算主评分，包括本地自动指标 `BCS/AEC`、VLM-as-judge 的 `IF/VQ/TC/NC`，以及可选 `OQ` 后的 `Quality`。输出到 `eval_results/<eval_id>/evaluation_scores.jsonl` 和 `summary.json`。

```bash
uv run python -m eval.run_evaluation --run runs/<run_id> --config eval/config.yaml
```

#### `python -m eval.run_specified_metrics`

单独计算专用指标，不参与主 `Quality`，用于按 prompt 类型做失败归因。输出到 `eval_results/<specified_metrics_id>/specified_metric_scores.jsonl` 和 `specified_metric_summary.json`。

```bash
uv run python -m eval.run_specified_metrics --run runs/<run_id> --config eval/config.yaml
```

`eval/config.yaml` 用于配置 VLM 模型名、API key、base URL、超时时间和指标权重。该文件包含本地密钥配置，已被 Git 忽略；请不要提交。

### 导出脚本

#### `scripts/export_evaluation_table.py`

将主评分结果导出为 Excel，按任务类型汇总 `IF/BCS/AEC/VQ/TC/NC/Quality`。

```bash
uv run python scripts/export_evaluation_table.py --model-name CutClaw --eval-id <eval_id>
```

#### `scripts/export_specified_metrics_table.py`

将专用指标结果导出为 Excel，按类型和指标汇总。

```bash
uv run python scripts/export_specified_metrics_table.py --model-name CutClaw --specified-metrics-id <specified_metrics_id>
```

#### `scripts/export_evaluation_detail_table.py`

将主评分和专用指标合并导出为 task 级明细表；非对应 prompt 类型的专用指标留空。

```bash
uv run python scripts/export_evaluation_detail_table.py --model-name CutClaw --eval-id <eval_id> --specified-metrics-id <specified_metrics_id>
```

## 许可证

- 仓库自有的代码、benchmark 元数据、任务定义、prompt、schema、manifest、文档和评测标注使用 Apache License 2.0，见 `LICENSE`。
- 本仓库不重新分发源视频或音频素材。用户需要自行从合法来源获取媒体文件，并遵守对应素材的原始版权、许可证和使用条款。
- 包含第三方版权媒体的生成视频不属于本仓库代码或数据许可证的授权范围。

第三方媒体和素材说明见 `NOTICE`。
