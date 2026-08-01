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

import copy
import os
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from adidt.profiles import resolve_ad9371_jif_config
from test.hw._system_base import (
    BoardSystemProfile,
    acquire_or_local_xsa,
    requires_lg,
    run_xsa_boot_and_verify,
)


DEFAULT_KUIPER_RELEASE = "2023_R2_P1"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv937x"
PROFILE_PATH = (
    Path(__file__).parents[2]
    / "examples/xsa/profiles/ad9371_5/profile_TxBW200_ORxBW200_RxBW100.txt"
)
PROFILE_DIR = Path(__file__).parents[2] / "examples/xsa/profiles/ad9371_5"

# Alternate (non-canonical) profiles booted only when the operator opts
# into the sweep.  Booting six DTBs sequentially on the single ZC706
# would blow the per-run hardware budget, so the default matrix boots the
# canonical profile (via ``test_adrv9371_zc706_xsa_hw``) and this sweep is
# gated behind ``ADIDT_AD9371_PROFILE_SWEEP=1``.
_ALTERNATE_PROFILES = (
    "profile_TxBW100_ORxBW100_RxBW100.txt",
    "profile_TxBW100_ORxBW100_RxBW50.txt",
    "profile_TxBW100_ORxBW100_RxBW20.txt",
    "profile_TxBW50_ORxBW50_RxBW50.txt",
    "profile_TxBW50_ORxBW50_RxBW25.txt",
)
_PROFILE_SWEEP_ENABLED = os.environ.get("ADIDT_AD9371_PROFILE_SWEEP") == "1"


@cache
def _solved_ad9371_config() -> tuple[dict[str, Any], dict[str, Any]]:
    """Solve the canonical profile once for this hardware-test process."""
    return resolve_ad9371_jif_config(PROFILE_PATH, solve=True)


@cache
def _solved_config_for(profile_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Solve an arbitrary shipped profile once per hardware-test process."""
    return resolve_ad9371_jif_config(PROFILE_DIR / profile_name, solve=True)


def _board_wiring(cfg: dict[str, Any]) -> dict[str, Any]:
    """Overlay the ZC706 board wiring onto a solved cfg (in place, copied)."""
    cfg = copy.deepcopy(cfg)
    cfg["adrv9009_board"].update(
        {
            "misc_clk_hz": 122_880_000,
            "spi_bus": "spi0",
            "clk_cs": 0,
            "trx_cs": 1,
            "trx_reset_gpio": 106,
            "trx_sysref_req_gpio": 112,
            "ad9528_reset_gpio": 113,
            "rx_link_id": 1,
            "rx_os_link_id": 2,
            "tx_link_id": 0,
        }
    )
    return cfg


def _adrv9371_cfg() -> dict[str, Any]:
    """Return the real solved pyadi-jif configuration plus board wiring."""
    cfg, _summary = _solved_ad9371_config()
    return _board_wiring(cfg)


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
    merged_dts_must_contain=(
        'compatible = "adi,ad9371"',
        'compatible = "adi,axi-ad9371-obs-1.0"',
    ),
    probe_signature_any=("ad9371", "mykonos"),
    probe_signature_message="AD9371 driver probe signature not found in dmesg",
    iio_required_all=("ad9371-phy", "ad9528-1"),
    expected_rx_jesd_links=2,
    rx_capture_target_names=("axi-ad9371-rx-hpc", "ad_ip_jesd204_tpl_adc"),
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

    cfg, solver_summary = _solved_ad9371_config()
    assert solver_summary["solver_succeeded"] is True
    clocks = solver_summary["clock_output_clocks"]
    assert clocks["adc_sysref"]["rate"] == clocks["obs_sysref"]["rate"]
    assert clocks["obs_sysref"]["rate"] == clocks["dac_sysref"]["rate"]
    assert {cfg[name]["type"] for name in ("fpga_adc", "fpga_obs", "fpga_dac")} == {
        "qpll"
    }
    print(f"pyadi-jif solved clock outputs: {clocks}")

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
    assert_jesd_links_data(
        shell, context="adrv9371_xsa", expected_rx_links=2
    )

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


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_adrv9371_zc706_obs_capture(board, tmp_path, request):
    """Observation-receiver enumeration + data-movement on real hardware.

    The obs JESD link reaches DATA and the obs TPL/DMAC blocks exist in
    the generated DT (TPL ``0x44a08000`` / DMAC ``0x7c440000``), but the
    primary-RX system test does not prove the *observation* data path
    moves samples.  This test:

    1. Boots the same solved-config DTB via the shared harness.
    2. Snapshots how (or whether) the obs receiver enumerates as an IIO
       device — see :func:`probe_obs_enumeration`.
    3. Dumps obs TPL-core + DMAC sysfs/register state for forensics.
    4. If the obs device enumerates with an RX scan element, captures a
       buffer and asserts non-zero, non-latched samples — closing the
       observation data-movement gap.
    5. If it does not enumerate, records the driver-side gap explicitly
       (``xfail``) rather than passing silently — the DT is correct and
       matches the Kuiper reference, so this is a kernel/driver binding
       limitation, not a pyadi-dt regression.
    """
    from test.hw.hw_helpers import (
        OBS_DMAC_ADDR,
        OBS_TPL_ADDR,
        assert_jesd_links_data,
        assert_rx_capture_valid,
        find_obs_capture_device,
        probe_obs_enumeration,
        shell_out,
    )

    shell, ctx, _dmesg = run_xsa_boot_and_verify(
        SPEC, board=board, request=request, tmp_path=tmp_path
    )

    # The obs link must be in DATA for any capture to be meaningful.
    assert_jesd_links_data(shell, context="adrv9371_obs", expected_rx_links=2)

    print("=== Observation TPL core + DMAC sysfs/register state ===")
    print(
        shell_out(
            shell,
            (
                f"echo '--- obs TPL @ 0x{OBS_TPL_ADDR} ---'; "
                f"busybox devmem 0x{OBS_TPL_ADDR}240 2>&1; "
                f"busybox devmem 0x{OBS_TPL_ADDR}244 2>&1; "
                f"echo '--- obs DMAC @ 0x{OBS_DMAC_ADDR} ---'; "
                f"for d in /sys/bus/platform/devices/*{OBS_DMAC_ADDR}*; do "
                '  echo "$d"; ls "$d" 2>/dev/null; done; '
                "echo '--- IIO devices ---'; "
                "for d in /sys/bus/iio/devices/iio:device*; do "
                "  printf '%s = %s\\n' \"$d\" \"$(cat $d/name 2>/dev/null)\"; done"
            ),
        )
    )

    snapshot = probe_obs_enumeration(ctx)
    print(f"=== Observation enumeration snapshot ===\n{snapshot}")
    assert snapshot["primary_rx"] is not None, (
        "Primary RX device missing — boot/verify should have caught this"
    )

    obs_dev = find_obs_capture_device(ctx)
    if obs_dev is None:
        pytest.xfail(
            "AD9371 observation receiver does not enumerate as a distinct "
            "capturable IIO device on this kernel. The generated DT node "
            "(compatible adi,axi-ad9371-obs-1.0 at 0x44a08000, DMAC "
            "0x7c440000) matches the Kuiper reference design; obs capture "
            "is gated on driver/kernel obs-buffer binding, not pyadi-dt DT "
            f"generation. Devices present: {snapshot['all_devices']}"
        )
        return  # pragma: no cover — pytest.xfail raises; aids type-narrowing

    # Obs device enumerated — prove it actually moves samples.
    assert obs_dev.name != snapshot["primary_rx"], (
        f"Obs device resolver returned the primary RX device "
        f"{obs_dev.name!r} — obs/primary disambiguation failed"
    )
    assert_rx_capture_valid(
        ctx,
        (obs_dev.name,),
        n_samples=2**12,
        context="adrv9371_obs",
    )


@requires_lg
@pytest.mark.skipif(
    not _PROFILE_SWEEP_ENABLED,
    reason=(
        "AD9371 alternate-profile hardware sweep is opt-in; set "
        "ADIDT_AD9371_PROFILE_SWEEP=1 to boot + capture all shipped "
        "profiles (booting six DTBs on one ZC706 is budget-heavy)."
    ),
)
@pytest.mark.lg_feature(list(SPEC.lg_features))
@pytest.mark.parametrize("profile_name", _ALTERNATE_PROFILES)
def test_adrv9371_zc706_profile_sweep_hw(profile_name, board, tmp_path, request):
    """Boot + RX-capture each alternate AD9371 profile on real hardware.

    The default matrix boots only the canonical
    ``TxBW200_ORxBW200_RxBW100`` profile.  This opt-in sweep proves the
    remaining shipped profiles also generate a bootable DTB whose primary
    RX path moves samples at the profile's distinct sample rate.  Each
    parameter reruns the full XSA → pipeline → boot → verify flow with
    the profile's own solved configuration.
    """
    cfg, summary = _solved_config_for(profile_name)
    assert summary["solver_succeeded"] is True
    wired = _board_wiring(cfg)

    # A per-parameter SPEC identical to the canonical one but driven by
    # this profile's solved cfg and labelled for its dmesg artifacts.
    label = profile_name.replace("profile_", "").replace(".txt", "").lower()
    spec = BoardSystemProfile(
        lg_features=SPEC.lg_features,
        cfg_builder=lambda: wired,
        xsa_resolver=SPEC.xsa_resolver,
        topology_assert=SPEC.topology_assert,
        boot_mode=SPEC.boot_mode,
        kernel_fixture_name=SPEC.kernel_fixture_name,
        out_label=f"adrv9371_{label}",
        dmesg_grep_pattern=SPEC.dmesg_grep_pattern,
        merged_dts_must_contain=SPEC.merged_dts_must_contain,
        probe_signature_any=SPEC.probe_signature_any,
        probe_signature_message=SPEC.probe_signature_message,
        iio_required_all=SPEC.iio_required_all,
        expected_rx_jesd_links=SPEC.expected_rx_jesd_links,
        rx_capture_target_names=SPEC.rx_capture_target_names,
    )

    shell, _ctx, _dmesg = run_xsa_boot_and_verify(
        spec, board=board, request=request, tmp_path=tmp_path
    )

    from test.hw.hw_helpers import assert_jesd_links_data, shell_out

    assert_jesd_links_data(shell, context=spec.out_label, expected_rx_links=2)
    print(f"=== {profile_name}: solved rates {summary['rates_hz']} ===")
    print(
        "AD9371 phy sample rates: "
        + shell_out(
            shell,
            "phy=$(find /sys/bus/iio/devices -maxdepth 2 -name ensm_mode "
            "2>/dev/null | xargs dirname 2>/dev/null | head -1); "
            '[ -n "$phy" ] && '
            "cat $phy/in_voltage0_sampling_frequency 2>/dev/null || "
            "echo unavailable",
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
