# Pairwise Human Judge

双视频盲评 UI。每轮先从配置覆盖的任务中**等概率随机抽一个 task**，再从启用的方法中**等概率随机选两个不同方法**，随机分配到 A/B。采用有放回抽样，因此同一标注者也可能遇到重复组合。刷新或重新连接会恢复尚未结束的一轮，不重新抽样。

## 启动

在 benchmark 根目录执行（Python 3.11+，Web 服务只用标准库）：

```bash
python web/human-pairwise-judge-webui/app.py check
python web/human-pairwise-judge-webui/app.py serve
```

浏览器打开 <http://127.0.0.1:8765>，输入固定标注者代号即可开始。也可使用项目的 `.venv/bin/python`。播放检查需要 `ffprobe`，不兼容视频的播放副本需要 `ffmpeg`：macOS 可用 `brew install ffmpeg`；Ubuntu 可用 `sudo apt install ffmpeg`。

同一局域网多人使用时，在有媒体的机器上启动：

```bash
python web/human-pairwise-judge-webui/app.py serve --host 0.0.0.0 --port 8765
```

标注者访问 `http://服务器局域网IP:8765`。结果统一保存于服务器。此服务面向本机／可信局域网，不提供公共互联网账号认证；如需公网部署，应另加 HTTPS 和访问认证。

## 评测流程与量表

1. 页面展示任务提示词、视频领域、意图、目标时长、源片标题和 BGM 信息。成片仅显示 A/B，不向浏览器发送方法名、run 路径或自动分数。
2. 用耳机分别完整观看两部视频，确认观看完成。播放一部时会自动暂停另一部，可全屏、拖动与重播。观看确认是标注者声明，不声称自动验证注意力或完整观看。
3. 判断视频整体质量：A 更好、相当或 B 更好。下方原因按钮可多选或不选：遵循指令、画面美观、转场丝滑、叙事连贯。点击“保存并抽取下一组”。重复点击或网络重试不会产生重复记录。
4. 无法播放或无法评价时填写原因并跳过。跳过与未完成记录单独保留，不计入已完成比较数。

整体质量（OQ）采用三档相对偏好：`+1=A更好`，`0=相当`，`-1=B更好`。原因分别以 IF/VQ/TC/NC 编码保存，只作可选解释，不再单独评分。人工判断不进入自动 `Quality`，也不写入 `runs/` 或 `eval_results/`。

## 旧数据迁移

停止成对网页服务后执行 `python web/human-pairwise-judge-webui/app.py migrate-overall`，再重启服务。保持原 study ID；迁移是事务性的，可重复执行。

四项中 A 获胜的数量大于 B 时整体记 A 更好，反之记 B 更好，数量相同记相当。原因取支持获胜方的原始指标；相当时原因留空。旧四项保存在 `legacy_ratings`，新整体偏好保存在 `ratings.OQ`，原因在 `reasons`。`rating_origin=derived_four_metrics` 标记迁移记录；新提交标记为 `direct_overall`。旧协议快照保存在 `protocol_migrations`。分析时应区分推导结果与直接整体判断。

## 配置

默认配置位于 [config.json](config.json)：五个 baseline 全部启用，CutMaster 指向 `runs/cutmaster_overlap_beat`。可复制为 `config.local.json`，通过 `--config web/human-pairwise-judge-webui/config.local.json` 使用。

- `methods`：自定义方法 ID、管理员可见名称、`run_dir`、`enabled`；至少启用两个，ID 唯一。任意方法都可加入／禁用，无硬编码的 baseline/ours 区分。
- 每个方法默认读取 `run_dir/task_outputs/{task_id}/output.mp4`；可提供 `output_pattern` 改变布局，例如 `"{task_id}/final.mp4"`。
- `benchmark_root` 相对于配置文件；`task_manifest`、`run_dir` 相对于 benchmark root；`database`、`media_cache` 相对于配置文件。绝对路径也支持。
- `task_ids: []` 表示全部任务；也可填写 `["task_001", "task_002"]` 来限定任务。所有启用方法必须覆盖所选全部任务；缺文件会明确报错，不静默改变抽样集合。
- `study_id` 标识一套固定实验；方法、任务内容、协议或源媒体变化后，须换一个新的 `study_id`。旧数据仍保存在数据库中，不混入新实验。
- `host` / `port` 设置监听地址和端口，命令行参数可覆盖。
- `browser_proxies: true` 自动为浏览器不兼容的编码生成播放副本；设为 false 则总是播放原文件，需要自行确认客户端兼容性。

标注者身份通过 HttpOnly Cookie 保留，未提交的选择在该浏览器本地暂存，提交后的数据在服务器 SQLite。使用固定浏览器和站点地址；清除 Cookie、换浏览器或点击“切换标注者”会生成新的 participant ID，即使再次输入相同代号也不会合并。多人不应共用同一浏览器身份。相同身份开多个标签页会显示同一待评组合。

## 视频兼容性

服务支持 HTTP Range，拖动视频不会要求重新下载整部文件。通常直接流式播放原始 H.264 8-bit 成片。遇到 High-10、非 H.264 或不兼容音频时，在 `data/media-cache/` 生成 H.264 8-bit / AAC 副本；保持原始分辨率、画幅和时间线，不裁切、不补齐、不覆盖源文件。第一次命中时页面显示“视频正在准备”。两条转换任务并发执行。

正式标注前可以预生成全部缓存并验证解码元数据：

```bash
python web/human-pairwise-judge-webui/app.py prepare-media
```

转换采用 `libx264 CRF18 / preset fast / yuv420p / AAC160k`，属于有损重编码，尤其可能影响 VQ。导出记录包括两侧是否使用副本、原始媒体信息及编码配置，便于分析时披露和检查；不要把代理播放描述为逐像素相同。缓存使用源路径、大小、修改时间和编码设置生成键，源结果变更后需要新 study ID。

## 保存与导出

默认数据库：`web/human-pairwise-judge-webui/data/judgments.sqlite3`，使用 WAL 支持多人写入。每条记录保存匿名 participant ID、标注者代号、任务、A/B 真实方法映射、创建／提交时间、整体偏好、可选原因、备注、状态及媒体版本信息；study 表保存配置与任务快照。服务器重启后可继续。

```bash
python web/human-pairwise-judge-webui/app.py export
# 或指定配置和导出目录
python web/human-pairwise-judge-webui/app.py export --config web/human-pairwise-judge-webui/config.json --output web/human-pairwise-judge-webui/exports
```

导出三个带 UTC 时间戳的文件，已有导出不会被覆盖：

- `.csv`：仅完成的比较，每组一行，包含整体 `preference`、实际方法 `winner`（或 tie）、`reasons`、`rating_origin` 和 `legacy_ratings`。
- `.jsonl`：所有完成、跳过和未完成比较，以及完整审计字段。保留原始备注。
- `.study.json`：该实验的固定配置、协议、任务与源文件信息。

为防电子表格把自由文本识别成公式，CSV 文本以 `= + - @` 开头时会加单引号；数值偏好仍是数值。数据库与导出含真实方法映射，仅供管理员保管。备份运行中的 SQLite 时应使用 SQLite backup API，或先停止服务再复制数据库与其 WAL 文件。

随机有放回抽样不会保证每个任务、方法对或每位标注者的样本量相同。分析时应报告实际覆盖与重复次数；可将人类偏好方向与同一任务两方法的 VLM 分数差进行比较，并单独处理自动分数并列与人工 tie。不要把这里的相对偏好直接当作旧版逐视频 1–5 分，或把重复记录当独立任务。此界面没有自动设定样本量或终止轮数。

## 验证

```bash
python -m unittest discover -s web/human-pairwise-judge-webui -p 'test_*.py' -v
```

测试覆盖身份隔离、抽样、并发续评、严格评分校验、幂等提交、跳过、配置变更隔离、导出和 HTTP Range。测试使用临时数据，不会写入正式人评数据库。
