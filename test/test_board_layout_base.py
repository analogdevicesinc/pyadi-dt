"""Tests for shared layout base class methods.

Validates __init__, kernel path resolution/validation,
get_dtc_include_paths, make_ints, and output filename handling
that are shared across all major board classes.
"""

import os
import pytest


class FakeBoard:
    """Minimal board subclass for testing layout base methods.

    Imports layout at usage time so tests can see both before/after
    states of the base class.
    """

    pass


def _make_fake_board_class():
    """Build a FakeBoard class inheriting from layout with PLATFORM_CONFIGS."""
    from adidt.boards.layout import layout

    class FakeBoard(layout):
        DEFAULT_KERNEL_PATH = "./linux"
        PLATFORM_CONFIGS = {
            "zcu102": {
                "template_filename": "fake_zcu102.tmpl",
                "base_dts_file": "arch/arm64/boot/dts/xilinx/zynqmp-zcu102.dts",
                "base_dts_include": "zynqmp-zcu102.dts",
                "arch": "arm64",
                "output_dir": "generated_dts",
            },
            "zc706": {
                "template_filename": "fake_zc706.tmpl",
                "base_dts_file": "arch/arm/boot/dts/xilinx/zynq-zc706.dts",
                "base_dts_include": "zynq-zc706.dts",
                "arch": "arm",
                "output_dir": "generated_dts",
            },
            "vcu118": {
                "template_filename": "fake_vcu118.tmpl",
                "base_dts_file": None,
                "base_dts_include": "vcu118_base.dts",
                "arch": "microblaze",
                "output_dir": None,
            },
        }

    return FakeBoard


# ---- Platform validation ----


def test_unsupported_platform_raises():
    Cls = _make_fake_board_class()
    with pytest.raises(ValueError, match="not supported"):
        Cls(platform="nonexistent")


def test_platform_and_config_stored():
    Cls = _make_fake_board_class()
    board = Cls(platform="zcu102")
    assert board.platform == "zcu102"
    assert board.platform_config is Cls.PLATFORM_CONFIGS["zcu102"]


# ---- Template / output filename ----


def test_template_filename_from_config():
    Cls = _make_fake_board_class()
    board = Cls(platform="zcu102")
    assert board.template_filename == "fake_zcu102.tmpl"


def test_output_filename_includes_class_name_and_platform():
    Cls = _make_fake_board_class()
    board = Cls(platform="zcu102")
    assert board.output_filename == os.path.join("generated_dts", "FakeBoard_zcu102.dts")


def test_output_dir_none_gives_bare_filename():
    """When output_dir is None (e.g. VCU118), output_filename is just the base name."""
    Cls = _make_fake_board_class()
    board = Cls(platform="vcu118")
    assert board.output_filename == "FakeBoard_vcu118.dts"
    assert os.sep not in board.output_filename or board.output_filename == "FakeBoard_vcu118.dts"


# ---- Kernel path 3-tier resolution ----


def test_kernel_path_explicit(tmp_path):
    """Explicit kernel_path argument has highest priority."""
    kernel = tmp_path / "linux"
    kernel.mkdir()
    # Create required base DTS file
    dts_dir = kernel / "arch" / "arm64" / "boot" / "dts" / "xilinx"
    dts_dir.mkdir(parents=True)
    (dts_dir / "zynqmp-zcu102.dts").write_text("/* stub */")

    Cls = _make_fake_board_class()
    board = Cls(platform="zcu102", kernel_path=str(kernel))
    assert board.kernel_path == os.path.abspath(str(kernel))


def test_kernel_path_from_env(tmp_path, monkeypatch):
    """LINUX_KERNEL_PATH env var is used when no explicit arg."""
    kernel = tmp_path / "envlinux"
    kernel.mkdir()
    dts_dir = kernel / "arch" / "arm64" / "boot" / "dts" / "xilinx"
    dts_dir.mkdir(parents=True)
    (dts_dir / "zynqmp-zcu102.dts").write_text("/* stub */")

    monkeypatch.setenv("LINUX_KERNEL_PATH", str(kernel))
    Cls = _make_fake_board_class()
    board = Cls(platform="zcu102")
    assert board.kernel_path == os.path.abspath(str(kernel))


def test_kernel_path_default_fallback(monkeypatch):
    """Falls back to DEFAULT_KERNEL_PATH when no arg or env."""
    monkeypatch.delenv("LINUX_KERNEL_PATH", raising=False)
    Cls = _make_fake_board_class()
    board = Cls(platform="zcu102")
    assert board.kernel_path == os.path.abspath("./linux")


# ---- Kernel path validation ----


def test_explicit_kernel_path_missing_raises():
    Cls = _make_fake_board_class()
    with pytest.raises(FileNotFoundError, match="Kernel source path not found"):
        Cls(platform="zcu102", kernel_path="/nonexistent/path/linux")


def test_explicit_kernel_path_missing_base_dts_raises(tmp_path):
    kernel = tmp_path / "linux"
    kernel.mkdir()
    Cls = _make_fake_board_class()
    with pytest.raises(FileNotFoundError, match="Base DTS file not found"):
        Cls(platform="zcu102", kernel_path=str(kernel))


def test_base_dts_file_none_skips_dts_validation(tmp_path):
    """When base_dts_file is None (like VCU118), skip DTS validation even with valid kernel."""
    kernel = tmp_path / "linux"
    kernel.mkdir()
    Cls = _make_fake_board_class()
    # Should NOT raise even though no DTS file exists
    board = Cls(platform="vcu118", kernel_path=str(kernel))
    assert board.kernel_path == os.path.abspath(str(kernel))


# ---- get_dtc_include_paths ----


def test_get_dtc_include_paths(tmp_path):
    kernel = tmp_path / "linux"
    kernel.mkdir()
    dts_dir = kernel / "arch" / "arm64" / "boot" / "dts" / "xilinx"
    dts_dir.mkdir(parents=True)
    (dts_dir / "zynqmp-zcu102.dts").write_text("/* stub */")

    Cls = _make_fake_board_class()
    board = Cls(platform="zcu102", kernel_path=str(kernel))
    paths = board.get_dtc_include_paths()
    kp = os.path.abspath(str(kernel))
    assert paths == [
        os.path.join(kp, "arch/arm64/boot/dts"),
        os.path.join(kp, "arch/arm64/boot/dts/xilinx"),
        os.path.join(kp, "include"),
    ]


# ---- make_ints ----


def test_make_ints_converts_whole_floats():
    from adidt.boards.layout import layout

    result = layout.make_ints({"a": 3.0, "b": 2.5, "c": 10.0}, ["a", "b", "c"])
    assert result["a"] == 3 and isinstance(result["a"], int)
    assert result["b"] == 2.5 and isinstance(result["b"], float)
    assert result["c"] == 10 and isinstance(result["c"], int)


def test_make_ints_skips_missing_keys():
    from adidt.boards.layout import layout

    result = layout.make_ints({"a": 3.0}, ["a", "missing"])
    assert result["a"] == 3 and isinstance(result["a"], int)


def test_make_ints_skips_non_float():
    from adidt.boards.layout import layout

    result = layout.make_ints({"a": 3, "b": "hello"}, ["a", "b"])
    assert result["a"] == 3
    assert result["b"] == "hello"


# ---- Boards without kernel path (no "arch" key) should not break ----


def test_no_arch_key_skips_kernel_path():
    """Platforms without 'arch' in config should skip kernel path entirely."""
    from adidt.boards.layout import layout

    class NoKernelBoard(layout):
        PLATFORM_CONFIGS = {
            "simple": {
                "template_filename": "simple.tmpl",
                "base_dts_include": "simple.dts",
                "output_dir": "generated_dts",
            },
        }

    board = NoKernelBoard(platform="simple")
    assert board.platform == "simple"
    assert not hasattr(board, "kernel_path")


# ---- validate_and_default_fpga_config (data-driven) ----


def _make_fpga_board_class(link_keys, default_out_clk="XCVR_REFCLK_DIV2"):
    """Build a board class with FPGA_LINK_KEYS for FPGA config testing."""
    from adidt.boards.layout import layout

    class FpgaBoard(layout):
        FPGA_LINK_KEYS = link_keys
        FPGA_DEFAULT_OUT_CLK = default_out_clk
        PLATFORM_CONFIGS = {
            "test_platform": {
                "template_filename": "test.tmpl",
                "base_dts_include": "test.dts",
                "output_dir": None,
                "default_fpga_adc_pll": "XCVR_QPLL",
                "default_fpga_dac_pll": "XCVR_CPLL",
                "default_fpga_rx_pll": "XCVR_CPLL",
                "default_fpga_tx_pll": "XCVR_QPLL",
                "default_fpga_orx_pll": "XCVR_CPLL",
            },
        }

    return FpgaBoard


def test_fpga_config_missing_keys_created_with_defaults():
    """Missing fpga keys get created as empty dicts with defaults applied."""
    Cls = _make_fpga_board_class(["fpga_adc", "fpga_dac"])
    board = Cls(platform="test_platform")
    cfg = {}
    result = board.validate_and_default_fpga_config(cfg)

    assert "fpga_adc" in result
    assert "fpga_dac" in result
    assert result["fpga_adc"]["sys_clk_select"] == "XCVR_QPLL"
    assert result["fpga_dac"]["sys_clk_select"] == "XCVR_CPLL"
    assert result["fpga_adc"]["out_clk_select"] == "XCVR_REFCLK_DIV2"
    assert result["fpga_dac"]["out_clk_select"] == "XCVR_REFCLK_DIV2"


def test_fpga_config_existing_values_preserved():
    """Existing values are preserved (not overwritten)."""
    Cls = _make_fpga_board_class(["fpga_adc", "fpga_dac"])
    board = Cls(platform="test_platform")
    cfg = {
        "fpga_adc": {"sys_clk_select": "XCVR_QPLL1", "out_clk_select": "XCVR_REFCLK"},
        "fpga_dac": {"sys_clk_select": "XCVR_CPLL"},
    }
    result = board.validate_and_default_fpga_config(cfg)

    assert result["fpga_adc"]["sys_clk_select"] == "XCVR_QPLL1"
    assert result["fpga_adc"]["out_clk_select"] == "XCVR_REFCLK"
    assert result["fpga_dac"]["sys_clk_select"] == "XCVR_CPLL"
    # out_clk_select was missing for dac, so default applied
    assert result["fpga_dac"]["out_clk_select"] == "XCVR_REFCLK_DIV2"


def test_fpga_config_adrv9009_style_keys():
    """Works with adrv9009-style keys (fpga_rx/tx/orx)."""
    Cls = _make_fpga_board_class(
        ["fpga_rx", "fpga_tx", "fpga_orx"], default_out_clk="XCVR_REFCLK"
    )
    board = Cls(platform="test_platform")
    cfg = {}
    result = board.validate_and_default_fpga_config(cfg)

    assert result["fpga_rx"]["sys_clk_select"] == "XCVR_CPLL"
    assert result["fpga_tx"]["sys_clk_select"] == "XCVR_QPLL"
    assert result["fpga_orx"]["sys_clk_select"] == "XCVR_CPLL"
    assert result["fpga_rx"]["out_clk_select"] == "XCVR_REFCLK"
    assert result["fpga_tx"]["out_clk_select"] == "XCVR_REFCLK"
    assert result["fpga_orx"]["out_clk_select"] == "XCVR_REFCLK"


def test_fpga_config_custom_default_out_clk():
    """Works with custom FPGA_DEFAULT_OUT_CLK."""
    Cls = _make_fpga_board_class(["fpga_adc"], default_out_clk="XCVR_REFCLK")
    board = Cls(platform="test_platform")
    cfg = {}
    result = board.validate_and_default_fpga_config(cfg)

    assert result["fpga_adc"]["out_clk_select"] == "XCVR_REFCLK"


def test_fpga_config_empty_link_keys_returns_unchanged():
    """Empty FPGA_LINK_KEYS returns cfg unchanged (base class default)."""
    Cls = _make_fpga_board_class([])
    board = Cls(platform="test_platform")
    cfg = {"some_key": "some_value"}
    result = board.validate_and_default_fpga_config(cfg)

    assert result == {"some_key": "some_value"}


# ---- AD936x shared to_board_model via class-level constants ----


class TestAD936xBoardModel:
    def test_fmcomms_builds_ad9361_component(self):
        from adidt.boards.fmcomms_fmc import fmcomms_fmc

        board = fmcomms_fmc(platform="zed")
        model = board.to_board_model({})
        assert len(model.components) == 1
        assert model.components[0].config["compatible"] == "adi,ad9361"
        assert model.components[0].part == "ad9361"

    def test_adrv9361_inherits_ad9361(self):
        from adidt.boards.adrv9361_z7035 import adrv9361_z7035

        board = adrv9361_z7035(platform="bob")
        model = board.to_board_model({})
        assert model.components[0].config["compatible"] == "adi,ad9361"

    def test_adrv9364_uses_ad9364(self):
        from adidt.boards.adrv9364_z7020 import adrv9364_z7020

        board = adrv9364_z7020(platform="bob")
        model = board.to_board_model({})
        assert model.components[0].config["compatible"] == "adi,ad9364"
        assert model.components[0].config["label"] == "ad9364_phy"
        assert model.components[0].part == "ad9364"

    def test_board_name_uses_class_name(self):
        from adidt.boards.adrv9361_z7035 import adrv9361_z7035

        board = adrv9361_z7035(platform="bob")
        model = board.to_board_model({})
        assert model.name == "adrv9361_z7035_bob"
