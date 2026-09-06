"""ADRV9009-ZU11EG hardware test driven by the XSA pipeline.

The ADRV9009-ZU11EG is a System-on-Module: the ADRV9009 transceiver sits
directly on an ``xczu11eg`` MPSoC (rather than an FMC eval card on a
ZCU102 carrier).  It is a dual-die design that the kernel binds as a
single ``adrv9009-x2`` device, clocked by an on-SoM HMC7044.

The ZU11EG lab place uses JTAG to reach production U-Boot. This test
runs the full XSA pipeline, compiles its generated tree, uploads that DTB
to RAM, and boots the stock SD kernel/rootfs with it. A unique marker must
match in U-Boot and Linux before PHY, JESD, and DMA checks run. No SD file
or persistent U-Boot environment is written.

The coordinator must advertise BootZynqMPJTAG and have the production
handoff artifacts. The shared environment preparation registers the pinned
plugin's strategy and accepts either connected Ethernet port.

Requires ``sdtgen`` (Vitis/Vivado) and ``dtc`` on PATH; skips cleanly if
either is missing.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.parse.topology import XsaParser
from test.hw._system_base import requires_lg
from test.hw.hw_helpers import (
    DEFAULT_OUT_DIR,
    compile_dts_to_dtb,
    collect_dmesg,
    assert_no_kernel_faults,
    assert_jesd_links_data,
    assert_rx_capture_valid,
    open_iio_context,
)
from test.hw._zynqmp_boot import boot_generated_zynqmp_dtb
from test.hw.xsa._overlay_spec import local_xsa_or_skip


LG_FEATURES = ("adrv9009zu11eg", "adrv2crr-fmc")

# The ZU11EG HDL XSA is committed under test/hw/xsa/ref_data/ like the
# other reference XSAs (ad9081/adrv9009 zcu102).  No Kuiper download
# exists for it yet, so this is local-only.
_XSA_RESOLVER = local_xsa_or_skip("system_top_adrv9009_zu11eg.xsa")


def _board_cfg() -> dict[str, Any]:
    """ADRV9009-ZU11EG JESD framing + board config for the pipeline.

    Uses the built-in ``adrv9009_zu11eg`` profile defaults for the board
    section (SPI, HMC7044 channels, dual-transceiver chip-selects) and a
    canonical M4/L2 RX + M4/L4 TX JESD framing.
    """
    from adidt.xsa.config.profiles import ProfileManager

    cfg: dict[str, Any] = dict(ProfileManager().load("adrv9009_zu11eg")["defaults"])
    cfg["jesd"] = {
        "rx": {"F": 4, "K": 32, "M": 4, "L": 2, "Np": 16, "S": 1},
        "tx": {"F": 2, "K": 32, "M": 4, "L": 4, "Np": 16, "S": 1},
    }
    return cfg


@requires_lg
@pytest.mark.lg_feature(list(LG_FEATURES))
def test_adrv9009_zu11eg_hw(board, tmp_path):
    """End-to-end pyadi-dt ADRV9009-ZU11EG device-tree generation from the real XSA.

    ``board`` is requested so the labgrid ``lg_feature`` gate binds this
    test to the ZU11EG place (and the dynamic HW matrix schedules it on
    the right runner); the device-tree generation itself is driven by the
    board's committed HDL XSA before the generated-DTB RAM handoff.
    """
    if shutil.which("sdtgen") is None:
        pytest.skip("sdtgen not on PATH (install Vitis/Vivado device-tree generator)")
    if shutil.which("dtc") is None:
        pytest.skip("dtc not on PATH (install device-tree-compiler)")

    xsa_path = _XSA_RESOLVER(tmp_path)
    assert xsa_path.exists(), f"ZU11EG XSA not found: {xsa_path}"

    # --- Topology: platform inference + JESD instances from the real XSA ---
    topology = XsaParser().parse(xsa_path)
    assert topology.inferred_platform() == "zu11eg", (
        f"expected zu11eg platform, got {topology.inferred_platform()!r}"
    )
    assert topology.jesd204_rx, "No JESD204 RX instances in ZU11EG XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in ZU11EG XSA topology"
    print(
        f"ZU11EG XSA topology: {len(topology.jesd204_rx)} rx jesd, "
        f"{len(topology.jesd204_tx)} tx jesd"
    )

    # --- Run the full pipeline (auto-detects the adrv9009_zu11eg profile) ---
    out_dir = DEFAULT_OUT_DIR / "adrv9009_zu11eg"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=_board_cfg(),
        output_dir=out_dir,
        sdtgen_timeout=300,
    )
    merged_dts = result["merged"]
    assert merged_dts.exists(), "pipeline did not write a merged DTS"
    merged = merged_dts.read_text()

    # --- Assert the ADRV9009-ZU11EG device-tree topology ---
    # Dual-die transceiver bound as a single adrv9009-x2 device on the SoM.
    assert 'compatible = "adrv9009-x2"' in merged, (
        "expected adrv9009-x2 (dual-die SoM) PHY compatible in merged DTS"
    )
    # On-SoM HMC7044 clock (not the ZCU102 FMC's AD9528).
    assert 'compatible = "adi,hmc7044"' in merged, (
        "expected HMC7044 clock node in merged DTS"
    )
    # RX + OBS + TX JESD cores from the ZU11EG HDL design.
    for needle in (
        "axi_adrv9009_som_rx_jesd",
        "axi_adrv9009_som_obs_jesd",
        "axi_adrv9009_som_tx_jesd",
    ):
        assert needle in merged, f"expected JESD core {needle!r} in merged DTS"

    # --- Compile the merged device tree to a DTB with dtc ---
    dtb_path = out_dir / "adrv9009_zu11eg.dtb"
    compile_dts_to_dtb(merged_dts, dtb_path)
    assert dtb_path.exists() and dtb_path.stat().st_size > 0, (
        f"dtc produced empty/missing DTB: {dtb_path}"
    )
    print(f"Compiled ZU11EG DTB: {dtb_path} ({dtb_path.stat().st_size} bytes)")

    shell = boot_generated_zynqmp_dtb(board, dtb_path)
    dmesg = collect_dmesg(shell, out_dir, "adrv9009_zu11eg")
    assert_no_kernel_faults(dmesg)
    assert_jesd_links_data(shell, expected_rx_links=2, expected_tx_links=1)
    ctx, _ = open_iio_context(shell)
    names = {device.name for device in ctx.devices}
    assert {"adrv9009-phy", "adrv9009-phy-b"} <= names, names
    assert_rx_capture_valid(ctx, "axi-adrv9009-rx-hpc")
