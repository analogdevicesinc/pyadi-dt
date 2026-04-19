"""Unit tests for ADRV937xBuilder."""

from adidt.xsa.builders.adrv937x import ADRV937xBuilder


ADRV937X_CFG = {
    "jesd": {
        "rx": {"F": 4, "K": 32, "M": 4, "L": 2},
        "tx": {"F": 4, "K": 32, "M": 4, "L": 4},
    },
}


class TestARDV937xBuilder:
    def test_matches_adrv937x_topology(self, topo_adrv937x):
        assert ADRV937xBuilder().matches(topo_adrv937x, ADRV937X_CFG)

    def test_does_not_match_adrv9009(self, topo_adrv9009):
        assert not ADRV937xBuilder().matches(topo_adrv9009, {})

    def test_does_not_match_fmcdaq2(self, topo_fmcdaq2):
        assert not ADRV937xBuilder().matches(topo_fmcdaq2, {})

    def test_build_model_returns_model(self, topo_adrv937x):
        model = ADRV937xBuilder().build_model(
            topo_adrv937x, ADRV937X_CFG, "clkc", 15, "gpio"
        )
        assert model is not None
        assert model.name.startswith("adrv937x_")

    def test_build_model_has_clock_component(self, topo_adrv937x):
        model = ADRV937xBuilder().build_model(
            topo_adrv937x, ADRV937X_CFG, "clkc", 15, "gpio"
        )
        clock = model.get_component("clock")
        assert clock is not None
        assert "9528" in clock.part

    def test_build_model_has_rx_tx_links(self, topo_adrv937x):
        model = ADRV937xBuilder().build_model(
            topo_adrv937x, ADRV937X_CFG, "clkc", 15, "gpio"
        )
        assert len(model.jesd_links) >= 2
        directions = sorted(l.direction for l in model.jesd_links)
        assert directions == ["rx", "tx"]

    def test_build_model_phy_compatible(self, topo_adrv937x):
        model = ADRV937xBuilder().build_model(
            topo_adrv937x, ADRV937X_CFG, "clkc", 15, "gpio"
        )
        phy = model.get_component("transceiver")
        assert phy is not None
        assert "ad9371" in phy.rendered
        assert 'compatible = "adi,ad9371"' in phy.rendered
