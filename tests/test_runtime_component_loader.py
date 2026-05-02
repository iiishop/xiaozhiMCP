from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from runtime import load_components_from_package_folder


class RuntimeComponentLoaderTests(unittest.TestCase):
    def test_loads_subfolder_component_with_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            comp_dir = root / "demo"
            comp_dir.mkdir(parents=True, exist_ok=True)
            (comp_dir / "component.py").write_text(
                textwrap.dedent(
                    """
                    class Component:
                        def __init__(self, config=None):
                            self.value = (config or {}).get("value", "")

                        def register(self, mcp):
                            return None
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            loaded = load_components_from_package_folder(str(root), {"demo": {"value": "ok"}})
            self.assertEqual(len(loaded), 1)
            self.assertEqual(getattr(loaded[0], "value", ""), "ok")

    def test_loads_file_component_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.py").write_text(
                textwrap.dedent(
                    """
                    class _C:
                        def __init__(self, value):
                            self.value = value

                        def register(self, mcp):
                            return None

                    def build_component(config=None):
                        return _C((config or {}).get("value", ""))
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            loaded = load_components_from_package_folder(str(root), {"sample": {"value": "file_ok"}})
            self.assertEqual(len(loaded), 1)
            self.assertEqual(getattr(loaded[0], "value", ""), "file_ok")


if __name__ == "__main__":
    unittest.main()
