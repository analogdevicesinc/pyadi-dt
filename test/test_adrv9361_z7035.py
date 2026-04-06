"""Unit tests for ADRV9361-Z7035 SOM board class.

Tests cover:
- Board initialization for each carrier variant (bob, fmc)
- Platform configuration completeness
- Unsupported platform rejection
- BoardModel generation
- DTS rendering end-to-end
"""

import pytest

from adidt.boards.adrv9361_z7035 import adrv9361_z7035
from adidt.model.board_model import BoardModel
from adidt.model.renderer import BoardModelRenderer


class TestBoardInitialization:
    """Test board initialization and platform support."""

    def test_bob_initialization(self):
        board = adrv9361_z7035(platform="bob")
        assert board.platform == "bob"
        assert board.platform_config["arch"] == "arm"
        assert board.platform_config["spi_bus"] == "spi0"

    def test_fmc_initialization(self):
        board = adrv9361_z7035(platform="fmc")
        assert board.platform == "fmc"
        assert board.platform_config["arch"] == "arm"

    def test_default_platform_is_bob(self):
        board = adrv9361_z7035()
        assert board.platform == "bob"

    def test_unsupported_platform_rejection(self):
        with pytest.raises(ValueError, match="not supported"):
            adrv9361_z7035(platform="zcu102")

    def test_platform_config_completeness(self):
        required_keys = ["base_dts_include", "arch", "spi_bus", "output_dir"]
        for platform, config in adrv9361_z7035.PLATFORM_CONFIGS.items():
            for key in required_keys:
                assert key in config, f"Platform {platform} missing key: {key}"

    def test_use_plugin_mode_disabled(self):
        board = adrv9361_z7035(platform="bob")
        assert board.use_plugin_mode is False


class TestBoardModel:
    """Test BoardModel generation."""

    def test_to_board_model_defaults(self):
        board = adrv9361_z7035(platform="bob")
        model = board.to_board_model({})
        assert isinstance(model, BoardModel)
        assert model.name == "adrv9361_z7035_bob"
        assert model.platform == "bob"
        assert len(model.components) == 1

    def test_to_board_model_fmc(self):
        board = adrv9361_z7035(platform="fmc")
        model = board.to_board_model({})
        assert model.name == "adrv9361_z7035_fmc"

    def test_component_is_ad9361(self):
        board = adrv9361_z7035(platform="bob")
        model = board.to_board_model({})
        comp = model.components[0]
        assert comp.role == "transceiver"
        assert comp.part == "ad9361"
        assert comp.spi_bus == "spi0"
        assert comp.spi_cs == 0

    def test_custom_compatible(self):
        board = adrv9361_z7035(platform="bob")
        model = board.to_board_model({"compatible": "adi,ad9364"})
        assert model.components[0].config["compatible"] == "adi,ad9364"

    def test_custom_spi_cs(self):
        board = adrv9361_z7035(platform="bob")
        model = board.to_board_model({"cs": 1})
        assert model.components[0].spi_cs == 1

    def test_no_jesd_links(self):
        board = adrv9361_z7035(platform="bob")
        model = board.to_board_model({})
        assert model.jesd_links == []

    def test_no_fpga_config(self):
        board = adrv9361_z7035(platform="bob")
        model = board.to_board_model({})
        assert model.fpga_config is None


class TestDTSRendering:
    """Test DTS generation end-to-end."""

    @pytest.mark.parametrize("platform", ["bob", "fmc"])
    def test_gen_dt_from_model(self, platform, tmp_path):
        board = adrv9361_z7035(platform=platform)
        board.output_filename = str(tmp_path / f"adrv9361_z7035_{platform}.dts")

        model = board.to_board_model({})
        result = board.gen_dt_from_model(model)

        output = tmp_path / f"adrv9361_z7035_{platform}.dts"
        assert output.exists()
        content = output.read_text()
        assert "ad9361" in content.lower()
        assert "SPDX-License-Identifier" in content

    def test_gen_dt_from_config(self, tmp_path):
        board = adrv9361_z7035(platform="bob")
        board.output_filename = str(tmp_path / "adrv9361_z7035.dts")

        result = board.gen_dt_from_config({})
        content = (tmp_path / "adrv9361_z7035.dts").read_text()
        assert "ad9361" in content.lower()

    def test_standalone_dts_no_plugin(self, tmp_path):
        board = adrv9361_z7035(platform="bob")
        board.output_filename = str(tmp_path / "test.dts")

        model = board.to_board_model({})
        board.gen_dt_from_model(model)

        content = (tmp_path / "test.dts").read_text()
        assert "/plugin/;" not in content
