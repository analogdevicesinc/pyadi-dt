"""Unit tests for ADRV9009Builder."""

from adidt.xsa.builders.adrv9009 import ADRV9009Builder


ADRV9009_CFG = {
    "jesd": {
        "rx": {"F": 4, "K": 32, "M": 4, "L": 2},
        "tx": {"F": 4, "K": 32, "M": 4, "L": 4},
    },
}


class TestARDV9009Builder:
    def test_matches_adrv9009_topology(self, topo_adrv9009):
        assert ADRV9009Builder().matches(topo_adrv9009, ADRV9009_CFG)

    def test_does_not_match_fmcdaq2(self, topo_fmcdaq2):
        assert not ADRV9009Builder().matches(topo_fmcdaq2, {})

    def test_build_model_returns_model(self, topo_adrv9009):
        model = ADRV9009Builder().build_model(
            topo_adrv9009, ADRV9009_CFG, "zynqmp_clk", 71, "gpio"
        )
        assert model is not None
        assert model.name.startswith("adrv9009_")

    def test_build_model_has_clock_component(self, topo_adrv9009):
        model = ADRV9009Builder().build_model(
            topo_adrv9009, ADRV9009_CFG, "zynqmp_clk", 71, "gpio"
        )
        clock = model.get_component("clock")
        assert clock is not None

    def test_build_model_has_rx_tx_links(self, topo_adrv9009):
        model = ADRV9009Builder().build_model(
            topo_adrv9009, ADRV9009_CFG, "zynqmp_clk", 71, "gpio"
        )
        assert len(model.jesd_links) >= 2

    def test_no_orx_nodes_when_no_orx_jesd(self, topo_adrv9009):
        """ORX nodes should be skipped when topology has no ORX JESD IP."""
        model = ADRV9009Builder().build_model(
            topo_adrv9009, ADRV9009_CFG, "zynqmp_clk", 71, "gpio"
        )
        extra_before = model.metadata.get("extra_nodes_before", [])
        extra_after = model.metadata.get("extra_nodes_after", [])
        all_nodes = " ".join(extra_before + extra_after)
        assert "core_rx_obs" not in all_nodes
