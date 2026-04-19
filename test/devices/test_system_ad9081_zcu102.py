"""End-to-end smoke test for the System-driven device composition flow.

Runs the same wiring as ``examples/ad9081_fmc_zcu102.py`` and asserts the
generated DTS contains the expected structural nodes: the HMC7044 clock
overlay, the AD9081 MxFE node wrapped under the SPI bus, JESD204 RX/TX
overlays, and both ADXCVR nodes.

This test is intentionally structural (not byte-identical to the legacy
boards/ad9081_fmc.py flow, which derives JESD framing from a JIF solver
run).  Byte-identical parity is a later phase once the System integrates
with the solver.
"""

from __future__ import annotations

import adidt


def _build_system() -> adidt.System:
    fmc = adidt.eval.ad9081_fmc()
    fmc.reference_frequency = 122_880_000
    fmc.converter.set_jesd204_mode(1, "jesd204c")
    fmc.converter.adc.sample_rate = int(250e6)
    fmc.converter.dac.sample_rate = int(250e6)
    fmc.converter.adc.cddc_decimation = 4
    fmc.converter.adc.fddc_decimation = 4
    fmc.converter.dac.cduc_interpolation = 12
    fmc.converter.dac.fduc_interpolation = 4

    fpga = adidt.fpga.zcu102()

    system = adidt.System(name="ad9081_zcu102", components=[fmc, fpga])
    system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0)
    system.connect_spi(
        bus_index=1, primary=fpga.spi[1], secondary=fmc.converter.spi, cs=0
    )

    system.add_link(
        source=fmc.converter.adc,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.clock.clk_out[0],
        sink_core_clock=fmc.clock.clk_out[1],
        sink_sysref=fmc.clock.clk_out[2],
    )
    system.add_link(
        source=fpga.gt[1],
        source_reference_clock=fmc.clock.clk_out[2],
        source_core_clock=fmc.clock.clk_out[3],
        sink=fmc.converter.dac,
        sink_sysref=fmc.clock.clk_out[4],
    )
    return system


def test_generate_dts_emits_expected_nodes() -> None:
    dts = _build_system().generate_dts()
    assert "/dts-v1/;" in dts
    assert "/plugin/;" in dts
    # HMC7044 overlay in spi0
    assert "&spi0" in dts
    assert "hmc7044: hmc7044@0" in dts
    assert 'compatible = "adi,hmc7044";' in dts
    # AD9081 MxFE overlay in spi1
    assert "&spi1" in dts
    assert "trx0_ad9081:" in dts
    # JESD204 RX and TX overlays with derived labels
    assert "&axi_mxfe_rx_jesd_rx_axi" in dts
    assert "&axi_mxfe_tx_jesd_tx_axi" in dts
    # ADXCVR nodes
    assert "&axi_mxfe_rx_xcvr" in dts
    assert "&axi_mxfe_tx_xcvr" in dts
    # TPL cores referencing converter spibus
    assert "spibus-connected = <&trx0_ad9081>;" in dts


def test_board_model_structure() -> None:
    model = _build_system().to_board_model()
    roles = sorted(c.role for c in model.components)
    assert roles == ["clock", "converter"]
    parts = sorted(c.part for c in model.components)
    assert parts == ["ad9081", "hmc7044"]

    directions = sorted(link.direction for link in model.jesd_links)
    assert directions == ["rx", "tx"]

    rx = next(link for link in model.jesd_links if link.direction == "rx")
    assert rx.jesd_label == "axi_mxfe_rx_jesd_rx_axi"
    assert rx.xcvr_label == "axi_mxfe_rx_xcvr"
    assert rx.dma_label == "axi_mxfe_rx_dma"
    assert rx.core_label == "rx_mxfe_tpl_core_adc_tpl_core"

    tx = next(link for link in model.jesd_links if link.direction == "tx")
    assert tx.jesd_label == "axi_mxfe_tx_jesd_tx_axi"
    assert tx.core_label == "tx_mxfe_tpl_core_dac_tpl_core"


def test_named_clock_aliases_resolve_to_clk_out() -> None:
    fmc = adidt.eval.ad9081_fmc()
    assert fmc.dev_refclk is fmc.clock.clk_out[2]
    assert fmc.dev_sysref is fmc.clock.clk_out[3]
    assert fmc.fpga_sysref is fmc.clock.clk_out[13]
    assert fmc.core_clk_rx is fmc.clock.clk_out[0]


def test_connect_spi_determines_component_bus() -> None:
    system = _build_system()
    model = system.to_board_model()
    clock_comp = next(c for c in model.components if c.role == "clock")
    conv_comp = next(c for c in model.components if c.role == "converter")
    assert clock_comp.spi_bus == "spi0"
    assert clock_comp.spi_cs == 0
    assert conv_comp.spi_bus == "spi1"
    assert conv_comp.spi_cs == 0
