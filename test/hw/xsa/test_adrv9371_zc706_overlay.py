"""ADRV9371 + ZC706 runtime device-tree overlay hardware test.

Same six-test shape as the rest of the overlay suite — fixtures + tests
live in :mod:`test.hw.xsa._overlay_base`.

Per-board specifics that stay in this file:

* :func:`_adrv9371_cfg` — the JESD framing + GPIO + AD9528 cfg.  Kept
  here because it is genuinely board-specific (gpio0:106 reset,
  gpio0:112 sysref-req, etc.) and is the same wiring the merged-DTB
  test ``test_adrv9371_zc706_xsa_hw`` uses.
* :func:`_dmac_irq_failure_probe` — Zynq-7000-specific GIC distributor
  forensics for the documented HDL IRQ-wiring blocker
  (``axi_dmac@7c400000`` SPI 31 → GIC IRQ 63).  Wired into the SPEC
  via ``fft_failure_diagnostics`` so it only fires when capture fails.

Two distinct bring-up blockers were debugged and fixed during this
test's development against the ``release:zynq-zc706-adv7511-adrv937x``
bitstream that ``bq`` loads:

1. **ILAS framing mismatch** — the AD9371 deframer's "received-ILAS"
   registers were stale zeros because the FPGA TX framer never emitted
   a valid ILAS sequence.  Fixed in
   ``adidt/xsa/builders/adrv937x.py`` ``tx_core_second`` block.
2. **AXI DMAC IRQ number wrong in DT** — sdtgen extracted SPI 31/32
   from the XSA but the bitstream wires the DMAC IRQ to SPI 57/56.
   Fixed by setting ``dma_interrupts_str`` on the RX/TX
   ``JesdLinkModel``s; the resulting overlay emits a
   ``/delete-property/ interrupts;`` + ``interrupts = <0 57 4>`` (RX)
   / ``<0 56 4>`` (TX) override matching upstream Kuiper.

LG_ENV: ``test/hw/env/bq.yaml``.
"""

from __future__ import annotations

from typing import Any

import pytest

from test.hw.hw_helpers import check_jesd_framing_plausibility, shell_out
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


DEFAULT_KUIPER_RELEASE = "2023_R2_P1"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv937x"
DEFAULT_VCXO_HZ = 122_880_000


def _adrv9371_cfg() -> dict[str, Any]:
    """ADRV9371+ZC706 XSA pipeline cfg.

    Matches :mod:`test.hw.test_adrv9371_zc706_hw` so the XSA pipeline
    path the overlay test exercises is identical to the one the
    full-DTB system test exercises — any framing or GPIO drift between
    the two stays a single edit.

    JESD framing matches the Kuiper reference design
    ``zynq-zc706-adv7511-adrv937x``: RX = M=4 L=2 S=1 → F=4;
    TX = M=4 L=4 S=1 → F=2.  Mykonos profile properties come from
    ``adidt/xsa/profiles/adrv937x_zc706.json``.
    """
    cfg: dict[str, Any] = {
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
    framing_warnings = check_jesd_framing_plausibility(cfg["jesd"])
    assert not framing_warnings, (
        "JESD cfg is structurally inconsistent (will fail ILAS):\n  "
        + "\n  ".join(framing_warnings)
    )
    return cfg


def _dmac_irq_failure_probe(shell) -> None:
    """Print Zynq-7000 GIC + DMAC state when an RX capture fails.

    Surfaces the canonical signature that distinguishes the documented
    HDL IRQ-wiring blocker from a real DT regression.  If
    ``TRANSFER_DONE > 0`` + ``IRQ_PENDING != 0`` + ``GICD pending == 0``
    + ``/proc/interrupts count == 0``, the DMAC IRQ line is the culprit
    (HDL bitstream).  Anything else is a new bug.
    """
    print("=== DMAC HW progress (TRANSFER_DONE / IRQ_PENDING / IRQ_SOURCE) ===")
    print(
        shell_out(
            shell,
            "for off in 0x084 0x088 0x418 0x428 0x42c; do "
            "  v=$(busybox devmem $((0x7c400000 + off)) 2>&1 | head -1); "
            "  printf 'dmac+%s = %s\\n' $off \"$v\"; "
            "done",
        )
    )
    print("=== GIC distributor (IRQ 63 enable + pending) ===")
    print(
        shell_out(
            shell,
            # Zynq-7000 GICD at 0xF8F01000;
            #   ICDISER1=+0x104 (enable for IRQs 32-63)
            #   ICDISPR1=+0x204 (pending for IRQs 32-63)
            # axi_dmac@7c400000 → SPI 31 → GIC IRQ 63 → bit 31 of word 1.
            "for r in 0x104 0x204; do "
            "  v=$(busybox devmem $((0xF8F01000 + r)) 2>&1 | head -1); "
            "  printf 'GICD+%s = %s\\n' $r \"$v\"; "
            "done",
        )
    )
    print("=== /proc/interrupts (jesd + axi_dmac counts) ===")
    print(
        shell_out(
            shell,
            "grep -E 'jesd|axi_dmac' /proc/interrupts || true",
        )
    )


def _topology_assert(topology) -> None:
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"


SPEC = BoardOverlayProfile(
    overlay_name="adrv9371_zc706_xsa",
    lg_features=("adrv9371", "zc706"),
    skip_reason_label="adrv9371 zc706",
    cfg_builder=_adrv9371_cfg,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_adrv9371_zc706.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
    ),
    sdtgen_profile="adrv937x_zc706",
    topology_assert=_topology_assert,
    dtso_must_contain_any=("ad9371", "axi-jesd204"),
    boot_mode="tftp",
    kernel_fixture_name="built_kernel_image_zynq",
    settle_after_apply_s=8.0,  # Mykonos re-init is slower than AD9081.
    iio_required_all=("ad9528-1", "ad9371-phy"),
    iio_required_any=("axi-ad9371-rx-hpc", "ad_ip_jesd204_tpl_adc"),
    iio_frontend_label="AD9371 RX frontend",
    fft_mode="optional",
    capture_target_names=("axi-ad9371-rx-hpc", "ad_ip_jesd204_tpl_adc"),
    pyadi_class_name="adrv9371",
    fft_failure_diagnostics=_dmac_irq_failure_probe,
)


@pytest.fixture(scope="module")
def overlay_spec() -> BoardOverlayProfile:
    return SPEC
