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
