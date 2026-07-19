from __future__ import annotations

import array
import json
import math
import re
import subprocess
from pathlib import Path


def run_cmd(cmd: list[str], *, input_bytes: bytes | None = None, timeout: int | None = None) -> bytes:
    proc = subprocess.run(
        cmd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{stderr}")
    return proc.stdout


def run_cmd_capture_stderr(cmd: list[str], *, input_bytes: bytes | None = None, timeout: int | None = None) -> tuple[bytes, bytes]:
    proc = subprocess.run(
        cmd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{stderr}")
    return proc.stdout, proc.stderr


def ffprobe_duration(path: Path) -> float:
    out = run_cmd([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(out.decode("utf-8").strip())


def has_audio_stream(path: Path) -> bool:
    out = run_cmd([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=index", "-of", "json", str(path),
    ])
    info = json.loads(out.decode("utf-8") or "{}")
    return bool(info.get("streams"))


def audio_rms_series(path: Path, *, sample_rate: int = 16000, window_sec: float = 0.5) -> list[float]:
    if not has_audio_stream(path):
        return []
    raw = run_cmd([
        "ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "-",
    ])
    samples = array.array("h")
    samples.frombytes(raw)
    if not samples:
        return []
    window = max(1, int(sample_rate * window_sec))
    values: list[float] = []
    for start in range(0, len(samples), window):
        chunk = samples[start:start + window]
        if not chunk:
            continue
        energy = math.sqrt(sum((s / 32768.0) ** 2 for s in chunk) / len(chunk))
        values.append(energy)
    return values


def audio_float_samples(path: Path, *, sample_rate: int = 22050) -> tuple[object, int]:
    if not has_audio_stream(path):
        import numpy as np

        return np.array([], dtype="float32"), sample_rate
    raw = run_cmd([
        "ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "f32le", "-",
    ])
    import numpy as np

    return np.frombuffer(raw, dtype="<f4"), sample_rate


def _read_ppm_frames(blob: bytes):
    idx = 0
    n = len(blob)
    while idx < n:
        if not blob.startswith(b"P6", idx):
            break
        idx += 2
        if idx < n and blob[idx] in b"\r\n":
            idx += 1
            if idx < n and blob[idx - 1] == 13 and blob[idx] == 10:
                idx += 1

        tokens: list[bytes] = []
        while len(tokens) < 3 and idx < n:
            while idx < n and blob[idx] in b" \t\r\n":
                idx += 1
            if idx < n and blob[idx] == ord("#"):
                while idx < n and blob[idx] not in b"\r\n":
                    idx += 1
                continue
            start = idx
            while idx < n and blob[idx] not in b" \t\r\n":
                idx += 1
            tokens.append(blob[start:idx])
        if len(tokens) < 3:
            break
        width, height, maxval = map(int, tokens)
        if maxval != 255:
            raise ValueError(f"only 8-bit PPM frames are supported; got maxval={maxval}")
        # PPM P6 has exactly one whitespace byte after maxval. Do not skip
        # arbitrary whitespace here because the following payload is binary and
        # can legitimately start with space/newline-valued pixel bytes.
        if idx < n and blob[idx] in b" \t\r\n":
            idx += 1
            if idx < n and blob[idx - 1] == 13 and blob[idx] == 10:
                idx += 1
        size = width * height * 3
        frame = blob[idx:idx + size]
        if len(frame) < size:
            break
        yield frame
        idx += size


def video_motion_series(path: Path, *, fps: float = 2.0, width: int = 320) -> list[float]:
    # Use raw rgb24 frames instead of PPM so 10-bit/HDR inputs cannot surface as
    # 16-bit PPM payloads.
    vf = f"fps={fps},scale={width}:-2,format=rgb24"
    blob, stderr = run_cmd_capture_stderr([
        "ffmpeg", "-v", "info", "-i", str(path), "-vf", vf,
        "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])
    match = re.search(rb"Video: rawvideo.*?, rgb24.*?, (\d+)x(\d+)", stderr)
    if not match:
        stderr_text = stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"could not determine rawvideo frame size from ffmpeg output\n{stderr_text}")
    out_width = int(match.group(1))
    out_height = int(match.group(2))
    frame_size = out_width * out_height * 3
    if frame_size <= 0:
        return []

    prev: bytes | None = None
    values: list[float] = []
    for start in range(0, len(blob) - frame_size + 1, frame_size):
        frame = blob[start:start + frame_size]
        if prev is not None:
            step = max(1, len(frame) // 50000)
            diff = sum(abs(frame[i] - prev[i]) for i in range(0, min(len(frame), len(prev)), step))
            count = max(1, len(range(0, min(len(frame), len(prev)), step)))
            values.append(diff / (count * 255.0))
        prev = frame
    return values


def detect_visual_cuts(
    path: Path,
    *,
    adaptive_threshold: float = 2.0,
    adaptive_min_content_val: float = 15.0,
    adaptive_min_scene_len: int = 5,
) -> list[float]:
    """Detect cuts from every frame of the rendered video with an adaptive content detector."""
    from scenedetect import SceneManager, open_video
    from scenedetect.detectors import AdaptiveDetector

    video = open_video(str(path))
    manager = SceneManager()
    manager.add_detector(
        AdaptiveDetector(
            adaptive_threshold=adaptive_threshold,
            min_content_val=adaptive_min_content_val,
            min_scene_len=adaptive_min_scene_len,
        )
    )
    manager.detect_scenes(video, show_progress=False)
    scenes = manager.get_scene_list(start_in_scene=True)
    return [start.seconds for start, _ in scenes[1:]]


def detect_audio_beats(path: Path, *, window_sec: float = 0.05) -> list[float]:
    rms = audio_rms_series(path, window_sec=window_sec)
    if len(rms) < 3:
        return []
    mean = sum(rms) / len(rms)
    std = math.sqrt(sum((v - mean) ** 2 for v in rms) / len(rms))
    threshold = mean + 0.35 * std
    min_gap = max(1, int(0.30 / window_sec))
    beats: list[float] = []
    last_idx = -min_gap
    for i in range(1, len(rms) - 1):
        if i - last_idx < min_gap:
            continue
        if rms[i] >= threshold and rms[i] >= rms[i - 1] and rms[i] >= rms[i + 1]:
            beats.append(i * window_sec)
            last_idx = i
    return beats


def detect_audio_beats_librosa(
    path: Path,
    *,
    sample_rate: int = 22050,
    hop_length: int = 512,
) -> list[float]:
    y, sr = audio_float_samples(path, sample_rate=sample_rate)
    if len(y) < hop_length * 4:
        return []

    import librosa

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    _, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=hop_length,
        units="frames",
        trim=False,
    )
    if len(beat_frames) == 0:
        return []

    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
    return [float(t) for t in beat_times]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    xs = xs[:n]
    ys = ys[:n]
    mx = sum(xs) / n
    my = sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 1e-12 or vy <= 1e-12:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def extract_evenly_spaced_frames(path: Path, out_dir: Path, *, max_frames: int = 8) -> list[Path]:
    duration = ffprobe_duration(path)
    if duration <= 0:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    if max_frames <= 1:
        times = [duration / 2]
    else:
        pad = min(1.0, duration * 0.05)
        start = pad
        end = max(start, duration - pad)
        times = [start + (end - start) * i / (max_frames - 1) for i in range(max_frames)]
    paths: list[Path] = []
    for idx, t in enumerate(times):
        out = out_dir / f"frame_{idx:03d}.jpg"
        run_cmd([
            "ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
            "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", str(out),
        ])
        if out.exists() and out.stat().st_size > 0:
            paths.append(out)
    return paths
