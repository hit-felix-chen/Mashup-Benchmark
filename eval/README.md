# Evaluation Code

This package evaluates submitted runs under `runs/<run_id>/`.

## Metrics Implemented

Cross-modal alignment:

- `IF`: instruction following, scored by VLM-as-judge.
- `BCS`: beat-cut synchronization. PySceneDetect proposes full-frame cut
  candidates, a VLM classifies each adjacent before/after frame pair as cut or
  non-cut, and only confirmed cuts are compared with audio beat peaks.
- `AEC`: audio-visual energy correspondence, computed from visual motion and audio RMS correlation.

Single-modal quality:

- `VQ`: visual quality, scored by VLM-as-judge.
- `TC`: transition continuity, scored by VLM-as-judge.
- `NC`: narrative coherence, scored by VLM-as-judge.

Quality is the arithmetic mean of six normalized scores. Convert VLM scores
with `(score - 1) / 4 * 100`; BCS/AEC already use 0–100. Legacy weights are
ignored. Missing metrics are omitted; partial Quality is not directly comparable
to full six-metric Quality.

Human `OQ` ratings are stored and analyzed by a separate human-evaluation
workflow. They are never copied into automatic evaluation records or included
in `Quality`.


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

By default, tasks are evaluated with `--concurrency 10`. Use `--concurrency <N>` to adjust parallelism. Output JSONL rows are still written in the original task order.

Outputs:

```text
eval_results/<specified_metrics_id>/specified_metric_scores.jsonl
eval_results/<specified_metrics_id>/specified_metric_summary.json
```

## Configure VLM Judge

The holistic VLM judge sends the final rendered `output.mp4` directly to the
configured model as a video input. BCS separately sends two adjacent still
frames for every PySceneDetect cut candidate and requests a strict binary
`is_cut` classification.

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

By default, tasks are evaluated with `--concurrency 10`. Use `--concurrency <N>` to adjust parallelism. Output JSONL rows are still written in the original task order.

Partially reevaluate selected tasks and metrics while reusing all other results:

```bash
uv run python -m eval.run_evaluation \
  --run runs/cutclaw_benchmark \
  --config eval/config.yaml \
  --reuse-eval-id <existing_eval_id> \
  --task-id task_022 \
  --metrics BCS
```

Run without the holistic IF/VQ/TC/NC judge. BCS still requires the configured
VLM for cut validation:

```bash
uv run python -m eval.run_evaluation --run runs/<run_id> --skip-vlm --limit 1
```

Outputs:

```text
eval_results/<eval_id>/evaluation_scores.jsonl
eval_results/<eval_id>/summary.json
```
