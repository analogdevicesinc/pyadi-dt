"""Unit tests for AD9081Builder."""

from adidt.model.renderer import BoardModelRenderer
from adidt.xsa.builders.ad9081 import AD9081Builder


AD9081_CFG = {
    "jesd": {
        "rx": {"F": 2, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1},
        "tx": {"F": 2, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1},
    },
    "ad9081": {
        "rx_link_mode": 10,
        "tx_link_mode": 9,
        "adc_frequency_hz": 4000000000,
        "dac_frequency_hz": 12000000000,
        "rx_cddc_decimation": 4,
        "rx_fddc_decimation": 4,
        "tx_cduc_interpolation": 8,
        "tx_fduc_interpolation": 6,
    },
}


class TestAD9081Builder:
    def test_matches_ad9081_topology(self, topo_ad9081):
        assert AD9081Builder().matches(topo_ad9081, AD9081_CFG)

    def test_does_not_match_fmcdaq2(self, topo_fmcdaq2):
        assert not AD9081Builder().matches(topo_fmcdaq2, {})

    def test_build_model_has_components(self, topo_ad9081):
        model = AD9081Builder().build_model(
            topo_ad9081, AD9081_CFG, "zynqmp_clk", 71, "gpio"
        )
        assert model.get_component("clock") is not None
        assert model.get_component("clock").part == "hmc7044"
        # AD9081 MxFE component
        mxfe = [c for c in model.components if c.part == "ad9081"]
        assert len(mxfe) == 1

    def test_build_model_has_rx_tx_links(self, topo_ad9081):
        model = AD9081Builder().build_model(
            topo_ad9081, AD9081_CFG, "zynqmp_clk", 71, "gpio"
        )
        assert model.get_jesd_link("rx") is not None
        assert model.get_jesd_link("tx") is not None

    def test_build_model_renders(self, topo_ad9081):
        model = AD9081Builder().build_model(
            topo_ad9081, AD9081_CFG, "zynqmp_clk", 71, "gpio"
        )
        nodes = BoardModelRenderer().render(model)
        assert nodes["converters"]
