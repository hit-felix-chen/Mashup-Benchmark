# Evaluation Code

This package evaluates submitted runs under `runs/<run_id>/`.

## Metrics Implemented

Cross-modal alignment:

- `IF`: instruction following, scored by VLM-as-judge.
- `BCS`: beat-cut synchronization, computed from full-frame scene-change detection on the final rendered video and audio beat peaks.
- `AEC`: audio-visual energy correspondence, computed from visual motion and audio RMS correlation.

Single-modal quality:

- `VQ`: visual quality, scored by VLM-as-judge.
- `TC`: transition continuity, scored by VLM-as-judge.
- `NC`: narrative coherence, scored by VLM-as-judge.

Human preference:

- `OQ`: optional 1-5 Likert overall quality rating from human evaluation.

Default seven-metric weights are `BCS=0.20`, `AEC=0.20`, `OQ=0.20`, and `IF/VQ/TC/NC=0.10` each. VLM scores and human `OQ` are stored as raw 1-5 Likert scores; for `Quality`, they are converted with `(score - 1) / 4 * 100`. If `OQ` or any other metric is missing, the evaluator renormalizes over available metrics.


## Specified Metrics

Specified metrics are independent from the main `Quality` score. They are VLM-as-judge Likert 1-5 scores used for prompt-type-specific failure analysis:

- Event prompts: `EC — Event Coverage — 事件覆盖率`, `KMS — Key Moment Salience — 片段显著性`.
- Character prompts: `PPR — Protagonist Presence Rate — 主体出镜率`, `PPM — Protagonist Prominence — 主体显著性`.
- Emotion prompts: `ES — Emotional Specificity — 情绪特异性`, `FBAE — Facial / Body Affect Evidence — 面部/肢体情绪证据`.
- Narrative prompts: `NSC — Narrative Structure Completeness — 叙事完整性`, `TLO — Temporal / Logical Order — 时间合理性`.

Run them separately:

```bash
uv run python -m eval.run_specified_metrics --run runs/<run_id> --config eval/config.yaml
```

Outputs:

```text
eval_results/<specified_metrics_id>/specified_metric_scores.jsonl
eval_results/<specified_metrics_id>/specified_metric_summary.json
```

## Configure VLM Judge

The VLM judge sends the final rendered `output.mp4` directly to the configured model as a video input. It does not sample still frames for VLM scoring.

By default, `vlm.provider: dashscope` uses the DashScope SDK and passes the local rendered video as a `file://` input. The SDK uploads the video before calling the model, which avoids sending a large base64 video inside a single JSON request. Set `vlm.provider: openai_compatible` only when you explicitly want to use the OpenAI-compatible HTTP endpoint and base64 data URLs.

Copy the example config and fill in credentials:

```bash
cp eval/config.example.yaml eval/config.yaml
```

`eval/config.yaml` is ignored by git.

## Run

```bash
uv run python -m eval.run_evaluation --run runs/<run_id> --config eval/config.yaml
```

Smoke-test automatic metrics only:

```bash
uv run python -m eval.run_evaluation --run runs/<run_id> --skip-vlm --limit 1
```

Outputs:

```text
eval_results/<eval_id>/evaluation_scores.jsonl
eval_results/<eval_id>/summary.json
```
