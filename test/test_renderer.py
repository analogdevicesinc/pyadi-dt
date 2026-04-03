"""Unit tests for BoardModelRenderer."""

import pytest

from adidt.model.board_model import (
    BoardModel,
    ComponentModel,
    FpgaConfig,
    JesdLinkModel,
)
from adidt.model.contexts import (
    build_ad9523_1_ctx,
    build_ad9680_ctx,
    build_adxcvr_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
)
from adidt.model.renderer import BoardModelRenderer


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
                    template="adis16495.tmpl",
                    spi_bus="spi0",
                    spi_cs=0,
                    config={
                        "label": "imu0",
                        "device": "adis16495",
                        "compatible": "adi,adis16495-1",
                        "cs": 0,
                        "spi_max_hz": 2000000,
                        "spi_cpol": True,
                        "spi_cpha": True,
                        "gpio_label": "gpio",
                        "interrupt_gpio": 25,
                        "irq_type": "IRQ_TYPE_EDGE_FALLING",
                    },
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
                    template="ad9523_1.tmpl",
                    spi_bus="spi0",
                    spi_cs=0,
                    config=build_ad9523_1_ctx(cs=0),
                ),
                ComponentModel(
                    role="adc",
                    part="ad9680",
                    template="ad9680.tmpl",
                    spi_bus="spi0",
                    spi_cs=2,
                    config=build_ad9680_ctx(
                        cs=2,
                        clks_str="<&clk 0>",
                        clk_names_str='"adc_clk"',
                    ),
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
                    template="ad9523_1.tmpl",
                    spi_bus="spi0",
                    spi_cs=0,
                    config=build_ad9523_1_ctx(cs=0),
                ),
                ComponentModel(
                    role="clock",
                    part="ad9523_1",
                    template="ad9523_1.tmpl",
                    spi_bus="spi1",
                    spi_cs=0,
                    config=build_ad9523_1_ctx(cs=0, label="clk1"),
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
            xcvr_config=build_adxcvr_ctx(
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
            jesd_overlay_config=build_jesd204_overlay_ctx(
                label=f"jesd_{direction}",
                direction=direction,
                clocks_str="<&clk 71>, <&xcvr 1>, <&xcvr 0>",
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name="lane_clk",
                f=1,
                k=32,
                jesd204_inputs="xcvr 0 0",
            ),
            tpl_core_config=build_tpl_core_ctx(
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
            xcvr_config={},
            jesd_overlay_config={},
            tpl_core_config={},
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
            xcvr_config={},
            jesd_overlay_config={},
            tpl_core_config={},
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
            xcvr_config={},
            jesd_overlay_config={},
            tpl_core_config={},
        )
        model = _simple_model(jesd_links=[link])
        nodes = BoardModelRenderer().render(model)
        dma_node = next(n for n in nodes["converters"] if "rx_dma" in n)
        assert "clocks" not in dma_node


class TestBoardModelToDts:
    """Test the to_dts() convenience method."""

    def test_to_dts_writes_file(self, tmp_path):
        from adidt.model import components

        model = _simple_model(
            components=[components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25)]
        )
        out = tmp_path / "test.dts"
        result = model.to_dts(str(out))
        assert result == str(out)
        assert out.exists()
        content = out.read_text()
        assert "SPDX-License-Identifier" in content
        assert "/dts-v1/;" in content
        assert "adis16495" in content

    def test_to_dts_round_trip(self, tmp_path):
        """Verify to_dts output compiles with dtc (syntax check)."""
        import shutil
        import subprocess

        if not shutil.which("dtc"):
            pytest.skip("dtc not available")

        from adidt.model import components

        model = _simple_model(
            components=[
                components.adis16495(
                    spi_bus="spi0", cs=0, interrupt_gpio=25, irq_type="2"
                )
            ]
        )
        dts = tmp_path / "test.dts"
        model.to_dts(str(dts))

        res = subprocess.run(
            ["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", "/dev/null", str(dts)],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"dtc failed: {res.stderr}"


class TestSerialization:
    """Test to_dict/from_dict round-trip."""

    def test_round_trip(self):
        from adidt.model import components

        original = _simple_model(
            components=[components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25)],
            metadata={"source": "test"},
        )
        d = original.to_dict()
        restored = BoardModel.from_dict(d)
        assert restored.name == original.name
        assert restored.platform == original.platform
        assert len(restored.components) == len(original.components)
        assert restored.components[0].part == "adis16495"
        assert restored.metadata["source"] == "test"

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
