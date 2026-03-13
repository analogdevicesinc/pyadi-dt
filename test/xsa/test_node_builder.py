# test/xsa/test_node_builder.py
import json
import warnings
from pathlib import Path
import pytest

from adidt.xsa.topology import (
    ClkgenInstance,
    ConverterInstance,
    Jesd204Instance,
    XsaTopology,
)
from adidt.xsa.node_builder import NodeBuilder

FIXTURE_CFG = Path(__file__).parent / "fixtures" / "ad9081_config.json"


@pytest.fixture
def topo():
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_jesd204_rx_0",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=54,
                link_clk="jesd_rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_jesd204_tx_0",
                base_addr=0x44B90000,
                num_lanes=4,
                irq=55,
                link_clk="jesd_tx_device_clk",
                direction="tx",
            )
        ],
        clkgens=[
            ClkgenInstance(
                name="axi_clkgen_0",
                base_addr=0x43C00000,
                output_clks=["jesd_rx_device_clk", "jesd_tx_device_clk"],
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9081_0",
                ip_type="axi_ad9081",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )


@pytest.fixture
def cfg():
    return json.loads(FIXTURE_CFG.read_text())


def test_build_rx_jesd_node_contains_compatible(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    assert "adi,axi-jesd204-rx-1.0" in nodes["jesd204_rx"][0]


def test_build_clkgen_nodes_generated(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    clk = nodes["clkgens"][0]
    assert "adi,axi-clkgen-2.00.a" in clk
    assert "#clock-cells = <1>" in clk


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
    assert "jesd204-device;" in rx
    assert "#jesd204-cells = <2>;" in rx
    assert "jesd204-inputs = <&" in rx


def test_build_tx_jesd_node(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    tx = nodes["jesd204_tx"][0]
    assert "adi,axi-jesd204-tx-1.0" in tx
    assert "44b90000" in tx.lower()
    assert "jesd204-device;" in tx


def test_build_uses_clkgen_for_device_clock_when_configured(topo, cfg):
    cfg["clock"]["rx_device_clk_label"] = "clkgen"
    cfg["clock"]["tx_device_clk_label"] = "clkgen"
    nodes = NodeBuilder().build(topo, cfg)
    rx = nodes["jesd204_rx"][0]
    tx = nodes["jesd204_tx"][0]
    assert "clocks = <&zynqmp_clk 71>, <&axi_clkgen_0 0>, <&axi_clkgen_0 0>;" in rx
    assert "clocks = <&zynqmp_clk 71>, <&axi_clkgen_0 0>, <&axi_clkgen_0 0>;" in tx


def test_build_warns_on_unresolvable_clock(cfg):
    topo_no_clkgen = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_jesd204_rx_0",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=None,
                link_clk="unknown_clk_net",
                direction="rx",
            )
        ],
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        NodeBuilder().build(topo_no_clkgen, cfg)
    assert any("unresolved clock" in str(warning.message) for warning in w)


def test_build_converter_renders_with_jesd_label(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    converter_node = nodes["converters"][0]
    assert "axi_jesd204_rx_0" in converter_node


def test_build_converter_fallback_template(cfg):
    topo_unknown = XsaTopology(
        converters=[
            ConverterInstance(
                name="axi_unknown_0",
                ip_type="axi_unknown_chip",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            )
        ]
    )
    nodes = NodeBuilder().build(topo_unknown, cfg)
    assert "no template for axi_unknown_chip" in nodes["converters"][0]


def test_build_adrv9009_includes_top_device_link_ids(cfg):
    topo_adrv9009 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9009_rx_jesd_rx_axi",
                base_addr=0x84AA0000,
                num_lanes=4,
                irq=106,
                link_clk="axi_rx_clkgen_clk",
                direction="rx",
            ),
            Jesd204Instance(
                name="axi_adrv9009_rx_os_jesd_rx_axi",
                base_addr=0x84AB0000,
                num_lanes=4,
                irq=104,
                link_clk="axi_rx_os_clkgen_clk",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9009_tx_jesd_tx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=105,
                link_clk="axi_tx_clkgen_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_adrv9009_0",
                ip_type="axi_adrv9009",
                base_addr=0x84A00000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )

    nodes = NodeBuilder().build(topo_adrv9009, cfg)
    merged = "\n".join(nodes["converters"])
    assert "trx0_adrv9009: adrv9009-phy@1" in merged
    assert "jesd204-top-device = <0>;" in merged
    assert "jesd204-link-ids = <1 2 0>;" in merged
    assert "&axi_adrv9009_rx_os_clkgen" in merged
    assert 'clock-names = "s_axi_aclk", "device_clk", "lane_clk";' in merged
    assert "adi,octets-per-frame = <4>;" in merged
    assert "adi,converters-per-device = <8>;" in merged
    assert 'clock-names = "conv", "div40";' in merged
    assert "&misc_clk_0" in merged
    assert "clock-frequency = <245760000>;" in merged
    assert "clk0_ad9528: ad9528-1@0" in merged
    assert "adi,vcxo-freq = <122880000>;" in merged
    assert "ad9528_0_c13: channel@13" in merged
    assert 'adi,extended-name = "DEV_CLK";' in merged
    assert (
        "clocks = <&clk0_ad9528 13>, <&clk0_ad9528 1>, <&clk0_ad9528 12>, <&clk0_ad9528 3>;"
        in merged
    )
    assert (
        'clock-names = "dev_clk", "fmc_clk", "sysref_dev_clk", "sysref_fmc_clk";'
        in merged
    )
