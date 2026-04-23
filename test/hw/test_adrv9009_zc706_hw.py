"""ADRV9009 + ZC706 hardware test.

Drives the XSA pipeline (:class:`adidt.xsa.pipeline.XsaPipeline` +
:class:`adidt.xsa.builders.adrv9009.ADRV9009Builder`) end-to-end on real
hardware attached to the ``nemo`` labgrid place.

Boot strategy is :class:`BootFPGASoCTFTP` (Zynq-7000 TFTP boot).  The DTB is
renamed to ``devicetree.dtb`` before :meth:`KuiperDLDriver.add_files_to_target`
so U-Boot's ``tftp devicetree.dtb`` finds it.

LG_ENV: lg_adrv9009_zc706_tftp.yaml
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

if not (os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV")):
    pytest.skip(
        "set LG_COORDINATOR or LG_ENV for ADRV9009 ZC706 hardware test"
        " (see .env.example)",
        allow_module_level=True,
    )

from adidt.xsa.pipeline import XsaPipeline  # noqa: E402
from adidt.xsa.topology import XsaParser  # noqa: E402
from test.hw.hw_helpers import (  # noqa: E402
    DEFAULT_OUT_DIR,
    acquire_xsa,
    assert_ilas_aligned,
    assert_jesd_links_data,
    assert_no_kernel_faults,
    assert_no_probe_errors,
    check_jesd_framing_plausibility,
    collect_dmesg,
    compile_dts_to_dtb,
    deploy_and_boot,
    open_iio_context,
    parse_ilas_status,
    read_jesd_status,
)


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv9009"


def _stage_dtb_as_devicetree(dtb: Path, staging_dir: Path) -> Path:
    """Copy *dtb* into *staging_dir* renamed to ``devicetree.dtb``.

    BootFPGASoCTFTP's YAML sets ``dtb_image_name: devicetree.dtb`` — the
    file must have that exact basename when it lands in the TFTP root.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged = staging_dir / "devicetree.dtb"
    shutil.copyfile(dtb, staged)
    return staged


@pytest.mark.lg_feature(["adrv9009", "zc706"])
def test_adrv9009_zc706_xsa_hw(board, built_kernel_image_zynq, tmp_path):
    """End-to-end pyadi-dt ADRV9009+ZC706 via the XSA pipeline."""
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Acquire XSA (auto-downloads from Kuiper if not local) ---
    xsa_path = acquire_xsa(
        Path(__file__).parent / "xsa" / "system_top_adrv9009_zc706.xsa",
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
    # ADRV9009 default HDL framing: RX M=4 L=2 S=1 Np=16 -> F=4;
    # TX M=4 L=4 S=1 Np=16 -> F=2.  Matches what
    # ``test_adrv9009_zcu102_hw._solve_adrv9009_config`` derives via
    # pyadi-jif and what the ZC706 ADRV9009 HDL reference design uses.
    #
    # ``adrv9009_board`` GPIO overrides: ADRV9009Builder defaults to
    # ZCU102 GPIO numbers (130/136); ZC706 wires the same signals to
    # gpio0:106 (reset) and gpio0:112 (sysref-req), matching the Kuiper
    # production zynq-zc706-adv7511-adrv9009 DT.
    cfg = {
        "adrv9009_board": {
            "trx_reset_gpio": 106,
            "trx_sysref_req_gpio": 112,
        },
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 4, "L": 2, "Np": 16, "S": 1},
            "tx": {"F": 2, "K": 32, "M": 4, "L": 4, "Np": 16, "S": 1},
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
        },
    }

    framing_warnings = check_jesd_framing_plausibility(cfg["jesd"])
    assert not framing_warnings, (
        "JESD cfg is structurally inconsistent (will fail ILAS):\n  "
        + "\n  ".join(framing_warnings)
    )

    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        sdtgen_timeout=300,
        profile="adrv9009_zc706",
    )
    merged_dts = result["merged"]
    assert merged_dts.exists(), f"Merged DTS not written: {merged_dts}"

    merged_content = merged_dts.read_text()
    assert 'compatible = "adi,adrv9009"' in merged_content, (
        "ADRV9009 compatible string missing from merged DTS"
    )

    # --- 4. Compile to DTB, stage as devicetree.dtb ---
    dtb_raw = out_dir / "adrv9009_zc706.dtb"
    compile_dts_to_dtb(merged_dts, dtb_raw)
    dtb = _stage_dtb_as_devicetree(dtb_raw, out_dir / "tftp_staging_xsa")

    # --- 5. Deploy + boot ---
    shell = deploy_and_boot(board, dtb, built_kernel_image_zynq)

    # --- 6. Diagnostics + probe verification ---
    dmesg_txt = collect_dmesg(
        shell,
        out_dir,
        label="adrv9009_xsa",
        grep_pattern="adrv9009|hmc7044|ad9528|jesd204|talise|probe|failed|error",
    )
    assert_no_kernel_faults(dmesg_txt)
    # si570 probe -EIO is a benign hardware artifact present in production
    # too (the optional Si570 clock chip sometimes doesn't ACK on the
    # default i2c address); strip it before the probe-error check.
    dmesg_filtered = "\n".join(
        line for line in dmesg_txt.splitlines()
        if not ("si570" in line and "failed" in line)
    )
    assert_no_probe_errors(dmesg_filtered)
    assert "adrv9009" in dmesg_txt.lower() or "talise" in dmesg_txt.lower(), (
        "ADRV9009 driver probe signature not found in dmesg"
    )

    ctx, _ = open_iio_context(shell)
    found = {d.name for d in ctx.devices if d.name}
    assert any("adrv9009" in n.lower() or "talise" in n.lower() for n in found), (
        f"No ADRV9009 IIO device found. Devices: {sorted(found)}"
    )
    assert any("9528" in n or "hmc7044" in n.lower() for n in found), (
        f"No AD9528/HMC7044 clock device found. Devices: {sorted(found)}"
    )

    # --- 7. JESD link + ILAS diagnostics ---
    rx_status, tx_status = read_jesd_status(shell)
    print("=== JESD204 RX status (sysfs) ===")
    print(rx_status)
    print("=== JESD204 TX status (sysfs) ===")
    print(tx_status)

    ilas_report = parse_ilas_status(dmesg_txt)
    print("=== ADRV9009 ILAS report ===")
    print(ilas_report.summary())
    if ilas_report.fields:
        for name in ilas_report.fields:
            print(f"  mismatched: {name}")
    assert_ilas_aligned(dmesg_txt, context="adrv9009_xsa")
    assert_jesd_links_data(shell, context="adrv9009_xsa")
