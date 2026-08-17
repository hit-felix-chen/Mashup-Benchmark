from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_narratoai as adapter

MUSIC_DURATION_SEC = 111.705896


def _task() -> dict:
    return {
        "id": "task_033",
        "video": {
            "id": "video_001",
            "local_path": "media/source.mp4",
            "title_en": "Source",
            "category": "film",
        },
        "audio": {
            "id": "audio_011",
            "local_path": "media/score.mp3",
        },
        "task": {
            "prompt": "Make a narrative montage",
            "type": "narrative",
            "target_output_length_sec": 60.0,
            "target_shot_length_sec": 4.0,
        },
    }


def _prepare_roots(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    benchmark_root = tmp_path / "benchmark"
    narratoai_root = tmp_path / "NarratoAI"
    video = benchmark_root / "media" / "source.mp4"
    audio = benchmark_root / "media" / "score.mp3"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    narratoai_root.mkdir()
    return benchmark_root, narratoai_root, video, audio


def _run_dry_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    **duration_options,
) -> tuple[dict, dict]:
    benchmark_root, narratoai_root, _video, _audio = _prepare_roots(tmp_path)
    monkeypatch.setattr(adapter, "repo_info", lambda _path: {"commit": "abc"})

    record = adapter.run_one_task(
        task=_task(),
        benchmark_root=benchmark_root,
        narratoai_root=narratoai_root,
        narratoai_python=Path(sys.executable),
        results_root=benchmark_root / "runs",
        run_id="duration-contract",
        method="NarratoAI",
        method_version="test",
        overwrite=False,
        dry_run=True,
        asr_backend="bailian",
        custom_clips=None,
        max_clip_duration_sec=None,
        bgm_volume=0.3,
        original_volume=1.0,
        video_aspect="16:9",
        n_threads=1,
        subtitle_enabled=False,
        reuse_asr=True,
        **duration_options,
    )
    payload_path = (
        benchmark_root
        / "runs"
        / "duration-contract"
        / "task_outputs"
        / "task_033"
        / "artifacts"
        / "narratoai_payload.json"
    )
    return record, json.loads(payload_path.read_text(encoding="utf-8"))


def test_default_task_mode_uses_canonical_target_in_payload_and_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_probe(_path: Path) -> float:
        raise AssertionError("task mode must not probe the BGM to resolve its target")

    monkeypatch.setattr(adapter, "ffprobe_duration", unexpected_probe)

    record, payload = _run_dry_task(tmp_path, monkeypatch)

    assert payload["target_output_length_sec"] == 60.0
    assert record["target_duration_mode"] == "task"
    assert record["target_output_length_sec"] == 60.0


def test_music_mode_probes_bgm_and_passes_effective_target_to_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark_root, narratoai_root, _video, audio = _prepare_roots(tmp_path)
    probed: list[Path] = []

    def fake_probe(path: Path) -> float:
        probed.append(path)
        return MUSIC_DURATION_SEC

    monkeypatch.setattr(adapter, "ffprobe_duration", fake_probe)
    monkeypatch.setattr(adapter, "repo_info", lambda _path: {"commit": "abc"})

    record = adapter.run_one_task(
        task=_task(),
        benchmark_root=benchmark_root,
        narratoai_root=narratoai_root,
        narratoai_python=Path(sys.executable),
        results_root=benchmark_root / "runs",
        run_id="music-duration",
        method="NarratoAI",
        method_version="test",
        overwrite=False,
        dry_run=True,
        asr_backend="bailian",
        custom_clips=None,
        max_clip_duration_sec=None,
        bgm_volume=0.3,
        original_volume=1.0,
        video_aspect="16:9",
        n_threads=1,
        subtitle_enabled=False,
        reuse_asr=True,
        target_duration_mode="music",
    )
    payload = json.loads(
        (
            benchmark_root
            / "runs"
            / "music-duration"
            / "task_outputs"
            / "task_033"
            / "artifacts"
            / "narratoai_payload.json"
        ).read_text(encoding="utf-8")
    )

    assert probed == [audio]
    assert payload["target_output_length_sec"] == MUSIC_DURATION_SEC
    assert record["target_duration_mode"] == "music"
    assert record["target_output_length_sec"] == MUSIC_DURATION_SEC


def test_legacy_success_without_mode_is_reusable_only_as_task_mode(tmp_path: Path) -> None:
    task_dir = tmp_path / "task_033"
    task_dir.mkdir()
    (task_dir / "output.mp4").write_bytes(b"legacy output")
    legacy = {"status": "success", "target_output_length_sec": 60.0}
    (task_dir / "run_output.json").write_text(json.dumps(legacy), encoding="utf-8")

    reused = adapter.reusable_success_record(
        task_dir,
        overwrite=False,
        target_duration_mode="task",
        target_output_length_sec=60.0,
    )

    assert reused == legacy
    with pytest.raises(RuntimeError, match="different target duration"):
        adapter.reusable_success_record(
            task_dir,
            overwrite=False,
            target_duration_mode="music",
            target_output_length_sec=MUSIC_DURATION_SEC,
        )


def test_run_one_task_reuses_matching_success_without_rewriting_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark_root, narratoai_root, _video, _audio = _prepare_roots(tmp_path)
    task_dir = benchmark_root / "runs" / "legacy-run" / "task_outputs" / "task_033"
    task_dir.mkdir(parents=True)
    (task_dir / "output.mp4").write_bytes(b"existing output")
    legacy = {
        "status": "success",
        "target_output_length_sec": 60.0,
        "started_at": "2026-01-01T00:00:00Z",
        "wall_clock_sec": 123.0,
    }
    original_record = json.dumps(legacy, indent=2)
    record_path = task_dir / "run_output.json"
    record_path.write_text(original_record, encoding="utf-8")
    monkeypatch.setattr(
        adapter,
        "stream_command",
        lambda *_args, **_kwargs: pytest.fail("matching output must not rerun NarratoAI"),
    )
    monkeypatch.setattr(
        adapter,
        "ffprobe_duration",
        lambda _path: pytest.fail("matching output must not be probed or rewritten"),
    )

    reused = adapter.run_one_task(
        task=_task(),
        benchmark_root=benchmark_root,
        narratoai_root=narratoai_root,
        narratoai_python=Path(sys.executable),
        results_root=benchmark_root / "runs",
        run_id="legacy-run",
        method="NarratoAI",
        method_version="test",
        overwrite=False,
        dry_run=False,
        asr_backend="bailian",
        custom_clips=None,
        max_clip_duration_sec=None,
        bgm_volume=0.3,
        original_volume=1.0,
        video_aspect="16:9",
        n_threads=1,
        subtitle_enabled=False,
        reuse_asr=True,
    )

    assert reused == legacy
    assert record_path.read_text(encoding="utf-8") == original_record


def test_duration_mismatch_rejects_preflight_without_touching_existing_success(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task_033"
    task_dir.mkdir()
    output = task_dir / "output.mp4"
    record_path = task_dir / "run_output.json"
    output.write_bytes(b"canonical old output")
    original_record = json.dumps(
        {
            "status": "success",
            "target_duration_mode": "task",
            "target_output_length_sec": 60.0,
        },
        indent=2,
    )
    record_path.write_text(original_record, encoding="utf-8")

    with pytest.raises(RuntimeError, match="different target duration"):
        adapter.reusable_success_record(
            task_dir,
            overwrite=False,
            target_duration_mode="music",
            target_output_length_sec=MUSIC_DURATION_SEC,
        )

    assert output.read_bytes() == b"canonical old output"
    assert record_path.read_text(encoding="utf-8") == original_record


def test_output_without_success_record_is_not_reused(tmp_path: Path) -> None:
    task_dir = tmp_path / "task_033"
    task_dir.mkdir()
    (task_dir / "output.mp4").write_bytes(b"orphan output")

    assert (
        adapter.reusable_success_record(
            task_dir,
            overwrite=False,
            target_duration_mode="task",
            target_output_length_sec=60.0,
        )
        is None
    )


def test_main_mismatch_preflight_does_not_overwrite_existing_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark_root, narratoai_root, _video, audio = _prepare_roots(tmp_path)
    results_root = benchmark_root / "runs"
    task_dir = results_root / "duration-mismatch" / "task_outputs" / "task_033"
    task_dir.mkdir(parents=True)
    output = task_dir / "output.mp4"
    record_path = task_dir / "run_output.json"
    output.write_bytes(b"old task-mode output")
    original_record = json.dumps(
        {
            "status": "success",
            "target_output_length_sec": 60.0,
        },
        indent=2,
    )
    record_path.write_text(original_record, encoding="utf-8")

    monkeypatch.setattr(
        adapter,
        "parse_args",
        lambda: SimpleNamespace(
            task_id=["task_033"],
            all=False,
            list_tasks=False,
            benchmark_root=benchmark_root,
            narratoai_root=narratoai_root,
            narratoai_python=Path(sys.executable),
            results_root=results_root,
            run_id="duration-mismatch",
            method="NarratoAI",
            method_version="test",
            target_duration_mode="music",
            overwrite=False,
            dry_run=False,
            asr_backend="bailian",
            no_reuse_asr=False,
            custom_clips=None,
            max_clip_duration_sec=None,
            bgm_volume=0.3,
            original_volume=1.0,
            video_aspect="16:9",
            n_threads=1,
            subtitle_enabled=False,
            notes=None,
        ),
    )
    monkeypatch.setattr(adapter, "load_tasks", lambda _path: [_task()])
    monkeypatch.setattr(
        adapter,
        "ffprobe_duration",
        lambda path: MUSIC_DURATION_SEC if path == audio else pytest.fail(f"unexpected probe: {path}"),
    )
    monkeypatch.setattr(
        adapter,
        "run_one_task",
        lambda **_kwargs: pytest.fail("duration mismatch must stop before execution"),
    )

    with pytest.raises(SystemExit, match="different target duration"):
        adapter.main()

    assert output.read_bytes() == b"old task-mode output"
    assert record_path.read_text(encoding="utf-8") == original_record
    assert not (results_root / "duration-mismatch" / "run_manifest.json").exists()


def test_main_failure_record_and_manifest_keep_music_duration_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark_root, narratoai_root, _video, audio = _prepare_roots(tmp_path)
    results_root = benchmark_root / "runs"
    task = _task()
    observed_run_options: dict = {}

    monkeypatch.setattr(
        adapter,
        "parse_args",
        lambda: SimpleNamespace(
            task_id=["task_033"],
            all=False,
            list_tasks=False,
            benchmark_root=benchmark_root,
            narratoai_root=narratoai_root,
            narratoai_python=Path(sys.executable),
            results_root=results_root,
            run_id="failed-music-run",
            method="NarratoAI",
            method_version="test",
            target_duration_mode="music",
            overwrite=False,
            dry_run=False,
            asr_backend="bailian",
            no_reuse_asr=False,
            custom_clips=None,
            max_clip_duration_sec=None,
            bgm_volume=0.3,
            original_volume=1.0,
            video_aspect="16:9",
            n_threads=1,
            subtitle_enabled=False,
            notes=None,
        ),
    )
    monkeypatch.setattr(adapter, "load_tasks", lambda _path: [task])
    monkeypatch.setattr(
        adapter,
        "ffprobe_duration",
        lambda path: MUSIC_DURATION_SEC if path == audio else pytest.fail(f"unexpected probe: {path}"),
    )
    monkeypatch.setattr(adapter, "repo_info", lambda _path: {"commit": "abc"})

    def fail_run_one_task(**kwargs) -> dict:
        observed_run_options.update(kwargs)
        raise RuntimeError("intentional adapter failure")

    monkeypatch.setattr(adapter, "run_one_task", fail_run_one_task)

    assert adapter.main() == 1
    assert observed_run_options["target_duration_mode"] == "music"
    assert observed_run_options["target_output_length_sec"] == MUSIC_DURATION_SEC

    run_dir = results_root / "failed-music-run"
    record = json.loads((run_dir / "task_outputs" / "task_033" / "run_output.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert record["status"] == "failed"
    assert record["target_duration_mode"] == "music"
    assert record["target_output_length_sec"] == MUSIC_DURATION_SEC
    assert manifest["adapter"]["options"]["target_duration_mode"] == "music"
