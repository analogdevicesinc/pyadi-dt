"""Unit tests for ADRV9364-Z7020 SOM board class.

Tests cover:
- Board initialization
- Platform configuration
- BoardModel generation (AD9364 defaults)
- DTS rendering
"""

import pytest

from adidt.boards.adrv9364_z7020 import adrv9364_z7020
from adidt.model.board_model import BoardModel


class TestBoardInitialization:
    def test_bob_initialization(self):
        board = adrv9364_z7020(platform="bob")
        assert board.platform == "bob"
        assert board.platform_config["arch"] == "arm"
        assert board.platform_config["spi_bus"] == "spi0"

    def test_default_platform_is_bob(self):
        board = adrv9364_z7020()
        assert board.platform == "bob"

    def test_unsupported_platform_rejection(self):
        with pytest.raises(ValueError, match="not supported"):
            adrv9364_z7020(platform="zcu102")

    def test_platform_config_completeness(self):
        required_keys = ["base_dts_include", "arch", "spi_bus", "output_dir"]
        for platform, config in adrv9364_z7020.PLATFORM_CONFIGS.items():
            for key in required_keys:
                assert key in config, f"Platform {platform} missing key: {key}"

    def test_use_plugin_mode_disabled(self):
        board = adrv9364_z7020(platform="bob")
        assert board.use_plugin_mode is False


class TestBoardModel:
    def test_to_board_model_defaults(self):
        board = adrv9364_z7020(platform="bob")
        model = board.to_board_model({})
        assert isinstance(model, BoardModel)
        assert model.name == "adrv9364_z7020_bob"
        assert model.platform == "bob"
        assert len(model.components) == 1

    def test_component_is_ad9364(self):
        board = adrv9364_z7020(platform="bob")
        model = board.to_board_model({})
        comp = model.components[0]
        assert comp.role == "transceiver"
        assert comp.part == "ad9364"
        assert comp.config["compatible"] == "adi,ad9364"
        assert comp.config["label"] == "ad9364_phy"

    def test_custom_compatible(self):
        board = adrv9364_z7020(platform="bob")
        model = board.to_board_model({"compatible": "adi,ad9361"})
        assert model.components[0].config["compatible"] == "adi,ad9361"

    def test_no_jesd_links(self):
        board = adrv9364_z7020(platform="bob")
        model = board.to_board_model({})
        assert model.jesd_links == []

    def test_no_fpga_config(self):
        board = adrv9364_z7020(platform="bob")
        model = board.to_board_model({})
        assert model.fpga_config is None


class TestDTSRendering:
    def test_gen_dt_from_model(self, tmp_path):
        board = adrv9364_z7020(platform="bob")
        board.output_filename = str(tmp_path / "adrv9364_z7020_bob.dts")
        model = board.to_board_model({})
        board.gen_dt_from_model(model)
        content = (tmp_path / "adrv9364_z7020_bob.dts").read_text()
        assert "ad9364" in content.lower()
        assert "SPDX-License-Identifier" in content

    def test_gen_dt_from_config(self, tmp_path):
        board = adrv9364_z7020(platform="bob")
        board.output_filename = str(tmp_path / "test.dts")
        board.gen_dt_from_config({})
        content = (tmp_path / "test.dts").read_text()
        assert "ad9364" in content.lower()

    def test_standalone_dts_no_plugin(self, tmp_path):
        board = adrv9364_z7020(platform="bob")
        board.output_filename = str(tmp_path / "test.dts")
        model = board.to_board_model({})
        board.gen_dt_from_model(model)
        content = (tmp_path / "test.dts").read_text()
        assert "/plugin/;" not in content
