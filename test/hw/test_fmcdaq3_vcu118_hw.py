"""FMCDAQ3 + VCU118 hardware test (MicroBlaze / JTAG boot).

VCU118 runs a MicroBlaze soft CPU from the FPGA fabric; there is no
PS / U-Boot / SD-card path.  Labgrid drives the boot through
:class:`BootFabric` + :class:`XilinxDeviceJTAG` on the ``nuc`` exporter
host, which loads the bitstream and a ``simpleImage.*.strip`` kernel
(kernel + embedded DTB) over JTAG.

This test is coordinator-first — the ``nuc`` place exposes the JTAG,
serial, network, and Vesync-outlet resources; the Kuiper-built
``simpleImage.vcu118_fmcdaq3.strip`` and ``system_top.bit`` live under
``/jenkins/vcu118_fmcdaq3/`` on nuc and are already wired onto the
:class:`XilinxDeviceJTAG` resource.  The smoke test below drives the
whole boot-and-verify cycle through those published resources.

LG_ENV / LG_COORDINATOR: see ``.env.example``.  Typical invocation::

    LG_COORDINATOR=10.0.0.41:20408 \\
    LG_ENV=test/hw/env/nuc.yaml \\
    pytest -p no:genalyzer test/hw/test_fmcdaq3_vcu118_hw.py -v -s
"""

from __future__ import annotations

import os

import pytest

if not (os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV")):
    pytest.skip(
        "set LG_COORDINATOR or LG_ENV for FMCDAQ3 VCU118 hardware test"
        " (see .env.example)",
        allow_module_level=True,
    )

from test.hw.hw_helpers import (  # noqa: E402
    DEFAULT_OUT_DIR,
    assert_no_kernel_faults,
    assert_no_probe_errors,
    collect_dmesg,
)


@pytest.mark.lg_feature(["fmcdaq3", "vcu118"])
def test_fmcdaq3_vcu118_boot_hw(board):
    """Boot FMCDAQ3+VCU118 with the prebuilt Kuiper image and verify IIO."""
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    board.transition("shell")
    shell = board.target.get_driver("ADIShellDriver")

    dmesg_txt = collect_dmesg(
        shell,
        out_dir,
        label="fmcdaq3_vcu118",
        grep_pattern="ad9680|ad9152|ad9528|jesd204|probe|failed|error",
    )
    assert_no_kernel_faults(dmesg_txt)
    assert_no_probe_errors(dmesg_txt)

    lowered = dmesg_txt.lower()
    assert "ad9680" in lowered, "AD9680 driver messages not seen in dmesg"
    assert "ad9152" in lowered, "AD9152 driver messages not seen in dmesg"

    _assert_iio_devices(shell)


def _assert_iio_devices(shell) -> None:
    """Fail unless the FMCDAQ3 converters show up under /sys/bus/iio."""
    out = shell.run_check(
        "for d in /sys/bus/iio/devices/iio:device*; do "
        'name=$(cat "$d/name" 2>/dev/null); '
        'printf "%s %s\\n" "$d" "$name"; '
        "done; true"
    )
    names = [line.split(" ", 1)[1] for line in out if " " in line]
    names_joined = " ".join(names)
    print(f"IIO device names: {names}")
    assert any("ad9680" in n or "axi-ad9680" in n for n in names), (
        f"AD9680 IIO device not found. Devices: {names_joined}"
    )
    assert any("ad9152" in n or "axi-ad9152" in n for n in names), (
        f"AD9152 IIO device not found. Devices: {names_joined}"
    )
    assert any("ad9528" in n for n in names), (
        f"AD9528 IIO clock device not found. Devices: {names_joined}"
    )
