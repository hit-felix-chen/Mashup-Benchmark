#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.config import load_config
from eval.evaluators.specified_metrics_judge import SpecifiedMetricsJudge
from eval.run_evaluation import ROOT, load_run_records, load_tasks, write_json


def summarize_specified_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_metric: dict[str, list[float]] = defaultdict(list)
    by_type_metric: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    by_type: dict[str, list[float]] = defaultdict(list)

    for record in records:
        if record.get("status") != "success":
            continue
        task_type = str(record.get("task_type") or "unknown")
        values = []
        for metric, value in (record.get("scores") or {}).items():
            score = float(value)
            by_metric[metric].append(score)
            by_type_metric[task_type][metric].append(score)
            values.append(score)
        if values:
            by_type[task_type].append(sum(values) / len(values))

    def stats(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"mean": None, "min": None, "max": None, "count": 0}
        return {
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "count": len(values),
        }

    return {
        "num_records": len(records),
        "metrics": {metric: stats(values) for metric, values in sorted(by_metric.items())},
        "task_types": {
            task_type: {
                "mean_diagnostic_score": stats(values),
                "metrics": {metric: stats(metric_values) for metric, metric_values in sorted(metrics.items())},
            }
            for task_type, metrics in sorted(by_type_metric.items())
            for values in [by_type.get(task_type, [])]
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate prompt-specified Mashup-Benchmark metrics for one run.")
    parser.add_argument("--run", required=True, help="Path to runs/<run_id>.")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to evaluator config YAML.")
    parser.add_argument("--specified-metrics-id", default=None, help="Specified-metrics id. Defaults to <run_id>_specified_metrics_<timestamp>.")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N records for smoke tests.")
    args = parser.parse_args()

    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    run_id = run_dir.name
    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d_%H%M%S")
    specified_metrics_id = args.specified_metrics_id or f"{run_id}_specified_metrics_{timestamp}"
    specified_metrics_dir = ROOT / "eval_results" / specified_metrics_id

    config = load_config(args.config, require_vlm=True)
    tasks = load_tasks()
    run_records = load_run_records(run_dir)
    if args.limit is not None:
        run_records = run_records[: args.limit]

    judge = SpecifiedMetricsJudge(config)
    outputs: list[dict[str, Any]] = []
    for idx, record in enumerate(run_records, 1):
        task_id = record["task_id"]
        task = tasks[task_id]
        output: dict[str, Any] = {
            "specified_metrics_id": specified_metrics_id,
            "run_id": run_id,
            "task_id": task_id,
            "method": record.get("method"),
            "method_version": record.get("method_version"),
            "task_type": task["task"]["type"],
            "status": "success" if record.get("status") == "success" else "skipped",
            "scores": {},
            "metric_details": {},
            "rationale": {},
            "diagnostics": {},
            "judge": None,
            "cost": {"api_cost_usd": record.get("api_cost_usd")},
            "efficiency": {"wall_clock_sec": record.get("wall_clock_sec")},
        }
        if record.get("status") != "success":
            outputs.append(output)
            continue

        output_video = ROOT / record["output_video"]
        result = judge.score_specified_metricsnostics(output_video, task, record)
        output["scores"] = result["scores"]
        output["metric_details"] = result["metric_details"]
        output["rationale"] = result.get("rationale") or {}
        output["diagnostics"] = result.get("diagnostics") or {}
        output["judge"] = {
            "type": "vlm_specified_metrics",
            "model": result.get("model"),
            "provider": result.get("vlm_provider"),
            "input_type": result.get("input_type"),
            "score_scale": result.get("score_scale"),
            "video_size_bytes": result.get("video_size_bytes"),
            "usage": result.get("usage"),
        }
        outputs.append(output)
        print(f"[{idx}/{len(run_records)}] specified-metrics evaluated {task_id} ({output['task_type']})")

    specified_metrics_dir.mkdir(parents=True, exist_ok=True)
    scores_path = specified_metrics_dir / "specified_metricsnostic_scores.jsonl"
    with scores_path.open("w", encoding="utf-8") as f:
        for row in outputs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = summarize_specified_metrics(outputs)
    summary.update({
        "specified_metrics_id": specified_metrics_id,
        "run_id": run_id,
        "run_dir": str(run_dir.relative_to(ROOT) if run_dir.is_relative_to(ROOT) else run_dir),
        "specified_metricsnostic_scores": str(scores_path.relative_to(ROOT)),
        "created_at": datetime.now(UTC).astimezone().isoformat(),
    })
    write_json(specified_metrics_dir / "specified_metricsnostic_summary.json", summary)
    print(f"Wrote {scores_path}")
    print(f"Wrote {specified_metrics_dir / 'specified_metricsnostic_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
