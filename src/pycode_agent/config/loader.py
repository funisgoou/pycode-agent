from __future__ import annotations
import os
import tomllib
from pathlib import Path
from .settings import Settings


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _env_to_nested(env: dict[str, str]) -> dict:
    """PYCODE_MODEL_NAME=x -> {'model': {'name': 'x'}}; only known top sections."""
    sections = {"model", "security", "context", "agent"}
    out: dict = {}
    for key, val in env.items():
        if not key.startswith("PYCODE_"):
            continue
        parts = key[len("PYCODE_"):].lower().split("_", 1)
        if len(parts) != 2 or parts[0] not in sections:
            continue
        out.setdefault(parts[0], {})[parts[1]] = val
    return out


def merge_config(*, env: dict, user_file: dict, project_file: dict, cli: dict) -> Settings:
    merged: dict = {}
    for layer in (_env_to_nested(env), user_file, project_file, cli):
        merged = _deep_merge(merged, layer)
    return Settings.model_validate(merged)


def _read_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def load_settings(project_dir: Path, cli_overrides: dict | None = None) -> Settings:
    user_file = _read_toml(Path.home() / ".pycode" / "config.toml")
    project_file = _read_toml(project_dir / ".pycode" / "config.toml")
    return merge_config(
        env=dict(os.environ),
        user_file=user_file,
        project_file=project_file,
        cli=cli_overrides or {},
    )
