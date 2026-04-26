"""ADRV9371 + ZC706 hardware test driven by the PetaLinux flow.

PetaLinux variant of :mod:`test.hw.test_adrv9371_zc706_hw`.  Reuses the
same SPEC and the same ZC706+ADRV9371-specific diagnostic tail (TPL
descriptor regs, AXI DMAC state, AD9371 phy snapshot).

LG_ENV: ``test/hw/env/bq.yaml``.  The ``bq`` host owns the local
``TFTPServerResource`` so this test must be invoked from there.
"""

from __future__ import annotations

import dataclasses

import pytest

from test.hw._petalinux_base import (
    requires_lg,
    requires_petalinux,
    run_petalinux_build_and_verify,
)
from test.hw.test_adrv9371_zc706_hw import SPEC as XSA_SPEC


SPEC = dataclasses.replace(XSA_SPEC, out_label="adrv9371_zc706_petalinux")


@requires_lg
@requires_petalinux
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_adrv9371_zc706_petalinux_hw(board, tmp_path, request):
    """End-to-end pyadi-dt ADRV9371+ZC706 boot + verify (PetaLinux path)."""
    from test.hw.hw_helpers import (
        assert_ilas_aligned,
        assert_jesd_links_data,
        parse_ilas_status,
        read_jesd_status,
        shell_out,
    )

    shell, _ctx, dmesg_txt = run_petalinux_build_and_verify(
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
    assert_ilas_aligned(dmesg_txt, context=SPEC.out_label)
    assert_jesd_links_data(shell, context=SPEC.out_label)

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
