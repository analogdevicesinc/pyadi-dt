import pytest
from adidt.boards import get_board, list_boards


class TestBoardRegistry:
    def test_list_boards_returns_all(self):
        boards = list_boards()
        expected = {
            "daq2",
            "ad9081_fmc",
            "ad9082_fmc",
            "ad9083_fmc",
            "ad9084_fmc",
            "adrv9009_fmc",
            "adrv9008_fmc",
            "adrv9025_fmc",
            "adrv937x_fmc",
            "fmcomms_fmc",
            "adrv9361_z7035",
            "adrv9364_z7020",
            "rpi",
        }
        assert set(boards) == expected

    def test_get_board_returns_instance(self):
        board = get_board("daq2", platform="zcu102")
        assert board.platform == "zcu102"

    def test_get_board_variant(self):
        board = get_board("ad9082_fmc", platform="zcu102")
        assert board.platform == "zcu102"
        assert hasattr(board, "to_board_model")

    def test_get_board_unknown_raises(self):
        with pytest.raises(KeyError, match="not_a_board"):
            get_board("not_a_board")

    def test_variant_has_parent_methods(self):
        board = get_board("adrv9025_fmc", platform="zcu102")
        assert hasattr(board, "to_board_model")
        assert hasattr(board, "map_clocks_to_board_layout")

    def test_variant_inherits_fpga_link_keys(self):
        board = get_board("ad9082_fmc", platform="zcu102")
        assert board.FPGA_LINK_KEYS == ["fpga_adc", "fpga_dac"]

    def test_adrv9009_variant_inherits_fpga_config(self):
        board = get_board("adrv9008_fmc", platform="zcu102")
        assert board.FPGA_LINK_KEYS == ["fpga_rx", "fpga_tx", "fpga_orx"]
        assert board.FPGA_DEFAULT_OUT_CLK == "XCVR_REFCLK"

    def test_variant_importable_from_boards(self):
        from adidt.boards import ad9082_fmc, adrv9008_fmc

        assert ad9082_fmc is not None
        assert adrv9008_fmc is not None
