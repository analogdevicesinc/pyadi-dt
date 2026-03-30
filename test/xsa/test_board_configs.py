"""Tests for board configuration dataclasses and PipelineConfig."""

import json
from pathlib import Path

import pytest

from adidt.xsa.board_configs import (
    AD9081BoardConfig,
    AD9084BoardConfig,
    AD9172BoardConfig,
    ADRV9009BoardConfig,
    ClockConfig,
    FMCDAQ2BoardConfig,
    FMCDAQ3BoardConfig,
    JesdConfig,
    JesdLinkParams,
)
from adidt.xsa.pipeline_config import PipelineConfig
from adidt.xsa.profiles import ProfileManager


FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# JesdLinkParams
# ---------------------------------------------------------------------------


class TestJesdLinkParams:
    def test_defaults(self):
        p = JesdLinkParams()
        assert p.F == 1
        assert p.K == 32
        assert p.M == 2
        assert p.L == 4
        assert p.Np == 16
        assert p.S == 1

    def test_from_dict_with_all_keys(self):
        d = {"F": 4, "K": 16, "M": 8, "L": 2, "Np": 12, "S": 2}
        p = JesdLinkParams.from_dict(d)
        assert p.F == 4
        assert p.K == 16
        assert p.M == 8
        assert p.L == 2
        assert p.Np == 12
        assert p.S == 2

    def test_from_dict_uses_defaults_for_missing_keys(self):
        p = JesdLinkParams.from_dict({"F": 6})
        assert p.F == 6
        assert p.K == 32  # default

    def test_from_dict_coerces_strings(self):
        p = JesdLinkParams.from_dict({"F": "4", "K": "32"})
        assert p.F == 4
        assert p.K == 32


# ---------------------------------------------------------------------------
# JesdConfig
# ---------------------------------------------------------------------------


class TestJesdConfig:
    def test_from_dict(self):
        d = {
            "rx": {"F": 4, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1},
            "tx": {"F": 4, "K": 32, "M": 4, "L": 8, "Np": 12, "S": 1},
        }
        cfg = JesdConfig.from_dict(d)
        assert cfg.rx.F == 4
        assert cfg.rx.M == 8
        assert cfg.tx.L == 8
        assert cfg.tx.Np == 12

    def test_from_empty_dict(self):
        cfg = JesdConfig.from_dict({})
        assert cfg.rx.F == 1
        assert cfg.tx.F == 1


# ---------------------------------------------------------------------------
# ClockConfig
# ---------------------------------------------------------------------------


class TestClockConfig:
    def test_from_dict_ignores_unknown_keys(self):
        d = {
            "rx_device_clk_label": "hmc7044",
            "rx_device_clk_index": 8,
            "unknown_key": 42,
        }
        cfg = ClockConfig.from_dict(d)
        assert cfg.rx_device_clk_label == "hmc7044"
        assert cfg.rx_device_clk_index == 8


# ---------------------------------------------------------------------------
# FMCDAQ2BoardConfig
# ---------------------------------------------------------------------------


class TestFMCDAQ2BoardConfig:
    def test_defaults_match_node_builder(self):
        """Verify defaults match the hardcoded values in _build_fmcdaq2_cfg."""
        cfg = FMCDAQ2BoardConfig()
        assert cfg.spi_bus == "spi0"
        assert cfg.clock_cs == 0
        assert cfg.adc_cs == 2
        assert cfg.dac_cs == 1
        assert cfg.clock_vcxo_hz == 125_000_000
        assert cfg.adc_dma_label == "axi_ad9680_dma"
        assert cfg.dac_dma_label == "axi_ad9144_dma"
        assert cfg.adc_core_label == "axi_ad9680_core"
        assert cfg.dac_core_label == "axi_ad9144_core"
        assert cfg.adc_xcvr_label == "axi_ad9680_adxcvr"
        assert cfg.dac_xcvr_label == "axi_ad9144_adxcvr"
        assert cfg.gpio_controller == "gpio0"
        assert cfg.adc_device_clk_idx == 13
        assert cfg.adc_sysref_clk_idx == 5
        assert cfg.dac_device_clk_idx == 1

    def test_from_dict_partial_override(self):
        cfg = FMCDAQ2BoardConfig.from_dict({"spi_bus": "spi1", "clock_cs": 2})
        assert cfg.spi_bus == "spi1"
        assert cfg.clock_cs == 2
        assert cfg.adc_cs == 2  # default kept

    def test_from_dict_ignores_unknown_keys(self):
        cfg = FMCDAQ2BoardConfig.from_dict({"spi_bus": "spi0", "bogus": 99})
        assert cfg.spi_bus == "spi0"

    def test_negative_chip_select_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            FMCDAQ2BoardConfig(clock_cs=-1)

    def test_empty_spi_bus_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            FMCDAQ2BoardConfig(spi_bus="")

    def test_bool_not_accepted_as_int(self):
        with pytest.raises(ValueError, match="expected integer"):
            FMCDAQ2BoardConfig(clock_cs=True)


# ---------------------------------------------------------------------------
# AD9084BoardConfig
# ---------------------------------------------------------------------------


class TestAD9084BoardConfig:
    def test_defaults(self):
        cfg = AD9084BoardConfig()
        assert cfg.converter_spi == "axi_spi_2"
        assert cfg.converter_cs == 0
        assert cfg.clock_spi == "axi_spi"
        assert cfg.hmc7044_cs == 1
        assert cfg.vcxo_hz == 125_000_000
        assert cfg.pll2_output_hz == 2_500_000_000
        assert cfg.rx_sys_clk_select == 3
        assert cfg.side_b_separate_tpl is True

    def test_from_dict_with_vcu118_overrides(self):
        d = {
            "converter_spi": "axi_spi_2",
            "converter_cs": 0,
            "hmc7044_cs": 1,
            "adf4382_cs": 0,
            "firmware_name": "204C_M4_L8_NP16_1p25_4x4.bin",
            "reset_gpio": 62,
            "rx_a_link_id": 4,
            "rx_b_link_id": 6,
            "tx_a_link_id": 0,
            "tx_b_link_id": 2,
        }
        cfg = AD9084BoardConfig.from_dict(d)
        assert cfg.adf4382_cs == 0
        assert cfg.firmware_name == "204C_M4_L8_NP16_1p25_4x4.bin"
        assert cfg.reset_gpio == 62
        assert cfg.rx_a_link_id == 4


# ---------------------------------------------------------------------------
# AD9172BoardConfig
# ---------------------------------------------------------------------------


class TestAD9172BoardConfig:
    def test_defaults_match_node_builder(self):
        cfg = AD9172BoardConfig()
        assert cfg.hmc7044_ref_clk_hz == 122_880_000
        assert cfg.hmc7044_vcxo_hz == 122_880_000
        assert cfg.ad9172_dac_rate_khz == 11_796_480
        assert cfg.ad9172_jesd_link_mode == 4


# ---------------------------------------------------------------------------
# PipelineConfig
# ---------------------------------------------------------------------------


class TestPipelineConfig:
    def test_from_dict_auto_detects_fmcdaq2(self):
        d = {
            "jesd": {"rx": {"F": 1}, "tx": {"F": 1}},
            "clock": {"rx_device_clk_label": "clk0_ad9523"},
            "fmcdaq2_board": {"spi_bus": "spi0", "clock_cs": 0},
        }
        cfg = PipelineConfig.from_dict(d)
        assert cfg.fmcdaq2_board is not None
        assert cfg.fmcdaq2_board.spi_bus == "spi0"
        assert cfg.ad9084_board is None

    def test_from_dict_auto_detects_ad9084(self):
        d = {
            "jesd": {"rx": {"F": 6}, "tx": {"F": 6}},
            "ad9084_board": {"converter_spi": "axi_spi_2"},
        }
        cfg = PipelineConfig.from_dict(d)
        assert cfg.ad9084_board is not None
        assert cfg.ad9084_board.converter_spi == "axi_spi_2"
        assert cfg.fmcdaq2_board is None

    def test_from_dict_with_no_board_section(self):
        d = {"jesd": {"rx": {"F": 4}, "tx": {"F": 4}}}
        cfg = PipelineConfig.from_dict(d)
        assert cfg.fmcdaq2_board is None
        assert cfg.ad9084_board is None
        assert cfg.jesd.rx.F == 4

    def test_from_dict_preserves_extra_keys(self):
        d = {"jesd": {}, "custom_key": "hello"}
        cfg = PipelineConfig.from_dict(d)
        assert cfg._extra["custom_key"] == "hello"

    def test_from_dict_preserves_fpga_solver_output(self):
        d = {
            "jesd": {},
            "fpga_adc": {"sys_clk_select": "XCVR_CPLL"},
            "fpga_dac": {"sys_clk_select": "XCVR_QPLL"},
        }
        cfg = PipelineConfig.from_dict(d)
        assert cfg.fpga_adc["sys_clk_select"] == "XCVR_CPLL"

    def test_round_trip_ad9081_fixture(self):
        """Verify the existing ad9081_config.json fixture round-trips."""
        fixture = FIXTURE_DIR / "ad9081_config.json"
        if not fixture.exists():
            pytest.skip("ad9081_config.json fixture not found")
        raw = json.loads(fixture.read_text())
        cfg = PipelineConfig.from_dict(raw)
        assert cfg.jesd.rx.F == raw["jesd"]["rx"]["F"]
        assert cfg.jesd.tx.M == raw["jesd"]["tx"]["M"]


# ---------------------------------------------------------------------------
# Profile compatibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("profile_name", ProfileManager().list_profiles())
def test_builtin_profile_parses_to_pipeline_config(profile_name):
    """Every built-in profile round-trips through PipelineConfig.from_dict()."""
    profile = ProfileManager().load(profile_name)
    defaults = profile.get("defaults", {})
    cfg = PipelineConfig.from_dict(defaults)
    # Basic sanity: JESD config was parsed
    assert isinstance(cfg.jesd, JesdConfig)
    assert isinstance(cfg.clock, ClockConfig)
