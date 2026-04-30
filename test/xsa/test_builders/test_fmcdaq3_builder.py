"""Unit tests for FMCDAQ3Builder."""

from adidt.model.renderer import BoardModelRenderer
from adidt.xsa.build.builders.fmcdaq3 import FMCDAQ3Builder


class TestFMCDAQ3Builder:
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
