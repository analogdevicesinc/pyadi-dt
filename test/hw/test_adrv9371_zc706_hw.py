"""ADRV9371 + ZC706 hardware test.

Exercises both code paths end-to-end on real hardware:

1. ``test_adrv9371_zc706_xsa_hw`` — XSA pipeline via
   :class:`adidt.xsa.pipeline.XsaPipeline` + :class:`ADRV937xBuilder`.
2. ``test_adrv9371_zc706_system_hw`` — declarative System API via
   :class:`adidt.eval.adrv937x_fmc` + :class:`adidt.fpga.zc706`.

Boot strategy is :class:`BootFPGASoCTFTP` (Zynq-7000 TFTP boot).  The
DTB is renamed to ``devicetree.dtb`` before :meth:`KuiperDLDriver.add_files_to_target`
so U-Boot's ``tftp devicetree.dtb`` finds it.

LG_ENV: lg_adrv9371_zc706_tftp.yaml
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

if not (os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV")):
    pytest.skip(
        "set LG_COORDINATOR or LG_ENV for ADRV9371 ZC706 hardware test"
        " (see .env.example)",
        allow_module_level=True,
    )

import adidt  # noqa: E402
from adidt.xsa.pipeline import XsaPipeline  # noqa: E402
from adidt.xsa.topology import XsaParser  # noqa: E402
from test.hw.hw_helpers import (  # noqa: E402
    DEFAULT_OUT_DIR,
    acquire_xsa,
    assert_no_kernel_faults,
    assert_no_probe_errors,
    collect_dmesg,
    compile_dts_to_dtb,
    deploy_and_boot,
    open_iio_context,
)


DEFAULT_KUIPER_RELEASE = "2023_R2_P1"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv937x"
DEFAULT_VCXO_HZ = 122_880_000


def _stage_dtb_as_devicetree(dtb: Path, staging_dir: Path) -> Path:
    """Copy *dtb* into *staging_dir* renamed to ``devicetree.dtb``.

    BootFPGASoCTFTP's YAML sets ``dtb_image_name: devicetree.dtb`` — the
    file must have that exact basename when it lands in the TFTP root.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged = staging_dir / "devicetree.dtb"
    shutil.copyfile(dtb, staged)
    return staged


# ---------------------------------------------------------------------------
# XSA pipeline test
# ---------------------------------------------------------------------------


@pytest.mark.lg_feature(["adrv9371", "zc706"])
def test_adrv9371_zc706_xsa_hw(board, built_kernel_image_zynq, tmp_path):
    """End-to-end pyadi-dt ADRV9371+ZC706 via the XSA pipeline."""
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Acquire XSA ---
    xsa_path = acquire_xsa(
        Path(__file__).parent / "xsa" / "system_top_adrv9371_zc706.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
        tmp_path,
    )
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    # --- 2. Sanity-check topology ---
    topology = XsaParser().parse(xsa_path)
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"
    print(
        f"XSA topology: {len(topology.converters)} converter(s), "
        f"{len(topology.jesd204_rx)} rx jesd, {len(topology.jesd204_tx)} tx jesd"
    )

    # --- 3. Run the XSA pipeline ---
    cfg = {
        "adrv9009_board": {
            "misc_clk_hz": 245_760_000,
            "spi_bus": "spi0",
            "clk_cs": 0,
            "trx_cs": 1,
            "trx_reset_gpio": 130,
            "trx_sysref_req_gpio": 136,
            "ad9528_vcxo_freq": DEFAULT_VCXO_HZ,
            "rx_link_id": 1,
            "tx_link_id": 0,
        },
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 4, "L": 2},
            "tx": {"F": 4, "K": 32, "M": 4, "L": 4},
        },
    }
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        sdtgen_timeout=300,
    )
    merged_dts = result["merged"]
    assert merged_dts.exists(), f"Merged DTS not written: {merged_dts}"

    merged_content = merged_dts.read_text()
    assert 'compatible = "adi,ad9371"' in merged_content, (
        "AD9371 compatible string missing from merged DTS"
    )

    # --- 4. Compile to DTB, stage as devicetree.dtb ---
    dtb_raw = out_dir / "adrv9371_zc706.dtb"
    compile_dts_to_dtb(merged_dts, dtb_raw)
    dtb = _stage_dtb_as_devicetree(dtb_raw, out_dir / "tftp_staging_xsa")

    # --- 5. Deploy + boot ---
    shell = deploy_and_boot(board, dtb, built_kernel_image_zynq)

    # --- 6. Diagnostics + probe verification ---
    dmesg_txt = collect_dmesg(
        shell,
        out_dir,
        label="adrv9371_xsa",
        grep_pattern="ad9371|ad9528|jesd204|mykonos|probe|failed|error",
    )
    assert_no_kernel_faults(dmesg_txt)
    assert_no_probe_errors(dmesg_txt)
    assert "ad9371" in dmesg_txt.lower() or "mykonos" in dmesg_txt.lower(), (
        "AD9371 driver probe signature not found in dmesg"
    )

    ctx, _ = open_iio_context(shell)
    found = {d.name for d in ctx.devices if d.name}
    assert any("9371" in n or "adrv9" in n.lower() for n in found), (
        f"No AD9371/ADRV9xxx IIO device found. Devices: {sorted(found)}"
    )
    assert any("9528" in n for n in found), (
        f"No AD9528 clock device found. Devices: {sorted(found)}"
    )


# ---------------------------------------------------------------------------
# System API test
# ---------------------------------------------------------------------------
#
# The declarative :class:`adidt.System` path does not yet emit the
# topology-aware XCVR / TPL-core / clkgen overlays that the ZC706 + AD9371
# design needs to bind; ``apply_xsa_topology`` only overrides the JESD204
# framing labels, leaving default ``axi_adrv9009_*`` xcvr/core labels that
# do not exist in the ZC706 base DTS. A structural smoke test lives at
# ``test/devices/test_system_adrv937x_zc706.py``; the end-to-end hardware
# path is covered by :func:`test_adrv9371_zc706_xsa_hw` above.
