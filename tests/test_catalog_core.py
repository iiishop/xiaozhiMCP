from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from catalog_core import CatalogCore, parse_github_repo


class CatalogCoreTests(unittest.TestCase):
    def test_parse_repo(self) -> None:
        owner, repo = parse_github_repo("https://github.com/iiishop/xiaozhiMCP-components.git")
        self.assertEqual(owner, "iiishop")
        self.assertEqual(repo, "xiaozhiMCP-components")

    def test_install_component_writes_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = CatalogCore(
                repo_url="https://github.com/iiishop/xiaozhiMCP-components.git",
                branch="main",
                install_folder=tmp,
            )
            with patch.object(
                core,
                "list_components",
                return_value=[
                    {
                        "name": "clipboard",
                        "description": "",
                        "version": "",
                        "path": "clipboard",
                        "entry": "component.py",
                        "readme": "README.md",
                        "platforms": ["Windows"],
                    }
                ],
            ), patch.object(
                core,
                "_get_text",
                side_effect=["class Component:\n    pass\n", "# Clipboard\n\nPlatforms: Windows\n"],
            ):
                out = core.install_component("clipboard")
            self.assertTrue(out["success"])
            target = Path(tmp) / "clipboard"
            self.assertTrue((target / "component.py").exists())
            self.assertTrue((target / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
