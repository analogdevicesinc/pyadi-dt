"""Unit tests for ADRV9009-ZU11EG SOM board class.

Tests cover:
- Board initialization and attribute defaults
- JESD struct mapping
- Clock-to-board layout mapping
- Profile parsing
- Integer fixup helpers
"""

import pytest
import numpy as np

from adidt.boards.adrv9009_zu11eg import adrv9009_zu11eg


class TestBoardInitialization:
    """Test board class attributes and defaults."""

    def test_class_attributes(self):
        board = adrv9009_zu11eg()
        assert board.clock == "HMC7044"
        assert board.adc == "adrv9009_rx"
        assert board.dac == "adrv9009_tx"

    def test_template_filename(self):
        board = adrv9009_zu11eg()
        assert board.template_filename == "adrv9009_zu11eg.dts"

    def test_output_filename(self):
        board = adrv9009_zu11eg()
        assert board.output_filename == "adrv9009_zu11eg_out.dts"

    def test_profile_initially_none(self):
        board = adrv9009_zu11eg()
        assert board.profile is None


class TestMakeInts:
    """Test the make_ints helper."""

    def test_converts_whole_floats(self):
        board = adrv9009_zu11eg()
        cfg = {"a": 1.0, "b": 2.0, "c": "untouched"}
        result = board.make_ints(cfg, ["a", "b"])
        assert result["a"] == 1
        assert isinstance(result["a"], int)
        assert result["b"] == 2
        assert isinstance(result["b"], int)

    def test_preserves_fractional_floats(self):
        board = adrv9009_zu11eg()
        cfg = {"a": 1.5}
        result = board.make_ints(cfg, ["a"])
        assert result["a"] == 1.5
        assert isinstance(result["a"], float)

    def test_preserves_already_int(self):
        board = adrv9009_zu11eg()
        cfg = {"a": 42}
        # make_ints only converts floats, ints pass through as-is
        result = board.make_ints(cfg, ["a"])
        assert result["a"] == 42


class TestMapJesdStructs:
    """Test JESD struct mapping."""

    @pytest.fixture
    def sample_cfg(self):
        return {
            "converter": {
                "sample_clock": 245760000,
            },
            "jesd_adc": {
                "jesd_class": "jesd204b",
                "converter_clock": 245760000.0,
                "sample_clock": 245760000.0,
                "L": 4,
                "M": 4,
                "F": 4,
                "S": 1,
                "K": 32,
                "Np": 16,
            },
            "jesd_dac": {
                "jesd_class": "jesd204b",
                "converter_clock": 245760000.0,
                "sample_clock": 245760000.0,
                "L": 4,
                "M": 4,
                "F": 4,
                "S": 1,
                "K": 32,
                "Np": 16,
            },
            "datapath_adc": {"decimation": 1},
            "datapath_dac": {"interpolation": 1},
        }

    def test_returns_adc_and_dac(self, sample_cfg):
        board = adrv9009_zu11eg()
        adc, dac = board.map_jesd_structs(sample_cfg)
        assert "jesd" in adc
        assert "jesd" in dac

    def test_jesd_class_mapped_to_int(self, sample_cfg):
        board = adrv9009_zu11eg()
        adc, dac = board.map_jesd_structs(sample_cfg)
        assert adc["jesd"]["jesd_class_int"] == 1  # jesd204b
        assert dac["jesd"]["jesd_class_int"] == 1

    def test_converter_clock_made_int(self, sample_cfg):
        board = adrv9009_zu11eg()
        adc, dac = board.map_jesd_structs(sample_cfg)
        assert isinstance(adc["jesd"]["converter_clock"], int)
        assert isinstance(dac["jesd"]["converter_clock"], int)

    def test_datapath_assigned(self, sample_cfg):
        board = adrv9009_zu11eg()
        adc, dac = board.map_jesd_structs(sample_cfg)
        assert adc["datapath"] == {"decimation": 1}
        assert dac["datapath"] == {"interpolation": 1}


class TestMapClocksToBoard:
    """Test clock-to-board layout mapping."""

    @pytest.fixture
    def full_cfg(self):
        return {
            "clock": {
                "vco": 2400000000.0,
                "vcxo": 100000000.0,
                "output_clocks": {
                    "AD9081_ref_clk": {"divider": 60},
                    "adc_sysref": {"divider": 3840},
                    "dac_sysref": {"divider": 3840},
                    "adc_fpga_ref_clk": {"divider": 60},
                    "dac_fpga_ref_clk": {"divider": 60},
                },
            },
            "converter": {"sample_clock": 245760000},
            "jesd_adc": {
                "jesd_class": "jesd204b",
                "converter_clock": 245760000.0,
                "sample_clock": 245760000.0,
                "L": 4,
                "M": 4,
                "F": 4,
                "S": 1,
                "K": 32,
                "Np": 16,
            },
            "jesd_dac": {
                "jesd_class": "jesd204b",
                "converter_clock": 245760000.0,
                "sample_clock": 245760000.0,
                "L": 4,
                "M": 4,
                "F": 4,
                "S": 1,
                "K": 32,
                "Np": 16,
            },
            "datapath_adc": {"decimation": 1},
            "datapath_dac": {"interpolation": 1},
            "fpga_adc": {"sys_clk_select": "XCVR_CPLL"},
            "fpga_dac": {"sys_clk_select": "XCVR_QPLL"},
        }

    def test_returns_four_tuple(self, full_cfg):
        board = adrv9009_zu11eg()
        result = board.map_clocks_to_board_layout(full_cfg)
        assert len(result) == 4
        ccfg, adc, dac, fpga = result

    def test_clock_map_has_expected_keys(self, full_cfg):
        board = adrv9009_zu11eg()
        ccfg, adc, dac, fpga = board.map_clocks_to_board_layout(full_cfg)
        clock_map = ccfg["map"]
        expected_keys = [
            "DEV_REFCLK",
            "DEV_SYSREF",
            "FPGA_SYSREF",
            "CORE_CLK_RX",
            "CORE_CLK_RX_ALT",
            "FPGA_REFCLK1",
            "CORE_CLK_TX",
            "FPGA_REFCLK2",
        ]
        for key in expected_keys:
            assert key in clock_map, f"Missing clock map key: {key}"

    def test_clock_map_source_ports(self, full_cfg):
        board = adrv9009_zu11eg()
        ccfg, _, _, _ = board.map_clocks_to_board_layout(full_cfg)
        clock_map = ccfg["map"]
        assert clock_map["DEV_REFCLK"]["source_port"] == 2
        assert clock_map["DEV_SYSREF"]["source_port"] == 3
        assert clock_map["FPGA_SYSREF"]["source_port"] == 13
        assert clock_map["CORE_CLK_RX"]["source_port"] == 0
        assert clock_map["CORE_CLK_TX"]["source_port"] == 6

    def test_vco_vcxo_int_fixup(self, full_cfg):
        board = adrv9009_zu11eg()
        ccfg, _, _, _ = board.map_clocks_to_board_layout(full_cfg)
        assert isinstance(ccfg["clock"]["vco"], int)
        assert isinstance(ccfg["clock"]["vcxo"], int)

    def test_fpga_config_passthrough(self, full_cfg):
        board = adrv9009_zu11eg()
        _, _, _, fpga = board.map_clocks_to_board_layout(full_cfg)
        assert fpga["fpga_adc"]["sys_clk_select"] == "XCVR_CPLL"
        assert fpga["fpga_dac"]["sys_clk_select"] == "XCVR_QPLL"

    def test_sysref_divider_is_max(self, full_cfg):
        """DEV_SYSREF divider should be max of adc and dac sysref dividers."""
        full_cfg["clock"]["output_clocks"]["adc_sysref"]["divider"] = 1920
        full_cfg["clock"]["output_clocks"]["dac_sysref"]["divider"] = 3840
        board = adrv9009_zu11eg()
        ccfg, _, _, _ = board.map_clocks_to_board_layout(full_cfg)
        assert ccfg["map"]["DEV_SYSREF"]["divider"] == 3840


class TestParseProfile:
    """Test profile parsing."""

    def test_missing_profile_raises(self, tmp_path):
        board = adrv9009_zu11eg()
        with pytest.raises(Exception, match="not found"):
            board.parse_profile(str(tmp_path / "nonexistent.txt"))

    def test_profile_parsing(self, tmp_path):
        """Test that parse_profile delegates to adrv9009.parse_profile."""
        # We just verify the method exists and handles the file-not-found case.
        # Actual profile parsing is tested via the adrv9009 parts tests.
        board = adrv9009_zu11eg()
        assert hasattr(board, "parse_profile")


class TestJesdSubclassMapping:
    """Test JESD subclass name-to-integer mapping (inherited from layout)."""

    def test_jesd204a(self):
        board = adrv9009_zu11eg()
        assert board.map_jesd_subclass("jesd204a") == 0

    def test_jesd204b(self):
        board = adrv9009_zu11eg()
        assert board.map_jesd_subclass("jesd204b") == 1

    def test_jesd204c(self):
        board = adrv9009_zu11eg()
        assert board.map_jesd_subclass("jesd204c") == 2

    def test_invalid_subclass_raises(self):
        board = adrv9009_zu11eg()
        with pytest.raises(Exception, match="not supported"):
            board.map_jesd_subclass("jesd204z")
