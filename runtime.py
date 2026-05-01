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


def load_user_components(folder: str) -> list[Any]:
    path = Path(folder)
    if not path.exists() or not path.is_dir():
        return []

    components: list[Any] = []
    for file in sorted(path.glob("*.py")):
        if file.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"user_component_{file.stem}", file)
        if not spec or not spec.loader:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Convention: file may expose `build_component()` returning an instance
        builder = getattr(module, "build_component", None)
        if callable(builder):
            instance = builder()
            if instance is not None:
                components.append(instance)
            continue

        # Or expose a `Component` class
        cls = getattr(module, "Component", None)
        if inspect.isclass(cls):
            try:
                components.append(cls())
            except Exception:
                continue

    return components
