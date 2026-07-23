"""Tests for release preflight script."""

import sys
from pathlib import Path

import pytest

# Ensure .github/scripts is importable
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / ".github" / "scripts"))

from release_preflight import (
    extract_changelog_notes,
    get_init_version,
    get_pyproject_version,
    main,
    run_preflight,
    validate_tag_format,
)


def test_validate_tag_format():
    assert validate_tag_format("v0.1.0") == "0.1.0"
    assert validate_tag_format("v1.2.3-rc1") == "1.2.3-rc1"
    assert validate_tag_format("v2.0.0+2026") == "2.0.0+2026"

    with pytest.raises(ValueError, match="invalid release tag format"):
        validate_tag_format("0.1.0")

    with pytest.raises(ValueError, match="invalid release tag format"):
        validate_tag_format("v1.0")

    with pytest.raises(ValueError, match="invalid release tag format"):
        validate_tag_format("invalid")


def test_run_preflight_success(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "adidt"\nversion = "1.2.3"\n'
    )
    init_dir = tmp_path / "adidt"
    init_dir.mkdir()
    (init_dir / "__init__.py").write_text('__version__ = "1.2.3"\n')
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [1.2.3] - 2026-07-23\n- Initial release notes\n\n## [1.2.2]\n"
    )

    tag, version, notes = run_preflight("v1.2.3", tmp_path)
    assert tag == "v1.2.3"
    assert version == "1.2.3"
    assert notes == "- Initial release notes\n"


def test_version_mismatch(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "adidt"\nversion = "1.2.3"\n'
    )
    init_dir = tmp_path / "adidt"
    init_dir.mkdir()
    (init_dir / "__init__.py").write_text('__version__ = "1.2.4"\n')
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.3]\n- Notes\n")

    with pytest.raises(ValueError, match="version mismatch"):
        run_preflight("v1.2.3", tmp_path)


def test_missing_changelog_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "adidt"\nversion = "1.2.3"\n'
    )
    init_dir = tmp_path / "adidt"
    init_dir.mkdir()
    (init_dir / "__init__.py").write_text('__version__ = "1.2.3"\n')
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.2]\n- Old notes\n")

    with pytest.raises(ValueError, match="CHANGELOG.md has no section"):
        run_preflight("v1.2.3", tmp_path)


def test_cli_main(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "adidt"\nversion = "0.5.0"\n'
    )
    init_dir = tmp_path / "adidt"
    init_dir.mkdir()
    (init_dir / "__init__.py").write_text('__version__ = "0.5.0"\n')
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [0.5.0]\n- Feature X\n")

    gh_out = tmp_path / "gh_output.txt"
    notes_out = tmp_path / "notes.md"

    ret = main(
        [
            "--tag",
            "v0.5.0",
            "--repo-dir",
            str(tmp_path),
            "--github-output",
            str(gh_out),
            "--notes-output",
            str(notes_out),
        ]
    )

    assert ret == 0
    assert gh_out.read_text() == "tag=v0.5.0\nversion=0.5.0\n"
    assert notes_out.read_text() == "- Feature X\n"


def test_repository_release_contract():
    tag, version, notes = run_preflight("v0.0.1", repo_root)

    assert tag == "v0.0.1"
    assert version == "0.0.1"
    assert notes.strip()


def test_manual_dispatch_cannot_publish():
    workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text()

    publish_guard = (
        "if: github.event_name == 'push' && "
        "startsWith(github.ref, 'refs/tags/v')"
    )
    assert workflow.count(publish_guard) == 2
    assert "Candidate v-prefixed tag to validate and dry-run from main" in workflow
    assert "Manual release dry runs must be dispatched from main" in workflow
    assert "github.event_name == 'workflow_dispatch' && github.sha" in workflow
