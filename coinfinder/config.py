"""Configuration loading with deep-merge over the packaged defaults."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"


class ConfigError(RuntimeError):
    pass


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ConfigError(f"config file {path} must contain a YAML mapping at the top level")
    return parsed


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the default config, deep-merging a user file over it when given."""
    config = _read_yaml(DEFAULT_CONFIG_PATH)
    if path is not None:
        config = _deep_merge(config, _read_yaml(Path(path)))
    _validate(config)
    return config


def _validate(config: dict[str, Any]) -> None:
    weights = config.get("scoring", {}).get("weights", {})
    if not weights:
        raise ConfigError("scoring.weights must define at least one component")
    for name, value in weights.items():
        if not isinstance(value, (int, float)) or value < 0:
            raise ConfigError(f"scoring.weights.{name} must be a non-negative number, got {value!r}")
    if sum(weights.values()) <= 0:
        raise ConfigError("scoring.weights must sum to more than zero")

    sweet_spot = config.get("scoring", {}).get("age_fit_sweet_spot_hours")
    if not (isinstance(sweet_spot, (list, tuple)) and len(sweet_spot) == 2 and sweet_spot[0] < sweet_spot[1]):
        raise ConfigError("scoring.age_fit_sweet_spot_hours must be [low, high] with low < high")

    chains = config.get("discovery", {}).get("chains")
    if not chains:
        raise ConfigError("discovery.chains must list at least one chain")


def resolve_path(config: dict[str, Any], key: str) -> Path:
    """Resolve a `storage.*` path relative to the repo root when not absolute."""
    raw = config.get("storage", {}).get(key)
    if not raw:
        raise ConfigError(f"storage.{key} is not configured")
    path = Path(raw)
    return path if path.is_absolute() else REPO_ROOT / path
