"""AD9081 + ZCU102 hardware test driven by the XSA pipeline.

Parallels :mod:`test.hw.test_adrv9009_zcu102_hw` stage-for-stage but
uses :class:`adidt.xsa.pipeline.XsaPipeline` + :class:`AD9081Builder`
instead of the declarative :class:`adidt.System` path.  The XSA
pipeline handles the full set of topology-driven overlays (XCVR clock
refs, TPL core binding, JESD link IDs, ``dev_clk`` phandles) that the
System path does not yet emit, so this variant reaches a fully probed
IIO device where the System test still falls short.

LG_ENV / LG_COORDINATOR: see ``.env.example``.  The test runs against
the ``mini2`` place (ZCU102 + AD9081-FMCA-EBZ) on the coordinator.
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


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9081"
DEFAULT_VCXO_HZ = 122_880_000


def _solve_ad9081_config(vcxo_hz: int = DEFAULT_VCXO_HZ) -> dict[str, Any]:
    """Resolve AD9081 JESD mode + datapath + clocks via pyadi-jif.

    Pins the AD9081 link modes to the jesd204b values Kuiper's stock
    ``m8_l4_vcxo122p88/system.dtb`` uses (rx=10, tx=9).  The default
    ``(M=8, L=4)`` lookup picks ``(17, 18)`` — jesd204c modes that
    fail the AD9081 driver's link-config table check.
    """
    try:
        import adijif
    except ModuleNotFoundError as exc:
        pytest.skip(f"pyadi-jif not available: {exc}")

    sys = adijif.system("ad9081", "hmc7044", "xilinx", vcxo=vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")

    cddc, fddc, cduc, fduc = 4, 4, 8, 6
    sys.converter.clocking_option = "integrated_pll"
    sys.converter.adc.sample_clock = 4_000_000_000 / cddc / fddc
    sys.converter.dac.sample_clock = 12_000_000_000 / cduc / fduc
    sys.converter.adc.datapath.cddc_decimations = [cddc] * 4
    sys.converter.dac.datapath.cduc_interpolation = cduc
    sys.converter.adc.datapath.fddc_decimations = [fddc] * 8
    sys.converter.dac.datapath.fduc_interpolation = fduc
    sys.converter.adc.datapath.fddc_enabled = [True] * 8
    sys.converter.dac.datapath.fduc_enabled = [True] * 8

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc, M=8, L=4, Np=16, jesd_class="jesd204b"
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac, M=8, L=4, Np=16, jesd_class="jesd204b"
    )
    if not mode_rx or not mode_tx:
        pytest.skip("pyadi-jif: no matching AD9081 M8/L4 mode found")

    rx_settings = mode_rx[0]["settings"]
    tx_settings = mode_tx[0]["settings"]

    return {
        "jesd": {
            "rx": {k: int(rx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
            "tx": {k: int(tx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
        },
        "ad9081": {
            "rx_link_mode": 10,
            "tx_link_mode": 9,
        },
    }


def _topology_assert(topology) -> None:
    assert topology.has_converter_types("axi_ad9081"), (
        f"XSA topology is not AD9081: converter IPs = "
        f"{[c.ip_type for c in topology.converters]}"
    )
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"


SPEC = BoardSystemProfile(
    lg_features=("ad9081", "zcu102"),
    cfg_builder=_solve_ad9081_config,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_ad9081_zcu102.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
    ),
    sdtgen_profile="ad9081_zcu102",
    topology_assert=_topology_assert,
    boot_mode="sd",
    kernel_fixture_name="built_kernel_image_zynqmp",
    out_label="ad9081_xsa",
    dmesg_grep_pattern="ad9081|hmc7044|jesd204|probe|failed|error",
    merged_dts_must_contain=(
        'compatible = "adi,ad9081"',
        'compatible = "adi,hmc7044"',
    ),
    probe_signature_any=("AD9081 Rev.", "probed ADC AD9081"),
    probe_signature_message="AD9081 probe signature not found in dmesg",
    iio_required_all=("hmc7044",),
    iio_required_any_groups=(
        ("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc"),
        ("axi-ad9081-tx-hpc", "ad_ip_jesd204_tpl_dac"),
    ),
    jesd_rx_glob="84a90000.axi[_-]jesd204[_-]rx",
    jesd_tx_glob="84b90000.axi[_-]jesd204[_-]tx",
    rx_capture_target_names=("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc"),
)


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_ad9081_zcu102_xsa_hw(board, tmp_path, request):
    """End-to-end pyadi-dt AD9081+ZCU102 boot + IIO verification (XSA path)."""
    run_xsa_boot_and_verify(SPEC, board=board, request=request, tmp_path=tmp_path)
