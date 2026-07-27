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


def test_workflows_use_release_manifest_without_sleep_loops():
    release_wf = (repo_root / ".github" / "workflows" / "release.yml").read_text()
    debian_wf = (repo_root / ".github" / "workflows" / "build_debian.yaml").read_text()
    system_wf = (
        repo_root / ".github" / "workflows" / "build_system_packages.yml"
    ).read_text()

    assert "release_manifest.py generate" in release_wf
    assert "release_manifest.py verify" in release_wf
    assert "release_manifest.py upsert-release" in release_wf

    assert debian_wf.count("release_manifest.py upsert-release") == 1
    assert "needs: [identify_version, build_and_deploy_for_kuiper, build_and_deploy_for_ubuntu]" in debian_wf
    assert "Expected three Debian artifacts" in debian_wf
    assert "group: release-${{ github.ref_name }}" in debian_wf
    assert "group: release-${{ github.event_name == 'workflow_dispatch' && inputs.tag || github.ref_name }}" in release_wf
    assert "sleep 10" not in debian_wf
    assert "for attempt in {1..30}" not in debian_wf

    assert system_wf.count("release_manifest.py upsert-release") == 1
    assert "group: release-${{ github.ref_name }}" in system_wf
    assert "Expected three native system packages" in system_wf
    assert "sleep 10" not in system_wf


def test_native_system_package_ci_contract():
    """Build each package in its native OS or distribution and smoke-test it."""
    workflow = (
        repo_root / ".github" / "workflows" / "build_system_packages.yml"
    ).read_text()
    builder = (repo_root / ".github" / "scripts" / "create_system_package.sh").read_text()
    verifier = (repo_root / ".github" / "scripts" / "verify_system_package.sh").read_text()

    assert "debian:12" in workflow
    assert "fedora:42" in workflow
    assert "runs-on: macos-14" in workflow
    assert 'package_type: "deb"' in workflow
    assert 'package_type: "rpm"' in workflow
    assert "create_system_package.sh osxpkg" in workflow
    assert workflow.count("actions/upload-artifact@v7") == 2
    assert "Install and verify package" in workflow
    assert "if-no-files-found: error" in workflow

    assert 'fpm -s python -t "$package_type"' in builder
    assert '--package "$output_file"' in builder
    assert "--no-auto-depends" in builder
    assert "dpkg -L python3-adidt" in verifier
    assert "rpm -ql python3-adidt" in verifier
    assert "--osxpkg-identifier-prefix com.analogdevices" in builder
    assert "pkgutil --files com.analogdevices.python3-adidt" in verifier
    assert '"$package_test_python" "$package_cli" --help' in verifier
