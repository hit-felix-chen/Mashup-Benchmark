# VLM Judge Rubric Draft

Use this rubric when scoring a generated video against one benchmark task.

Inputs:

- User prompt
- Source video title/category metadata
- BGM metadata
- Generated short video

The VLM judge scores only four metrics on a 1-5 Likert scale. Keep metrics independent:

- Do not penalize IF for visual quality or transition quality unless they prevent judging prompt fulfillment.
- Do not score beat synchronization or audio-visual energy alignment here; those are computed separately.
- Use BGM metadata only when judging whether the requested style or emotion is supported.
- Length mismatch should affect IF only if it substantially violates the requested output length or prevents satisfying the prompt.

## Metric Anchors

### IF: Instruction Following

Does the edit follow the requested subject, event, style, emotion, or narrative?

- 1 = unrelated or contradicts the prompt.
- 2 = weakly related; misses most key requested elements.
- 3 = partially follows; covers some key elements but misses important ones.
- 4 = mostly follows; minor omissions or weak emphasis.
- 5 = strongly follows all key requested elements and constraints.

### VQ: Visual Quality

Is the video clear, well-composed, subject-focused, and free of obvious technical defects?

- 1 = severe visual defects make the video hard to watch.
- 2 = frequent blur, occlusion, bad framing, or unstable subject focus.
- 3 = generally watchable but with noticeable quality or framing issues.
- 4 = clear and stable with only minor visual issues.
- 5 = consistently clear, well-composed, and subject-focused.

### TC: Transition Continuity

Do adjacent segments feel coherent in visual semantics, motion, and composition?

- 1 = chaotic or jarring cuts that break comprehension.
- 2 = many abrupt jumps or mismatched transitions.
- 3 = mixed continuity; some transitions work, some feel abrupt.
- 4 = mostly smooth and coherent transitions with minor jumps.
- 5 = consistently natural, purposeful, and rhythmically coherent transitions.

### NC: Narrative Coherence

Does the edit have a clear structure, progression, or story arc matching the prompt?

- 1 = random clips with no understandable structure.
- 2 = weak structure; sequence feels mostly disjointed.
- 3 = basic progression is present but underdeveloped or uneven.
- 4 = clear progression with minor gaps or pacing issues.
- 5 = strong beginning-middle-end or emotional/story progression.

`OQ` is not scored by the VLM judge. It is reserved for optional human overall-quality evaluation on the same 1-5 Likert scale and can be supplied as `human_scores.OQ` or `scores.OQ` in a run record.

Return JSON only:

```json
{
  "scores": {
    "IF": 1,
    "VQ": 1,
    "TC": 1,
    "NC": 1
  },
  "rationale": {
    "IF": "short reason",
    "VQ": "short reason",
    "TC": "short reason",
    "NC": "short reason"
  },
  "diagnostics": {
    "matched_prompt_elements": ["visible requested element"],
    "missing_prompt_elements": ["requested element not visible"],
    "visual_quality_issues": ["blur, bad framing, occlusion, or empty list"],
    "transition_issues": ["abrupt jump, mismatched motion, or empty list"],
    "narrative_issues": ["weak opening, temporal disorder, or empty list"],
    "length_issue": "none | too_short | too_long",
    "uncertain_observations": ["things that could not be verified, or empty list"]
  }
}
```
