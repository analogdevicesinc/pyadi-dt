"""ADRV9009 + ZC706 runtime device-tree overlay hardware test.

Same six-test shape as the rest of the overlay suite — fixtures + tests
live in :mod:`test.hw.xsa._overlay_base`.

Per-board specifics that stay in this file:

* :func:`_adrv9009_cfg` — JESD framing + GPIO + clock cfg matching the
  Kuiper reference design ``zynq-zc706-adv7511-adrv9009``.
* :func:`_filter_si570_probe_noise` — strips the benign si570 ``-EIO``
  probe lines from dmesg before :func:`assert_no_probe_errors`.  The
  optional Si570 clock chip on the ADRV9009-FMC sometimes does not ACK
  at its default I2C address; the failure is present in the production
  reference DT too and is unrelated to the overlay path.

Per-family hooks pulled in from :mod:`test.hw.xsa._overlay_hooks`:

* :func:`push_talise_profile` — ZC706 + ADRV9009 leaves buffered RX
  inert in the default post-boot Talise state.  Pushing any DC-245.76
  MHz profile re-inits the radio to ``radio_on`` without changing the
  JESD lane rate.
* :func:`resolve_adrv9009_rx_tpl` — picks the RX TPL by reg address
  when the OBS TPL shares the same IIO name (sdtgen DTB).

LG_ENV: ``test/hw/env/nemo.yaml``.
"""

from __future__ import annotations

from typing import Any

import pytest

from test.hw.hw_helpers import check_jesd_framing_plausibility
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
from test.hw.xsa._overlay_hooks import push_talise_profile, resolve_adrv9009_rx_tpl
from test.hw.xsa._overlay_spec import BoardOverlayProfile, acquire_or_local_xsa


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv9009"


def _adrv9009_cfg() -> dict[str, Any]:
    """ADRV9009+ZC706 XSA pipeline cfg.

    Hardcoded JESD framing matches Kuiper's stock
    ``zynq-zc706-adv7511-adrv9009`` reference design.  ADRV9009Builder
    defaults to ZCU102 GPIOs (130/136); ZC706 wires the same signals to
    gpio0:106 (reset) and gpio0:112 (sysref-req), matching the Kuiper
    production zynq-zc706-adv7511-adrv9009 DT.
    """
    cfg: dict[str, Any] = {
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
    return cfg


def _filter_si570_probe_noise(dmesg_txt: str) -> str:
    """Strip benign si570 -EIO probe lines from dmesg."""
    return "\n".join(
        line
        for line in dmesg_txt.splitlines()
        if not ("si570" in line and "failed" in line)
    )


def _topology_assert(topology) -> None:
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"


SPEC = BoardOverlayProfile(
    overlay_name="adrv9009_zc706_xsa",
    lg_features=("adrv9009", "zc706"),
    skip_reason_label="adrv9009 zc706",
    cfg_builder=_adrv9009_cfg,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_adrv9009_zc706.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
    ),
    sdtgen_profile="adrv9009_zc706",
    topology_assert=_topology_assert,
    dtso_must_contain_any=("axi-jesd204", "adrv9009"),
    boot_mode="tftp",
    kernel_fixture_name="built_kernel_image_zynq",
    settle_after_apply_s=8.0,  # Talise re-init is slower than AD9081.
    iio_required_all=("adrv9009-phy",),
    iio_required_any=(
        "axi-adrv9009-rx-hpc",
        "axi-adrv9009-rx-obs-hpc",
        "ad_ip_jesd204_tpl_adc",
    ),
    iio_frontend_label="ADRV9009 RX frontend",
    dmesg_filter=_filter_si570_probe_noise,
    fft_mode="optional",
    pre_capture_hook=push_talise_profile,
    capture_targets_resolver=resolve_adrv9009_rx_tpl,
    pyadi_class_name="adrv9009",
)


@pytest.fixture(scope="module")
def overlay_spec() -> BoardOverlayProfile:
    return SPEC
