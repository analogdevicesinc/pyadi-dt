# test/xsa/test_node_builder.py
import json
import warnings
from pathlib import Path
import pytest

from adidt.xsa.topology import (
    ClkgenInstance, ConverterInstance, Jesd204Instance, XsaTopology,
)
from adidt.xsa.node_builder import NodeBuilder

FIXTURE_CFG = Path(__file__).parent / "fixtures" / "ad9081_config.json"


@pytest.fixture
def topo():
    return XsaTopology(
        jesd204_rx=[Jesd204Instance(
            name="axi_jesd204_rx_0", base_addr=0x44A90000, num_lanes=4,
            irq=54, link_clk="jesd_rx_device_clk", direction="rx",
        )],
        jesd204_tx=[Jesd204Instance(
            name="axi_jesd204_tx_0", base_addr=0x44B90000, num_lanes=4,
            irq=55, link_clk="jesd_tx_device_clk", direction="tx",
        )],
        clkgens=[ClkgenInstance(
            name="axi_clkgen_0", base_addr=0x43C00000,
            output_clks=["jesd_rx_device_clk", "jesd_tx_device_clk"],
        )],
        converters=[ConverterInstance(
            name="axi_ad9081_0", ip_type="axi_ad9081",
            base_addr=0x44A00000, spi_bus=None, spi_cs=None,
        )],
    )


@pytest.fixture
def cfg():
    return json.loads(FIXTURE_CFG.read_text())


def test_build_rx_jesd_node_contains_compatible(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    assert "adi,axi-jesd204-rx-1.0" in nodes["jesd204_rx"][0]


def test_build_rx_jesd_node_contains_base_addr(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    assert "44A90000".lower() in nodes["jesd204_rx"][0].lower()


def test_build_rx_jesd_node_contains_irq(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    assert "54" in nodes["jesd204_rx"][0]


def test_build_rx_jesd_node_contains_jesd_params(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    rx = nodes["jesd204_rx"][0]
    assert "adi,octets-per-frame = <4>" in rx
    assert "adi,frames-per-multiframe = <32>" in rx


def test_build_tx_jesd_node(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    tx = nodes["jesd204_tx"][0]
    assert "adi,axi-jesd204-tx-1.0" in tx
    assert "44b90000" in tx.lower()


def test_build_warns_on_unresolvable_clock(cfg):
    topo_no_clkgen = XsaTopology(
        jesd204_rx=[Jesd204Instance(
            name="axi_jesd204_rx_0", base_addr=0x44A90000, num_lanes=4,
            irq=None, link_clk="unknown_clk_net", direction="rx",
        )],
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        NodeBuilder().build(topo_no_clkgen, cfg)
    assert any("unresolved clock" in str(warning.message) for warning in w)
