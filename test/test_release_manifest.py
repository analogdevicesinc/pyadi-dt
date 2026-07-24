"""Tests for release artifact manifest and release upsert helper script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / ".github" / "scripts"))

from release_manifest import (
    compute_sha256,
    generate_manifest,
    main,
    upsert_github_release,
    verify_manifest,
)


def test_compute_sha256(tmp_path):
    file1 = tmp_path / "test.txt"
    file1.write_bytes(b"hello world\n")
    # sha256 of "hello world\n"
    # echo "hello world" | sha256sum -> d2a842e44ec75078f08d66653347917e6e522502693892787729227f272e505a
    expected = hashlib_sha256(b"hello world\n")
    assert compute_sha256(file1) == expected


def hashlib_sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def test_generate_manifest_deterministic(tmp_path):
    (tmp_path / "z_file.whl").write_bytes(b"content z")
    (tmp_path / "a_file.tar.gz").write_bytes(b"content a")
    (tmp_path / "SHA256SUMS").write_text("old manifest")

    manifest = generate_manifest(tmp_path)
    lines = manifest.strip().splitlines()

    assert len(lines) == 2
    # Verify sorted order (a_file before z_file)
    assert lines[0].endswith("a_file.tar.gz")
    assert lines[1].endswith("z_file.whl")

    # Verify standard sha256sum format: hash + two spaces + filename
    h_a = hashlib_sha256(b"content a")
    h_z = hashlib_sha256(b"content z")
    assert lines[0] == f"{h_a}  a_file.tar.gz"
    assert lines[1] == f"{h_z}  z_file.whl"

    # Test writing output file
    out_file = tmp_path / "OUTPUT_MANIFEST"
    generate_manifest(tmp_path, output_file=out_file)
    assert out_file.read_text(encoding="utf-8") == manifest


def test_verify_manifest(tmp_path):
    (tmp_path / "pkg.whl").write_bytes(b"package content")
    manifest_file = tmp_path / "SHA256SUMS"
    generate_manifest(tmp_path, output_file=manifest_file)

    # Valid verification
    ok, errors = verify_manifest(manifest_file, tmp_path)
    assert ok
    assert not errors

    # Corrupt file
    (tmp_path / "pkg.whl").write_bytes(b"corrupted content")
    ok, errors = verify_manifest(manifest_file, tmp_path)
    assert not ok
    assert any("Checksum mismatch" in e for e in errors)

    # Missing file
    (tmp_path / "pkg.whl").unlink()
    ok, errors = verify_manifest(manifest_file, tmp_path)
    assert not ok
    assert any("Missing file" in e for e in errors)


def test_sha256sum_cli_compatibility(tmp_path):
    """Verify standard sha256sum CLI utility accepts generated SHA256SUMS file."""
    (tmp_path / "dist1.whl").write_bytes(b"data 1")
    (tmp_path / "dist2.tar.gz").write_bytes(b"data 2")
    manifest_file = tmp_path / "SHA256SUMS"
    generate_manifest(tmp_path, output_file=manifest_file)

    proc = subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.returncode == 0
    assert "dist1.whl: OK" in proc.stdout
    assert "dist2.tar.gz: OK" in proc.stdout


def test_upsert_release_creates_new(tmp_path):
    tag = "v1.0.0"
    file1 = tmp_path / "adidt-1.0.0.whl"
    file1.write_bytes(b"wheel content")
    notes_file = tmp_path / "notes.md"
    notes_file.write_text("- Release notes v1.0.0")

    executed_cmds = []

    def mock_runner(cmd: list[str], check: bool = True):
        executed_cmds.append(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""
        # Simulate initial view failing (release does not exist yet)
        if cmd[:3] == ["gh", "release", "view"]:
            if len([c for c in executed_cmds if c[:3] == ["gh", "release", "view"]]) == 1:
                proc.returncode = 1
        return proc

    upsert_github_release(tag, [file1], notes_file=notes_file, runner_func=mock_runner)

    cmd_heads = [c[:3] for c in executed_cmds]
    assert ["gh", "release", "view"] in cmd_heads
    assert ["gh", "release", "create"] in cmd_heads
    assert ["gh", "release", "upload"] in cmd_heads
    assert ["gh", "release", "download"] in cmd_heads


def test_upsert_release_edits_existing(tmp_path):
    tag = "v1.0.0"
    file1 = tmp_path / "adidt-1.0.0.whl"
    file1.write_bytes(b"wheel content")
    notes_file = tmp_path / "notes.md"
    notes_file.write_text("- Release notes v1.0.0")

    executed_cmds = []

    def mock_runner(cmd: list[str], check: bool = True):
        executed_cmds.append(cmd)
        proc = MagicMock()
        proc.returncode = 0
        return proc

    upsert_github_release(tag, [file1], notes_file=notes_file, runner_func=mock_runner)

    cmd_heads = [c[:3] for c in executed_cmds]
    assert ["gh", "release", "view"] in cmd_heads
    assert ["gh", "release", "create"] not in cmd_heads
    assert ["gh", "release", "edit"] in cmd_heads
    assert ["gh", "release", "upload"] in cmd_heads


def test_cli_subcommands(tmp_path):
    (tmp_path / "test.txt").write_bytes(b"content")
    out_manifest = tmp_path / "SHA256SUMS"

    # test generate
    ret = main(["generate", "--dir", str(tmp_path), "--output", str(out_manifest)])
    assert ret == 0
    assert out_manifest.exists()

    # test verify
    ret = main(["verify", "--manifest", str(out_manifest), "--dir", str(tmp_path)])
    assert ret == 0
