"""Replay the first retained trajectory from an existing CutMaster benchmark.

No model calls. This offline ablation reuses historical retrieval/validation,
and bypasses fresh T and E execution. It is not an online cost measurement.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import datetime
from functools import cache
from pathlib import Path

from cutmaster.configuration.loader import _decode_effective_config
from cutmaster.domain.ids import MaterialId
from cutmaster.domain.materials import MaterialFingerprint, MaterialType
from cutmaster.infrastructure.storage.local.material_catalog import fingerprint_file
from cutmaster.workflow.contracts.material import (
    AnalysedMusicRuntimeHandle,
    AnalysedVideoRuntimeHandle,
    MaterialRuntimeHandle,
    RenderRuntimeBindings,
)
from cutmaster.workflow.contracts.planners import (
    PlannersBrief,
    PlannersOptions,
    PlannersRequest,
    PlannersWorkspace,
)
from cutmaster.workflow.contracts.render_plan import RenderPlan
from cutmaster.workflow.contracts.rendering import (
    RenderOptions,
    RenderOutputTarget,
    RenderRequest,
)
from cutmaster.workflow.planners.replay_ablation import _artifact, replay
from cutmaster.workflow.planners.tools.plan_compiler import compile_render_plan
from cutmaster.workflow.renderer.renderer import Renderer


def now():
    return datetime.now().astimezone().isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


@cache
def verified_fingerprint(path):
    return fingerprint_file(path)


def material_handle(library, catalogue, material_id, expected):
    entry = catalogue[str(material_id)]
    source = (library / entry["source"]).resolve()
    if verified_fingerprint(source) != str(expected):
        raise ValueError(f"Material fingerprint mismatch: {material_id}")
    return MaterialRuntimeHandle(
        MaterialId(str(material_id)),
        MaterialType(entry["type"]),
        entry["name"],
        MaterialFingerprint(str(expected)),
        source,
        (library / entry["analysis"]).resolve(),
    )


def prepare(root, source, destination, library, catalogue, config, *, render_prepared=False):
    preparation_started = time.monotonic()
    script, selection = replay(root, source)
    old_plan = RenderPlan.from_dict(read(_artifact(root, source, "render_plan")))
    video = material_handle(library, catalogue, old_plan.video_material_id, old_plan.video_expected_fingerprint)
    music = material_handle(library, catalogue, old_plan.music_material_id, old_plan.music_expected_fingerprint)
    video_description = read(video.memory_root / "video_description.json")
    music_memory = read(music.memory_root / "music_memory.json")
    profile = read(_artifact(root, source, "music_profile"))
    task = read(_artifact(root, source, "benchmark_task"))
    config = replace(config, renderer=replace(config.renderer, fps=old_plan.fps))
    request = PlannersRequest(
        AnalysedVideoRuntimeHandle(
            video,
            str(video_description["schema_version"]),
            video.memory_root / "video_description.json",
            video.memory_root / "video_summary.json",
            video.memory_root / "dialogues.json",
        ),
        AnalysedMusicRuntimeHandle(
            music,
            str(music_memory["schema_version"]),
            music.memory_root / "music_memory.json",
        ),
        PlannersBrief(task["task"]["prompt"], source["target_output_length_sec"]),
        PlannersOptions(source["target_shot_length_sec"], source["prompt_type"]),
        PlannersWorkspace(destination / "artifacts"),
    )
    if render_prepared:
        saved = read(destination / "artifacts/selection.json")
        if (
            saved["source_plan_id"] != old_plan.plan_id
            or saved["selected_trajectory_ids"] != selection["selected_trajectory_ids"]
            or read(destination / "artifacts/raw_script.json") != script
        ):
            raise ValueError("Prepared plan no longer matches source/first-candidate selection")
        plan = RenderPlan.from_dict(read(destination / "artifacts/render_plan.json"))
        if plan.plan_id != saved["compiled_plan_id"]:
            raise ValueError("Prepared plan identity changed")
    else:
        plan = compile_render_plan(
            request=request,
            raw_script=script,
            music_profile=profile,
            video_description=video_description,
            config=config,
        )
    if plan.total_frames != old_plan.total_frames:
        raise ValueError("Ablation changed output duration")
    if len(plan.clips) != len(old_plan.clips):
        raise ValueError("Ablation changed Slot count")
    for clip, old in zip(plan.clips, old_plan.clips, strict=True):
        if clip["slot_id"] != old["slot_id"] or clip["output_frame_range"] != old["output_frame_range"]:
            raise ValueError("Ablation changed output timeline")
        if old.get("dialogue_anchor") is not None:
            if clip["timestamp"] != old["timestamp"] or clip.get("dialogue_anchor") != old["dialogue_anchor"]:
                raise ValueError("Ablation changed an Anchor")
    selection.update(
        {
            "ablation": "T_E",
            "fresh_T_execution": False,
            "fresh_E_execution": False,
            "historical_candidate_validation_reused": True,
            "source_plan_id": old_plan.plan_id,
            "compiled_plan_id": plan.plan_id,
            "preparation_wall_clock_sec": time.monotonic() - preparation_started,
            "compiled_plan_reused": render_prepared,
            "changed_source_windows": sum(
                a["timestamp"] != b["timestamp"] for a, b in zip(plan.clips, old_plan.clips, strict=True)
            ),
        }
    )
    write(destination / "artifacts/raw_script.json", script)
    write(destination / "artifacts/selection.json", selection)
    plan.write(destination / "artifacts/render_plan.json")
    return plan, RenderRuntimeBindings(video, music), config, selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cutmaster-root", type=Path, required=True)
    parser.add_argument("--source-run", default="cutmaster_overlap_beat")
    parser.add_argument("--run-id", default="cutmaster_overlap_beat_ablation_T_E")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--render-prepared", action="store_true")
    args = parser.parse_args()
    if Path(args.run_id).name != args.run_id or args.run_id in {".", "..", args.source_run}:
        parser.error("run-id must be a new, single directory name")
    root = args.benchmark_root.resolve()
    output = root / "runs" / args.run_id
    if output.exists() and not args.resume:
        parser.error("Destination exists; use --resume only for this ablation")
    if output.exists():
        previous = read(output / "run_manifest.json")
        adapter = previous.get("adapter", {})
        if adapter.get("options", {}).get("source_run", adapter.get("source_run")) != args.source_run:
            parser.error("Destination provenance does not match")

    # Prevent any accidental Python model/provider network request.
    def forbid_network(event, _args):
        if event == "socket.connect":
            raise RuntimeError("Network calls are forbidden in offline ablation")

    sys.addaudithook(forbid_network)
    config_path = args.cutmaster_root / "config.toml"
    config = _decode_effective_config(tomllib.loads(config_path.read_text()), config_path)
    library = config.analyser.material_analysis.material_library_dir.resolve()
    catalogue = {x["material_id"]: x for x in read(library / "manifest.json")["materials"]}
    records = [
        json.loads(line)
        for line in (root / "runs" / args.source_run / "run_outputs.jsonl").read_text().splitlines()
        if line.strip()
    ]
    if len(records) != 40 or any(r["status"] != "success" for r in records):
        raise ValueError("Expected all 40 successful source tasks")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.cutmaster_root, text=True).strip()
    manifest = {
        "run_id": args.run_id,
        "method": "CutMaster",
        "method_version": "offline_ablation_T_E_first_retained",
        "benchmark": "Mashup-Benchmark",
        "task_file": "data/tasks/mashup_benchmark.jsonl",
        "created_at": now(),
        "started_at": now(),
        "status": "running",
        "num_tasks": len(records),
        "num_success": 0,
        "num_failed": 0,
        "run_outputs": f"runs/{args.run_id}/run_outputs.jsonl",
        "code": {"repo": "CutMaster", "commit": commit, "dirty": True},
        "adapter": {
            "name": "run_cutmaster_ablation",
            "script": "scripts/run_cutmaster_ablation.py",
            "project_root": str(args.cutmaster_root.resolve()),
            "python": sys.executable,
            "benchmark_root": str(root),
            "results_root": "runs",
            "task_selection": {"mode": "all", "task_ids": [r["task_id"] for r in records]},
            "options": {"source_run": args.source_run, "ablation": "T_E", "offline": True},
        },
        "notes": "Offline first-retained validated trajectory; no fresh T/E or other model calls. Historical retrieval costs are excluded from incremental cost, not eliminated retroactively.",
    }
    write(output / "run_manifest.json", manifest)
    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    logger.add(output / "generation.log", level="INFO")
    prepared = {}
    for record in records:
        destination = output / "task_outputs" / record["task_id"]
        prepared[record["task_id"]] = prepare(
            root,
            record,
            destination,
            library,
            catalogue,
            config,
            render_prepared=args.render_prepared,
        )
        print(f"PREPARED {record['task_id']}", flush=True)
    if args.prepare_only:
        manifest["notes"] += " Prepared only; no videos rendered yet."
        write(output / "run_manifest.json", manifest)
        return 0
    existing = {}
    if (output / "run_outputs.jsonl").exists():
        existing = {r["task_id"]: r for r in map(json.loads, (output / "run_outputs.jsonl").read_text().splitlines())}
    results = existing.copy()

    def render(record):
        task_id = record["task_id"]
        if task_id in existing and existing[task_id]["status"] == "success":
            return existing[task_id]
        if shutil.disk_usage(output).free < 2 * 1024**3:
            raise RuntimeError("Less than 2 GiB free; stopping before rendering")
        started, stamp = time.monotonic(), now()
        destination = output / "task_outputs" / task_id
        plan, bindings, task_config, selection = prepared[task_id]
        record_out = {
            **record,
            "run_id": args.run_id,
            "method_version": manifest["method_version"],
            "output_video": str((destination / "output.mp4").relative_to(root)),
            "started_at": stamp,
            "created_at": stamp,
            "api_cost_usd": 0,
            "code_commit": commit,
            "artifacts": {
                **{
                    k: str(_artifact(root, record, k).relative_to(root))
                    for k in ["benchmark_task", "edit_plan", "candidate_pool", "planning_segments", "music_profile"]
                },
                **{
                    k: str((destination / "artifacts" / f).relative_to(root))
                    for k, f in [
                        ("script_raw", "raw_script.json"),
                        ("render_plan", "render_plan.json"),
                        ("selection", "selection.json"),
                    ]
                },
            },
            "config": {
                "renderer": asdict(task_config.renderer),
                "dialogue_audio_included": False,
                "provenance": selection,
                "incremental_api_cost_yuan": 0,
            },
            "notes": manifest["notes"],
            "error": None,
        }
        try:
            result = Renderer(task_config.renderer).render(
                RenderRequest(plan, bindings, RenderOptions("bgm_only"), RenderOutputTarget(destination))
            )
            record_out.update(status="success", actual_output_length_sec=result.duration_sec)
            record_out["config"]["stage_timings_sec"] = result.stage_timings_sec
        except Exception as exc:
            record_out.update(
                status="failed", actual_output_length_sec=0, error={"type": type(exc).__name__, "message": str(exc)}
            )
        record_out.update(
            wall_clock_sec=time.monotonic() - started + selection["preparation_wall_clock_sec"],
            ended_at=now(),
        )
        return record_out

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(render, r): r["task_id"] for r in records}
        for future in as_completed(futures):
            result = future.result()
            results[result["task_id"]] = result
            write(output / "task_outputs" / result["task_id"] / "run_output.json", result)
            ordered = [results[k] for k in sorted(results)]
            temporary = output / "run_outputs.jsonl.tmp"
            temporary.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ordered))
            temporary.replace(output / "run_outputs.jsonl")
            manifest["num_success"] = sum(r["status"] == "success" for r in ordered)
            manifest["num_failed"] = sum(r["status"] == "failed" for r in ordered)
            write(output / "run_manifest.json", manifest)
            print(f"FINISHED {result['task_id']} {result['status']} ({len(results)}/40)", flush=True)
    manifest.update(status="success" if manifest["num_failed"] == 0 else "failed", ended_at=now())
    write(output / "run_manifest.json", manifest)
    write(
        output / "ablation_summary.json",
        {
            "run_id": args.run_id,
            "source_run_id": args.source_run,
            "status": manifest["status"],
            "num_tasks": len(records),
            "num_success": manifest["num_success"],
            "num_failed": manifest["num_failed"],
            "changed_tasks": sum(value[3]["changed_slots"] > 0 for value in prepared.values()),
            "changed_slots": sum(value[3]["changed_slots"] for value in prepared.values()),
            "total_slots": sum(len(value[0].clips) for value in prepared.values()),
            "anchors_preserved": True,
            "output_timelines_preserved": True,
            "additional_api_requests": 0,
            "additional_api_cost_yuan": 0,
            "historical_retrieval_and_validation_reused": True,
            "evaluation_run": False,
            "rendering_task_seconds_sum": sum(
                r["config"].get("stage_timings_sec", {}).get("rendering", 0) for r in results.values()
            ),
        },
    )
    return int(manifest["num_failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
