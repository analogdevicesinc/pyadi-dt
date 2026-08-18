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
    assert "--reinstall-package labgrid-plugins" in installer
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
        "labgrid-plugins.git@e9c89616013f008122370dba59af4758be5ae7da" in pyproject
    )


def test_zu11eg_hardware_ci_uses_fixed_jtag_environment() -> None:
    workflow = (ROOT / ".github/workflows/hardware-test.yml").read_text()
    environment = (ROOT / "test/hw/config/zu11eg-jtag.yaml").read_text()

    assert "test/hw/config/zu11eg-jtag.yaml" in workflow
    assert "LG_FORCE_LOCAL_XSDB=1" in workflow
    assert "verify-zu11eg-jtag-artifacts.sh" in workflow
    assert "BootZynqMPJTAG:" in environment
    assert "adi_lg_plugins.strategies.bootzynqmpjtag" in environment
    assert "production_uboot_prompt: 'ZynqMP>'" in environment
    assert "sd_boot_command: 'setenv partid 1; run sdboot'" in environment
    assert "kuiper_shell_marker: 'root@analog:.*#'" in environment
    manifest = (ROOT / "test/hw/config/zu11eg-jtag-artifacts.sha256").read_text()
    assert (
        "8687502e06d3d23d060d988b926250bce51b9b78cd966824f987e5e0561e55ab  u-boot.bin"
        in manifest
    )


def test_zu11eg_hardware_test_keeps_generated_output_private() -> None:
    test_source = (ROOT / "test/hw/test_adrv9009zu11eg_adrv2crr-fmc_hw.py").read_text()

    assert 'out_dir = tmp_path / "output"' in test_source
    assert "DEFAULT_OUT_DIR" not in test_source


def test_zu11eg_dtb_transaction_is_recovery_safe() -> None:
    """Keep partial installs and failed direct restores recoverable."""
    test_source = (ROOT / "test/hw/test_adrv9009zu11eg_adrv2crr-fmc_hw.py").read_text()

    assert test_source.index("transaction_started = True") < test_source.index(
        "_install_generated_dtb(shell, dtb_path)"
    )
    assert "except Exception as direct_restore_error:" in test_source
    assert test_source.count("_recover_and_restore_production_dtb(board)") >= 2
    assert f"cp -p {{_BACKUP_DTB}} {{_BOOT_DTB}}.restore; sync;" in test_source
    assert f"rm {{_BACKUP_DTB}}; sync;" in test_source


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
