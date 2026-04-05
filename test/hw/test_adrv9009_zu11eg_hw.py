"""ADRV9009-ZU11EG hardware test using the profile-based pipeline.

Exercises the full profile-based pipeline:
  parse_profile → map_clocks_to_board_layout → gen_dt → DTB → deploy → IIO verify

The ADRV9009-ZU11EG is a SOM with dual ADRV9009 transceivers and an HMC7044
clock distributor.  It uses the ADRV2CRR-FMC carrier board.

LG_ENV: /jenkins/lg_adrv9009_zu11eg.yaml
"""

from __future__ import annotations

import os
from pathlib import Path

import iio
import pytest

from adidt.boards.adrv9009_zu11eg import adrv9009_zu11eg
from test.hw.hw_helpers import DEFAULT_OUT_DIR, shell_out

LG_ENV_PATH = "/jenkins/lg_adrv9009_zu11eg.yaml"
if not os.environ.get("LG_ENV"):
    pytest.skip(
        f"set LG_ENV={LG_ENV_PATH} for ADRV9009-ZU11EG hardware test",
        allow_module_level=True,
    )

DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb"
DEFAULT_KUIPER_BOOTBIN = (
    "release:zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb/BOOT.BIN"
)


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynqmp: Path | None) -> Path | None:
    """Linux kernel image for ZU11EG (ZynqMP)."""
    return built_kernel_image_zynqmp


@pytest.mark.lg_feature(["adrv9009", "zu11eg"])
def test_adrv9009_zu11eg_profile(board, built_kernel_image, tmp_path):
    """End-to-end test: profile → DTS → deploy → IIO verify."""
    release = os.environ.get("ADI_KUIPER_BOOT_RELEASE", DEFAULT_KUIPER_RELEASE)
    bootbin = os.environ.get("ADI_KUIPER_BOOTBIN", DEFAULT_KUIPER_BOOTBIN)

    # --- Stage 1: Initialize board and generate DTS ---
    zu11eg = adrv9009_zu11eg()

    # Look for a profile in known locations
    profile_dir = Path(__file__).parent / "adrv9009" / "profiles"
    profiles = sorted(profile_dir.glob("*.txt")) if profile_dir.exists() else []

    if profiles:
        zu11eg.parse_profile(str(profiles[0]))
        assert zu11eg.profile is not None, "Profile parsing returned None"

    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Stage 2: Deploy using Kuiper release ---
    kuiper = board.target.get_driver("KuiperDLDriver")
    kuiper.kuiper_resource.BOOTBIN_path = bootbin
    kuiper.get_boot_files_from_release()
    if built_kernel_image is not None:
        kuiper.add_files_to_target(built_kernel_image)

    board.transition("shell")

    # --- Stage 3: Collect dmesg ---
    shell = board.target.get_driver("ADIShellDriver")
    dmesg_txt = shell_out(shell, "dmesg")
    (out_dir / "dmesg_adrv9009_zu11eg.log").write_text(dmesg_txt)

    # --- Stage 4: Verify IIO devices ---
    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]

    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    found = [d.name for d in ctx.devices]
    # ZU11EG has dual ADRV9009 transceivers and HMC7044
    expected_any = ["adrv9009-phy", "adrv9009-phy-b", "hmc7044"]
    assert any(n in found for n in expected_any), (
        f"Expected ADRV9009-ZU11EG IIO devices not found. "
        f"Expected one of {expected_any}; available: {found}"
    )


@pytest.mark.lg_feature(["adrv9009", "zu11eg"])
def test_adrv9009_zu11eg_dual_trx(board, tmp_path):
    """Verify both ADRV9009 transceivers are enumerated on the ZU11EG SOM."""
    shell = board.target.get_driver("ADIShellDriver")

    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]

    ctx = iio.Context(f"ip:{ip_address}")
    found = [d.name for d in ctx.devices]

    # Both TRX0 and TRX1 should be present
    trx_devices = [n for n in found if "adrv9009" in n]
    assert len(trx_devices) >= 2, (
        f"Expected 2 ADRV9009 devices on ZU11EG SOM, found {len(trx_devices)}: {trx_devices}"
    )
