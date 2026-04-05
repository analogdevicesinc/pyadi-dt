"""ADRV9364-Z7020 SOM hardware test using the BoardModel pipeline.

Exercises the BoardModel pipeline:
  to_board_model → gen_dt_from_model → deploy → IIO verify

The ADRV9364-Z7020 is a SOM pairing an AD9364 (1x1 TRX) SDR transceiver
with a Zynq Z-7020 SoC on a BOB carrier.

LG_ENV: /jenkins/lg_adrv9364_z7020.yaml
"""

from __future__ import annotations

import os
from pathlib import Path

import iio
import pytest

from adidt.boards.adrv9364_z7020 import adrv9364_z7020
from test.hw.hw_helpers import DEFAULT_OUT_DIR, shell_out

LG_ENV_PATH = "/jenkins/lg_adrv9364_z7020.yaml"
if not os.environ.get("LG_ENV"):
    pytest.skip(
        f"set LG_ENV={LG_ENV_PATH} for ADRV9364-Z7020 hardware test",
        allow_module_level=True,
    )

DEFAULT_KUIPER_BOOTBIN = "release:zynq-adrv9364-z7020-bob/BOOT.BIN"


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynq: Path | None) -> Path | None:
    """Linux kernel image for Z7020 (Zynq-7000)."""
    return built_kernel_image_zynq


@pytest.mark.lg_feature(["adrv9364", "z7020", "bob"])
def test_adrv9364_z7020_bob(board, built_kernel_image, tmp_path):
    """End-to-end test: BoardModel → DTS → deploy → IIO verify (BOB carrier)."""
    bootbin = os.environ.get("ADI_KUIPER_BOOTBIN", DEFAULT_KUIPER_BOOTBIN)

    # --- Stage 1: Generate BoardModel and DTS ---
    som = adrv9364_z7020(platform="bob")

    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    som.output_filename = str(out_dir / "adrv9364_z7020_bob.dts")

    model = som.to_board_model({})
    assert model.name == "adrv9364_z7020_bob"
    assert len(model.components) == 1
    assert model.components[0].part == "ad9364"

    som.gen_dt_from_model(model)
    assert (out_dir / "adrv9364_z7020_bob.dts").exists()

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
    (out_dir / "dmesg_adrv9364_z7020_bob.log").write_text(dmesg_txt)

    # --- Stage 4: Verify IIO devices ---
    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]

    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    found = [d.name for d in ctx.devices]
    assert any(n in found for n in ("ad9361-phy", "ad9364-phy", "cf-ad9361-lpc")), (
        f"Expected AD9364 IIO device not found. Available: {found}"
    )
