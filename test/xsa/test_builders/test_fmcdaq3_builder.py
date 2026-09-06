"""Unit tests for FMCDAQ3Builder."""

import pytest

from adidt._naming import out_clk_select
from adidt.model.renderer import BoardModelRenderer
from adidt.xsa.build.builders.fmcdaq3 import FMCDAQ3Builder


class TestFMCDAQ3Builder:
    @pytest.mark.parametrize(
        "selector,value",
        [
            ("XCVR_OUTCLK_PCS", 1),
            ("XCVR_OUTCLK_PMA", 2),
            ("XCVR_REFCLK", 3),
            ("XCVR_REFCLK_DIV2", 4),
            ("XCVR_PROGDIV_CLK", 5),
        ],
    )
    def test_clock_selectors_match_linux_binding(self, topo_fmcdaq3, selector, value):
        model = FMCDAQ3Builder().build_model(
            topo_fmcdaq3,
            {
                "fpga_adc": {"out_clk_select": selector},
                "fpga_dac": {"out_clk_select": selector},
            },
            "clk_bus_0",
            None,
            "axi_gpio",
        )
        rendered = str(BoardModelRenderer().render(model))
        assert rendered.count(f"adi,out-clk-select = <{value}>;") == 2
        assert out_clk_select(selector) == value

    def test_fmc_reference_and_sysref_outputs_use_reference_dividers(
        self, topo_fmcdaq3
    ):
        model = FMCDAQ3Builder().build_model(
            topo_fmcdaq3, {}, "clk_bus_0", None, "axi_gpio"
        )
        clock = model.get_component("clock").rendered
        for channel in (4, 5, 6, 7, 8, 9):
            node = clock.split(f"channel@{channel} {{", 1)[1].split("};", 1)[0]
            assert "adi,channel-divider = <4>;" in node
            assert "adi,driver-mode = <0>;" in node
        assert "adi,sysref-k-div = <64>;" in clock
        assert "spi-cpol;" in clock and "spi-cpha;" in clock
        adc = model.get_component("adc").rendered
        assert "adi,sfdr-optimization-config = <14 160 80 9 24 0 31 4>;" in adc
        assert "adi,sysref-mode = <1>;" in adc
        assert "adi,sysref-mode = <1>;" in model.get_component("dac").rendered

    def test_matches_fmcdaq3_topology(self, topo_fmcdaq3):
        assert FMCDAQ3Builder().matches(topo_fmcdaq3, {})

    def test_does_not_match_fmcdaq2(self, topo_fmcdaq2):
        assert not FMCDAQ3Builder().matches(topo_fmcdaq2, {})

    def test_build_model_has_three_components(self, topo_fmcdaq3):
        model = FMCDAQ3Builder().build_model(topo_fmcdaq3, {}, "zynqmp_clk", 71, "gpio")
        assert len(model.components) == 3
        assert model.get_component("clock").part == "ad9528"
        assert model.get_component("adc").part == "ad9680"
        assert model.get_component("dac").part == "ad9152"

    def test_build_model_renders(self, topo_fmcdaq3):
        model = FMCDAQ3Builder().build_model(topo_fmcdaq3, {}, "zynqmp_clk", 71, "gpio")
        nodes = BoardModelRenderer().render(model)
        assert nodes["converters"]

    def test_microblaze_bus_clock_has_no_specifier(self, topo_fmcdaq3):
        model = FMCDAQ3Builder().build_model(
            topo_fmcdaq3, {}, "clk_bus_0", None, "axi_gpio"
        )
        nodes = BoardModelRenderer().render(model)
        rendered = str(nodes)
        assert "<&clk_bus_0>" in rendered
        assert "<&clk_bus_0 None>" not in rendered

    def test_shared_sysref_provider_belongs_to_tx_topology(self, topo_fmcdaq3):
        model = FMCDAQ3Builder().build_model(
            topo_fmcdaq3,
            {"fmcdaq3_board": {"adc_jesd_link_id": 2, "dac_jesd_link_id": 3}},
            "clk_bus_0",
            None,
            "axi_gpio",
        )
        rendered = str(BoardModelRenderer().render(model))
        assert "jesd204-inputs = <&clk0_ad9528 0 2>" not in rendered
        assert "jesd204-inputs = <&clk0_ad9528 1 3>" in rendered
