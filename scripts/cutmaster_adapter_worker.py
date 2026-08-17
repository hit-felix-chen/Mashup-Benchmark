#!/usr/bin/env python3
"""Run one benchmark task through CutMaster's managed local workflow."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from cutmaster import CutMasterApplication
from cutmaster.application.workflow import ExecuteManagedWorkflowCommand


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one benchmark task as Web-visible managed CutMaster history."
    )
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--subtitle", type=Path)
    parser.add_argument("--target-duration", type=float, required=True)
    parser.add_argument("--target-shot-length", type=float, required=True)
    parser.add_argument("--prompt-type", required=True)
    parser.add_argument("--video-title", default="")
    parser.add_argument("--video-material-name", default="")
    parser.add_argument("--music-material-name", default="")
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--max-clip-duration", type=float)
    parser.add_argument(
        "--dialogue-audio",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include original-dialogue anchors in the final audio mix.",
    )
    return parser


def build_command(args: argparse.Namespace) -> ExecuteManagedWorkflowCommand:
    return ExecuteManagedWorkflowCommand(
        video_path=args.video.resolve(),
        audio_path=args.audio.resolve(),
        prompt=args.prompt,
        project_name=args.project_name,
        target_output_length_sec=args.target_duration,
        target_shot_length_sec=args.target_shot_length,
        prompt_type=args.prompt_type,
        video_title=args.video_title,
        subtitle_path=args.subtitle.resolve() if args.subtitle else None,
        max_clip_duration_sec=args.max_clip_duration,
        audio_mode="dialogue" if args.dialogue_audio else "bgm_only",
        video_material_name=args.video_material_name,
        music_material_name=args.music_material_name,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.config.resolve()
    result_file = args.result_file.resolve()
    result_file.parent.mkdir(parents=True, exist_ok=True)

    command = build_command(args)
    try:
        application = CutMasterApplication.open(config_path)
        result = application.workflows.execute_and_wait(command)
    except Exception as exc:
        print(
            f"CutMaster benchmark task failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise
    payload = result.to_dict()
    descriptor, temporary_name = tempfile.mkstemp(
        dir=result_file.parent,
        prefix=f".{result_file.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(result_file)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
