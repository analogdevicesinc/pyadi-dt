"""Tests for the ADRV9009 JSON profile-file example."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "examples" / "xsa" / "adrv9009_profile_file.py"
PROFILE = (
    REPO_ROOT
    / "examples"
    / "xsa"
    / "profiles"
    / "adrv9009_zc706_custom.json"
)
TUTORIAL = REPO_ROOT / "doc" / "source" / "examples" / "xsa_tutorial.md"


def _load_example_module():
    spec = importlib.util.spec_from_file_location("adrv9009_profile_file", EXAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_show_config_executes_with_checked_in_profile() -> None:
    """The documented no-hardware path must validate and merge both profiles."""
    result = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--profile-file",
            str(PROFILE),
            "--show-config",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    config = json.loads(result.stdout)

    board = config["adrv9009_board"]
    assert board["spi_bus"] == "spi0"  # inherited from the built-in profile
    assert board["trx_spi_max_frequency"] == 10_000_000  # file override
    assert board["trx_reset_gpio"] == 130  # inherited built-in wiring


def test_pipeline_receives_profile_file_overrides(monkeypatch, tmp_path) -> None:
    """Custom profile values must remain explicit when the pipeline adds defaults."""
    module = _load_example_module()
    fake_xsa = tmp_path / "system_top.xsa"
    fake_xsa.write_text("xsa")
    runner = MagicMock()
    runner.run.return_value = {"merged": tmp_path / "adrv9009_zc706.dts"}
    monkeypatch.setattr(module, "XsaPipeline", lambda: runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "adrv9009_profile_file.py",
            "--profile-file",
            str(PROFILE),
            "--xsa",
            str(fake_xsa),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    module.main()

    kwargs = runner.run.call_args.kwargs
    assert kwargs["profile"] == "adrv9009_zc706"
    assert kwargs["cfg"]["adrv9009_board"]["trx_spi_max_frequency"] == 10_000_000
    assert kwargs["cfg"]["adrv9009_board"]["trx_reset_gpio"] == 130


def test_profile_file_example_is_documented() -> None:
    """Keep the runnable profile-file commands discoverable in Sphinx docs."""
    tutorial = TUTORIAL.read_text()
    assert "ADRV9009 custom profile files" in tutorial
    assert "examples/xsa/adrv9009_profile_file.py" in tutorial
    assert "examples/xsa/profiles/adrv9009_zc706_custom.json" in tutorial
    assert "--show-config" in tutorial
