from __future__ import annotations

import importlib.util
import inspect
import os
from pathlib import Path
from typing import Any


def detect_platform() -> str:
    if os.name == "nt":
        return "windows"
    if os.uname().sysname.lower() == "darwin":
        return "macos"
    return "linux"


def _load_python_module(module_name: str, file_path: Path) -> Any | None:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _instantiate_from_module(
    module: Any,
    config: dict[str, Any],
    full_config: dict[str, Any],
    component_name: str,
) -> Any | None:
    builder = getattr(module, "build_component", None)
    if callable(builder):
        try:
            return builder(config, full_config)
        except TypeError:
            pass
        try:
            return builder(config)
        except TypeError:
            return builder()

    cls = getattr(module, "Component", None)
    if inspect.isclass(cls):
        try:
            return cls(config, full_config)
        except TypeError:
            pass
        try:
            return cls(config)
        except TypeError:
            return cls()

    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ != module.__name__:
            continue
        if not hasattr(obj, "register"):
            continue
        try:
            return obj(config, full_config)
        except TypeError:
            pass
        try:
            return obj(config)
        except TypeError:
            try:
                return obj()
            except Exception:
                continue
    return None


def load_components_from_package_folder(folder: str, config: dict[str, Any]) -> list[Any]:
    path = Path(folder)
    if not path.exists() or not path.is_dir():
        return []

    components: list[Any] = []
    for item in sorted(path.iterdir()):
        if item.name.startswith("_"):
            continue

        module: Any | None = None
        component_name = item.stem

        if item.is_file() and item.suffix == ".py":
            module = _load_python_module(f"dyn_component_{item.stem}", item)
            component_name = item.stem
        elif item.is_dir():
            entry = item / "component.py"
            if entry.exists():
                module = _load_python_module(f"dyn_component_{item.name}", entry)
                component_name = item.name

        if module is None:
            continue

        component_config = config.get(component_name, {}) if isinstance(config.get(component_name), dict) else {}
        try:
            instance = _instantiate_from_module(module, component_config, config, component_name)
            if instance is not None:
                components.append(instance)
        except Exception:
            continue

    return components


def load_user_components(folder: str, config: dict[str, Any]) -> list[Any]:
    return load_components_from_package_folder(folder, config)
