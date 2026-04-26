"""ADRV9371 + ZC706 hardware test.

Exercises the XSA pipeline path end-to-end on the ``bq`` labgrid place.

The standard verify body (boot, dmesg, IIO, JESD DATA) runs through
:func:`test.hw._system_base.run_xsa_boot_and_verify`.  Three pieces of
post-boot diagnostic output stay in this file because they are
ZC706+ADRV9371-specific forensics for documented bring-up blockers
(JESD framing-parameter mismatch, TPL ADC RSTN, AXI DMAC IRQ wiring):

* HDL compile-time JESD framing — read the TPL ADC/DAC/OBS descriptor
  registers per
  https://analogdevicesinc.github.io/hdl/library/jesd204/ad_ip_jesd204_tpl_{adc,dac}/
* TPL ADC sysfs snapshot (channel enables, sampling rate, buffer state).
* AXI DMAC + AD9371 phy snapshot (ENSM mode, RF bandwidth, sample rate).

LG_ENV: lg_adrv9371_zc706_tftp.yaml.
"""

from __future__ import annotations

from typing import Any

import pytest

from test.hw._system_base import (
    BoardSystemProfile,
    acquire_or_local_xsa,
    requires_lg,
    run_xsa_boot_and_verify,
)


DEFAULT_KUIPER_RELEASE = "2023_R2_P1"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv937x"
DEFAULT_VCXO_HZ = 122_880_000


def _adrv9371_cfg() -> dict[str, Any]:
    """ADRV9371+ZC706 XSA pipeline cfg.

    JESD framing matches the Kuiper reference
    ``zynq-zc706-adv7511-adrv937x``: RX = M=4 L=2 S=1 → F=4;
    TX = M=4 L=4 S=1 → F=2.
    """
    return {
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
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 4, "L": 2},
            "tx": {"F": 2, "K": 32, "M": 4, "L": 4},
        },
    }


def _topology_assert(topology) -> None:
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"


SPEC = BoardSystemProfile(
    lg_features=("adrv9371", "zc706"),
    cfg_builder=_adrv9371_cfg,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_adrv9371_zc706.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
    ),
    topology_assert=_topology_assert,
    boot_mode="tftp",
    kernel_fixture_name="built_kernel_image_zynq",
    out_label="adrv9371_xsa",
    dmesg_grep_pattern="ad9371|ad9528|jesd204|mykonos|probe|failed|error",
    merged_dts_must_contain=('compatible = "adi,ad9371"',),
    probe_signature_any=("ad9371", "mykonos"),
    probe_signature_message="AD9371 driver probe signature not found in dmesg",
    iio_required_any=("9371", "adrv9", "9528"),
    iio_frontend_label="AD9371 / ADRV9xxx phy device",
)


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_adrv9371_zc706_xsa_hw(board, tmp_path, request):
    """End-to-end pyadi-dt ADRV9371+ZC706 via the XSA pipeline."""
    from test.hw.hw_helpers import (
        assert_ilas_aligned,
        assert_jesd_links_data,
        parse_ilas_status,
        read_jesd_status,
        shell_out,
    )

    shell, _ctx, dmesg_txt = run_xsa_boot_and_verify(
        SPEC, board=board, request=request, tmp_path=tmp_path
    )

    rx_status, tx_status = read_jesd_status(shell)
    print("=== JESD204 RX status (sysfs) ===")
    print(rx_status)
    print("=== JESD204 TX status (sysfs) ===")
    print(tx_status)

    ilas_report = parse_ilas_status(dmesg_txt)
    print("=== AD937x ILAS report ===")
    print(ilas_report.summary())
    if ilas_report.fields:
        for name in ilas_report.fields:
            print(f"  mismatched: {name}")
    assert_ilas_aligned(dmesg_txt, context="adrv9371_xsa")
    assert_jesd_links_data(shell, context="adrv9371_xsa")

    # HDL compile-time framing — TPL descriptor registers.
    # Descriptor 1 @ +0x240: [31:24]=F, [23:16]=S, [15:8]=L, [7:0]=M
    # Descriptor 2 @ +0x244: [15:8]=Np, [7:0]=N
    print("=== HDL compile-time JESD framing (TPL descriptor regs) ===")
    print(
        "which devmem: "
        + shell_out(
            shell,
            "which devmem devmem2 busybox 2>/dev/null; busybox | head -1 2>/dev/null",
        )
    )
    print(
        shell_out(
            shell,
            (
                "for base in 0x44a00000 0x44a04000 0x44a08000; do "
                '  echo "--- TPL @ $base ---"; '
                "  busybox devmem $(printf '0x%x' $((base + 0x240))) 2>&1; "
                "  busybox devmem $(printf '0x%x' $((base + 0x244))) 2>&1; "
                "done"
            ),
        )
    )

    print("=== TPL ADC sysfs (/sys/bus/iio/devices/<ad_ip_jesd204_tpl_adc>/) ===")
    print(
        shell_out(
            shell,
            (
                "tpl=$(ls -d /sys/bus/iio/devices/iio:device* 2>/dev/null "
                "| while read d; do "
                "  name=$(cat $d/name 2>/dev/null); "
                '  case "$name" in *tpl_adc*|*ad9371*rx*|*axi-ad9371-rx*) echo $d; esac; '
                "done | head -1); "
                'echo "PATH: $tpl"; '
                '[ -n "$tpl" ] && ls -la $tpl/; '
                'for f in "$tpl"/name "$tpl"/sampling_frequency "$tpl"/buffer/enable '
                '         "$tpl"/buffer/length "$tpl"/buffer/watermark; do '
                "  [ -e $f ] && printf '%s = %s\\n' $f \"$(cat $f 2>/dev/null)\"; "
                "done"
            ),
        )
    )
    print("=== TPL ADC channel enables ===")
    print(
        shell_out(
            shell,
            (
                "for ch in /sys/bus/iio/devices/iio:device*/scan_elements/*_en; do "
                "  [ -e $ch ] && printf '%s = %s\\n' $ch \"$(cat $ch 2>/dev/null)\"; "
                "done | grep -E 'tpl_adc|ad9371'"
            ),
        )
    )
    print("=== AXI DMAC (rx/tx) state ===")
    print(
        shell_out(
            shell,
            (
                "for d in /sys/bus/platform/devices/7c4?0000.axi_dmac; do "
                '  echo "--- $d ---"; ls $d 2>/dev/null; '
                "done; "
                "dmesg | grep -iE 'dmac|axi-dmac|dma' | tail -n 20"
            ),
        )
    )
    print("=== AD9371 phy sysfs snapshot ===")
    print(
        shell_out(
            shell,
            (
                "phy=$(find /sys/bus/iio/devices -maxdepth 2 -name ensm_mode 2>/dev/null "
                "     | xargs dirname 2>/dev/null | head -1); "
                'echo "PHY: $phy"; '
                '[ -n "$phy" ] && for f in $phy/ensm_mode $phy/gain_control_mode '
                "     $phy/in_voltage0_rf_bandwidth $phy/in_voltage0_sampling_frequency "
                "     $phy/rx_path_clks; do "
                "  [ -e $f ] && printf '%s = %s\\n' $f \"$(cat $f 2>/dev/null)\"; "
                "done"
            ),
        )
    )


# ---------------------------------------------------------------------------
# System API test
# ---------------------------------------------------------------------------
#
# The declarative :class:`adidt.System` path does not yet emit the
# topology-aware XCVR / TPL-core / clkgen overlays that the ZC706 + AD9371
# design needs to bind; ``apply_xsa_topology`` only overrides the JESD204
# framing labels, leaving default ``axi_adrv9009_*`` xcvr/core labels that
# do not exist in the ZC706 base DTS.  A structural smoke test lives at
# ``test/devices/test_system_adrv937x_zc706.py``; the end-to-end hardware
# path is covered by :func:`test_adrv9371_zc706_xsa_hw` above.
