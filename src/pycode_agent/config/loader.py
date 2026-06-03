from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel

from .settings import Settings

# Known config sections -> their pydantic model, used to validate dotted keys.
# Every top-level Settings field is itself a BaseModel section.
_SECTION_MODELS: dict[str, type[BaseModel]] = {
    name: ann
    for name, field in Settings.model_fields.items()
    if isinstance((ann := field.annotation), type) and issubclass(ann, BaseModel)
}


def _split_key(dotted: str) -> tuple[str, str]:
    parts = dotted.split(".")
    if len(parts) != 2:
        raise KeyError(f"config key must be 'section.field': {dotted}")
    section, field = parts
    model = _SECTION_MODELS.get(section)
    if model is None or field not in model.model_fields:
        raise KeyError(f"unknown config key: {dotted}")
    return section, field


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


def get_setting(dotted: str, *, env: dict, user_file: dict,
                project_file: dict) -> tuple[object, str]:
    """Return (value, source) for a dotted config key.

    Source precedence (highest first): project > user > env > default.
    Raises KeyError for unknown keys.
    """
    section, field = _split_key(dotted)
    settings = merge_config(env=env, user_file=user_file, project_file=project_file, cli={})
    value = getattr(getattr(settings, section), field)

    layers = (
        ("project", project_file),
        ("user", user_file),
        ("env", _env_to_nested(env)),
    )
    for source, data in layers:
        if section in data and field in data[section]:
            return value, source
    return value, "default"


def get_setting_for_dir(project_dir: Path, dotted: str) -> tuple[object, str]:
    """get_setting using the same file/env sources as load_settings."""
    return get_setting(
        dotted,
        env=dict(os.environ),
        user_file=_read_toml(Path.home() / ".pycode" / "config.toml"),
        project_file=_read_toml(project_dir / ".pycode" / "config.toml"),
    )


def _coerce(model_field, raw: str):
    """Coerce a string CLI value to the field's declared type."""
    ann = model_field.annotation
    if ann is bool or ann == (bool | None):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if ann is int or ann == (int | None):
        return int(raw)
    if ann is float or ann == (float | None):
        return float(raw)
    return raw


def set_project_setting(project_dir: Path, dotted: str, raw_value: str) -> object:
    """Write a value into the project config file (.pycode/config.toml).

    Returns the coerced value. Raises KeyError for unknown keys.
    """
    section, field = _split_key(dotted)
    model = _SECTION_MODELS[section]
    value = _coerce(model.model_fields[field], raw_value)

    cfg_path = project_dir / ".pycode" / "config.toml"
    data = _read_toml(cfg_path)
    data.setdefault(section, {})[field] = value
    # Validate the merged result before persisting.
    Settings.model_validate(data)

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(_dump_toml(data), encoding="utf-8")
    return value


def _dump_toml(data: dict) -> str:
    """Minimal TOML writer for our flat section/field config."""
    lines: list[str] = []
    for section, fields in data.items():
        lines.append(f"[{section}]")
        for field, value in fields.items():
            lines.append(f"{field} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
