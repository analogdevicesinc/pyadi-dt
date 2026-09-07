from pathlib import Path

import pytest

from test.hw.hw_helpers import hardware_prereq_unavailable


ROOT = Path(__file__).parents[1]


def test_hardware_venv_installs_and_exposes_sdtgen():
    """Hardware CI must install the XSA extra and prepend its venv to PATH."""
    pyproject = (ROOT / "pyproject.toml").read_text()
    installer = (ROOT / ".github/scripts/install-adidt-venv.sh").read_text()
    environment = (ROOT / ".github/scripts/prepare-hardware-env.sh").read_text()
    workflow = (ROOT / ".github/workflows/hardware-test.yml").read_text()

    assert '"pyadi-dt[test,xsa]"' in pyproject
    assert '"$VENV/bin/sdtgen" -help' in installer
    assert "requirements/pyadi-jif-ad9371.txt" in installer
    assert "hasattr(adijif, 'ad9371')" in installer
    assert "/tools/Xilinx/2025.1/Vivado/bin/sdtgen" in installer
    assert "source .github/scripts/prepare-hardware-env.sh" in workflow
    assert (
        "test/hw/xsa -maxdepth 1 -type f -name "
        '"test_*${BOARD}*${CARRIER}*_overlay.py"' in workflow
    )
    assert '[[ "$entry" == "$HOME/.local/bin" ]] && continue' in environment
    assert 'export PATH="$VENV_DIR/bin:/usr/bin' in environment
    assert '"$(command -v as)" != "/usr/bin/as"' in environment


def test_labgrid_plugins_dependency_is_immutable() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()

    assert (
        "labgrid-plugins[kuiper] @ git+https://github.com/tfcollins/"
        "labgrid-plugins.git@00c508aef6612b7de8dd8f263f5c4b1411a81a04" in pyproject
    )


def test_missing_hardware_prerequisite_fails_in_coordinator_mode(monkeypatch):
    """Coordinator runs must not report skip-only green on broken tooling."""
    monkeypatch.setenv("LG_COORDINATOR", "coordinator.example:20408")

    with pytest.raises(pytest.fail.Exception, match="missing tool"):
        hardware_prereq_unavailable("missing tool")


def test_missing_hardware_prerequisite_skips_outside_coordinator(monkeypatch):
    """Developer machines without lab access retain the convenient skip behavior."""
    monkeypatch.delenv("LG_COORDINATOR", raising=False)

    with pytest.raises(pytest.skip.Exception, match="missing tool"):
        hardware_prereq_unavailable("missing tool")


def test_fmcdaq3_overlay_uses_coordinator_feature_names():
    """The overlay suite must run on the same place as the DAQ3 boot test."""
    from test.hw.xsa.test_fmcdaq3_vcu118_overlay import SPEC

    assert SPEC.lg_features == ("daq3", "vcu118")


def test_preparation_loads_only_the_selected_board_configuration(tmp_path):
    import os
    import subprocess

    tool_dir = tmp_path / "venv/bin"
    tool_dir.mkdir(parents=True)
    for name in ("labgrid-client", "pytest", "sdtgen"):
        tool = tool_dir / name
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(0o755)
    config = tmp_path / "config"
    config.mkdir()
    (config / "adrv9371-zc706.env").write_text(
        "export ADIDT_OVERLAY_MODULES_ARCHIVE=/private/ad9371.tar.gz\n"
    )
    (config / "daq3-vcu118.env").write_text(
        "export ADIDT_OVERLAY_MODULES_ARCHIVE=/wrong/board.tar.gz\n"
    )
    env = dict(
        os.environ,
        BOARD="adrv9371",
        CARRIER="zc706",
        VENV_DIR=str(tool_dir.parent),
        ADIDT_HARDWARE_CONFIG_DIR=str(config),
    )
    env.pop("LG_ENV", None)
    env.pop("LG_COORDINATOR", None)
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; printf "%s" "$ADIDT_OVERLAY_MODULES_ARCHIVE"',
            "bash",
            str(ROOT / ".github/scripts/prepare-hardware-env.sh"),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "/private/ad9371.tar.gz"
