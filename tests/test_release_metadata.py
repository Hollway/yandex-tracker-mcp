"""`pyproject.toml`, `manifest.json` and `CHANGELOG.md` agree on the
version - see `rules/docs.md`. Publishing a release with one of them left behind is a
step nobody catches by reading the diff.
"""

import json
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]

VERSION: str = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
]["version"]
MANIFEST: dict[str, Any] = json.loads(
    (ROOT / "manifest.json").read_text(encoding="utf-8")
)
CHANGELOG: str = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_manifest_carries_the_project_version() -> None:
    assert MANIFEST["version"] == VERSION


def test_changelog_has_a_section_for_the_project_version() -> None:
    assert f"## [{VERSION}]" in CHANGELOG, (
        f"CHANGELOG.md has no section for {VERSION}. Every release gets one, patch "
        "releases included - see rules/changelog.md."
    )
