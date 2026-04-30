# test/xsa/test_node_builder_templates.py
from types import SimpleNamespace

from adidt.xsa.build.builders.adrv9009 import ADRV9009Builder
from adidt.xsa.build.node_builder import NodeBuilder
from adidt.xsa.parse.topology import ConverterInstance, Jesd204Instance, XsaTopology


def test_wrap_spi_bus_produces_overlay():
    nb = NodeBuilder()
    result = nb._wrap_spi_bus("spi0", "\t\tchild_node;\n")
    assert "\t&spi0 {" in result
    assert 'status = "okay";' in result
    assert "\t\tchild_node;" in result
    assert "\t};" in result


def _make_ad9680_ctx():
    # fmcdaq2-style: 3 clocks (jesd_label, device_clk, sysref_clk), no spi-cpol/cpha
    return {
        "label": "adc0_ad9680",
        "cs": 2,
        "spi_max_hz": 1000000,
        "use_spi_3wire": False,  # fmcdaq2: no spi-cpol/cpha/spi-3wire
        "clks_str": "<&axi_ad9680_jesd204_rx>, <&clk0_ad9523 13>, <&clk0_ad9523 5>",
        "clk_names_str": '"jesd_adc_clk", "adc_clk", "adc_sysref"',
        "sampling_frequency_hz": 1000000000,
        "m": 2,
        "l": 4,
        "f": 1,
        "k": 32,
        "np": 16,
        "jesd204_top_device": 0,
        "jesd204_link_ids": [0],
        "jesd204_inputs": "axi_ad9680_core 0 0",
        "gpio_lines": [],
    }


def _make_ad9144_ctx():
    return {
        "label": "dac0_ad9144",
        "cs": 1,
        "spi_max_hz": 1000000,
        "clk_ref": "clk0_ad9523 1",
        "jesd204_top_device": 1,
        "jesd204_link_ids": [0],
        # offset 1: AD9144 device node references the TPL core at link offset 1
        "jesd204_inputs": "axi_ad9144_core 1 0",
        "gpio_lines": [],
    }


def _make_jesd_overlay_ctx_rx():
    return {
        "label": "axi_ad9680_jesd204_rx",
        "direction": "rx",
        "clocks_str": "<&zynqmp_clk 71>, <&axi_ad9680_adxcvr 1>, <&axi_ad9680_adxcvr 0>",
        "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
        "clock_output_name": "jesd_adc_lane_clk",
        "f": 1,
        "k": 32,
        "jesd204_inputs": "axi_ad9680_adxcvr 0 0",
        "converter_resolution": None,
        "converters_per_device": None,
        "bits_per_sample": None,
        "control_bits_per_sample": None,
    }


def _make_standard_adrv9009_topology():
    """Return a minimal XsaTopology for a standard (non-FMComms8) ADRV9009 design."""
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9009_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=107,
                link_clk="axi_adrv9009_rx_clkgen",
                direction="rx",
            ),
            Jesd204Instance(
                name="axi_adrv9009_rx_os_jesd_rx_axi",
                base_addr=0x84AA0000,
                num_lanes=2,
                irq=108,
                link_clk="axi_adrv9009_rx_os_clkgen",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9009_tx_jesd_tx_axi",
                base_addr=0x84A80000,
                num_lanes=4,
                irq=106,
                link_clk="axi_adrv9009_tx_clkgen",
                direction="tx",
            ),
        ],
        converters=[
            ConverterInstance(
                name="axi_adrv9009_core_rx",
                ip_type="axi_adrv9009",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_adrv9009_core_tx",
                ip_type="axi_adrv9009",
                base_addr=0x84A04000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_adrv9009_core_rx_obs",
                ip_type="axi_adrv9009",
                base_addr=0x84A14000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
        fpga_part="xczu9eg",
    )


def _make_standard_adrv9009_cfg():
    """Return a minimal cfg dict for a standard ADRV9009 design."""
    return {
        "adrv9009_board": {},
        "jesd": {
            "rx": {"F": 4, "K": 32},
            "tx": {"F": 2, "K": 32, "M": 4},
        },
    }


def _build_adrv9009_via_builder(topology, cfg):
    """Route through the ADRV9009Builder the same way NodeBuilder.build() does."""
    nb = NodeBuilder()
    ps_clk_label, ps_clk_index, gpio_label = nb._platform_ps_labels(topology)
    nb._addr_cells = 2
    return ADRV9009Builder().build_nodes(
        nb, topology, cfg, ps_clk_label, ps_clk_index, gpio_label
    )


def test_build_adrv9009_nodes_standard_returns_nonempty():
    topology = _make_standard_adrv9009_topology()
    cfg = _make_standard_adrv9009_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    assert len(result) > 0


def test_build_adrv9009_nodes_standard_has_ad9528_clock_chip():
    topology = _make_standard_adrv9009_topology()
    cfg = _make_standard_adrv9009_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    text = "\n".join(result)
    assert "clk0_ad9528: ad9528-1@0" in text


def test_build_adrv9009_nodes_standard_has_tx_jesd_converter_resolution():
    topology = _make_standard_adrv9009_topology()
    cfg = _make_standard_adrv9009_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    text = "\n".join(result)
    assert "adi,octets-per-frame" in text
    # ADRV9009 Talise DACs are 16-bit (production Kuiper DT uses
    # converter-resolution=16 / control-bits-per-sample=0).  An earlier
    # revision of this builder emitted 14/2 by mistake.
    assert "adi,converter-resolution = <16>" in text
    assert "adi,control-bits-per-sample = <0>" in text


def test_build_adrv9009_nodes_standard_has_phy_node():
    topology = _make_standard_adrv9009_topology()
    cfg = _make_standard_adrv9009_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    text = "\n".join(result)
    assert "trx0_adrv9009: adrv9009-phy@1" in text


def test_build_adrv9009_nodes_standard_has_clkgen_nodes():
    topology = _make_standard_adrv9009_topology()
    cfg = _make_standard_adrv9009_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    text = "\n".join(result)
    assert "adi,axi-clkgen-2.00.a" in text


def _make_fmcomms8_topology():
    """Return a minimal XsaTopology for an FMComms8 dual-chip ADRV9009 design.

    FMComms8 is detected by TPL core instances with 'adrv9009' and 'tpl_core' in the name.
    """
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9009_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=107,
                link_clk="hmc7044_fmc_9",
                direction="rx",
            ),
            Jesd204Instance(
                name="axi_adrv9009_rx_os_jesd_rx_axi",
                base_addr=0x84AA0000,
                num_lanes=2,
                irq=108,
                link_clk="hmc7044_fmc_8",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9009_tx_jesd_tx_axi",
                base_addr=0x84A80000,
                num_lanes=4,
                irq=106,
                link_clk="hmc7044_fmc_8",
                direction="tx",
            ),
        ],
        converters=[
            ConverterInstance(
                name="adrv9009_tpl_core_rx_adc_tpl_core",
                ip_type="axi_adrv9009",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="adrv9009_tpl_core_tx_dac_tpl_core",
                ip_type="axi_adrv9009",
                base_addr=0x84A04000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="adrv9009_tpl_core_obs_adc_tpl_core",
                ip_type="axi_adrv9009",
                base_addr=0x84A14000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
        fpga_part="xczu9eg",
    )


def _make_fmcomms8_cfg():
    return {
        "adrv9009_board": {},
        "jesd": {
            "rx": {"F": 4, "K": 32},
            "tx": {"F": 2, "K": 32, "M": 4},
        },
    }


def test_build_adrv9009_nodes_fmcomms8_returns_nonempty():
    topology = _make_fmcomms8_topology()
    cfg = _make_fmcomms8_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    assert len(result) > 0


def test_build_adrv9009_nodes_fmcomms8_has_hmc7044_clock_chip():
    topology = _make_fmcomms8_topology()
    cfg = _make_fmcomms8_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    text = "\n".join(result)
    assert "hmc7044_fmc: hmc7044@0" in text


def test_build_adrv9009_nodes_fmcomms8_has_primary_phy():
    topology = _make_fmcomms8_topology()
    cfg = _make_fmcomms8_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    text = "\n".join(result)
    assert "trx0_adrv9009: adrv9009-phy@1" in text


def test_build_adrv9009_nodes_fmcomms8_has_second_phy():
    topology = _make_fmcomms8_topology()
    cfg = _make_fmcomms8_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    text = "\n".join(result)
    assert "trx1_adrv9009" in text


def test_build_adrv9009_nodes_fmcomms8_no_clkgen():
    topology = _make_fmcomms8_topology()
    cfg = _make_fmcomms8_cfg()
    result = _build_adrv9009_via_builder(topology, cfg)
    text = "\n".join(result)
    assert "adi,axi-clkgen-2.00.a" not in text
