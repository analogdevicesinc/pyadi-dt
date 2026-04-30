from __future__ import annotations

from adidt.xsa.build.node_builder import NodeBuilder
from adidt.xsa.parse.topology import ConverterInstance, Jesd204Instance, XsaTopology


def test_node_builder_generates_fmcdaq3_specific_nodes():
    topology = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9680_jesd_rx_axi",
                base_addr=0x84AA0000,
                num_lanes=4,
                irq=107,
                link_clk="util_daq3_xcvr_rx_out_clk_0",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9152_jesd_tx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=106,
                link_clk="util_daq3_xcvr_tx_out_clk_0",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9680_tpl_core_adc_tpl_core",
                ip_type="axi_ad9680",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_ad9152_tpl_core_dac_tpl_core",
                ip_type="axi_ad9152",
                base_addr=0x84A04000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
        fpga_part="xczu9eg",
    )

    cfg = {
        "fmcdaq3_board": {
            "spi_bus": "spi0",
            "clock_cs": 0,
            "adc_cs": 2,
            "dac_cs": 1,
            "adc_core_label": "axi_ad9680_tpl_core_adc_tpl_core",
            "dac_core_label": "axi_ad9152_tpl_core_dac_tpl_core",
            "adc_xcvr_label": "axi_ad9680_xcvr",
            "dac_xcvr_label": "axi_ad9152_xcvr",
            "adc_jesd_label": "axi_ad9680_jesd_rx_axi",
            "dac_jesd_label": "axi_ad9152_jesd_tx_axi",
            "adc_dma_label": "axi_ad9680_dma",
            "dac_dma_label": "axi_ad9152_dma",
            "gpio_controller": "gpio",
        },
        "jesd": {
            "rx": {"L": 4, "M": 2, "F": 1, "K": 32, "Np": 16, "S": 1},
            "tx": {"L": 4, "M": 2, "F": 1, "K": 32, "Np": 16, "S": 1},
        },
    }

    result = NodeBuilder().build(topology, cfg)
    text = "\n".join(result["converters"])

    assert "spibus-connected = <&adc0_ad9680>;" in text
    assert 'compatible = "adi,axi-adxcvr-1.0";' in text
    assert "&axi_ad9680_xcvr" in text
    assert "&axi_ad9152_xcvr" in text
