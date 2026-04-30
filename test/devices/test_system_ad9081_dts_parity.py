"""Pin System-API ``AD9081+ZCU102`` DTS against the XSA reference.

The XSA-pipeline flow (``adidt.xsa.build.builders.ad9081``) is the known-good
emission path — its DTS boots successfully on hardware.  The
System-API (declarative) flow should, for the same inputs, emit DTS
whose *kernel-critical* properties match.  When they diverge the
kernel AD9081 driver fails with probe errors that are slow to
diagnose on real hardware (``ENOENT`` from missing dev_clk,
``jesd_l == 0`` from wrong framing, ``JESD PLL is not locked`` from
wrong M, "Link is disabled" from wrong HMC7044 dividers, …).

This test parses a committed, recently-passed XSA DTS and asserts the
System-API output matches on every property in
``KERNEL_CRITICAL_KEYS``.  It runs in <1s — orders of magnitude
faster than the hw-coord CI feedback loop.  Regenerate the fixture
by pulling the ``hw-coord-mini2-output`` artifact from a passing
``Hardware Tests`` workflow run:

    gh run download <RUN_ID> -n hw-coord-mini2-output -D /tmp/ref
    cp /tmp/ref/ad9081_zcu102.dts test/devices/fixtures/
"""

from __future__ import annotations

from pathlib import Path

import pytest

import adidt
from adidt.tools.dts_inspect import (
    KERNEL_CRITICAL_KEYS,
    compare_properties,
    extract_props,
)


REFERENCE = (
    Path(__file__).parent / "fixtures" / "ad9081_zcu102_xsa_reference.dts"
)


def _build_system() -> adidt.System:
    """Mirror ``test_ad9081_zcu102_system_hw._configure_converter`` +
    ``_build_system`` for the same XSA reference case (M=8, L=4,
    mode=10/9, cduc=8, fduc=6)."""
    fmc = adidt.eval.ad9081_fmc()
    fmc.converter.adc.set_jesd204_mode(10, "jesd204b")
    fmc.converter.dac.set_jesd204_mode(9, "jesd204b")
    fmc.converter.adc.sample_rate = 250_000_000
    fmc.converter.dac.sample_rate = 250_000_000
    fmc.converter.adc.cddc_decimation = 4
    fmc.converter.adc.fddc_decimation = 4
    fmc.converter.dac.cduc_interpolation = 8
    fmc.converter.dac.fduc_interpolation = 6

    fpga = adidt.fpga.zcu102()
    system = adidt.System(name="ad9081_zcu102_parity", components=[fmc, fpga])
    system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0)
    system.connect_spi(
        bus_index=1, primary=fpga.spi[1], secondary=fmc.converter.spi, cs=0
    )
    system.add_link(
        source=fmc.converter.adc,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.dev_refclk,
        sink_core_clock=fmc.core_clk_rx,
        sink_sysref=fmc.dev_sysref,
    )
    system.add_link(
        source=fpga.gt[1],
        sink=fmc.converter.dac,
        source_reference_clock=fmc.fpga_refclk_tx,
        source_core_clock=fmc.core_clk_tx,
        sink_sysref=fmc.fpga_sysref,
    )
    return system


def _reference_props() -> dict[str, str]:
    if not REFERENCE.exists():
        pytest.skip(f"Reference DTS not present: {REFERENCE}")
    return extract_props(REFERENCE.read_text())


@pytest.mark.parametrize("key", KERNEL_CRITICAL_KEYS)
def test_system_ad9081_property_matches_xsa_reference(key: str) -> None:
    """One parametrized case per kernel-critical property — each one
    gives a focused failure message if the System-API flow drifts."""
    ref = _reference_props()
    if key not in ref:
        pytest.skip(f"Key {key!r} not in reference (irrelevant for this DTS)")
    system_dts = _build_system().generate_dts()
    cand = extract_props(system_dts)
    assert cand.get(key) == ref[key], (
        f"System-API DTS diverges from XSA reference at {key}:\n"
        f"  reference : {ref[key]}\n"
        f"  candidate : {cand.get(key)!r}"
    )


def test_system_ad9081_full_kernel_critical_parity() -> None:
    """Roll-up aggregate so a single failure report lists everything that
    drifted — handy when a DT-emission regression hits multiple
    properties at once."""
    ref = _reference_props()
    cand = extract_props(_build_system().generate_dts())
    diffs = compare_properties(ref, cand)
    assert not diffs, "System-API DTS drifts from XSA reference:\n  " + "\n  ".join(diffs)
