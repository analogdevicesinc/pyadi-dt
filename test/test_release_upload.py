"""Exercise the exact staging operation used by the release dry run."""

import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / ".github/scripts/stage-pypi-artifacts.sh"


@pytest.mark.parametrize("missing", [None, "pkg.whl", "pkg.tar.gz"])
def test_stage_only_complete_python_distributions(tmp_path, missing):
    source = tmp_path / "release assets"
    destination = tmp_path / "upload"
    source.mkdir()
    for name in ("pkg.whl", "pkg.tar.gz", "SHA256SUMS", "release-notes.md", "pkg.deb"):
        if name != missing:
            (source / name).write_bytes(name.encode())
    result = subprocess.run(
        ["bash", str(SCRIPT), str(source), str(destination)],
        capture_output=True,
        text=True,
    )
    if missing:
        assert result.returncode != 0
        assert not list(destination.iterdir())
    else:
        assert result.returncode == 0, result.stderr
        assert {p.name for p in destination.iterdir()} == {"pkg.whl", "pkg.tar.gz"}
        for path in destination.iterdir():
            assert path.read_bytes() == (source / path.name).read_bytes()
    assert (source / "SHA256SUMS").exists()


def test_staging_rejects_stale_upload_contents(tmp_path):
    (tmp_path / "SHA256SUMS").write_text("stale")
    result = subprocess.run(
        ["bash", str(SCRIPT), str(tmp_path), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "must be empty" in result.stderr
