"""End-to-end smoke test for ADRV937x + ZC706 via the System API."""

from __future__ import annotations

import adidt


def _build_system() -> adidt.System:
    fmc = adidt.eval.adrv937x_fmc(reference_frequency=122_880_000)
    fpga = adidt.fpga.zc706()

    system = adidt.System(name="adrv937x_zc706", components=[fmc, fpga])
    system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0)
    system.connect_spi(
        bus_index=0, primary=fpga.spi[0], secondary=fmc.converter.spi, cs=1
    )

    # RX: converter -> FPGA GT
    system.add_link(
        source=fmc.converter,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.xcvr_refclk,
        sink_core_clock=fmc.dev_clk,
        sink_sysref=fmc.sysref_dev,
    )
    # TX: FPGA GT -> converter
    system.add_link(
        source=fpga.gt[1],
        sink=fmc.converter,
        source_reference_clock=fmc.xcvr_refclk,
        source_core_clock=fmc.dev_clk,
        sink_sysref=fmc.sysref_fmc,
    )
    return system


def test_generate_dts_emits_expected_nodes() -> None:
    dts = _build_system().generate_dts()
    assert "/dts-v1/;" in dts
    assert "/plugin/;" in dts
    assert "&spi0" in dts
    assert "clk0_ad9528:" in dts
    assert "trx0_ad9371:" in dts
    assert 'compatible = "adi,ad9371"' in dts


def test_board_model_has_expected_components() -> None:
    model = _build_system().to_board_model()
    parts = sorted(c.part for c in model.components)
    # Both clock and transceiver/converter should be present.
    assert "adrv9009" in parts
    assert any("9528" in p for p in parts)


def test_zc706_platform_constants() -> None:
    fpga = adidt.fpga.zc706()
    assert fpga.ADDR_CELLS == 1
    assert fpga.PS_CLK_LABEL == "clkc"
    assert len(fpga.spi) == 2
    assert len(fpga.gt) == 8


def test_connect_spi_determines_component_bus() -> None:
    system = _build_system()
    model = system.to_board_model()
    clock_comp = next((c for c in model.components if "9528" in c.part), None)
    conv_comp = next((c for c in model.components if c.part == "adrv9009"), None)
    assert clock_comp is not None
    assert conv_comp is not None
    assert clock_comp.spi_bus == "spi0"
    assert clock_comp.spi_cs == 0
    assert conv_comp.spi_bus == "spi0"
    assert conv_comp.spi_cs == 1
