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

    assert '"adidt[test,xsa]"' in pyproject
    assert '"$VENV/bin/sdtgen" -help' in installer
    assert "requirements/pyadi-jif-ad9371.txt" in installer
    assert "hasattr(adijif, 'ad9371')" in installer
    assert "/tools/Xilinx/2025.1/Vivado/bin/sdtgen" in installer
    assert "source .github/scripts/prepare-hardware-env.sh" in workflow
    assert 'test/hw/xsa -maxdepth 1 -type f -name "test_*${BOARD}*${CARRIER}*_overlay.py"' in workflow
    assert '[[ "$entry" == "$HOME/.local/bin" ]] && continue' in environment
    assert 'export PATH="$VENV_DIR/bin:/usr/bin' in environment
    assert '"$(command -v as)" != "/usr/bin/as"' in environment


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