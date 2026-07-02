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

## Configure VLM Judge

The VLM judge sends the final rendered `output.mp4` directly to the configured model as a video input. It does not sample still frames for VLM scoring.

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
