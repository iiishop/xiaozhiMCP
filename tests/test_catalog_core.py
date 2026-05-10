from __future__ import annotations

from catalog_core import CatalogCore


class FakeCatalogCore(CatalogCore):
    def __init__(self, install_folder: str) -> None:
        super().__init__(
            repo_url="https://github.com/example/components",
            branch="main",
            install_folder=install_folder,
        )
        self.entry_text = "print('hello')\n"
        self.readme_text = "# Demo\n\nPlatforms: Windows|Linux\n"

    def list_components(self) -> list[dict]:
        return [
            {
                "name": "alpha",
                "description": "calendar helper",
                "version": "1.0.0",
                "path": "alpha",
                "entry": "component.py",
                "readme": "README.md",
                "platforms": ["Windows", "Linux"],
            },
            {
                "name": "beta",
                "description": "clipboard helper",
                "version": "1.0.0",
                "path": "beta",
                "entry": "component.py",
                "readme": "README.md",
                "platforms": ["MacOs"],
            },
            {
                "name": "apple_music_macos",
                "description": "Apple Music control on macOS",
                "version": "1.0.0",
                "path": "apple_music_macos",
                "entry": "component.py",
                "readme": "README.md",
                "platforms": ["MacOs"],
            },
        ]

    def _get_text(self, url: str) -> str:
        if url.endswith("component.py"):
            return self.entry_text
        return self.readme_text


def test_parse_platforms_from_readme_normalizes_and_deduplicates(tmp_path):
    core = FakeCatalogCore(str(tmp_path))

    result = core.parse_platforms_from_readme("# Tool\n\nPlatforms: windows|Linux|windows\n")

    assert result == {"platforms": ["Windows", "Linux"], "valid": True, "warning": ""}


def test_search_components_filters_by_query_and_platform(tmp_path):
    core = FakeCatalogCore(str(tmp_path))

    result = core.search_components(query="calendar", platform="windows")

    assert result["success"] is True
    assert result["count"] == 1
    assert result["components"][0]["name"] == "alpha"


def test_install_component_writes_entry_readme_and_init(tmp_path):
    core = FakeCatalogCore(str(tmp_path))


    result = core.install_component("alpha")


    assert result["success"] is True
    target_dir = tmp_path / "alpha"
    assert (target_dir / "component.py").read_text(encoding="utf-8") == core.entry_text
    assert (target_dir / "README.md").read_text(encoding="utf-8") == core.readme_text
    assert (target_dir / "__init__.py").read_text(encoding="utf-8") == ""


def test_install_apple_music_component_uses_runtime_layout(tmp_path):
    core = FakeCatalogCore(str(tmp_path))

    result = core.install_component("apple_music_macos")

    assert result["success"] is True
    target_dir = tmp_path / "apple_music_macos"
    assert (target_dir / "component.py").read_text(encoding="utf-8") == core.entry_text
    assert (target_dir / "README.md").read_text(encoding="utf-8") == core.readme_text
    assert (target_dir / "__init__.py").read_text(encoding="utf-8") == ""
