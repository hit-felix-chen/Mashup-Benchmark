#!/usr/bin/env python3
"""Run one benchmark task through CutMaster's public Python entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cutmaster import Orchestrator
from cutmaster.configuration.loader import load_config
from cutmaster.contracts.workflow import WorkflowRequest
from cutmaster.runtime.observability import (
    configure_logging,
    error_summary,
    log_event,
)
from dotenv import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one benchmark task with Orchestrator(config).run(request)."
    )
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--subtitle", type=Path)
    parser.add_argument("--target-duration", type=float, required=True)
    parser.add_argument("--target-shot-length", type=float, required=True)
    parser.add_argument("--prompt-type", required=True)
    parser.add_argument("--video-title", default="")
    parser.add_argument("--max-clip-duration", type=float)
    parser.add_argument(
        "--dialogue-audio",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include original-dialogue anchors in the final audio mix.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.config.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    load_dotenv(config_path.parent / ".env", override=False)
    configure_logging(output_dir / "cutmaster.log", console_color=True)

    request = WorkflowRequest(
        video_path=args.video.resolve(),
        audio_path=args.audio.resolve(),
        prompt=args.prompt,
        output_dir=output_dir,
        target_output_length_sec=args.target_duration,
        target_shot_length_sec=args.target_shot_length,
        prompt_type=args.prompt_type,
        video_title=args.video_title,
        subtitle_path=args.subtitle.resolve() if args.subtitle else None,
        max_clip_duration_sec=args.max_clip_duration,
        audio_mode="dialogue" if args.dialogue_audio else "bgm_only",
        overwrite=args.overwrite,
    )
    try:
        result = Orchestrator(load_config(config_path)).run(request)
    except Exception as exc:
        log_event(
            "ERROR",
            "cutmaster",
            "workflow.fail",
            "CutMaster benchmark task failed",
            error_type=type(exc).__name__,
            reason=error_summary(exc),
        )
        raise
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
