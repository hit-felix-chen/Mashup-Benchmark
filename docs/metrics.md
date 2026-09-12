# Evaluation Metrics

The automatic evaluator supports six quality metrics: two local automatic metrics and four VLM-as-judge metrics. Local automatic metrics and `Quality` are reported on `[0, 100]`. VLM-as-judge metrics are reported as raw 1-5 Likert scores and normalized internally for `Quality`. Human ratings are stored and analyzed separately.

## Quality Score

```text
Quality = mean(IF_normalized, BCS, AEC, VQ_normalized, TC_normalized, NC_normalized)
```

For `Quality`, Likert scores are converted to `[0, 100]` by:

```text
normalized_vlm_score = (likert_score - 1) / 4 * 100
```

Use the arithmetic mean of normalized scores. Legacy weights are ignored. Missing metrics are omitted; partial Quality is not directly comparable to full six-metric Quality. Human OQ never affects Quality.

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

## Human Validation

### OQ: Overall Quality

Records whether a viewer considers the final video good, natural, professional, and publishable.

Implementation: an independent 1-5 Likert human rating used to validate the automatic evaluation through agreement and correlation analyses. It is stored outside run outputs and automatic evaluation records, and it never contributes to `Quality`.

## Efficiency

Efficiency is reported separately:

- API cost per task
- end-to-end latency per task
- optional module-level latency breakdown
