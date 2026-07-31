# Evaluation Metrics

The evaluator supports seven quality metrics: two local automatic metrics, four VLM-as-judge metrics, and one optional human metric. Local automatic metrics and `Quality` are reported on `[0, 100]`. VLM-as-judge metrics and the optional human `OQ` metric are reported as raw 1-5 Likert scores and normalized internally for `Quality`.

## Quality Score

```text
Quality = weighted_mean(IF, BCS, AEC, VQ, TC, NC, OQ)
```

For `Quality`, Likert scores are converted to `[0, 100]` by:

```text
normalized_vlm_score = (likert_score - 1) / 4 * 100
```

Default seven-metric weights:

```text
BCS = 0.20  # local automatic
AEC = 0.20  # local automatic
IF  = 0.10  # VLM-as-judge
VQ  = 0.10  # VLM-as-judge
TC  = 0.10  # VLM-as-judge
NC  = 0.10  # VLM-as-judge
OQ  = 0.20  # human evaluation
```

If `OQ` is unavailable, the evaluator renormalizes over the six available metrics:

```text
BCS = 0.25
AEC = 0.25
IF  = 0.125
VQ  = 0.125
TC  = 0.125
NC  = 0.125
```

The implementation also renormalizes automatically for any other missing metric, which keeps smoke tests and partial evaluations comparable within the metrics they actually compute.

## Cross-Modal Alignment

### IF: Instruction Following

Checks whether the output follows the prompt's requested subject, event, emotion, style, and narrative intent.

Implementation: VLM-as-judge. The evaluator sends the final rendered video to the configured VLM and asks it to score consistency with the task prompt on a 1-5 Likert scale.

### BCS: Beat-Cut Synchronization

Measures whether visual cuts align with music beats or energy peaks.

Implementation: the evaluator runs PySceneDetect on the final rendered video to
produce high-recall cut candidates. For each candidate, it sends the immediately
adjacent before/after frame pair to the configured VLM for strict binary
shot-boundary classification. It extracts audio beats with librosa, computes
each VLM-confirmed cut's distance to the nearest beat, and averages
`exp(-distance / tau)`. The default `tau=0.196` makes a 100 ms offset score
about 60/100. It does not read the edit timeline, so confirmed internal cuts
inside selected source clips are counted.

### AEC: Audio-Visual Energy Correspondence

Measures whether visual motion intensity follows audio energy.

Implementation: the evaluator computes frame-difference motion energy and audio RMS energy, then maps their Pearson correlation from `[-1, 1]` to `[0, 100]`.

## Single-Modal Quality

### VQ: Visual Quality

Scores clarity, composition, subject prominence, and absence of obvious technical defects.

Implementation: VLM-as-judge over the final rendered video on a 1-5 Likert scale.

### TC: Transition Continuity

Scores whether neighboring clips connect naturally in semantics, movement, and composition.

Implementation: VLM-as-judge over the final rendered video sequence on a 1-5 Likert scale.

### NC: Narrative Coherence

Scores whether the complete edit has a coherent structure, emotional progression, or story arc.

Implementation: VLM-as-judge using the final rendered video plus task metadata on a 1-5 Likert scale.

## Human Preference

### OQ: Overall Quality

Scores whether a viewer considers the final video good, natural, professional, and publishable.

Implementation: optional human rating on a 1-5 Likert scale. If a run record provides `human_scores.OQ` or `scores.OQ`, the evaluator includes it in `Quality` after converting it with `(score - 1) / 4 * 100`; otherwise the score is computed from the available automatic and VLM metrics only.

## Efficiency

Efficiency is reported separately:

- API cost per task
- end-to-end latency per task
- optional module-level latency breakdown
