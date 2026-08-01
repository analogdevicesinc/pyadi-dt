"""ADRV9009-ZU11EG hardware test driven by the XSA pipeline.

The ADRV9009-ZU11EG is a System-on-Module: the ADRV9009 transceiver sits
directly on an ``xczu11eg`` MPSoC (rather than an FMC eval card on a
ZCU102 carrier).  It is a dual-die design that the kernel binds as a
single ``adrv9009-x2`` device, clocked by an on-SoM HMC7044.

Unlike the ZCU102/ZC706 ADRV9009 tests, the ZU11EG lab place boots over
**JTAG** (Xilinx "mini" U-Boot SPL — see ``BootZynqMPJTAG`` in
adi-labgrid-plugins); it does not yet have a Kuiper Linux SD/TFTP boot
path.  So this test validates the piece pyadi-dt owns end-to-end against
the *real* board's HDL artifact: parse the committed ZU11EG XSA, run the
full ``XsaPipeline`` (sdtgen → build → merge), assert the generated
device tree carries the correct ADRV9009-ZU11EG topology
(``adrv9009-x2`` PHY, HMC7044 clock, RX/OBS/TX JESD links), and compile
it to a DTB with ``dtc``.

It is gated by ``@pytest.mark.lg_feature(("adrv9009zu11eg", "adrv2crr-fmc"))``
so the dynamic hardware-CI matrix runs it against the coordinator place
tagged for the ZU11EG (``daughter-board=adrv9009zu11eg``,
``carrier=adrv2crr-fmc``).  When Kuiper Linux boot lands on the ZU11EG,
extend this with the standard ``run_xsa_boot_and_verify`` flow
(boot_mode="sd").

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
from test.hw.hw_helpers import DEFAULT_OUT_DIR, compile_dts_to_dtb
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
    board's committed HDL XSA rather than a live network boot.
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
    out_dir = DEFAULT_OUT_DIR
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
