from __future__ import annotations

import json
from pathlib import Path

import scripts.run_cutmaster as adapter


def test_cutmaster_adapter_reads_three_stage_artifact_layout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark_root = tmp_path / "benchmark"
    project_root = tmp_path / "cutmaster"
    run_dir = benchmark_root / "runs" / "test"
    video = benchmark_root / "media" / "source.mp4"
    audio = benchmark_root / "media" / "score.mp3"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    project_root.mkdir()
    config = project_root / "config.toml"
    config.write_text("", encoding="utf-8")

    def fake_stream(command: list[str], log_path: Path, _cwd: Path) -> int:
        work_dir = Path(command[command.index("--output-dir") + 1])
        paths = [
            work_dir / "analyser" / "analysis_result.json",
            work_dir / "analyser" / "dialogues.json",
            work_dir / "analyser" / "dialogue_merged.srt",
            work_dir / "analyser" / "music" / "music_analysis_result.json",
            work_dir / "planners" / "planners_result.json",
            work_dir / "planners" / "script_raw.json",
            work_dir / "planners" / "render_plan.json",
            work_dir / "renderer" / "render_result.json",
        ]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        (work_dir / "renderer" / "output.mp4").write_bytes(b"rendered")
        (work_dir / "result.json").write_text(
            json.dumps(
                {
                    "dialogue_audio_included": False,
                    "num_raw_clips": 4,
                    "num_planned_clips": 3,
                    "stage_timings_sec": {},
                }
            ),
            encoding="utf-8",
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(adapter, "stream_command", fake_stream)
    monkeypatch.setattr(adapter, "ffprobe_duration", lambda _path: 10.0)
    monkeypatch.setattr(adapter, "repo_info", lambda _path: {"commit": "abc"})
    task = {
        "id": "task_001",
        "video": {
            "id": "video_001",
            "local_path": "media/source.mp4",
            "title_zh": "Source",
        },
        "audio": {"id": "audio_001", "local_path": "media/score.mp3"},
        "task": {
            "prompt": "Make a montage",
            "type": "event",
            "target_output_length_sec": 10.0,
            "target_shot_length_sec": 2.0,
        },
    }

    result = adapter.run_task(
        task,
        benchmark_root=benchmark_root,
        project_root=project_root,
        python=Path("python"),
        config=config,
        run_dir=run_dir,
        run_id="test",
        method="CutMaster",
        method_version="test",
        overwrite=False,
        subtitle=None,
        dialogue_audio=False,
    )

    output = run_dir / "task_outputs" / "task_001" / "output.mp4"
    assert output.read_bytes() == b"rendered"
    assert result["config"]["num_planned_clips"] == 3
    assert result["artifacts"]["script_raw"].endswith(
        "artifacts/cutmaster/planners/script_raw.json"
    )
    assert result["artifacts"]["planners_result"].endswith(
        "artifacts/cutmaster/planners/planners_result.json"
    )
    assert result["artifacts"]["render_result"].endswith(
        "artifacts/cutmaster/renderer/render_result.json"
    )
