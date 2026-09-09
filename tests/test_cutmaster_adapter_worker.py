from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.cutmaster_adapter_worker as worker

build_command = worker.build_command
build_parser = worker.build_parser

WORKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cutmaster_adapter_worker.py"


def test_worker_builds_real_managed_command_and_defaults_to_bgm_only(
    tmp_path: Path,
) -> None:
    video = tmp_path / "source.mp4"
    audio = tmp_path / "score.mp3"
    result_file = tmp_path / "adapter-result.json"
    config = tmp_path / "config.toml"
    args = build_parser().parse_args(
        [
            "--video",
            str(video),
            "--audio",
            str(audio),
            "--prompt",
            "A story",
            "--result-file",
            str(result_file),
            "--config",
            str(config),
            "--target-duration",
            "60",
            "--target-shot-length",
            "4",
            "--prompt-type",
            "event",
            "--video-material-name",
            "Stable Video",
            "--music-material-name",
            "Stable Music",
            "--project-name",
            "Benchmark · test · task_001",
        ]
    )

    command = build_command(args)

    assert command.video_path == video.resolve()
    assert command.audio_path == audio.resolve()
    assert command.project_name == "Benchmark · test · task_001"
    assert command.video_material_name == "Stable Video"
    assert command.music_material_name == "Stable Music"
    assert command.audio_mode == "bgm_only"


def test_worker_preserves_all_legacy_subprocess_arguments(
    tmp_path: Path,
) -> None:
    subtitle = tmp_path / "dialogue.srt"
    args = build_parser().parse_args(
        [
            *_worker_argv(tmp_path),
            "--subtitle",
            str(subtitle),
            "--video-title",
            "Source title",
            "--max-clip-duration",
            "7.5",
            "--dialogue-audio",
        ]
    )

    command = build_command(args)

    assert command.prompt == "A story"
    assert command.subtitle_path == subtitle.resolve()
    assert command.target_output_length_sec == 60.0
    assert command.target_shot_length_sec == 4.0
    assert command.prompt_type == "event"
    assert command.video_title == "Source title"
    assert command.max_clip_duration_sec == 7.5
    assert command.audio_mode == "dialogue"
    assert command.video_material == ""
    assert command.music_material == ""


def test_worker_no_longer_imports_legacy_workflow_entrypoints() -> None:
    tree = ast.parse(WORKER_PATH.read_text(encoding="utf-8"))
    imported_names = {
        alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    }

    assert "CutMasterApplication" in imported_names
    assert "ExecuteManagedWorkflowCommand" in imported_names
    assert "LocalManagedWorkflow" not in imported_names
    assert "Orchestrator" not in imported_names
    assert "WorkflowRequest" not in imported_names
    assert "load_config" not in imported_names


def _worker_argv(tmp_path: Path) -> list[str]:
    return [
        "--video",
        str(tmp_path / "source.mp4"),
        "--audio",
        str(tmp_path / "score.mp3"),
        "--prompt",
        "A story",
        "--result-file",
        str(tmp_path / "adapter-result.json"),
        "--config",
        str(tmp_path / "config.toml"),
        "--target-duration",
        "60",
        "--target-shot-length",
        "4",
        "--prompt-type",
        "event",
        "--project-name",
        "Benchmark · test · task_001",
    ]


def test_worker_anchor_flag_defaults_on_and_can_disable(tmp_path):
    for flags, expected in (([], True), (["--no-anchor"], False), (["--anchor"], True)):
        args = worker.build_parser().parse_args(_worker_argv(tmp_path) + flags)
        assert worker.build_command(args).anchor_enabled is expected


def test_worker_prints_workflow_result_json_and_returns_zero(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    observed: dict[str, object] = {}

    class FakeManaged:
        def execute_and_wait(self, command):
            observed["command"] = command
            return SimpleNamespace(to_dict=lambda: {"status": "success", "output_video": "final.mp4"})

    def open_application(config_path: Path):
        observed["config"] = config_path
        application = SimpleNamespace(workflows=FakeManaged())
        observed["application"] = application
        return application

    monkeypatch.setattr(
        worker,
        "CutMasterApplication",
        SimpleNamespace(open=open_application),
    )
    exit_code = worker.main(_worker_argv(tmp_path))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "status": "success",
        "output_video": "final.mp4",
    }
    assert captured.err == ""
    assert json.loads((tmp_path / "adapter-result.json").read_text()) == {
        "status": "success",
        "output_video": "final.mp4",
    }
    assert observed["config"] == (tmp_path / "config.toml").resolve()
    assert observed["command"].audio_mode == "bgm_only"


def test_worker_reports_and_reraises_application_failure(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    class FailingManaged:
        def execute_and_wait(self, _command):
            raise RuntimeError("service unavailable")

    monkeypatch.setattr(
        worker,
        "CutMasterApplication",
        SimpleNamespace(
            open=lambda _config: SimpleNamespace(workflows=FailingManaged())
        ),
    )

    with pytest.raises(RuntimeError, match="service unavailable"):
        worker.main(_worker_argv(tmp_path))

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "CutMaster benchmark task failed: RuntimeError: service unavailable" in captured.err
