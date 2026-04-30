"""FMCDAQ3 + VCU118 runtime device-tree overlay hardware test.

Same six-test shape as the AD9081/ADRV9009/ADRV9371 overlay tests; the
shared fixtures + tests live in :mod:`test.hw.xsa._overlay_base`.

Differences encoded in :data:`SPEC`:

* **Boot transport** — VCU118 runs a MicroBlaze soft CPU from the FPGA
  fabric; there is no PS, U-Boot, SD card, or TFTP path.  Labgrid drives
  the boot through :class:`BootFabric` + :class:`XilinxDeviceJTAG` on
  the ``nuc`` exporter, which loads the bitstream and a
  ``simpleImage.vcu118_fmcdaq3.strip`` (kernel + embedded DTB) over
  JTAG.  The overlay is layered on top of the embedded DTB at runtime
  via configfs — no DTB rebuild and no kernel-image fixture are
  required (``boot_mode="fabric_jtag"``, ``kernel_fixture_name=None``).

* **Configfs gate** — Kuiper's MicroBlaze simpleImage is the most
  likely place we will find ``CONFIG_OF_OVERLAY``/``CONFIG_OF_CONFIGFS``
  missing.  The shared ``booted_board`` fixture probes for the
  configfs overlay directory in ``fabric_jtag`` mode and skips the
  lifecycle/DMA tests cleanly when absent;
  :func:`test_configfs_overlay_support` retains its strict-assert
  behavior so a configfs-less kernel is still an explicit failure of
  *that* test (it uses the ``board`` fixture directly, bypassing
  ``booted_board``).

* **XSA prerequisite** — the standard Kuiper boot-partition release
  does not include a ``vcu118_fmcdaq3`` project (it only ships Zynq
  family projects), so :func:`acquire_xsa` cannot download one.  The
  FMCDAQ3+VCU118 ``system_top.xsa`` from the local HDL/PetaLinux build
  must be committed to ``test/hw/xsa/system_top_fmcdaq3_vcu118.xsa``
  before the test can run; ``local_xsa_or_skip`` ``pytest.skip``s with
  a clear message until that file is present.

LG_ENV: ``test/hw/env/nuc.yaml``.
"""

from __future__ import annotations

from typing import Any

import pytest

from test.hw.hw_helpers import check_jesd_framing_plausibility
from test.hw.xsa._overlay_base import (  # noqa: F401 — pytest collects these
    # Fixtures (alphabetical, F401 above suppresses unused-import warning).
    booted_board,
    overlay_dtbo,
    pipeline_result,
    # Tests — import order is collection / execution order.  Keep the
    # canonical six-step shape: unit, configfs, load, dma, unload, reload.
    # ``test_dma_loopback`` skips itself if the overlay is not loaded, so
    # it must follow ``test_load_overlay``; the rest are independent but
    # share module-scoped fixtures whose teardown happens once at the end.
    test_overlay_generation_unit,
    test_configfs_overlay_support,
    test_load_overlay,
    test_dma_loopback,
    test_unload_overlay,
    test_reload_overlay,
)
from test.hw.xsa._overlay_spec import BoardOverlayProfile, local_xsa_or_skip


def _fmcdaq3_vcu118_cfg() -> dict[str, Any]:
    """FMCDAQ3+VCU118 XSA pipeline cfg.

    The profile JSON ``adidt/xsa/config/profiles/fmcdaq3_vcu118.json`` already
    supplies the full ``fmcdaq3_board`` defaults and the JESD framing
    (RX & TX both M=2 L=4 F=1 Np=16 S=1, the FMCDAQ3 reference HDL
    default).  We re-state the framing here only so
    :func:`check_jesd_framing_plausibility` can sanity-check it before
    the pipeline is run.
    """
    cfg: dict[str, Any] = {
        "fmcdaq3_board": {},
        "jesd": {
            "rx": {"F": 1, "K": 32, "M": 2, "L": 4, "Np": 16, "S": 1},
            "tx": {"F": 1, "K": 32, "M": 2, "L": 4, "Np": 16, "S": 1},
        },
    }
    framing_warnings = check_jesd_framing_plausibility(cfg["jesd"])
    assert not framing_warnings, (
        "JESD cfg is structurally inconsistent (will fail ILAS):\n  "
        + "\n  ".join(framing_warnings)
    )
    return cfg


def _topology_assert(topology) -> None:
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"


SPEC = BoardOverlayProfile(
    overlay_name="fmcdaq3_vcu118_xsa",
    lg_features=("fmcdaq3", "vcu118"),
    skip_reason_label="fmcdaq3 vcu118",
    cfg_builder=_fmcdaq3_vcu118_cfg,
    xsa_resolver=local_xsa_or_skip("system_top_fmcdaq3_vcu118.xsa"),
    sdtgen_profile="fmcdaq3_vcu118",
    topology_assert=_topology_assert,
    dtso_must_contain_any=("ad9680", "ad9152", "axi-jesd204"),
    boot_mode="fabric_jtag",
    iio_required_all=("ad9528",),
    iio_required_any=(
        "axi-ad9680-hpc",
        "axi-ad9680-rx-hpc",
        "axi-ad9680-core-lpc",
        "ad_ip_jesd204_tpl_adc",
    ),
    iio_frontend_label="AD9680 RX frontend",
    fft_mode="skip",
    capture_target_names=(
        "axi-ad9680-hpc",
        "axi-ad9680-rx-hpc",
        "axi-ad9680-core-lpc",
        "ad_ip_jesd204_tpl_adc",
    ),
)


@pytest.fixture(scope="module")
def overlay_spec() -> BoardOverlayProfile:
    return SPEC
