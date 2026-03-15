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


def test_build_falls_back_to_zynqmp_clk_when_unresolvable_and_clkgen_requested(cfg):
    topo_no_clkgen = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=None,
                link_clk="External_Ports_rx_device_clk",
                direction="rx",
            )
        ]
    )
    cfg["clock"]["rx_device_clk_label"] = "clkgen"
    nodes = NodeBuilder().build(topo_no_clkgen, cfg)
    rx = nodes["jesd204_rx"][0]
    assert "clocks = <&zynqmp_clk 71>, <&zynqmp_clk 71>, <&axi_mxfe_rx_xcvr 0>;" in rx


def test_build_converter_renders_with_jesd_label(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    converter_node = nodes["converters"][0]
    assert "axi_jesd204_rx_0" in converter_node
    assert "JESD204_" not in converter_node
    assert "jesd204-link-ids = <1 0>;" in converter_node
    assert "jesd204-inputs = <&axi_jesd204_rx_0 0 1>;" in converter_node


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


def test_build_adrv9026_label_variant_reuses_adrv9009_generation_path(cfg):
    topo_adrv9026 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9026_rx_jesd_rx_axi",
                base_addr=0x84AA0000,
                num_lanes=4,
                irq=106,
                link_clk="axi_rx_clkgen_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9026_tx_jesd_tx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=105,
                link_clk="axi_tx_clkgen_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_adrv9026_0",
                ip_type="axi_adrv9026",
                base_addr=0x84A00000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )

    nodes = NodeBuilder().build(topo_adrv9026, cfg)
    merged = "\n".join(nodes["converters"])

    assert "&axi_adrv9026_rx_jesd_rx_axi {" in merged
    assert "&axi_adrv9026_tx_jesd_tx_axi {" in merged
    assert "jesd204-link-ids = <1 0>;" in merged
    assert "trx0_adrv9025: adrv9025-phy@1" in merged
    assert 'compatible = "adi,adrv9025", "adrv9025";' in merged


def test_build_ad9081_mxfe_generates_spi_clock_and_core_nodes(cfg):
    topo_ad9081 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=107,
                link_clk="External_Ports_rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=4,
                irq=106,
                link_clk="External_Ports_tx_device_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9081_0",
                ip_type="axi_ad9081",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )
    cfg["clock"]["rx_device_clk_label"] = "hmc7044"
    cfg["clock"]["tx_device_clk_label"] = "hmc7044"
    cfg["clock"]["hmc7044_rx_channel"] = 10
    cfg["clock"]["hmc7044_tx_channel"] = 6

    nodes = NodeBuilder().build(topo_ad9081, cfg)
    merged = "\n".join(nodes["converters"])
    jesd = "\n".join(nodes["jesd204_rx"] + nodes["jesd204_tx"])

    assert "&spi1 {" in merged
    assert "&spi0 {" in merged
    assert "hmc7044: hmc7044@0" in merged
    assert "trx0_ad9081: ad9081@0" in merged
    assert 'compatible = "adi,axi-ad9081-rx-1.0";' in merged
    assert 'compatible = "adi,axi-ad9081-tx-1.0";' in merged
    assert "adi,sys-clk-select = <3>;" in merged
    assert "adi,out-clk-select = <4>;" in merged
    assert "spibus-connected = <&trx0_ad9081>;" in merged
    assert "jesd204-link-ids = <2 0>;" in merged
    assert (
        "jesd204-inputs = <&rx_mxfe_tpl_core_adc_tpl_core 0 2>, <&tx_mxfe_tpl_core_dac_tpl_core 0 0>;"
        in merged
    )
    assert jesd == ""
    assert "clocks = <&zynqmp_clk 71>, <&hmc7044 10>, <&axi_mxfe_rx_xcvr 0>;" in merged
    assert "clocks = <&zynqmp_clk 71>, <&hmc7044 6>, <&axi_mxfe_tx_xcvr 0>;" in merged
    assert "&axi_mxfe_rx_jesd_rx_axi {" in merged
    assert "&axi_mxfe_tx_jesd_tx_axi {" in merged
    assert 'compatible = "adi,axi-jesd204-rx-1.0";' in merged
    assert 'compatible = "adi,axi-jesd204-tx-1.0";' in merged
    assert "jesd204-device;" in merged
    assert "#jesd204-cells = <2>;" in merged
    assert "jesd204-inputs = <&axi_mxfe_rx_xcvr 0 2>;" in merged
    assert "jesd204-inputs = <&axi_mxfe_tx_xcvr 0 0>;" in merged
    assert "/delete-property/ jesd204-device;" not in merged
    assert "/delete-property/ #jesd204-cells;" not in merged
    assert "/delete-property/ jesd204-inputs;" not in merged


def test_build_ad9081_mxfe_uses_cfg_rx_m_for_converter_select(cfg):
    topo_ad9081 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=8,
                irq=107,
                link_clk="External_Ports_rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=8,
                irq=106,
                link_clk="External_Ports_tx_device_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9081_0",
                ip_type="axi_ad9081",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )
    cfg["jesd"]["rx"]["M"] = 4
    cfg["jesd"]["rx"]["L"] = 8
    cfg["jesd"]["tx"]["M"] = 4
    cfg["jesd"]["tx"]["L"] = 8
    cfg["ad9081"] = {
        "adc_frequency_hz": 3000000000,
        "dac_frequency_hz": 12000000000,
        "rx_cddc_decimation": 2,
        "rx_fddc_decimation": 1,
        "tx_cduc_interpolation": 8,
        "tx_fduc_interpolation": 1,
        "rx_link_mode": 18,
        "tx_link_mode": 17,
    }

    nodes = NodeBuilder().build(topo_ad9081, cfg)
    merged = "\n".join(nodes["converters"])

    assert (
        "adi,converter-select = <&ad9081_rx_fddc_chan0 0>, <&ad9081_rx_fddc_chan0 1>, "
        "<&ad9081_rx_fddc_chan1 0>, <&ad9081_rx_fddc_chan1 1>;"
    ) in merged
    assert (
        "adi,converter-select = <&ad9081_tx_fddc_chan0 0>, <&ad9081_tx_fddc_chan0 1>, "
        "<&ad9081_tx_fddc_chan1 0>, <&ad9081_tx_fddc_chan1 1>;"
    ) in merged
    assert "adi,logical-lane-mapping = /bits/ 8 <2 0 7 6 5 4 3 1>;" in merged
    assert "adi,logical-lane-mapping = /bits/ 8 <0 2 7 6 1 5 4 3>;" in merged
    assert "adi,adc-frequency-hz = /bits/ 64 <3000000000>;" in merged
    assert "adi,dac-frequency-hz = /bits/ 64 <12000000000>;" in merged
    assert "adi,link-mode = <18>;" in merged
    assert "adi,link-mode = <17>;" in merged
    assert "adi,decimation = <2>;" in merged
    assert "adi,interpolation = <1>;" in merged


def test_build_ad9081_mxfe_uses_ad9081_default_link_ids(cfg):
    topo_ad9081 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=8,
                irq=107,
                link_clk="External_Ports_rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=8,
                irq=106,
                link_clk="External_Ports_tx_device_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9081_0",
                ip_type="axi_ad9081",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )

    nodes = NodeBuilder().build(topo_ad9081, cfg)
    merged = "\n".join(nodes["converters"])

    assert "jesd204-link-ids = <2 0>;" in merged
    assert (
        "jesd204-inputs = <&rx_mxfe_tpl_core_adc_tpl_core 0 2>, "
        "<&tx_mxfe_tpl_core_dac_tpl_core 0 0>;"
    ) in merged
    assert "jesd204-inputs = <&hmc7044 0 2>;" in merged
    assert "jesd204-inputs = <&axi_mxfe_rx_jesd_rx_axi 0 2>;" in merged
    assert "jesd204-inputs = <&axi_mxfe_rx_xcvr 0 2>;" in merged


def test_build_ad9081_mxfe_applies_board_overrides(cfg):
    topo_ad9081 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=8,
                irq=107,
                link_clk="External_Ports_rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=8,
                irq=106,
                link_clk="External_Ports_tx_device_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9081_0",
                ip_type="axi_ad9081",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )
    cfg["ad9081_board"] = {
        "clock_spi": "spi2",
        "clock_cs": 1,
        "adc_spi": "spi3",
        "adc_cs": 2,
        "reset_gpio": 99,
        "sysref_req_gpio": 98,
        "rx2_enable_gpio": 97,
        "rx1_enable_gpio": 96,
        "tx2_enable_gpio": 95,
        "tx1_enable_gpio": 94,
    }

    nodes = NodeBuilder().build(topo_ad9081, cfg)
    merged = "\n".join(nodes["converters"])

    assert "&spi2 {" in merged
    assert "hmc7044: hmc7044@1" in merged
    assert "&spi3 {" in merged
    assert "trx0_ad9081: ad9081@2" in merged
    assert "reset-gpios = <&gpio 99 0>;" in merged
    assert "sysref-req-gpios = <&gpio 98 0>;" in merged
    assert "rx2-enable-gpios = <&gpio 97 0>;" in merged
    assert "rx1-enable-gpios = <&gpio 96 0>;" in merged
    assert "tx2-enable-gpios = <&gpio 95 0>;" in merged
    assert "tx1-enable-gpios = <&gpio 94 0>;" in merged


def test_build_fmcdaq2_zc706_nodes(cfg):
    topo_fmcdaq2 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9680_jesd204_rx",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=61,
                link_clk="rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9144_jesd204_tx",
                base_addr=0x44B90000,
                num_lanes=4,
                irq=62,
                link_clk="tx_device_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9680_0",
                ip_type="axi_ad9680",
                base_addr=0x44A10000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_ad9144_0",
                ip_type="axi_ad9144",
                base_addr=0x44A20000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
    )
    cfg["fmcdaq2_board"] = {
        "spi_bus": "spi0",
        "clock_cs": 0,
        "adc_cs": 2,
        "dac_cs": 1,
        "clock_vcxo_hz": 125000000,
        "adc_core_label": "axi_ad9680_core",
        "dac_core_label": "axi_ad9144_core",
        "adc_jesd_link_id": 1,
        "dac_jesd_link_id": 0,
    }
    cfg["clock"]["rx_device_clk_label"] = "clk0_ad9523"
    cfg["clock"]["tx_device_clk_label"] = "clk0_ad9523"
    cfg["clock"]["rx_device_clk_index"] = 13
    cfg["clock"]["tx_device_clk_index"] = 1

    nodes = NodeBuilder().build(topo_fmcdaq2, cfg)
    merged = "\n".join(nodes["converters"])
    jesd = "\n".join(nodes["jesd204_rx"] + nodes["jesd204_tx"])

    assert "&spi0 {" in merged
    assert "clk0_ad9523: ad9523-1@0" in merged
    assert "adc0_ad9680: ad9680@2" in merged
    assert "dac0_ad9144: ad9144@1" in merged
    assert "jesd204-link-ids = <0>;" in merged
    assert "&axi_ad9680_core {" in merged
    assert "&axi_ad9144_core {" in merged
    assert "&axi_ad9680_jesd204_rx {" in merged
    assert "&axi_ad9144_jesd204_tx {" in merged
    assert jesd == ""


def test_build_fmcdaq2_zcu102_nodes(cfg):
    topo_fmcdaq2 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9680_jesd204_rx",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=61,
                link_clk="rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9144_jesd204_tx",
                base_addr=0x84B90000,
                num_lanes=4,
                irq=62,
                link_clk="tx_device_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9680_0",
                ip_type="axi_ad9680",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_ad9144_0",
                ip_type="axi_ad9144",
                base_addr=0x84A20000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
    )
    cfg["fmcdaq2_board"] = {
        "spi_bus": "fmc_spi",
        "clock_cs": 0,
        "adc_cs": 2,
        "dac_cs": 1,
        "clock_vcxo_hz": 125000000,
        "gpio_controller": "gpio",
        "clk_sync_gpio": 116,
        "clk_status0_gpio": 110,
        "clk_status1_gpio": 111,
        "dac_txen_gpio": 119,
        "dac_reset_gpio": 118,
        "dac_irq_gpio": 112,
        "adc_powerdown_gpio": 120,
        "adc_fastdetect_a_gpio": 113,
        "adc_fastdetect_b_gpio": 114,
        "adc_core_label": "axi_ad9680_core",
        "dac_core_label": "axi_ad9144_core",
        "adc_jesd_link_id": 1,
        "dac_jesd_link_id": 0,
    }
    cfg["clock"]["rx_device_clk_label"] = "clk0_ad9523"
    cfg["clock"]["tx_device_clk_label"] = "clk0_ad9523"
    cfg["clock"]["rx_device_clk_index"] = 13
    cfg["clock"]["tx_device_clk_index"] = 1

    nodes = NodeBuilder().build(topo_fmcdaq2, cfg)
    merged = "\n".join(nodes["converters"])

    assert "&fmc_spi {" in merged
    assert "sync-gpios = <&gpio 116 0>;" in merged
    assert "status0-gpios = <&gpio 110 0>;" in merged
    assert "status1-gpios = <&gpio 111 0>;" in merged
    assert "txen-gpios = <&gpio 119 0>;" in merged
    assert "reset-gpios = <&gpio 118 0>;" in merged
    assert "irq-gpios = <&gpio 112 0>;" in merged
    assert "powerdown-gpios = <&gpio 120 0>;" in merged
    assert "fastdetect-a-gpios = <&gpio 113 0>;" in merged
    assert "fastdetect-b-gpios = <&gpio 114 0>;" in merged
    assert "adi,pll1-bypass-enable;" in merged
    assert "adi,pll2-m1-freq = <1000000000>;" in merged
    assert "ad9523_0_c13:channel@13" in merged
    assert "jesd204-device;" in merged
    assert "&axi_ad9680_jesd204_rx {" in merged
    assert "&axi_ad9144_jesd204_tx {" in merged
    assert "adi,sampling-frequency = /bits/ 64 <1000000000>;" in merged
    assert "adi,input-clock-divider-ratio = <1>;" in merged


def test_build_fmcdaq2_rejects_invalid_gpio_value(cfg):
    topo_fmcdaq2 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9680_jesd204_rx",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=61,
                link_clk="rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9144_jesd204_tx",
                base_addr=0x84B90000,
                num_lanes=4,
                irq=62,
                link_clk="tx_device_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9680_0",
                ip_type="axi_ad9680",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_ad9144_0",
                ip_type="axi_ad9144",
                base_addr=0x84A20000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
    )
    cfg["fmcdaq2_board"] = {
        "spi_bus": "fmc_spi",
        "clk_sync_gpio": "bad-pin",
    }

    with pytest.raises(ValueError, match="fmcdaq2_board.clk_sync_gpio"):
        NodeBuilder().build(topo_fmcdaq2, cfg)


def test_build_fmcdaq2_rejects_invalid_chip_select(cfg):
    topo_fmcdaq2 = XsaTopology(
        converters=[
            ConverterInstance(
                name="axi_ad9680_0",
                ip_type="axi_ad9680",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_ad9144_0",
                ip_type="axi_ad9144",
                base_addr=0x84A20000,
                spi_bus=None,
                spi_cs=None,
            ),
        ]
    )
    cfg["fmcdaq2_board"] = {
        "spi_bus": "fmc_spi",
        "adc_cs": "bad-cs",
    }

    with pytest.raises(ValueError, match="fmcdaq2_board.adc_cs"):
        NodeBuilder().build(topo_fmcdaq2, cfg)


def test_build_fmcdaq2_rejects_bool_for_numeric_field(cfg):
    topo_fmcdaq2 = XsaTopology(
        converters=[
            ConverterInstance(
                name="axi_ad9680_0",
                ip_type="axi_ad9680",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_ad9144_0",
                ip_type="axi_ad9144",
                base_addr=0x84A20000,
                spi_bus=None,
                spi_cs=None,
            ),
        ]
    )
    cfg["fmcdaq2_board"] = {
        "spi_bus": "fmc_spi",
        "clock_cs": True,
    }

    with pytest.raises(ValueError, match="fmcdaq2_board.clock_cs"):
        NodeBuilder().build(topo_fmcdaq2, cfg)


def test_build_ad9081_allows_hmc7044_channel_block_override(cfg):
    topo_ad9081 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=8,
                irq=107,
                link_clk="External_Ports_rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=8,
                irq=106,
                link_clk="External_Ports_tx_device_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9081_0",
                ip_type="axi_ad9081",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )
    cfg["ad9081_board"] = {
        "hmc7044_channel_blocks": [
            "hmc7044_c5: channel@5 {\n"
            "reg = <5>;\n"
            'adi,extended-name = "CUSTOM";\n'
            "adi,divider = <8>;\n"
            "adi,driver-mode = <1>;\n"
            "};\n"
        ]
    }

    nodes = NodeBuilder().build(topo_ad9081, cfg)
    merged = "\n".join(nodes["converters"])

    assert "hmc7044_c5: channel@5 {" in merged
    assert 'adi,extended-name = "CUSTOM";' in merged
    assert "hmc7044_c13: channel@13" not in merged


def test_build_ad9081_mxfe_inferrs_link_modes_from_jesd_params(cfg):
    topo_ad9081 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=107,
                link_clk="External_Ports_rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=4,
                irq=106,
                link_clk="External_Ports_tx_device_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9081_0",
                ip_type="axi_ad9081",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )

    cfg.pop("ad9081", None)

    nodes = NodeBuilder().build(topo_ad9081, cfg)
    merged = "\n".join(nodes["converters"])

    assert "adi,link-mode = <17>;" in merged
    assert "adi,link-mode = <18>;" in merged
    assert "adi,link-mode = <4>;" not in merged
    assert "adi,link-mode = <9>;" not in merged


def test_build_adrv9009_applies_board_overrides(cfg):
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
    cfg["adrv9009_board"] = {
        "misc_clk_hz": 260000000,
        "spi_bus": "spi5",
        "clk_cs": 3,
        "trx_cs": 4,
        "trx_reset_gpio": 210,
        "trx_sysref_req_gpio": 211,
        "trx_spi_max_frequency": 20000000,
        "ad9528_vcxo_freq": 100000000,
        "rx_link_id": 9,
        "rx_os_link_id": 8,
        "tx_link_id": 7,
        "tx_octets_per_frame": 5,
        "rx_os_octets_per_frame": 6,
    }

    nodes = NodeBuilder().build(topo_adrv9009, cfg)
    merged = "\n".join(nodes["converters"])

    assert "&spi5 {" in merged
    assert "clk0_ad9528: ad9528-1@3" in merged
    assert "reg = <3>;" in merged
    assert "trx0_adrv9009: adrv9009-phy@4" in merged
    assert "reg = <4>;" in merged
    assert "clock-frequency = <260000000>;" in merged
    assert "spi-max-frequency = <20000000>;" in merged
    assert "reset-gpios = <&gpio 210 0>;" in merged
    assert "sysref-req-gpios = <&gpio 211 0>;" in merged
    assert "adi,vcxo-freq = <100000000>;" in merged
    assert "jesd204-link-ids = <9 8 7>;" in merged
    assert (
        "jesd204-inputs = <&axi_adrv9009_rx_xcvr 0 9>, <&axi_adrv9009_rx_os_xcvr 0 8>, <&axi_adrv9009_tx_xcvr 0 7>;"
        in merged
    )
    assert "adi,octets-per-frame = <5>;" in merged
    assert "&axi_adrv9009_rx_os_jesd_rx_axi {" in merged
    assert "adi,octets-per-frame = <6>;" in merged


def test_build_adrv9009_uses_zynq_ps_labels_on_zc706(cfg):
    topo_adrv9009 = XsaTopology(
        fpga_part="xc7z045ffg900-2",
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9009_rx_jesd_rx_axi",
                base_addr=0x44AA0000,
                num_lanes=4,
                irq=106,
                link_clk="axi_rx_clkgen_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9009_tx_jesd_tx_axi",
                base_addr=0x44A90000,
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
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )
    nodes = NodeBuilder().build(topo_adrv9009, cfg)
    merged = "\n".join(nodes["converters"])

    assert (
        "clocks = <&clkc 15>, <&axi_adrv9009_rx_clkgen>, <&axi_adrv9009_rx_xcvr 0>;"
        in merged
    )
    assert (
        "clocks = <&clkc 15>, <&axi_adrv9009_tx_clkgen>, <&axi_adrv9009_tx_xcvr 0>;"
        in merged
    )
    assert "reset-gpios = <&gpio0 130 0>;" in merged
    assert "sysref-req-gpios = <&gpio0 136 0>;" in merged


def test_build_adrv9009_allows_trx_profile_props_override(cfg):
    topo_adrv9009 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9009_rx_jesd_rx_axi",
                base_addr=0x84AA0000,
                num_lanes=4,
                irq=106,
                link_clk="axi_rx_clkgen_clk",
                direction="rx",
            )
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
    cfg["adrv9009_board"] = {
        "trx_profile_props": [
            "adi,custom-profile-property = <123>;",
        ]
    }

    nodes = NodeBuilder().build(topo_adrv9009, cfg)
    merged = "\n".join(nodes["converters"])

    assert "adi,custom-profile-property = <123>;" in merged
    assert "adi,rx-profile-rx-fir-num-fir-coefs" not in merged


def test_build_adrv9009_allows_ad9528_channel_block_override(cfg):
    topo_adrv9009 = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9009_rx_jesd_rx_axi",
                base_addr=0x84AA0000,
                num_lanes=4,
                irq=106,
                link_clk="axi_rx_clkgen_clk",
                direction="rx",
            )
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
    cfg["adrv9009_board"] = {
        "ad9528_channel_blocks": [
            "ad9528_0_c9: channel@9 {\n"
            "reg = <9>;\n"
            'adi,extended-name = "CUSTOM_CLK";\n'
            "adi,driver-mode = <1>;\n"
            "adi,divider-phase = <0>;\n"
            "adi,channel-divider = <7>;\n"
            "adi,signal-source = <0>;\n"
            "};\n"
        ]
    }

    nodes = NodeBuilder().build(topo_adrv9009, cfg)
    merged = "\n".join(nodes["converters"])

    assert "ad9528_0_c9: channel@9 {" in merged
    assert 'adi,extended-name = "CUSTOM_CLK";' in merged
    assert "ad9528_0_c13: channel@13" not in merged
