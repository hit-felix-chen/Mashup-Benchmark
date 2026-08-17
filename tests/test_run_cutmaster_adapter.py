from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_cutmaster as adapter

RELOCATED_MANIFEST = {
    "workflow.result": "result.json",
    "workflow.model_usage": "metadata/usage.json",
    "workflow.log": "logs/workflow.log",
    "analyser.video_result": "metadata/video-analysis.json",
    "analyser.music_result": "metadata/music-analysis.json",
    "analyser.dialogues": "metadata/dialogues.json",
    "analyser.dialogue_subtitle": "metadata/dialogue.srt",
    "planners.render_plan": "metadata/portable-plan.json",
    "planners.raw_script": "metadata/script.json",
    "planners.job_log": "logs/aster.log",
    "renderer.output_video": "media/final.mp4",
}


def _write_manifest_bundle(
    root: Path,
    *,
    manifest: dict[str, str] | None = None,
    version: str = "1.0",
) -> dict[str, str]:
    selected = dict(RELOCATED_MANIFEST if manifest is None else manifest)
    for logical_key, relative_path in selected.items():
        if logical_key == "workflow.result":
            continue
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if logical_key == "renderer.output_video":
            path.write_bytes(b"rendered")
        elif logical_key == "workflow.log":
            path.write_text("managed workflow log\n", encoding="utf-8")
        elif logical_key == "planners.job_log":
            path.write_text("managed ASTER log\n", encoding="utf-8")
        else:
            path.write_text("{}\n", encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    (root / "result.json").write_text(
        json.dumps(
            {
                "status": "success",
                "dialogue_audio_included": False,
                "num_raw_clips": 4,
                "num_planned_clips": 3,
                "stage_timings_sec": {},
                "artifact_manifest_version": version,
                "artifacts": selected,
                "artifact_root": str(root.resolve()),
                "project_id": "project_test",
                "run_id": "run_test",
                "frozen_edit_id": "edit_test",
                "render_variant_id": "render_test",
            }
        ),
        encoding="utf-8",
    )
    return selected


def _write_worker_result(command: list[str], managed_root: Path) -> None:
    _write_manifest_bundle(managed_root)
    payload = json.loads((managed_root / "result.json").read_text(encoding="utf-8"))
    result_file = Path(command[command.index("--result-file") + 1])
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(json.dumps(payload), encoding="utf-8")


def test_worker_process_inherits_stdout_and_stderr(tmp_path: Path, monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_subprocess_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(adapter.subprocess, "run", fake_subprocess_run)

    return_code = adapter.run_command(["python", "worker.py"], tmp_path)

    assert return_code == 7
    assert observed["command"] == ["python", "worker.py"]
    kwargs = observed["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["cwd"] == tmp_path
    assert kwargs["env"]["PYTHONUNBUFFERED"] == "1"
    assert "stdout" not in kwargs
    assert "stderr" not in kwargs


def test_cutmaster_adapter_consumes_artifact_manifest_without_physical_paths(
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
    observed_command: list[str] = []

    def fake_run(command: list[str], _cwd: Path) -> int:
        observed_command.extend(command)
        _write_worker_result(command, project_root / "managed")
        return 0

    monkeypatch.setattr(adapter, "run_command", fake_run)
    monkeypatch.setattr(adapter, "ffprobe_duration", lambda _path: 10.0)
    monkeypatch.setattr(adapter, "repo_info", lambda _path: {"commit": "abc"})
    task = {
        "id": "task_001",
        "video": {
            "id": "video_001",
            "local_path": "media/source.mp4",
            "title_zh": "Source",
            "material_name": "Stable Video",
        },
        "audio": {
            "id": "audio_001",
            "local_path": "media/score.mp3",
            "material_name": "Stable Music",
        },
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
    assert result["target_duration_mode"] == "task"
    assert result["target_output_length_sec"] == 10.0
    assert observed_command[observed_command.index("--target-duration") + 1] == "10.0"
    assert result["artifacts"]["script_raw"].endswith(
        "managed_artifacts/planners/raw_script/script.json"
    )
    assert result["config"]["cutmaster_project_id"] == "project_test"
    assert result["config"]["cutmaster_run_id"] == "run_test"
    backend_log = run_dir / "task_outputs" / "task_001" / "logs" / "backend.log"
    assert backend_log.read_text(encoding="utf-8") == "managed workflow log\n"
    managed_log_copy = (
        run_dir
        / "task_outputs"
        / "task_001"
        / "artifacts"
        / "cutmaster"
        / "managed_artifacts"
        / "planners"
        / "job_log"
        / "aster.log"
    )
    assert managed_log_copy.read_text(encoding="utf-8") == "managed ASTER log\n"
    managed_workflow_log_copy = (
        run_dir
        / "task_outputs"
        / "task_001"
        / "artifacts"
        / "cutmaster"
        / "managed_artifacts"
        / "workflow"
        / "log"
        / "workflow.log"
    )
    assert managed_workflow_log_copy.read_text(encoding="utf-8") == (
        "managed workflow log\n"
    )
    assert result["artifacts"]["backend_log"] == (
        "runs/test/task_outputs/task_001/logs/backend.log"
    )
    assert "--output-dir" not in observed_command
    assert "--result-file" in observed_command
    assert "--video-material-name" in observed_command
    assert observed_command[observed_command.index("--video-material-name") + 1] == ("Stable Video")
    assert observed_command[observed_command.index("--music-material-name") + 1] == ("Stable Music")
    assert "--no-dialogue-audio" in observed_command


def test_material_names_default_to_source_stems(tmp_path: Path, monkeypatch) -> None:
    benchmark_root = tmp_path / "benchmark"
    project_root = tmp_path / "cutmaster"
    run_dir = benchmark_root / "runs" / "test"
    video = benchmark_root / "media" / "source-video.mp4"
    audio = benchmark_root / "media" / "score-track.mp3"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    project_root.mkdir()
    config = project_root / "config.toml"
    config.touch()
    observed_command: list[str] = []

    def fake_run(command: list[str], _cwd: Path) -> int:
        observed_command.extend(command)
        _write_worker_result(command, project_root / "managed")
        return 0

    monkeypatch.setattr(adapter, "run_command", fake_run)
    monkeypatch.setattr(adapter, "ffprobe_duration", lambda _path: 10.0)
    monkeypatch.setattr(adapter, "repo_info", lambda _path: {"commit": "abc"})

    adapter.run_task(
        {
            "id": "task_001",
            "video": {
                "id": "video_001",
                "local_path": "media/source-video.mp4",
                "title_en": "Source",
            },
            "audio": {
                "id": "audio_001",
                "local_path": "media/score-track.mp3",
            },
            "task": {
                "prompt": "Make a montage",
                "type": "event",
                "target_output_length_sec": 10.0,
                "target_shot_length_sec": 2.0,
            },
        },
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

    assert observed_command[observed_command.index("--video-material-name") + 1] == ("source-video")
    assert observed_command[observed_command.index("--music-material-name") + 1] == ("score-track")


def test_music_duration_mode_probes_bgm_and_passes_effective_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark_root = tmp_path / "benchmark"
    project_root = tmp_path / "cutmaster"
    run_dir = benchmark_root / "runs" / "music-duration"
    video = benchmark_root / "media" / "source.mp4"
    audio = benchmark_root / "media" / "full-score.mp3"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    project_root.mkdir()
    config = project_root / "config.toml"
    config.touch()
    observed_command: list[str] = []
    probed: list[Path] = []

    def fake_run(command: list[str], _cwd: Path) -> int:
        observed_command.extend(command)
        _write_worker_result(command, project_root / "managed")
        return 0

    def fake_ffprobe(path: Path) -> float:
        probed.append(path)
        return 111.705896 if path == audio else 111.7

    monkeypatch.setattr(adapter, "run_command", fake_run)
    monkeypatch.setattr(adapter, "ffprobe_duration", fake_ffprobe)
    monkeypatch.setattr(adapter, "repo_info", lambda _path: {"commit": "abc"})

    result = adapter.run_task(
        {
            "id": "task_033",
            "video": {"id": "video_001", "local_path": "media/source.mp4"},
            "audio": {"id": "audio_001", "local_path": "media/full-score.mp3"},
            "task": {
                "prompt": "Make a montage",
                "type": "narrative",
                "target_output_length_sec": 60.0,
                "target_shot_length_sec": 4.0,
            },
        },
        benchmark_root=benchmark_root,
        project_root=project_root,
        python=Path("python"),
        config=config,
        run_dir=run_dir,
        run_id="music-duration",
        method="CutMaster",
        method_version="test",
        overwrite=False,
        subtitle=None,
        dialogue_audio=False,
        target_duration_mode="music",
    )

    assert probed[0] == audio
    assert result["target_duration_mode"] == "music"
    assert result["target_output_length_sec"] == 111.705896
    assert observed_command[observed_command.index("--target-duration") + 1] == "111.705896"


def test_existing_success_requires_matching_duration_mode_and_target(tmp_path: Path) -> None:
    task_dir = tmp_path / "task_033"
    task_dir.mkdir(parents=True)
    (task_dir / "output.mp4").write_bytes(b"old output")
    (task_dir / "run_output.json").write_text(
        json.dumps(
            {
                "status": "success",
                "target_duration_mode": "task",
                "target_output_length_sec": 60.0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="different target duration"):
        adapter.reusable_success_record(
            task_dir,
            overwrite=False,
            target_duration_mode="music",
            target_output_length_sec=111.705896,
        )


def test_legacy_success_without_mode_is_reusable_as_task_mode(tmp_path: Path) -> None:
    task_dir = tmp_path / "task_033"
    task_dir.mkdir(parents=True)
    (task_dir / "output.mp4").write_bytes(b"old output")
    legacy = {"status": "success", "target_output_length_sec": 60.0}
    (task_dir / "run_output.json").write_text(json.dumps(legacy), encoding="utf-8")

    reused = adapter.reusable_success_record(
        task_dir,
        overwrite=False,
        target_duration_mode="task",
        target_output_length_sec=60.0,
    )

    assert reused == legacy


def test_main_leaves_a_fully_reused_run_byte_for_byte_unchanged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark_root = tmp_path / "benchmark"
    project_root = tmp_path / "cutmaster"
    results_root = benchmark_root / "runs"
    run_dir = results_root / "preserved-run"
    task_dir = run_dir / "task_outputs" / "task_001"
    video = benchmark_root / "media" / "source.mp4"
    audio = benchmark_root / "media" / "score.mp3"
    worker = benchmark_root / adapter.CUTMASTER_WORKER_REL
    config = project_root / "config.toml"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    worker.parent.mkdir(parents=True)
    worker.touch()
    project_root.mkdir()
    config.touch()
    task_dir.mkdir(parents=True)
    (task_dir / "output.mp4").write_bytes(b"original output")
    record = {
        "run_id": "preserved-run",
        "method": "CutMaster",
        "method_version": "original-version",
        "task_id": "task_001",
        "video_id": "video_001",
        "audio_id": "audio_001",
        "prompt_type": "event",
        "status": "success",
        "output_video": "runs/preserved-run/task_outputs/task_001/output.mp4",
        "target_duration_mode": "task",
        "target_output_length_sec": 10.0,
        "target_shot_length_sec": 2.0,
        "actual_output_length_sec": 10.0,
        "wall_clock_sec": 123.0,
        "created_at": "2026-08-01T00:00:00+08:00",
    }
    (task_dir / "run_output.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run_outputs.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "preserved-run",
                "method": "CutMaster",
                "method_version": "original-version",
                "benchmark": "Mashup-Benchmark",
                "task_file": "data/tasks/mashup_benchmark.jsonl",
                "created_at": "2026-08-01T00:00:00+08:00",
                "started_at": "2026-08-01T00:00:00+08:00",
                "ended_at": "2026-08-01T00:02:03+08:00",
                "status": "success",
                "num_tasks": 1,
                "num_success": 1,
                "num_failed": 0,
                "run_outputs": "runs/preserved-run/run_outputs.jsonl",
                "code": {"commit": "original-commit", "dirty": False},
                "adapter": {
                    "name": "run_cutmaster",
                    "script": "scripts/run_cutmaster.py",
                    "project_root": "/original/cutmaster",
                    "python": "/original/python",
                    "benchmark_root": "/original/benchmark",
                    "results_root": "runs",
                    "task_selection": {
                        "mode": "task_ids",
                        "task_ids": ["task_001"],
                    },
                    "options": {"target_duration_mode": "task"},
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    task = {
        "id": "task_001",
        "video": {"id": "video_001", "local_path": "media/source.mp4"},
        "audio": {"id": "audio_001", "local_path": "media/score.mp3"},
        "task": {
            "prompt": "Make a montage",
            "type": "event",
            "target_output_length_sec": 10.0,
            "target_shot_length_sec": 2.0,
        },
    }
    monkeypatch.setattr(
        adapter,
        "parse_args",
        lambda: SimpleNamespace(
            benchmark_root=benchmark_root,
            cutmaster_root=project_root,
            cutmaster_python=Path(sys.executable),
            cutmaster_config=config,
            results_root=results_root,
            run_id="preserved-run",
            method="CutMaster",
            method_version="new-version",
            target_duration_mode="task",
            subtitle_path=None,
            overwrite=False,
            dialogue_audio=False,
            list_tasks=False,
            all=False,
            task_id=["task_001"],
        ),
    )
    monkeypatch.setattr(adapter, "load_tasks", lambda _path: [task])
    before = {
        path.relative_to(run_dir): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    assert adapter.main() == 0

    after = {
        path.relative_to(run_dir): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_run_index_preserves_original_generation_metadata_when_appending(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark_root = tmp_path / "benchmark"
    project_root = tmp_path / "cutmaster"
    run_dir = benchmark_root / "runs" / "append-run"
    project_root.mkdir(parents=True)
    records = []
    for number, created_at in ((1, "2026-08-01T00:00:00+08:00"), (2, "2026-08-02T00:00:00+08:00")):
        task_id = f"task_{number:03d}"
        record = {
            "run_id": "append-run",
            "method": "CutMaster",
            "method_version": f"version-{number}",
            "task_id": task_id,
            "status": "success",
            "wall_clock_sec": float(number),
            "api_cost_usd": 0.0,
            "created_at": created_at,
        }
        task_dir = run_dir / "task_outputs" / task_id
        task_dir.mkdir(parents=True)
        (task_dir / "run_output.json").write_text(
            json.dumps(record) + "\n",
            encoding="utf-8",
        )
        records.append(record)
    original_manifest = {
        "run_id": "append-run",
        "method": "CutMaster",
        "method_version": "original-version",
        "benchmark": "Mashup-Benchmark",
        "task_file": "data/tasks/mashup_benchmark.jsonl",
        "created_at": "2026-08-01T00:00:00+08:00",
        "started_at": "2026-08-01T00:00:01+08:00",
        "ended_at": "2026-08-01T00:01:00+08:00",
        "status": "success",
        "num_tasks": 1,
        "run_outputs": "runs/append-run/run_outputs.jsonl",
        "code": {"commit": "original-commit", "dirty": False},
        "environment": {"python": "/original/python"},
        "adapter": {
            "name": "run_cutmaster",
            "script": "scripts/run_cutmaster.py",
            "project_root": "/original/cutmaster",
            "python": "/original/python",
            "benchmark_root": "/original/benchmark",
            "results_root": "runs",
            "task_selection": {"mode": "task_ids", "task_ids": ["task_001"]},
            "options": {"target_duration_mode": "task", "dialogue_audio": False},
        },
        "config": {"original": True},
        "notes": "keep this note",
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps(original_manifest) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        adapter,
        "repo_info",
        lambda _path: pytest.fail("existing code metadata must be preserved"),
    )

    adapter.write_run_index(
        run_dir,
        benchmark_root,
        "append-run",
        "CutMaster",
        "new-version",
        "2026-08-02T00:00:00+08:00",
        project_root,
        Path("/new/python"),
        {
            "name": "run_cutmaster",
            "script": "scripts/run_cutmaster.py",
            "project_root": "/new/cutmaster",
            "python": "/new/python",
            "benchmark_root": "/new/benchmark",
            "results_root": "runs",
            "task_selection": {"mode": "task_ids", "task_ids": ["task_002"]},
            "options": {"target_duration_mode": "task", "dialogue_audio": True},
        },
    )

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["created_at"] == original_manifest["created_at"]
    assert manifest["started_at"] == original_manifest["started_at"]
    assert manifest["method_version"] == "original-version"
    assert manifest["code"] == original_manifest["code"]
    assert manifest["environment"] == original_manifest["environment"]
    assert manifest["config"] == {"original": True}
    assert manifest["notes"] == "keep this note"
    assert manifest["adapter"]["project_root"] == "/original/cutmaster"
    assert manifest["adapter"]["options"] == original_manifest["adapter"]["options"]
    assert manifest["adapter"]["task_selection"] == {
        "mode": "task_ids",
        "task_ids": ["task_001", "task_002"],
    }
    assert manifest["num_tasks"] == 2
    assert manifest["num_success"] == 2
    assert manifest["status"] == "success"


def test_main_records_music_mode_and_effective_target_in_adapter_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    benchmark_root = tmp_path / "benchmark"
    project_root = tmp_path / "cutmaster"
    results_root = benchmark_root / "runs"
    audio = benchmark_root / "media" / "score.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"audio")
    worker = benchmark_root / adapter.CUTMASTER_WORKER_REL
    worker.parent.mkdir(parents=True)
    worker.touch()
    project_root.mkdir()
    config = project_root / "config.toml"
    config.touch()
    task = {
        "id": "task_033",
        "video": {"id": "video_001", "local_path": "media/source.mp4"},
        "audio": {"id": "audio_001", "local_path": "media/score.mp3"},
        "task": {
            "prompt": "Make a montage",
            "type": "narrative",
            "target_output_length_sec": 60.0,
            "target_shot_length_sec": 4.0,
        },
    }
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        adapter,
        "parse_args",
        lambda: SimpleNamespace(
            benchmark_root=benchmark_root,
            cutmaster_root=project_root,
            cutmaster_python=Path(sys.executable),
            cutmaster_config=config,
            results_root=results_root,
            run_id="music-mode",
            method="CutMaster",
            method_version="test",
            target_duration_mode="music",
            subtitle_path=None,
            overwrite=False,
            dialogue_audio=False,
            list_tasks=False,
            all=False,
            task_id=["task_033"],
        ),
    )
    monkeypatch.setattr(adapter, "load_tasks", lambda _path: [task])
    monkeypatch.setattr(adapter, "ffprobe_duration", lambda path: 111.705896 if path == audio else 0.0)

    def fake_run_task(_task, **kwargs):
        observed["run_task"] = kwargs
        return {}

    def fake_write_run_index(*args):
        observed["adapter"] = args[-1]

    monkeypatch.setattr(adapter, "run_task", fake_run_task)
    monkeypatch.setattr(adapter, "write_run_index", fake_write_run_index)

    assert adapter.main() == 0

    run_kwargs = observed["run_task"]
    assert isinstance(run_kwargs, dict)
    assert run_kwargs["target_duration_mode"] == "music"
    assert run_kwargs["target_output_length_sec"] == 111.705896
    manifest_adapter = observed["adapter"]
    assert isinstance(manifest_adapter, dict)
    assert manifest_adapter["options"]["target_duration_mode"] == "music"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/absolute/output.mp4",
        "../outside.mp4",
        "nested/../outside.mp4",
        "nested\\output.mp4",
        "nested//output.mp4",
        "nested/./output.mp4",
        "nested/output.mp4/",
    ],
)
def test_artifact_manifest_rejects_nonportable_paths(
    tmp_path: Path,
    value: str,
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    manifest = dict(RELOCATED_MANIFEST)
    manifest["renderer.output_video"] = value
    result = {
        "artifact_manifest_version": "1.0",
        "artifacts": manifest,
    }

    with pytest.raises((TypeError, ValueError, FileNotFoundError)):
        adapter.resolve_cutmaster_artifacts(root, result)


def test_artifact_manifest_rejects_unsupported_major_and_missing_keys(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()

    with pytest.raises(ValueError, match="Unsupported"):
        adapter.resolve_cutmaster_artifacts(
            root,
            {"artifact_manifest_version": "2.0", "artifacts": {}},
        )
    with pytest.raises(ValueError, match="missing keys"):
        adapter.resolve_cutmaster_artifacts(
            root,
            {"artifact_manifest_version": "1.0", "artifacts": {}},
        )

    manifest_without_log = dict(RELOCATED_MANIFEST)
    manifest_without_log.pop("workflow.log")
    _write_manifest_bundle(root, manifest=manifest_without_log)
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="workflow.log"):
        adapter.resolve_cutmaster_artifacts(root, result)


def test_artifact_manifest_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    manifest = _write_manifest_bundle(root)
    output = root / manifest["renderer.output_video"]
    output.unlink()
    output.symlink_to(outside)
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match="escapes"):
        adapter.resolve_cutmaster_artifacts(root, result)


def test_manifest_accepts_compatible_minor_and_ignores_unknown_keys(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bundle"
    manifest = dict(RELOCATED_MANIFEST)
    manifest["future.optional_artifact"] = "metadata/future.json"
    _write_manifest_bundle(root, manifest=manifest, version="1.7")
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))

    resolved = adapter.resolve_cutmaster_artifacts(root, result)

    assert resolved["future.optional_artifact"] == (root / "metadata" / "future.json").resolve()


def test_adapter_metadata_names_managed_application_entrypoint() -> None:
    assert adapter.CUTMASTER_APPLICATION_ENTRYPOINT == (
        "CutMasterApplication.open(config).workflows.execute_and_wait("
        "ExecuteManagedWorkflowCommand(...))"
    )
