from __future__ import annotations

from adidt.xsa.build.node_builder import NodeBuilder
from adidt.xsa.parse.topology import Jesd204Instance, XsaTopology


def test_node_builder_generates_ad9172_specific_nodes():
    topology = XsaTopology(
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9172_jesd_tx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=106,
                link_clk="util_ad9172_xcvr_tx_out_clk",
                direction="tx",
            )
        ],
        fpga_part="xczu9eg",
    )
    cfg = {
        "ad9172_board": {
            "spi_bus": "spi0",
            "dac_core_label": "axi_ad9172_core",
            "dac_xcvr_label": "axi_ad9172_adxcvr",
            "dac_jesd_label": "axi_ad9172_jesd_tx_axi",
        }
    }

    result = NodeBuilder().build(topology, cfg)
    text = "\n".join(result["converters"])

    assert "hmc7044: hmc7044@0" in text
    assert "adi,gpi-controls = <0x00 0x00 0x00 0x00>;" in text
    assert "adi,gpo-controls = <0x1f 0x2b 0x00 0x00>;" in text
    assert "dac0_ad9172: ad9172@1" in text
    assert 'compatible = "adi,axi-ad9172-1.0";' in text
    assert "spibus-connected = <&dac0_ad9172>;" in text
    assert "&axi_ad9172_adxcvr" in text


def test_node_builder_infers_ad9172_labels_from_jesd_tx_instance():
    topology = XsaTopology(
        jesd204_tx=[
            Jesd204Instance(
                name="dac_jesd204_link_tx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=106,
                link_clk="util_dac_jesd204_xcvr_tx_out_clk_0",
                direction="tx",
            )
        ],
        fpga_part="xczu9eg",
    )
    cfg = {"ad9172_board": {"spi_bus": "spi0"}}

    result = NodeBuilder().build(topology, cfg)
    text = "\n".join(result["converters"])

    assert "&dac_jesd204_transport_dac_tpl_core" in text
    assert "&dac_jesd204_xcvr" in text
    assert "&dac_jesd204_link_tx_axi" in text
