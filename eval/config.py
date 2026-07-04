from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "eval" / "config.yaml"
DEFAULT_WEIGHTS = {
    "IF": 0.1000,
    "BCS": 0.2000,
    "AEC": 0.2000,
    "VQ": 0.1000,
    "TC": 0.1000,
    "NC": 0.1000,
    "OQ": 0.2000,
}


def _coerce_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if any(ch in value for ch in [".", "e", "E"]):
            return float(value)
        return int(value)
    except ValueError:
        return value


def load_simple_yaml(path: Path) -> dict[str, Any]:
    """Load the small YAML subset used by this benchmark config.

    PyYAML is used when available. The fallback supports nested dictionaries
    with two-space indentation and scalar values, which is enough for
    eval/config.yaml.
    """
    try:
        import yaml  # type: ignore

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError("config root must be a mapping")
        return data
    except ModuleNotFoundError:
        pass

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, sep, value = line.strip().partition(":")
        if not sep:
            raise ValueError(f"invalid config line: {raw_line}")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip() == "":
            node: dict[str, Any] = {}
            parent[key] = node
            stack.append((indent, node))
        else:
            parent[key] = _coerce_scalar(value)
    return root


def load_config(path: str | Path | None = None, require_vlm: bool = True) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    if not config_path.exists():
        if require_vlm:
            raise FileNotFoundError(
                f"Missing config file: {config_path}. Copy eval/config.example.yaml "
                "to eval/config.yaml and fill in vlm.model/api_key/base_url."
            )
        return {"metrics": {"weights": DEFAULT_WEIGHTS}}
    data = load_simple_yaml(config_path)
    data.setdefault("metrics", {})
    data["metrics"].setdefault("weights", DEFAULT_WEIGHTS)
    data.setdefault("automatic_metrics", {})
    data["automatic_metrics"].setdefault("video_sample_fps", 2.0)
    data["automatic_metrics"].setdefault("audio_window_sec", 0.5)
    data["automatic_metrics"].setdefault("scene_threshold", 0.30)
    data["automatic_metrics"].setdefault("scene_min_gap_sec", 0.25)
    data["automatic_metrics"].setdefault("beat_window_sec", 0.05)
    data["automatic_metrics"].setdefault("bcs_tau_sec", 0.196)
    return data


def weights_from_config(config: dict[str, Any]) -> dict[str, float]:
    raw = config.get("metrics", {}).get("weights", DEFAULT_WEIGHTS)
    weights = {key: float(raw.get(key, DEFAULT_WEIGHTS[key])) for key in DEFAULT_WEIGHTS}
    total = sum(weights.values())
    if total <= 0:
        return DEFAULT_WEIGHTS.copy()
    return {key: value / total for key, value in weights.items()}
