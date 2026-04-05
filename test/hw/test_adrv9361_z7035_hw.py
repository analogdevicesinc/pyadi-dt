"""ADRV9361-Z7035 SOM hardware test using the BoardModel pipeline.

Exercises the BoardModel pipeline:
  to_board_model → gen_dt_from_model → deploy → IIO verify

The ADRV9361-Z7035 is a SOM pairing an AD9361 SDR transceiver with a
Zynq Z-7035 SoC.  Carrier variants: BOB (breakout) and FMC.

LG_ENV: /jenkins/lg_adrv9361_z7035.yaml
"""

from __future__ import annotations

import os
from pathlib import Path

import iio
import pytest

from adidt.boards.adrv9361_z7035 import adrv9361_z7035
from test.hw.hw_helpers import DEFAULT_OUT_DIR, shell_out

LG_ENV_PATH = "/jenkins/lg_adrv9361_z7035.yaml"
if not os.environ.get("LG_ENV"):
    pytest.skip(
        f"set LG_ENV={LG_ENV_PATH} for ADRV9361-Z7035 hardware test",
        allow_module_level=True,
    )

DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT_BOB = "zynq-adrv9361-z7035-bob"
DEFAULT_KUIPER_PROJECT_FMC = "zynq-adrv9361-z7035-fmc"
DEFAULT_KUIPER_BOOTBIN_BOB = "release:zynq-adrv9361-z7035-bob/BOOT.BIN"
DEFAULT_KUIPER_BOOTBIN_FMC = "release:zynq-adrv9361-z7035-fmc/BOOT.BIN"


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynq: Path | None) -> Path | None:
    """Linux kernel image for Z7035 (Zynq-7000)."""
    return built_kernel_image_zynq


@pytest.mark.lg_feature(["adrv9361", "z7035", "bob"])
def test_adrv9361_z7035_bob(board, built_kernel_image, tmp_path):
    """End-to-end test: BoardModel → DTS → deploy → IIO verify (BOB carrier)."""
    bootbin = os.environ.get("ADI_KUIPER_BOOTBIN", DEFAULT_KUIPER_BOOTBIN_BOB)

    # --- Stage 1: Generate BoardModel and DTS ---
    som = adrv9361_z7035(platform="bob")

    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    som.output_filename = str(out_dir / "adrv9361_z7035_bob.dts")

    model = som.to_board_model({})
    assert model.name == "adrv9361_z7035_bob"
    assert len(model.components) == 1
    assert model.components[0].part == "ad9361"

    som.gen_dt_from_model(model)
    assert (out_dir / "adrv9361_z7035_bob.dts").exists()

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
    (out_dir / "dmesg_adrv9361_z7035_bob.log").write_text(dmesg_txt)

    # --- Stage 4: Verify IIO devices ---
    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]

    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    found = [d.name for d in ctx.devices]
    assert any(n in found for n in ("ad9361-phy", "cf-ad9361-lpc")), (
        f"Expected AD9361 IIO device not found. Available: {found}"
    )


@pytest.mark.lg_feature(["adrv9361", "z7035", "fmc"])
def test_adrv9361_z7035_fmc(board, built_kernel_image, tmp_path):
    """End-to-end test: BoardModel → DTS → deploy → IIO verify (FMC carrier)."""
    bootbin = os.environ.get("ADI_KUIPER_BOOTBIN", DEFAULT_KUIPER_BOOTBIN_FMC)

    # --- Stage 1: Generate BoardModel and DTS ---
    som = adrv9361_z7035(platform="fmc")

    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    som.output_filename = str(out_dir / "adrv9361_z7035_fmc.dts")

    model = som.to_board_model({})
    assert model.name == "adrv9361_z7035_fmc"
    som.gen_dt_from_model(model)
    assert (out_dir / "adrv9361_z7035_fmc.dts").exists()

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
    (out_dir / "dmesg_adrv9361_z7035_fmc.log").write_text(dmesg_txt)

    # --- Stage 4: Verify IIO devices ---
    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]

    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    found = [d.name for d in ctx.devices]
    assert any(n in found for n in ("ad9361-phy", "cf-ad9361-lpc")), (
        f"Expected AD9361 IIO device not found. Available: {found}"
    )


@pytest.mark.lg_feature(["adrv9361", "z7035"])
def test_adrv9361_z7035_sampling_frequency(board, tmp_path):
    """Verify AD9361 reports a non-zero sampling frequency via IIO."""
    shell = board.target.get_driver("ADIShellDriver")

    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]

    ctx = iio.Context(f"ip:{ip_address}")
    phy = None
    for d in ctx.devices:
        if d.name == "ad9361-phy":
            phy = d
            break

    assert phy is not None, "ad9361-phy IIO device not found"

    # Read RX sampling frequency
    rx_freq = int(
        phy.find_channel("voltage0", is_output=False).attrs["sampling_frequency"].value
    )
    assert rx_freq > 0, f"RX sampling frequency should be > 0, got {rx_freq}"
