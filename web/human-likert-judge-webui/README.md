# Likert Human Judge

匿名单视频人工评分网页。每轮等概率随机抽取一个任务和一个启用方法的成片；标注者不知道方法名、run 路径或自动分数。完整观看后，按新版通用 VLM 量表分别给 IF、VQ、TC、NC 赋 1–5 分。

在 benchmark 根目录运行：

```bash
.venv/bin/python web/human-likert-judge-webui/app.py check
.venv/bin/python web/human-likert-judge-webui/app.py serve --host 0.0.0.0 --port 8766
```

评分写入本目录 `data/ratings.sqlite3`，与成对评测数据库完全隔离。

导出管理员可见的明细（含真实方法映射）到独立目录：

```bash
.venv/bin/python web/human-likert-judge-webui/app.py export
```

导出包含逐指标 CSV、完整 JSONL 和固定实验快照。数据库与导出仅供管理员保管，浏览器始终不会收到方法身份或自动评测分数。
