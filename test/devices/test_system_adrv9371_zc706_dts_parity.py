"""Pin System-API ``ADRV9371+ZC706`` DTS against the XSA reference.

Mirrors :mod:`test_system_ad9081_dts_parity` for the ZC706 board.

The declarative path shares the complete AD9371 clock/JESD board wiring
with the XSA builder, including the observation link and TX TPL dependency.
All pinned properties are executable regression checks.

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


REFERENCE = Path(__file__).parent / "fixtures" / "adrv9371_zc706_xsa_reference.dts"


# Properties that *both* the XSA pipeline and the System-API path
# already emit identically.  Any divergence here is a regression.
COMMON_KEYS: tuple[str, ...] = (
    # AD9371 top-level SPI device.
    "ad9371:clocks",
    "ad9371:clock-names",
    "ad9371:jesd204-inputs",
    "ad9371:jesd204-link-ids",
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
