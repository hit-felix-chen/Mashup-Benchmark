#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.aggregate_scores import compute_quality, normalize_score_for_quality, summarize
from eval.config import load_config
from eval.evaluators.cut_boundary_validator import CutBoundaryValidator
from eval.evaluators.vlm_judge import VLMJudge, VLMJudgeSkipped
from eval.metrics.alignment import audio_visual_energy_correspondence, beat_cut_synchronization

ROOT = Path(__file__).resolve().parents[1]
TASK_FILE = ROOT / "data" / "tasks" / "mashup_benchmark.jsonl"
BASE_METRICS = ("BCS", "AEC", "IF", "VQ", "TC", "NC", "OQ")
VLM_METRICS = frozenset({"IF", "VQ", "TC", "NC"})


def load_tasks() -> dict[str, dict[str, Any]]:
    rows = {}
    with TASK_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                rows[row["id"]] = row
    return rows


def load_run_records(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "run_outputs.jsonl"
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_csv_args(values: list[str] | None, *, uppercase: bool = False) -> list[str]:
    parsed: list[str] = []
    for value in values or []:
        for item in value.split(","):
            item = item.strip()
            if item:
                parsed.append(item.upper() if uppercase else item)
    return list(dict.fromkeys(parsed))


def load_evaluation_records(eval_id: str) -> dict[str, dict[str, Any]]:
    path = ROOT / "eval_results" / eval_id / "evaluation_scores.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Reusable evaluation scores not found: {path}")
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                records[row["task_id"]] = row
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one Mashup-Benchmark run.")
    parser.add_argument("--run", required=True, help="Path to runs/<run_id>.")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to evaluator config YAML.")
    parser.add_argument("--eval-id", default=None, help="Evaluation id. Defaults to <run_id>_eval_<timestamp>.")
    parser.add_argument(
        "--skip-vlm",
        action="store_true",
        help=("Skip holistic VLM judge metrics IF/VQ/TC/NC. BCS still uses VLM cut validation."),
    )
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N records for smoke tests.")
    parser.add_argument("--concurrency", type=int, default=10, help="Number of tasks to evaluate concurrently.")
    parser.add_argument(
        "--task-id",
        "--task-ids",
        dest="task_ids",
        action="append",
        default=None,
        help="Only reevaluate these task ids. Accepts comma-separated values or repeated arguments.",
    )
    parser.add_argument(
        "--metrics",
        action="append",
        default=None,
        help="Only recompute these metrics: BCS,AEC,IF,VQ,TC,NC,OQ. Quality is always recomputed.",
    )
    parser.add_argument(
        "--reuse-eval-id",
        default=None,
        help="Copy unselected tasks/metrics from eval_results/<eval_id> for a partial reevaluation.",
    )
    args = parser.parse_args()

    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    run_id = run_dir.name
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d_%H%M%S")
    eval_id = args.eval_id or args.reuse_eval_id or f"{run_id}_eval_{timestamp}"
    eval_dir = ROOT / "eval_results" / eval_id

    requested_task_ids = set(parse_csv_args(args.task_ids))
    requested_metrics_list = parse_csv_args(args.metrics, uppercase=True)
    invalid_metrics = sorted(set(requested_metrics_list) - set(BASE_METRICS))
    if invalid_metrics:
        parser.error(f"Unsupported metrics: {', '.join(invalid_metrics)}")
    if args.skip_vlm and set(requested_metrics_list) & VLM_METRICS:
        parser.error("--skip-vlm cannot be combined with VLM metrics IF,VQ,TC,NC.")
    is_partial = bool(requested_task_ids or requested_metrics_list)
    if is_partial and not args.reuse_eval_id:
        parser.error("--reuse-eval-id is required with --task-ids or --metrics.")

    if requested_metrics_list:
        selected_metrics = set(requested_metrics_list)
    elif args.skip_vlm:
        selected_metrics = {"BCS", "AEC", "OQ"}
    else:
        selected_metrics = set(BASE_METRICS)

    require_vlm = bool(("BCS" in selected_metrics) or (selected_metrics & VLM_METRICS and not args.skip_vlm))
    config = load_config(args.config, require_vlm=require_vlm)
    auto_cfg = config.get("automatic_metrics", {})
    cut_validator = (
        CutBoundaryValidator(
            config,
            max_concurrency=int(auto_cfg.get("bcs_cut_vlm_max_concurrency", 10)),
            frame_width=int(auto_cfg.get("bcs_cut_vlm_frame_width", 640)),
            enable_thinking=bool(auto_cfg.get("bcs_cut_vlm_enable_thinking", False)),
        )
        if "BCS" in selected_metrics
        else None
    )
    tasks = load_tasks()
    run_records = load_run_records(run_dir)
    if args.limit is not None:
        run_records = run_records[: args.limit]

    run_task_ids = {record["task_id"] for record in run_records}
    missing_task_ids = sorted(requested_task_ids - run_task_ids)
    if missing_task_ids:
        parser.error(f"Task ids not found in run: {', '.join(missing_task_ids)}")

    reevaluate_task_ids = requested_task_ids or run_task_ids
    reused_records = load_evaluation_records(args.reuse_eval_id) if args.reuse_eval_id else {}
    if args.reuse_eval_id:
        missing_reused = sorted(run_task_ids - reevaluate_task_ids - set(reused_records))
        if missing_reused:
            parser.error(f"Reusable evaluation {args.reuse_eval_id} is missing tasks: {', '.join(missing_reused)}")

    total_records = len(run_records)
    concurrency = max(1, int(args.concurrency or 1))

    def evaluate_one(idx: int, record: dict[str, Any]) -> tuple[int, dict[str, Any], str | None]:
        task_id = record["task_id"]
        task = tasks[task_id]
        if task_id in reused_records:
            score_record = copy.deepcopy(reused_records[task_id])
            score_record["eval_id"] = eval_id
        else:
            score_record = {
                "eval_id": eval_id,
                "run_id": run_id,
                "task_id": task_id,
                "method": record.get("method"),
                "method_version": record.get("method_version"),
                "status": "success" if record.get("status") == "success" else "skipped",
                "scores": {},
                "metric_details": {},
                "judge": None,
                "rationale": {},
                "cost": {"api_cost_usd": record.get("api_cost_usd")},
                "efficiency": {"wall_clock_sec": record.get("wall_clock_sec")},
            }
        score_record.setdefault("scores", {})
        score_record.setdefault("metric_details", {})
        score_record.setdefault("rationale", {})

        if task_id not in reevaluate_task_ids:
            score_record["scores"]["Quality"] = compute_quality(score_record["scores"], config)
            return idx, score_record, f"[{idx}/{total_records}] reused {task_id}"
        if record.get("status") != "success":
            return idx, score_record, None

        output_video = ROOT / record["output_video"]
        if "BCS" in selected_metrics:
            bcs = beat_cut_synchronization(
                output_video,
                cut_validator=cut_validator,
                adaptive_threshold=float(auto_cfg.get("adaptive_threshold", 2.0)),
                adaptive_min_content_val=float(auto_cfg.get("adaptive_min_content_val", 15.0)),
                adaptive_min_scene_len=int(auto_cfg.get("adaptive_min_scene_len", 5)),
                beat_window_sec=float(auto_cfg.get("beat_window_sec", 0.05)),
                beat_detector=str(auto_cfg.get("bcs_beat_detector", "librosa")),
                librosa_sample_rate=int(auto_cfg.get("bcs_librosa_sample_rate", 22050)),
                librosa_hop_length=int(auto_cfg.get("bcs_librosa_hop_length", 512)),
                tau_sec=float(auto_cfg.get("bcs_tau_sec", 0.196)),
            )
            score_record["scores"]["BCS"] = bcs["score"]
            score_record["metric_details"]["BCS"] = bcs
        if "AEC" in selected_metrics:
            aec = audio_visual_energy_correspondence(
                output_video,
                video_fps=float(auto_cfg.get("video_sample_fps", 2.0)),
                audio_window_sec=float(auto_cfg.get("audio_window_sec", 0.5)),
            )
            score_record["scores"]["AEC"] = aec["score"]
            score_record["metric_details"]["AEC"] = aec

        # Optional human rating. If present, OQ joins the weighted Quality score;
        # otherwise compute_quality renormalizes over the available metrics.
        if "OQ" in selected_metrics:
            human_scores = record.get("human_scores") or {}
            record_scores = record.get("scores") or {}
            oq_score = human_scores.get("OQ", record_scores.get("OQ"))
            if oq_score is not None:
                oq_score = max(1.0, min(5.0, float(oq_score)))
                score_record["scores"]["OQ"] = oq_score
                score_record["metric_details"]["OQ"] = {
                    "source": "human_scores" if "OQ" in human_scores else "scores",
                    "scale": "likert_1_5",
                    "raw_score": oq_score,
                    "normalized_score": normalize_score_for_quality("OQ", oq_score),
                }
            else:
                score_record["scores"].pop("OQ", None)
                score_record["metric_details"].pop("OQ", None)

        selected_vlm_metrics = selected_metrics & VLM_METRICS
        if selected_vlm_metrics:
            judge = VLMJudge(config)
            try:
                vlm_result = judge.score(output_video, task, record)
            except VLMJudgeSkipped as exc:
                for metric in selected_vlm_metrics:
                    score_record["scores"].pop(metric, None)
                    score_record["metric_details"].pop(metric, None)
                    score_record["rationale"].pop(metric, None)
                skip_detail = exc.to_dict()
                score_record["diagnostics"] = {"vlm_skip": skip_detail}
                score_record["judge"] = {
                    "type": "vlm_as_judge",
                    "status": "skipped",
                    "model": exc.model or judge.model,
                    "provider": exc.provider or judge.provider,
                    "input_type": "video",
                    "failure_type": exc.failure_type,
                    "status_code": exc.status_code,
                    "code": exc.code,
                    "request_id": exc.request_id,
                    "message": exc.message,
                }
                message = f"[{idx}/{total_records}] evaluated {task_id} (VLM skipped: {exc.failure_type})"
            else:
                for metric in selected_vlm_metrics:
                    value = vlm_result["scores"][metric]
                    score_record["scores"][metric] = value
                    if metric in (vlm_result.get("rationale") or {}):
                        score_record["rationale"][metric] = vlm_result["rationale"][metric]
                score_record["diagnostics"] = vlm_result.get("diagnostics") or {}
                for metric in selected_vlm_metrics:
                    value = vlm_result["scores"][metric]
                    score_record["metric_details"][metric] = {
                        "scale": vlm_result.get("score_scale"),
                        "raw_score": value,
                        "normalized_score": normalize_score_for_quality(metric, value),
                    }
                score_record["judge"] = {
                    "type": "vlm_as_judge",
                    "status": "success",
                    "model": vlm_result.get("model"),
                    "provider": vlm_result.get("vlm_provider"),
                    "input_type": vlm_result.get("input_type"),
                    "score_scale": vlm_result.get("score_scale"),
                    "video_size_bytes": vlm_result.get("video_size_bytes"),
                    "usage": vlm_result.get("usage"),
                }
                message = f"[{idx}/{total_records}] evaluated {task_id}"
        else:
            message = f"[{idx}/{total_records}] evaluated {task_id}"

        score_record["scores"]["Quality"] = compute_quality(score_record["scores"], config)
        return idx, score_record, message

    indexed_records = list(enumerate(run_records, 1))
    outputs_by_index: dict[int, dict[str, Any]] = {}
    try:
        if concurrency == 1:
            for idx, record in indexed_records:
                result_idx, score_record, message = evaluate_one(idx, record)
                outputs_by_index[result_idx] = score_record
                if message:
                    print(message)
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(evaluate_one, idx, record) for idx, record in indexed_records]
                for future in as_completed(futures):
                    result_idx, score_record, message = future.result()
                    outputs_by_index[result_idx] = score_record
                    if message:
                        print(message)
    finally:
        if cut_validator is not None:
            cut_validator.close()

    outputs = [outputs_by_index[idx] for idx, _record in indexed_records]

    eval_dir.mkdir(parents=True, exist_ok=True)
    scores_path = eval_dir / "evaluation_scores.jsonl"
    with scores_path.open("w", encoding="utf-8") as f:
        for row in outputs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = summarize(outputs)
    vlm_skips = [(row.get("judge") or {}) for row in outputs if (row.get("judge") or {}).get("status") == "skipped"]
    if vlm_skips:
        summary["vlm_judge"] = {
            "skipped_count": len(vlm_skips),
            "skip_reasons": dict(Counter(skip.get("failure_type") or "unknown" for skip in vlm_skips)),
        }
    summary.update(
        {
            "eval_id": eval_id,
            "run_id": run_id,
            "run_dir": str(run_dir.relative_to(ROOT) if run_dir.is_relative_to(ROOT) else run_dir),
            "evaluation_scores": str(scores_path.relative_to(ROOT)),
            "created_at": datetime.now(UTC).astimezone().isoformat(),
            "skip_vlm": args.skip_vlm,
            "reuse_eval_id": args.reuse_eval_id,
            "reevaluated_task_ids": sorted(reevaluate_task_ids) if is_partial else None,
            "reevaluated_metrics": sorted(selected_metrics) if is_partial else None,
        }
    )
    write_json(eval_dir / "summary.json", summary)
    print(f"Wrote {scores_path}")
    print(f"Wrote {eval_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
