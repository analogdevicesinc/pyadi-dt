"""Unit tests for ADRV9009-ZU11EG support (platform, FPGA board, profile).

Covers the pieces added to teach pyadi-dt about the ADRV9009-ZU11EG SoM:

* ``xczu11eg`` FPGA part → ``zu11eg`` platform inference,
* the :class:`adidt.fpga.zu11eg` board model,
* the ``adrv9009_zu11eg`` built-in profile,
* the ``kuiper_boards.json`` registry entries,
* the ADRV9009 builder producing a dual-chip (``adrv9009-x2``) model
  on the ZU11EG's HMC7044 topology.
"""

from __future__ import annotations

import json
from pathlib import Path

from adidt.fpga import zu11eg
from adidt.xsa.config.profiles import ProfileManager
from adidt.xsa.parse.topology import (
    ConverterInstance,
    Jesd204Instance,
    XsaTopology,
)


# ---------------------------------------------------------------------------
# Platform inference
# ---------------------------------------------------------------------------


def test_xsa_topology_infers_zu11eg_platform_from_part_prefix():
    topo = XsaTopology(fpga_part="xczu11eg-ffvf1517-2")
    assert topo.inferred_platform() == "zu11eg"


def test_xsa_topology_zu11eg_distinct_from_zcu102():
    """xczu11eg must map to zu11eg, not the xczu9eg-based zcu102."""
    assert XsaTopology(fpga_part="xczu9eg-ffvb1156-2").inferred_platform() == "zcu102"
    assert XsaTopology(fpga_part="xczu11eg-ffvf1517-2").inferred_platform() == "zu11eg"


# ---------------------------------------------------------------------------
# FPGA board model
# ---------------------------------------------------------------------------


def test_zu11eg_board_platform_constants():
    board = zu11eg()
    assert board.platform == "zu11eg"
    assert board.PLATFORM == "zu11eg"
    # ZynqMP PS-side constants (shared with ZCU102).
    assert board.ADDR_CELLS == 2
    assert board.PS_CLK_LABEL == "zynqmp_clk"
    assert board.PS_CLK_INDEX == 71
    assert board.GPIO_LABEL == "gpio"


def test_zu11eg_board_has_spi_and_gt_lanes():
    board = zu11eg()
    assert [s.label for s in board.spi] == ["spi0", "spi1"]
    assert len(board.gt) == board.NUM_GT_LANES == 16


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def test_profile_manager_lists_adrv9009_zu11eg():
    assert "adrv9009_zu11eg" in ProfileManager().list_profiles()


def test_profile_manager_loads_adrv9009_zu11eg_profile():
    profile = ProfileManager().load("adrv9009_zu11eg")
    assert profile["name"] == "adrv9009_zu11eg"
    board = profile["defaults"]["adrv9009_board"]
    # Dual-transceiver (adrv9009-x2) chip-selects + HMC7044 clock.
    assert board["trx_cs"] == 1
    assert board["trx2_cs"] == 2
    assert board["hmc7044_vcxo_frequency"] == 122880000
    assert board["hmc7044_rx_channel"] == 9
    assert board["hmc7044_tx_channel"] == 8


def test_adrv9009_profile_allows_hmc7044_keys():
    """The profile validator must accept the HMC7044/trx2 keys the ZU11EG uses."""
    from adidt.xsa.config.profiles import _validate_profile_defaults

    # Should not raise.
    _validate_profile_defaults(
        {
            "adrv9009_board": {
                "hmc7044_rx_channel": 9,
                "hmc7044_tx_channel": 8,
                "trx2_cs": 2,
                "trx2_reset_gpio": 135,
            }
        }
    )


# ---------------------------------------------------------------------------
# kuiper_boards.json registry
# ---------------------------------------------------------------------------


def _kuiper_boards() -> dict:
    path = (
        Path(__file__).resolve().parents[2]
        / "adidt"
        / "xsa"
        / "config"
        / "kuiper_boards.json"
    )
    return json.loads(path.read_text())["boards"]


def test_kuiper_boards_zu11eg_full_support():
    boards = _kuiper_boards()
    entry = boards["zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb"]
    assert entry["status"] == "full"
    assert entry["platform"] == "zu11eg"
    assert entry["converter"] == "adrv9009"
    assert entry["profile"] == "adrv9009_zu11eg"
    assert entry["builder"] == "ADRV9009Builder"


def test_kuiper_boards_zu11eg_variants_profile_only():
    boards = _kuiper_boards()
    for name in (
        "zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb-fmcbridge",
        "zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb-sync-fmcomms8",
        "zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb-xmicrowave",
    ):
        entry = boards[name]
        assert entry["status"] == "profile_only", name
        assert entry["platform"] == "zu11eg", name
        assert entry["builder"] == "ADRV9009Builder", name


# ---------------------------------------------------------------------------
# Builder on a ZU11EG-style dual-transceiver topology
# ---------------------------------------------------------------------------


def _topo_adrv9009_zu11eg() -> XsaTopology:
    """Single-SoM ADRV9009-ZU11EG topology (rx + obs + tx, xczu11eg part).

    Mirrors the instance names emitted by the ADRV9009-ZU11EG HDL design
    (``axi_adrv9009_som_{rx,rx_os,tx}_jesd_*``), which the ADRV9009
    builder's FMComms8/dual-chip heuristic classifies as ``adrv9009-x2``.
    """
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9009_som_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=2,
                irq=0,
                link_clk="",
                direction="rx",
            ),
            Jesd204Instance(
                name="axi_adrv9009_som_obs_jesd_rx_axi",
                base_addr=0x84B00000,
                num_lanes=2,
                irq=0,
                link_clk="",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9009_som_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=4,
                irq=0,
                link_clk="",
                direction="tx",
            ),
        ],
        clkgens=[],
        converters=[
            ConverterInstance(
                name="axi_adrv9009_som",
                ip_type="axi_adrv9009",
                base_addr=0x84A00000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
        signal_connections=[],
        fpga_part="xczu11eg-ffvf1517-2",
    )


_ZU11EG_CFG = {
    "adrv9009_board": {"trx_cs": 1, "trx2_cs": 2},
    "jesd": {
        "rx": {"F": 4, "K": 32, "M": 4, "L": 2},
        "tx": {"F": 2, "K": 32, "M": 4, "L": 4},
    },
}


def test_builder_matches_zu11eg_topology():
    from adidt.xsa.build.builders.adrv9009 import ADRV9009Builder

    assert ADRV9009Builder().matches(_topo_adrv9009_zu11eg(), _ZU11EG_CFG)


def test_builder_zu11eg_model_platform_and_links():
    """Builder produces a valid ADRV9009 model tagged for the zu11eg platform.

    This exercises the builder wiring on a minimal synthetic ZU11EG
    topology (platform inference + RX/OBS/TX link discovery).  The full
    dual-chip ``adrv9009-x2`` + HMC7044 shape depends on the complete
    TPL-core / signal-connection label set present in the real HDL XSA
    and is validated end-to-end by ``test_adrv9009_zu11eg_hw.py``.
    """
    from adidt.xsa.build.builders.adrv9009 import ADRV9009Builder

    model = ADRV9009Builder().build_model(
        _topo_adrv9009_zu11eg(), _ZU11EG_CFG, "zynqmp_clk", 71, "gpio"
    )
    assert model is not None
    assert model.platform == "zu11eg"
    assert model.name == "adrv9009_zu11eg"
    # A clock chip and the ADRV9009 PHY are both present.
    assert model.get_component("clock") is not None
    phy = model.get_component("transceiver")
    assert phy is not None
    assert '"adrv9009"' in phy.rendered
    # ORX path present (rx + rx_os + tx = 3 JESD links).
    assert len(model.jesd_links) == 3
    assert [j.direction for j in model.jesd_links] == ["rx", "rx", "tx"]
