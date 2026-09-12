# General VLM rubric v2

Version: `general_v2_1_evidence_anchored`. The executable English anchors and output
contract are in `eval/evaluators/vlm_judge.py::USER_PROMPT_TEMPLATE`.

The six general metrics remain IF, BCS, AEC, VQ, TC, and NC. Four are holistic
VLM scores; BCS and AEC retain their existing calculations. Task-specific metrics are unchanged. Quality uses an unweighted mean after normalization. VQ retains its storage key but now measures
editing technical quality rather than source cinematography or resolution.

## Evidence and independence

Review the complete video, record timestamped diagnostics, explain each anchor,
then assign integer scores from 1 to 5. Titles are context, not evidence.
Uncertain observations must not become confirmed successes or invented defects.
Do not infer unseen events or identities from metadata.

Use the same anchors across methods and genres. Do not force a score spread,
ranking, maximum, or quota of high scores. Award 5 when its conditions are met.
A recognizable theme or polished source alone cannot justify high scores.
3 denotes adequate execution with substantive limitations; 4 requires strong
execution; 5 requires all metric-specific conditions.

| Score | IF: Instruction Following | VQ: Editing Technical Quality | TC: Transition Continuity | NC: Narrative Coherence |
| --- | --- | --- | --- | --- |
| 1 | Central request absent or contradicted | Pervasive technical problems | Most boundaries disrupt comprehension | No discernible organization |
| 2 | Most core requirements unsupported | Repeated substantial defects | Repeated disruptive boundaries | Disconnected or repetitive sequence |
| 3 | A core omission/partial fulfillment or several secondary weaknesses | One substantial or several minor defects | Several weak boundaries or an important interruption | Basic organization but weak development, emphasis, or closure |
| 4 | All core requirements supported; minor secondary limitations | Isolated minor defects | Almost all boundaries purposeful and readable | Sustained progression with minor gaps or redundancy |
| 5 | All explicit requirements fully supported with appropriate emphasis | Precise presentation throughout with no observed editing-induced defects | All observed boundaries preserve meaning and orientation with precise timing | Fully developed, economical progression and convincing task-appropriate ending |

IF uses a prompt-derived checklist with core/secondary and complete/partial/
missing/uncertain labels. Missing or unverified core requirements rule out 4 and
5. Context or implied outcomes cannot substitute for requested actions/processes.
Do not add unstated requirements. Duration affects IF only for substantive
violations of the request or fulfillment.
Broad style/genre terms do not mandate a particular outcome, emotional valence,
or chronology. Do not turn genre conventions into additional core requirements.

VQ evaluates defects introduced or aggravated by editing. Intentional stillness,
repetition, and brief shots are not automatically defective. Source resolution
and cinematography do not earn credit. Semantic boundary problems belong to TC.
Attribute defects to editing only with visible evidence; source appearance alone
is insufficient, and uncertain attribution should be reported as uncertain.

TC evaluates local readability and action/thought completion at boundaries.
Changes in time, location, and shot scale are not inherently problems. Fast cuts
require evidence of harm before being penalized. Music synchronization belongs
to BCS; montage does not require continuous action.

NC evaluates organization of included material, not coverage (IF) or individual
cut execution (TC). Shared subjects and chronology alone do not imply developed
structure. Thematic, emotional, and nonlinear organization are valid.
Non-narrative tasks do not require a plot.

Diagnostics retain the existing schema: timestamped evidence, omission severity,
defect impact, and uncertainty. Each rationale explains the selected anchor and
why the next is not met, or why 5 is justified.

## Version comparison and validation

`rubric_version` is stored in judge metadata and each evaluated metric's details.
V1 and V2 scores are not directly comparable, especially VQ. Re-evaluate all
compared methods with V2 before reporting rankings. Retain historical evaluations
under their original IDs. Partial evaluations can mix versions; inspect
per-metric metadata rather than only judge metadata.

Validate with method-blind human comparisons and repeated judgments. Report
spread, ceiling frequency, repeatability, and human agreement as observations,
not guaranteed outcomes. Choose criteria before inspecting new rankings; do not
tune anchors or weights to reward a specific method.

`OQ` is not scored by the VLM judge. It is collected by a separate human-evaluation workflow and stored outside run and automatic evaluation records. The earlier per-video protocol uses a 1–5 Likert scale; the [pairwise WebUI](../human-judge-webui/README.md) collects five-level relative preferences between A and B for OQ and human counterparts of IF/VQ/TC/NC. Keep the two protocols distinct. OQ is used only for human-validation analyses and never contributes to automatic `Quality`.
