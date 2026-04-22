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
    shell_out,
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
            "misc_clk_hz": 122_880_000,
            "spi_bus": "spi0",
            "clk_cs": 0,
            "trx_cs": 1,
            "trx_reset_gpio": 106,
            "trx_sysref_req_gpio": 112,
            "ad9528_reset_gpio": 113,
            "ad9528_vcxo_freq": DEFAULT_VCXO_HZ,
            "rx_link_id": 1,
            "tx_link_id": 0,
        },
        # JESD framing parameters matching the default HDL config for
        # ``projects/adrv9371x/zc706`` (see analogdevicesinc/hdl
        # README): RX = M=4 L=2 S=1 → F=4; TX = M=4 L=4 S=1 → F=2.
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 4, "L": 2},
            "tx": {"F": 2, "K": 32, "M": 4, "L": 4},
        },
    }

    # Pre-flight: catch cfg typos (swapped M/L, wrong F) before we
    # spend 60s compiling + deploying only to fail during ILAS.
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

    # --- 7. Gather JESD link + ILAS + DMA-path diagnostics. ---
    # The JESD-DATA assert is intentionally *disabled* here: the
    # bq run after the 122.88 MHz misc_clk fix (commit 99ad39c)
    # showed clocks match (Measured 122.882 / Reported 122.880 MHz)
    # but the AD9371 deframer reports ILAS mismatch on all 7
    # framing parameters (lanes/converter, scrambling, octets/frame,
    # frames/multiframe, converters, sample-resolution, control-
    # bits), so the link stays "disabled" — a framing-parameter fix
    # the profile-and-cfg combination needs, not a link-clock fix.
    # Keep printing the full status for future iterations.
    rx_status, tx_status = read_jesd_status(shell)
    print("=== JESD204 RX status (sysfs) ===")
    print(rx_status)
    print("=== JESD204 TX status (sysfs) ===")
    print(tx_status)

    # Surface AD937x ILAS state + assert it's clean.  The builder
    # now emits the full Kuiper-matching topology (xcvrs → AD9528,
    # phy → JESD cores, RX_OS overlay present), so every ILAS field
    # should match and all three JESD links should reach
    # "Link is enabled".
    ilas_report = parse_ilas_status(dmesg_txt)
    print("=== AD937x ILAS report ===")
    print(ilas_report.summary())
    if ilas_report.fields:
        for name in ilas_report.fields:
            print(f"  mismatched: {name}")
    assert_ilas_aligned(dmesg_txt, context="adrv9371_xsa")
    assert_jesd_links_data(shell, context="adrv9371_xsa")

    # HDL compile-time framing — read the TPL ADC/DAC/OBS descriptor
    # registers per
    # https://analogdevicesinc.github.io/hdl/library/jesd204/ad_ip_jesd204_tpl_{adc,dac}/
    # Descriptor 1 @ +0x240: [31:24]=F, [23:16]=S, [15:8]=L, [7:0]=M
    # Descriptor 2 @ +0x244: [15:8]=Np, [7:0]=N
    print("=== HDL compile-time JESD framing (TPL descriptor regs) ===")
    print("which devmem: " + shell_out(shell, "which devmem devmem2 busybox 2>/dev/null; busybox | head -1 2>/dev/null"))
    # Two descriptor words per TPL core: +0x240 and +0x244.
    # Decoded layout (per ADI HDL docs):
    #   d1[31:24]=F d1[23:16]=S d1[15:8]=L d1[7:0]=M
    #   d2[15:8]=Np d2[7:0]=N
    print(shell_out(shell, (
        "for base in 0x44a00000 0x44a04000 0x44a08000; do "
        "  echo \"--- TPL @ $base ---\"; "
        "  busybox devmem $(printf '0x%x' $((base + 0x240))) 2>&1; "
        "  busybox devmem $(printf '0x%x' $((base + 0x244))) 2>&1; "
        "done"
    )))

    # Dump TPL ADC sysfs (enable state, sampling freq, etc.) and DMA
    # controller state.  These surface the most common DMA-stall
    # causes: ADC channels not scan-enabled, TPL rate register at 0,
    # axi-dmac refusing to arm a descriptor, or the buffer sysfs
    # knob left disabled.
    print("=== TPL ADC sysfs (/sys/bus/iio/devices/<ad_ip_jesd204_tpl_adc>/) ===")
    print(shell_out(shell, (
        "tpl=$(ls -d /sys/bus/iio/devices/iio:device* 2>/dev/null "
        "| while read d; do "
        "  name=$(cat $d/name 2>/dev/null); "
        "  case \"$name\" in *tpl_adc*|*ad9371*rx*|*axi-ad9371-rx*) echo $d; esac; "
        "done | head -1); "
        "echo \"PATH: $tpl\"; "
        "[ -n \"$tpl\" ] && ls -la $tpl/; "
        "for f in \"$tpl\"/name \"$tpl\"/sampling_frequency \"$tpl\"/buffer/enable "
        "         \"$tpl\"/buffer/length \"$tpl\"/buffer/watermark; do "
        "  [ -e $f ] && printf '%s = %s\\n' $f \"$(cat $f 2>/dev/null)\"; "
        "done"
    )))
    print("=== TPL ADC channel enables ===")
    print(shell_out(shell, (
        "for ch in /sys/bus/iio/devices/iio:device*/scan_elements/*_en; do "
        "  [ -e $ch ] && printf '%s = %s\\n' $ch \"$(cat $ch 2>/dev/null)\"; "
        "done | grep -E 'tpl_adc|ad9371'"
    )))
    print("=== AXI DMAC (rx/tx) state ===")
    print(shell_out(shell, (
        "for d in /sys/bus/platform/devices/7c4?0000.axi_dmac; do "
        "  echo \"--- $d ---\"; ls $d 2>/dev/null; "
        "done; "
        "dmesg | grep -iE 'dmac|axi-dmac|dma' | tail -n 20"
    )))
    print("=== AD9371 phy sysfs snapshot ===")
    print(shell_out(shell, (
        "phy=$(find /sys/bus/iio/devices -maxdepth 2 -name ensm_mode 2>/dev/null "
        "     | xargs dirname 2>/dev/null | head -1); "
        "echo \"PHY: $phy\"; "
        "[ -n \"$phy\" ] && for f in $phy/ensm_mode $phy/gain_control_mode "
        "     $phy/in_voltage0_rf_bandwidth $phy/in_voltage0_sampling_frequency "
        "     $phy/rx_path_clks; do "
        "  [ -e $f ] && printf '%s = %s\\n' $f \"$(cat $f 2>/dev/null)\"; "
        "done"
    )))
    # TODO(adrv9371-capture): data-path smoke test still deferred.
    #
    # Progress across this series (all landed on this branch):
    #
    # - AD9528 channel@{1,3,12,13} subnodes + reset-gpios=<113>
    #   + jesd204-device / #jesd204-cells=2 /
    #   jesd204-sysref-provider flags.
    # - AD9371 reset-gpios=<106>, sysref-req-gpios=<112>.
    # - ~60 Mykonos ``adi,{rx,obs,tx,sniffer}-profile-*`` +
    #   ``adi,clocks-*`` baked into ad9371-phy@1.
    # - AD9528 added as jesd204-inputs link 2 on the AD9371.
    # - ``adi,{sys,out}-clk-select`` + ``adi,use-lpm-enable`` on
    #   the adxcvr (commit bad15c2) — unblocked axi-jesd204-rx/tx
    #   platform driver probe.
    # - ``misc_clk_0`` rate 245.76 → 122.88 MHz (commit 99ad39c)
    #   to match the real FMC clock that physically lands on the
    #   clkgen's clkin1.
    #
    # Now-observable state on bq (from the ``=== JESD204 ... ===``
    # dump above):
    #
    # - Measured Link Clock = Reported = 122.882 MHz → clock-layer
    #   healthy.
    # - JESD FSM reaches ``opt_post_running_stage`` on all 3 links
    #   (RX, TX, AD9528 sysref), no rollback.
    # - AD9371 firmware initialised ("AD9371 Rev 3, Firmware 5.2.2
    #   API version: 1.5.2.3566 successfully initialized via
    #   jesd204-fsm").
    # - TPL ADC + DAC both probe as MASTER.
    #
    # Still-open blocker — ILAS framing parameter mismatch:
    #
    #     ad9371 spi1.1: deframerStatus (0x21)
    #     ad9371 spi1.1: ILAS mismatch: c7f8
    #     ILAS lanes per converter did not match
    #     ILAS scrambling did not match
    #     ILAS octets per frame did not match
    #     ILAS frames per multiframe did not match
    #     ILAS number of converters did not match
    #     ILAS sample resolution did not match
    #     ILAS control bits per sample did not match
    #
    # After the link trains, every ILAS parameter disagrees between
    # what ``axi-jesd204-tx`` sends and what the AD9371's Mykonos
    # deframer expects (based on its profile).  The link drops to
    # ``Link is disabled`` and the TPL DMA has nothing to collect.
    #
    # The HDL reference (``analogdevicesinc/hdl/projects/adrv9371x/
    # zc706/README``) documents the default framing as::
    #
    #     TX_JESD_M=4, TX_JESD_L=4, TX_JESD_S=1   (→ F=2 for Np=16)
    #     RX_JESD_M=4, RX_JESD_L=2, RX_JESD_S=1   (→ F=4)
    #
    # Our ``axi-jesd204-tx`` overlay already emits F=2 (from the
    # ``tx_octets_per_frame`` default), M=4, Np=16, CS=2 — matching
    # HDL — and ``axi-jesd204-rx`` emits F=4.  All 7 ILAS params
    # still disagree, so the Mykonos profile we baked in
    # (``_DEFAULT_MYKONOS_PROFILE_PROPS``) must be for a different
    # HDL build than the default one the XSA represents.
    #
    # Next step: pair the profile to the HDL.  Either
    # (a) regenerate ``_DEFAULT_MYKONOS_PROFILE_PROPS`` from an
    # iio-oscilloscope profile whose implied JESD framing matches
    # (M=4, L=4, F=2, K=32, Np=16) for TX and (M=4, L=2, F=4, K=32,
    # Np=16) for RX — typically the 100 MHz-BW profile at a
    # specific IQ rate the HDL compiles in, or
    # (b) override ``trx_profile_props`` in the profile JSON for
    # this board to a per-profile list that matches the
    # build-time HDL settings.


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
