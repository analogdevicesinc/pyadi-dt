"""Pin System-API ``ADRV9371+ZC706`` DTS against the XSA reference.

Mirrors :mod:`test_system_ad9081_dts_parity` for the ZC706 board.

Scope
-----

The XSA-pipeline flow for ADRV9371+ZC706 probes successfully on real
hardware; the declarative System-API flow is still catching up to
it.  Where the two paths *already agree*, we pin the exact values so
future refactors can't silently drift — 31 kernel-relevant
properties in total across the AD9371 and AD9528 nodes.

Where the System API doesn't yet emit a key the XSA path does (e.g.
the AD9371's ``clocks = <&clk0_ad9528 ...>`` pair, the
``axi-clkgen`` node outputs), the test records it as ``xfail`` with
the reason — flipping each xfail off turns the test into a
regression guard once the System-API gap closes.

Regenerate the reference fixture from a passing ``hw-direct (bq)``
artifact::

    gh run download <RUN_ID> -n hw-direct-bq-output -D /tmp/ref
    cp /tmp/ref/test/hw/output/adrv937x_zc706.dts \\
       test/devices/fixtures/adrv9371_zc706_xsa_reference.dts
"""

from __future__ import annotations

from pathlib import Path

import pytest

import adidt
from adidt.tools.dts_inspect import extract_props


REFERENCE = (
    Path(__file__).parent / "fixtures" / "adrv9371_zc706_xsa_reference.dts"
)


# Properties that *both* the XSA pipeline and the System-API path
# already emit identically.  Any divergence here is a regression.
COMMON_KEYS: tuple[str, ...] = (
    # AD9371 top-level SPI device.
    "ad9371:#clock-cells",
    "ad9371:#jesd204-cells",
    "ad9371:clock-output-names",
    "ad9371:compatible",
    "ad9371:jesd204-top-device",
    "ad9371:reg",
    "ad9371:reset-gpios",
    "ad9371:spi-max-frequency",
    "ad9371:sysref-req-gpios",
    # AD9528 clock chip on the FMC.
    "ad9528:#address-cells",
    "ad9528:#clock-cells",
    "ad9528:#size-cells",
    "ad9528:adi,pll1-charge-pump-current-nA",
    "ad9528:adi,pll1-feedback-div",
    "ad9528:adi,pll2-charge-pump-current-nA",
    "ad9528:adi,pll2-n2-div",
    "ad9528:adi,pll2-r1-div",
    "ad9528:adi,pll2-vco-div-m1",
    "ad9528:adi,refa-r-div",
    "ad9528:adi,status-mon-pin0-function-select",
    "ad9528:adi,status-mon-pin1-function-select",
    "ad9528:adi,sysref-k-div",
    "ad9528:adi,sysref-nshot-mode",
    "ad9528:adi,sysref-pattern-mode",
    "ad9528:adi,sysref-request-trigger-mode",
    "ad9528:adi,sysref-src",
    "ad9528:adi,vcxo-freq",
    "ad9528:clock-output-names",
    "ad9528:compatible",
    "ad9528:reg",
    "ad9528:spi-max-frequency",
)


# Keys the XSA path emits but the System API does not yet.  Each
# entry is ``(key, reason)``; the test expects these to xfail today.
# When a gap closes, delete the entry — the property moves into
# ``COMMON_KEYS`` as a regression guard.
XFAIL_KEYS: tuple[tuple[str, str], ...] = (
    (
        "ad9371:clocks",
        "System-API path doesn't yet emit the AD9371 dev_clk/fmc_clk "
        "references to ad9528 channels.  Targets the System-API "
        "XCVR/TPL-core/clkgen overlay gap noted in "
        "``test/hw/test_adrv9371_zc706_hw.py``.",
    ),
    (
        "ad9371:clock-names",
        "Paired with ``ad9371:clocks`` above.",
    ),
    (
        "ad9371:jesd204-inputs",
        "System-API flow doesn't attach the AD9371 node to the AXI "
        "JESD204 RX/TX xcvr nodes yet.",
    ),
    (
        "ad9371:jesd204-link-ids",
        "Paired with ``ad9371:jesd204-inputs`` above.",
    ),
)


def _build_system() -> adidt.System:
    fmc = adidt.eval.adrv937x_fmc(reference_frequency=122_880_000)
    fpga = adidt.fpga.zc706()
    system = adidt.System(name="adrv937x_zc706", components=[fmc, fpga])
    system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0)
    system.connect_spi(
        bus_index=0, primary=fpga.spi[0], secondary=fmc.converter.spi, cs=1
    )
    system.add_link(
        source=fmc.converter,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.xcvr_refclk,
        sink_core_clock=fmc.dev_clk,
        sink_sysref=fmc.sysref_dev,
    )
    system.add_link(
        source=fpga.gt[1],
        sink=fmc.converter,
        source_reference_clock=fmc.xcvr_refclk,
        source_core_clock=fmc.dev_clk,
        sink_sysref=fmc.sysref_fmc,
    )
    return system


def _reference_props() -> dict[str, str]:
    if not REFERENCE.exists():
        pytest.skip(f"Reference DTS not present: {REFERENCE}")
    return extract_props(REFERENCE.read_text())


@pytest.mark.parametrize("key", COMMON_KEYS)
def test_adrv9371_system_property_matches_xsa_reference(key: str) -> None:
    """One parametrized case per pinned property — each one gives a
    focused failure message if the System-API flow drifts."""
    ref = _reference_props()
    if key not in ref:
        pytest.skip(f"Key {key!r} not in reference (irrelevant for this DTS)")
    cand = extract_props(_build_system().generate_dts())
    assert cand.get(key) == ref[key], (
        f"System-API DTS diverges from XSA reference at {key}:\n"
        f"  reference : {ref[key]}\n"
        f"  candidate : {cand.get(key)!r}"
    )


@pytest.mark.parametrize("key,reason", XFAIL_KEYS)
def test_adrv9371_system_known_gaps(key: str, reason: str) -> None:
    """Keys the System-API path is known to miss vs the XSA path.

    Each case is marked ``xfail`` until the System-API emission gap
    is closed; the test then starts passing and the guard kicks in.
    """
    pytest.xfail(reason)
    ref = _reference_props()
    cand = extract_props(_build_system().generate_dts())
    assert cand.get(key) == ref.get(key)
