"""Unit tests for FMCDAQ2Builder."""

from adidt.model.renderer import BoardModelRenderer
from adidt.xsa.build.builders.fmcdaq2 import FMCDAQ2Builder


class TestFMCDAQ2Builder:
    def test_matches_fmcdaq2_topology(self, topo_fmcdaq2):
        assert FMCDAQ2Builder().matches(topo_fmcdaq2, {})

    def test_does_not_match_adrv9009(self, topo_adrv9009):
        assert not FMCDAQ2Builder().matches(topo_adrv9009, {})

    def test_build_model_returns_board_model(self, topo_fmcdaq2):
        model = FMCDAQ2Builder().build_model(topo_fmcdaq2, {}, "zynqmp_clk", 71, "gpio")
        assert model.name.startswith("fmcdaq2_")
        assert model.platform == "zcu102"

    def test_build_model_has_three_components(self, topo_fmcdaq2):
        model = FMCDAQ2Builder().build_model(topo_fmcdaq2, {}, "zynqmp_clk", 71, "gpio")
        assert len(model.components) == 3
        assert model.get_component("clock").part == "ad9523_1"
        assert model.get_component("adc").part == "ad9680"
        assert model.get_component("dac").part == "ad9144"

    def test_build_model_has_two_jesd_links(self, topo_fmcdaq2):
        model = FMCDAQ2Builder().build_model(topo_fmcdaq2, {}, "zynqmp_clk", 71, "gpio")
        assert len(model.jesd_links) == 2
        assert model.get_jesd_link("rx") is not None
        assert model.get_jesd_link("tx") is not None

    def test_build_model_renders_without_error(self, topo_fmcdaq2):
        model = FMCDAQ2Builder().build_model(topo_fmcdaq2, {}, "zynqmp_clk", 71, "gpio")
        nodes = BoardModelRenderer().render(model)
        assert nodes["converters"]
        assert nodes["jesd204_rx"]
        assert nodes["jesd204_tx"]

    def test_jesd_params_from_config(self, topo_fmcdaq2):
        cfg = {"jesd": {"rx": {"L": 2, "M": 1}, "tx": {"L": 2, "M": 1}}}
        model = FMCDAQ2Builder().build_model(
            topo_fmcdaq2, cfg, "zynqmp_clk", 71, "gpio"
        )
        rx = model.get_jesd_link("rx")
        assert rx.link_params["L"] == 2
        assert rx.link_params["M"] == 1
