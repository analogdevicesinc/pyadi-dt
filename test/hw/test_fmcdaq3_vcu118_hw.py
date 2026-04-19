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
    LG_ENV=env_remote_nuc.yaml \\
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


@pytest.mark.lg_feature(["fmcdaq3", "vcu118"])
def test_fmcdaq3_vcu118_boot_hw(target):
    """Boot FMCDAQ3+VCU118 with the prebuilt Kuiper image and verify IIO."""
    shell = _boot_and_get_shell(target)
    _assert_probed_drivers(shell)
    _assert_iio_devices(shell)


def _boot_and_get_shell(target):
    """Drive ``BootFabric`` through ``powered_off`` → ``shell`` and return shell."""
    strategy = target.get_driver("Strategy")
    strategy.transition("powered_off")
    strategy.transition("shell")
    return target.get_driver("ADIShellDriver")


def _assert_probed_drivers(shell) -> None:
    """Fail unless dmesg shows AD9680 / AD9152 / AD9528 / JESD driver probes."""
    out = shell.run_check(
        "dmesg | grep -Ei 'ad9680|ad9152|ad9528|jesd204|fail|error' | tail -n 200; true"
    )
    dmesg = "\n".join(out) if isinstance(out, list) else str(out)
    print("\n=== FMCDAQ3 probe-relevant dmesg ===")
    print(dmesg)
    print("====================================")
    assert "ad9680" in dmesg.lower(), "AD9680 driver messages not seen in dmesg"
    assert "ad9152" in dmesg.lower(), "AD9152 driver messages not seen in dmesg"


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
