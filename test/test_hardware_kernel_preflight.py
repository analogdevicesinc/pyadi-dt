"""Execute the real pre-acquisition shell without accessing hardware or CIM."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def run_preflight(tmp_path, **settings):
    venv = tmp_path / "venv/bin"
    venv.mkdir(parents=True)
    (venv / "python").symlink_to(sys.executable)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("ADIDT_", "ADI_XSA_", "CIM_"))
    }
    env.update(
        VENV_DIR=str(venv.parent),
        BOARD="adrv9009",
        CARRIER="zc706",
        ADIDT_HARDWARE_CONFIG_DIR=str(tmp_path / "config"),
        GITHUB_ENV=str(tmp_path / "github-env"),
    )
    env.update(settings)
    return subprocess.run(
        ["bash", str(ROOT / ".github/scripts/prepare-hardware-kernels.sh")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_workflow_prepares_before_acquisition():
    caller = yaml.safe_load((ROOT / ".github/workflows/hardware-test.yml").read_text())
    assert caller["jobs"]["hardware"]["uses"] == "./.github/workflows/hw-matrix.yml"
    workflow = yaml.safe_load((ROOT / ".github/workflows/hw-matrix.yml").read_text())
    steps = workflow["jobs"]["hw-dynamic"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Prepare kernels before acquiring hardware") < names.index(
        "Acquire coordinator place"
    )
    step = steps[names.index("Prepare kernels before acquiring hardware")]
    assert step["run"] == "bash .github/scripts/prepare-hardware-kernels.sh"
    assert set(step["env"]) == {"BOARD", "CARRIER"}


def test_explicit_image_and_separate_overlay_do_not_require_cim(tmp_path):
    image = tmp_path / "uImage"
    image.write_bytes(b"external-image")
    overlay = tmp_path / "modular-uImage"
    overlay.write_bytes(b"separately-qualified-overlay")
    config = tmp_path / "config"
    config.mkdir()
    config_file = config / "adrv9009-zc706.env"
    content = f'export ADIDT_OVERLAY_KERNEL_IMAGE_ZYNQ="{overlay}"\nexport ADIDT_OVERLAY_MODULES_ARCHIVE=/preserved/modules.tar.gz\n'
    config_file.write_text(content)
    result = run_preflight(tmp_path, ADIDT_KERNEL_IMAGE_ZYNQ=str(image))
    assert result.returncode == 0, result.stderr
    assert config_file.read_text() == content
    assert overlay.read_bytes() == b"separately-qualified-overlay"


@pytest.mark.parametrize("disabled", ["0", "false", "no"])
def test_disabled_does_not_require_artifacts_or_cim(tmp_path, disabled):
    result = run_preflight(tmp_path, ADI_XSA_BUILD_KERNEL=disabled)
    assert result.returncode == 0, result.stderr


def test_overlay_cannot_silently_boot_stock_cim(tmp_path):
    result = run_preflight(tmp_path)
    assert result.returncode != 0
    assert "stock CIM images cannot replace them" in result.stderr


def test_missing_source_pin_fails_before_build(tmp_path):
    overlay = tmp_path / "overlay"
    overlay.write_bytes(b"qualified")
    result = run_preflight(
        tmp_path,
        ADIDT_OVERLAY_KERNEL_IMAGE_ZYNQ=str(overlay),
        CIM_MANIFEST_COMMIT="main",
    )
    assert result.returncode != 0
    assert "full Git commit SHA" in result.stderr


def test_fabric_does_not_prepare_arm_kernel(tmp_path):
    result = run_preflight(tmp_path, CARRIER="vcu118", BOARD="daq3")
    assert result.returncode == 0, result.stderr
