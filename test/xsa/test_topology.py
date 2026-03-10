# test/xsa/test_topology.py
from adidt.xsa.topology import (
    Jesd204Instance,
    ClkgenInstance,
    ConverterInstance,
    XsaTopology,
)


def test_jesd204_instance_creation():
    inst = Jesd204Instance(
        name="axi_jesd204_rx_0",
        base_addr=0x44A90000,
        num_lanes=4,
        irq=54,
        link_clk="device_clk_net",
        direction="rx",
    )
    assert inst.name == "axi_jesd204_rx_0"
    assert inst.direction == "rx"
    assert inst.irq == 54


def test_clkgen_instance_has_output_clks():
    inst = ClkgenInstance(
        name="axi_clkgen_0",
        base_addr=0x43C00000,
        output_clks=["clk_out1", "clk_out2"],
    )
    assert len(inst.output_clks) == 2


def test_converter_instance_optional_spi():
    inst = ConverterInstance(
        name="axi_ad9081_0",
        ip_type="axi_ad9081",
        base_addr=0x44A00000,
        spi_bus=None,
        spi_cs=None,
    )
    assert inst.spi_bus is None


def test_xsa_topology_defaults_to_empty():
    topo = XsaTopology()
    assert topo.jesd204_rx == []
    assert topo.jesd204_tx == []
    assert topo.clkgens == []
    assert topo.converters == []
    assert topo.fpga_part == ""
