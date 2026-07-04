#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.aggregate_scores import compute_quality, normalize_score_for_quality, summarize
from eval.config import load_config
from eval.evaluators.vlm_judge import VLMJudge
from eval.metrics.alignment import audio_visual_energy_correspondence, beat_cut_synchronization

ROOT = Path(__file__).resolve().parents[1]
TASK_FILE = ROOT / "data" / "tasks" / "mashup_benchmark.jsonl"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one Mashup-Benchmark run.")
    parser.add_argument("--run", required=True, help="Path to runs/<run_id>.")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to evaluator config YAML.")
    parser.add_argument("--eval-id", default=None, help="Evaluation id. Defaults to <run_id>_eval_<timestamp>.")
    parser.add_argument("--skip-vlm", action="store_true", help="Only compute automatic BCS/AEC metrics.")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N records for smoke tests.")
    args = parser.parse_args()

    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    run_id = run_dir.name
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d_%H%M%S")
    eval_id = args.eval_id or f"{run_id}_eval_{timestamp}"
    eval_dir = ROOT / "eval_results" / eval_id

    config = load_config(args.config, require_vlm=not args.skip_vlm)
    auto_cfg = config.get("automatic_metrics", {})
    tasks = load_tasks()
    run_records = load_run_records(run_dir)
    if args.limit is not None:
        run_records = run_records[: args.limit]

    judge = None if args.skip_vlm else VLMJudge(config)
    outputs = []
    for idx, record in enumerate(run_records, 1):
        task_id = record["task_id"]
        task = tasks[task_id]
        score_record: dict[str, Any] = {
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
        if record.get("status") != "success":
            outputs.append(score_record)
            continue

        output_video = ROOT / record["output_video"]
        bcs = beat_cut_synchronization(
            output_video,
            scene_threshold=float(auto_cfg.get("scene_threshold", 0.30)),
            scene_min_gap_sec=float(auto_cfg.get("scene_min_gap_sec", 0.25)),
            beat_window_sec=float(auto_cfg.get("beat_window_sec", 0.05)),
            tau_sec=float(auto_cfg.get("bcs_tau_sec", 0.196)),
        )
        aec = audio_visual_energy_correspondence(
            output_video,
            video_fps=float(auto_cfg.get("video_sample_fps", 2.0)),
            audio_window_sec=float(auto_cfg.get("audio_window_sec", 0.5)),
        )
        score_record["scores"]["BCS"] = bcs["score"]
        score_record["scores"]["AEC"] = aec["score"]
        score_record["metric_details"]["BCS"] = bcs
        score_record["metric_details"]["AEC"] = aec

        # Optional human rating. If present, OQ joins the weighted Quality score;
        # otherwise compute_quality renormalizes over the available metrics.
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

        if judge is not None:
            vlm_result = judge.score(output_video, task, record)
            score_record["scores"].update(vlm_result["scores"])
            score_record["rationale"].update(vlm_result.get("rationale") or {})
            score_record["diagnostics"] = vlm_result.get("diagnostics") or {}
            for metric, value in vlm_result["scores"].items():
                score_record["metric_details"][metric] = {
                    "scale": vlm_result.get("score_scale"),
                    "raw_score": value,
                    "normalized_score": normalize_score_for_quality(metric, value),
                }
            score_record["judge"] = {
                "type": "vlm_as_judge",
                "model": vlm_result.get("model"),
                "provider": vlm_result.get("vlm_provider"),
                "input_type": vlm_result.get("input_type"),
                "score_scale": vlm_result.get("score_scale"),
                "video_size_bytes": vlm_result.get("video_size_bytes"),
                "usage": vlm_result.get("usage"),
            }

        score_record["scores"]["Quality"] = compute_quality(score_record["scores"], config)
        outputs.append(score_record)
        print(f"[{idx}/{len(run_records)}] evaluated {task_id}")

    eval_dir.mkdir(parents=True, exist_ok=True)
    scores_path = eval_dir / "evaluation_scores.jsonl"
    with scores_path.open("w", encoding="utf-8") as f:
        for row in outputs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = summarize(outputs)
    summary.update({
        "eval_id": eval_id,
        "run_id": run_id,
        "run_dir": str(run_dir.relative_to(ROOT) if run_dir.is_relative_to(ROOT) else run_dir),
        "evaluation_scores": str(scores_path.relative_to(ROOT)),
        "created_at": datetime.now(UTC).astimezone().isoformat(),
        "skip_vlm": args.skip_vlm,
    })
    write_json(eval_dir / "summary.json", summary)
    print(f"Wrote {scores_path}")
    print(f"Wrote {eval_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
