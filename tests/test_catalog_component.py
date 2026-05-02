from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from components.catalog.component import CatalogComponent, _parse_github_repo


class ParseGithubRepoTests(unittest.TestCase):
    def test_parse_repo_url(self) -> None:
        owner, repo = _parse_github_repo("https://github.com/iiishop/xiaozhiMCP-components.git")
        self.assertEqual(owner, "iiishop")
        self.assertEqual(repo, "xiaozhiMCP-components")


class CatalogInstallTests(unittest.TestCase):
    def test_install_component_writes_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "user_components"
            c = CatalogComponent(
                repo_url="https://github.com/iiishop/xiaozhiMCP-components.git",
                install_folder=str(install_dir),
            )

            with patch.object(
                c,
                "list_components",
                return_value=[
                    {
                        "name": "clipboard",
                        "description": "",
                        "version": "",
                        "path": "clipboard",
                        "entry": "component.py",
                        "readme": "README.md",
                    }
                ],
            ), patch.object(
                c,
                "_get_text",
                side_effect=["class Component:\n    pass\n", "# Clipboard\n"],
            ):
                out = c.install_component("clipboard")

            self.assertTrue(out["success"])
            target = install_dir / "clipboard"
            self.assertTrue((target / "component.py").exists())
            self.assertTrue((target / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
