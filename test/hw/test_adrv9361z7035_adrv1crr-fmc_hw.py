"""ADRV9361-Z7035 + ADRV1CRR-FMC hardware test (Zynq-7000, JTAG + TFTP boot).

The ADRV9361-Z7035 is a Zynq-7000 (XC7Z035) SOM carrying an AD9361.  Unlike
every other board in this directory it is **not** a JESD204 part -- the AD9361
uses a parallel LVDS/CMOS interface -- so this test cannot use
:class:`~test.hw.\\_system_base.BoardSystemProfile`, whose
``boot_and_verify_from_dtb`` calls ``assert_jesd_links_data`` unconditionally.
It is written directly against ``board`` + ``hw_helpers`` instead, the escape
hatch documented in ``test/hw/README.md`` and used by
``test_fmcdaq3_vcu118_hw.py``.

The ``lablp`` rig has no SD-mux *and no working SD card*, so labgrid
JTAG-bootstraps U-Boot (``ps7-init-tcl`` + ``bitstream-path`` + ``fsbl-elf`` +
``uboot-elf`` place tags) and then TFTPs ``uImage`` + ``devicetree.dtb``.
The bitstream is mandatory: the DT binds ``cf-ad9361-lpc`` /
``cf-ad9361-dds-core-lpc`` in the PL, and an unprogrammed fabric hangs the AXI
probe.

This validates the *booted stock* device tree, not a generated one --
``adidt`` has no AD9361 model, and ``kuiper_boards.json`` still marks
``zynq-adrv9361-z7035-fmc`` ``unsupported``.

Validated on hardware 2026-09-10: passes from the ``bq`` runner against the
``lablp`` rig in ~51 s.  The asserted IIO names were read off that booted
board::

    iio:device1 ad9361-phy
    iio:device4 cf-ad9361-dds-core-lpc
    iio:device5 cf-ad9361-lpc
    (also present: ad7291, xadc, ad9517-3)

.. note::

   The rig publishes its resources as ``lablp.local``, not bare ``lablp`` --
   the exporter runs with ``--hostname lablp.local`` because the bare name does
   not resolve from bq and ``SerialDriver`` would fail to open the rfc2217
   console.  lablp also needs ser2net >= 4.6.1 (it ships 4.6.0, whose RFC2217
   negotiation hangs on ``purge``); it currently runs a locally built 4.6.7.
"""

from __future__ import annotations

import os

import pytest

if not (os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV")):
    pytest.skip(
        "set LG_COORDINATOR or LG_ENV for ADRV9361-Z7035 hardware test"
        " (see .env.example)",
        allow_module_level=True,
    )

from test.hw.hw_helpers import (  # noqa: E402
    DEFAULT_OUT_DIR,
    assert_no_kernel_faults,
    assert_no_probe_errors,
    assert_rx_capture_valid,
    collect_dmesg,
    open_iio_context,
)

# Must equal the coordinator place tags (daughter-board, carrier) in order --
# render_env turns them into the labgrid ``features`` this marker selects on,
# and the CI job globs test/hw/*<board>*<carrier>*_hw.py for the filename.
LG_FEATURES = ("adrv9361z7035", "adrv1crr-fmc")

# Observed on the bench at bring-up (kernel 6.1.70, Kuiper 2023_R2_P1):
#   ad9361 spi0.0: ad9361_probe : AD936x Rev 0 successfully initialized
#   cf_axi_adc 79020000.cf-ad9361-lpc: ADI AIM ... probed ADC AD9361 as MASTER
#   cf_axi_dds 79024000.cf-ad9361-dds-core-lpc: ... probed DDS AD9361
PHY_NAME = "ad9361-phy"
RX_DEVICE_CANDIDATES = ("cf-ad9361-lpc", "cf-ad9361-A", "axi-ad9361-lpc")


@pytest.mark.lg_feature(list(LG_FEATURES))
def test_adrv9361z7035_adrv1crr_fmc_boot_hw(board):
    """Boot the SOM over JTAG+TFTP and verify the AD9361 data path."""
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    board.transition("shell")
    shell = board.target.get_driver("ADIShellDriver")

    dmesg_txt = collect_dmesg(
        shell,
        out_dir,
        label="adrv9361z7035_adrv1crr-fmc",
        grep_pattern="ad9361|cf-ad9361|cf_axi|axi_dmac|probe|failed|error",
    )
    assert_no_kernel_faults(dmesg_txt)
    assert_no_probe_errors(dmesg_txt)

    lowered = dmesg_txt.lower()
    assert "ad9361" in lowered, "AD9361 driver messages not seen in dmesg"
    assert "successfully initialized" in lowered, (
        "AD9361 did not report a successful probe; see the collected dmesg"
    )

    # The DT model string is the cheapest proof the right tree booted.
    model = shell.run_check("cat /proc/device-tree/model; echo")
    assert any("ADRV9361-Z7035" in line for line in model), (
        f"Unexpected device-tree model: {model}"
    )

    _assert_iio_devices(shell)

    # Data-path smoke test: capture a real AD9361 RX buffer. No JESD204 link to
    # assert on -- the AD9361 is parallel LVDS/CMOS -- so the capture is the
    # data-path check.
    ctx, _ = open_iio_context(shell)
    assert_rx_capture_valid(
        ctx,
        RX_DEVICE_CANDIDATES,
        n_samples=2**12,
        context="adrv9361-z7035 boot",
    )


def _assert_iio_devices(shell) -> None:
    """Fail unless the AD9361 PHY and its capture device are on /sys/bus/iio."""
    out = shell.run_check(
        "for d in /sys/bus/iio/devices/iio:device*; do "
        'name=$(cat "$d/name" 2>/dev/null); '
        'printf "%s %s\\n" "$d" "$name"; '
        "done; true"
    )
    names = [line.split(" ", 1)[1] for line in out if " " in line]
    joined = " ".join(names)
    print(f"IIO device names: {names}")
    assert any(PHY_NAME in n for n in names), (
        f"{PHY_NAME} IIO device not found. Devices: {joined}"
    )
    assert any(any(c in n for c in RX_DEVICE_CANDIDATES) for n in names), (
        f"AD9361 capture device not found. Devices: {joined}"
    )
