"""AD9081 + ZCU102 runtime device-tree overlay hardware test.

Same six-test shape as the rest of the overlay suite — fixtures + tests
live in :mod:`test.hw.xsa._overlay_base`.  Per-board specifics
(:func:`_solve_ad9081_config`, :func:`_create_ad9081`) stay in this
file because they are genuinely AD9081-only.

Boot strategy: ``KuiperDLDriver.get_boot_files_from_release()`` followed
by an SD-card stage of the merged DTB (renamed to ``system.dtb`` so
Kuiper's ZCU102 U-Boot picks it up).  The merged DTB has the AD9081
SPI nodes already in place, so the overlay exercises the configfs
lifecycle on top of an already-probed tree.

Stock-Kuiper boot was tried first; on the lab's current 2023_R2 image
the AD9081 SPI probe fails at boot with ``-EBUSY`` (the bitstream's
clock chain is not yet up when the SPI driver runs), which then makes
every subsequent overlay test see an unrelated boot-time error.
Booting with our merged DTB avoids that and is deterministic across
runs.

LG_ENV / LG_COORDINATOR: see ``.env.example``.  Runs against the
``mini2`` labgrid place (ZCU102 + AD9081-FMCA-EBZ).
"""

from __future__ import annotations

from typing import Any

import pytest

from test.hw.xsa._overlay_base import (  # noqa: F401 — pytest collects these
    booted_board,
    overlay_dtbo,
    pipeline_result,
    test_overlay_generation_unit,
    test_configfs_overlay_support,
    test_load_overlay,
    test_dma_loopback,
    test_unload_overlay,
    test_reload_overlay,
)
from test.hw.xsa._overlay_spec import BoardOverlayProfile, acquire_or_local_xsa


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9081"
DEFAULT_VCXO_HZ = 122_880_000


def _solve_ad9081_config(vcxo_hz: int = DEFAULT_VCXO_HZ) -> dict[str, Any]:
    """Resolve AD9081 JESD mode + datapath + clocks via pyadi-jif.

    Uses the same M8/L4 jesd204b pinning as Kuiper's reference
    ``zynqmp-zcu102-rev10-ad9081-m8-l4.dts``: ``rx_link_mode=10``,
    ``tx_link_mode=9``.
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


def _create_ad9081(uri: str):
    """Return an ``adi.ad9081`` that tolerates sdtgen IIO device names.

    pyadi-iio's ``adi.ad9081`` hardcodes ``axi-ad9081-{rx,tx}-hpc``.  If
    the live context exposes the sdtgen-generated TPL names instead, the
    standard constructor raises ``AttributeError``; we fall back to a
    patched ``iio.Context`` that aliases the TPL names to the hpc ones.
    """
    import adi
    import iio

    try:
        return adi.ad9081(uri=uri)
    except (AttributeError, TypeError):
        pass

    ctx = iio.Context(uri)
    name_map = {
        "axi-ad9081-rx-hpc": "ad_ip_jesd204_tpl_adc",
        "axi-ad9081-tx-hpc": "ad_ip_jesd204_tpl_dac",
    }
    orig_find = ctx.find_device

    def _patched_find(name):
        result = orig_find(name)
        if result is None and name in name_map:
            result = orig_find(name_map[name])
        return result

    ctx.find_device = _patched_find

    dev = adi.ad9081.__new__(adi.ad9081)
    dev._ctx = ctx
    dev.uri = uri
    adi.ad9081.__init__(dev, uri=uri)
    return dev


def _topology_assert(topology) -> None:
    assert topology.has_converter_types("axi_ad9081"), (
        f"XSA topology is not AD9081: converter IPs = "
        f"{[c.ip_type for c in topology.converters]}"
    )


SPEC = BoardOverlayProfile(
    overlay_name="ad9081_zcu102_xsa",
    lg_features=("ad9081", "zcu102"),
    skip_reason_label="ad9081 zcu102",
    cfg_builder=_solve_ad9081_config,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_ad9081_zcu102.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
        fallback_filenames=("system_top.xsa",),
    ),
    sdtgen_profile="ad9081_zcu102",
    topology_assert=_topology_assert,
    dtso_must_contain_all=("axi-ad9081",),
    boot_mode="sd",
    kernel_fixture_name="built_kernel_image_zynqmp",
    iio_required_all=("hmc7044",),
    iio_required_any=("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc"),
    iio_frontend_label="AD9081 RX frontend",
    fft_mode="required",
    capture_target_names=("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc"),
    pyadi_factory=_create_ad9081,
    pyadi_class_name="ad9081",
)


@pytest.fixture(scope="module")
def overlay_spec() -> BoardOverlayProfile:
    return SPEC
