"""Unit tests for BoardModelRenderer."""

import pytest

from adidt.model.board_model import (
    BoardModel,
    ComponentModel,
    FpgaConfig,
    JesdLinkModel,
)
from adidt.devices.clocks import AD9523_1, AD9523Channel
from adidt.devices.converters import AD9680
from adidt.devices.fpga_ip import (
    build_adxcvr_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
)
from adidt.model.renderer import BoardModelRenderer


def _ad9523_rendered(cs: int = 0, label: str = "clk0_ad9523") -> str:
    return AD9523_1(
        label=label,
        channels={1: AD9523Channel(id=1, name="DAC_CLK", divider=1)},
    ).render_dt(cs=cs)


def _ad9680_rendered(cs: int = 2) -> str:
    return AD9680(
        label="adc0_ad9680",
        sampling_frequency_hz=1_000_000_000,
        clks_str="<&clk 0>",
        clk_names_str='"adc_clk"',
    ).render_dt(cs=cs, context={"jesd204_link_ids": "0"})


def _simple_model(**kwargs):
    """Helper to build a minimal BoardModel for testing."""
    defaults = dict(name="test", platform="test")
    defaults.update(kwargs)
    return BoardModel(**defaults)


class TestSPIBusGrouping:
    """Test that components on the same SPI bus are grouped."""

    def test_single_component_wrapped_in_spi_bus(self):
        model = _simple_model(
            components=[
                ComponentModel(
                    role="imu",
                    part="adis16495",
                    template="",
                    spi_bus="spi0",
                    spi_cs=0,
                    config={},
                    rendered="\t\timu0: adis16495@0 { reg = <0>; };",
                ),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        assert len(nodes["converters"]) == 1
        assert "&spi0 {" in nodes["converters"][0]

    def test_two_components_same_bus_grouped(self):
        model = _simple_model(
            components=[
                ComponentModel(
                    role="clock",
                    part="ad9523_1",
                    template="",
                    spi_bus="spi0",
                    spi_cs=0,
                    config={},
                    rendered=_ad9523_rendered(cs=0),
                ),
                ComponentModel(
                    role="adc",
                    part="ad9680",
                    template="",
                    spi_bus="spi0",
                    spi_cs=2,
                    config={},
                    rendered=_ad9680_rendered(cs=2),
                ),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        assert len(nodes["converters"]) == 1
        spi = nodes["converters"][0]
        assert spi.count("&spi0") == 1
        assert "ad9523" in spi
        assert "ad9680" in spi

    def test_two_buses_produce_two_blocks(self):
        model = _simple_model(
            components=[
                ComponentModel(
                    role="clock",
                    part="ad9523_1",
                    template="",
                    spi_bus="spi0",
                    spi_cs=0,
                    config={},
                    rendered=_ad9523_rendered(cs=0),
                ),
                ComponentModel(
                    role="clock",
                    part="ad9523_1",
                    template="",
                    spi_bus="spi1",
                    spi_cs=0,
                    config={},
                    rendered=_ad9523_rendered(cs=0, label="clk1"),
                ),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        assert len(nodes["converters"]) == 2


class TestJesdLinkRendering:
    """Test JESD link rendering (DMA, TPL, JESD overlay, ADXCVR)."""

    def _make_link(self, direction="rx", dma_label="rx_dma"):
        return JesdLinkModel(
            direction=direction,
            jesd_label=f"jesd_{direction}",
            xcvr_label=f"xcvr_{direction}",
            core_label=f"core_{direction}",
            dma_label=dma_label,
            xcvr_rendered=build_adxcvr_ctx(
                label=f"xcvr_{direction}",
                sys_clk_select=0,
                out_clk_select=4,
                clk_ref="clk 0",
                clock_output_names_str='"gt_clk", "out_clk"',
                jesd_l=4,
                jesd_m=2,
                jesd_s=1,
                is_rx=(direction == "rx"),
            ),
            jesd_overlay_rendered=build_jesd204_overlay_ctx(
                label=f"jesd_{direction}",
                direction=direction,
                clocks_str="<&clk 71>, <&xcvr 1>, <&xcvr 0>",
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name="lane_clk",
                f=1,
                k=32,
                jesd204_inputs="xcvr 0 0",
            ),
            tpl_core_rendered=build_tpl_core_ctx(
                label=f"core_{direction}",
                compatible="adi,axi-ad9680-1.0",
                direction=direction,
                dma_label=dma_label,
                spibus_label="adc0",
                jesd_label=f"jesd_{direction}",
                jesd_link_offset=0,
                link_id=0,
            ),
        )

    def test_rx_link_renders_all_nodes(self):
        model = _simple_model(jesd_links=[self._make_link("rx")])
        nodes = BoardModelRenderer().render(model)
        assert len(nodes["converters"]) >= 3  # DMA + TPL + ADXCVR
        assert len(nodes["jesd204_rx"]) == 1
        assert len(nodes["jesd204_tx"]) == 0

    def test_tx_link_renders_to_tx_category(self):
        model = _simple_model(jesd_links=[self._make_link("tx", "tx_dma")])
        nodes = BoardModelRenderer().render(model)
        assert len(nodes["jesd204_tx"]) == 1
        assert len(nodes["jesd204_rx"]) == 0

    def test_dma_overlay_rendered(self):
        model = _simple_model(jesd_links=[self._make_link("rx")])
        nodes = BoardModelRenderer().render(model)
        dma_found = any("rx_dma" in n for n in nodes["converters"])
        assert dma_found

    def test_dma_skipped_when_none(self):
        link = self._make_link("rx")
        link.dma_label = None
        model = _simple_model(jesd_links=[link])
        nodes = BoardModelRenderer().render(model)
        dma_found = any("axi-dmac" in n for n in nodes["converters"])
        assert not dma_found

    def test_empty_configs_skipped(self):
        link = JesdLinkModel(
            direction="rx",
            jesd_label="j",
            xcvr_label="x",
            core_label="c",
            dma_label="d",
        )
        model = _simple_model(jesd_links=[link])
        nodes = BoardModelRenderer().render(model)
        # Only DMA should render (configs are empty, others skipped)
        assert len(nodes["jesd204_rx"]) == 0


class TestExtraNodes:
    """Test extra_nodes are appended to converters."""

    def test_extra_nodes_appended(self):
        model = _simple_model(
            extra_nodes=["\t&misc_clk { clock-frequency = <100000000>; };"]
        )
        nodes = BoardModelRenderer().render(model)
        assert any("misc_clk" in n for n in nodes["converters"])

    def test_empty_extra_nodes(self):
        model = _simple_model(extra_nodes=[])
        nodes = BoardModelRenderer().render(model)
        assert nodes["converters"] == []


class TestDmaClocks:
    """Test dma_clocks_str support."""

    def test_dma_clocks_included(self):
        link = JesdLinkModel(
            direction="rx",
            jesd_label="j",
            xcvr_label="x",
            core_label="c",
            dma_label="rx_dma",
            dma_clocks_str="<&clk 71>",
        )
        model = _simple_model(jesd_links=[link])
        nodes = BoardModelRenderer().render(model)
        dma_node = next(n for n in nodes["converters"] if "rx_dma" in n)
        assert "clocks = <&clk 71>" in dma_node

    def test_no_dma_clocks_when_none(self):
        link = JesdLinkModel(
            direction="rx",
            jesd_label="j",
            xcvr_label="x",
            core_label="c",
            dma_label="rx_dma",
        )
        model = _simple_model(jesd_links=[link])
        nodes = BoardModelRenderer().render(model)
        dma_node = next(n for n in nodes["converters"] if "rx_dma" in n)
        assert "clocks" not in dma_node


class TestBoardModelToDts:
    """Test the to_dts() convenience method."""


class TestSerialization:
    """Test to_dict/from_dict round-trip."""

    def test_round_trip_with_fpga_config(self):
        original = _simple_model(
            fpga_config=FpgaConfig(
                platform="zcu102",
                addr_cells=2,
                ps_clk_label="zynqmp_clk",
                ps_clk_index=71,
                gpio_label="gpio",
            )
        )
        d = original.to_dict()
        restored = BoardModel.from_dict(d)
        assert restored.fpga_config is not None
        assert restored.fpga_config.platform == "zcu102"
        assert restored.fpga_config.addr_cells == 2
