from __future__ import annotations

from pathlib import Path
from typing import Any


def load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}

    file_path = Path(path)
    if not file_path.exists():
        return {}

    return _load_toml(file_path)


def get_nested_str(data: dict[str, Any], section: str, key: str) -> str:
    section_data = data.get(section)
    if not isinstance(section_data, dict):
        return ""

    value = section_data.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError as exc:
        raise RuntimeError("tomllib is unavailable. Please use Python 3.11+.") from exc

    with path.open("rb") as f:
        data = tomllib.load(f)
    return data if isinstance(data, dict) else {}
