"""
Test suite for ADRV9009 device tree generation functionality (JSON-based).

Tests cover:
- Board initialization for each platform (ZCU102, ZC706)
- Kernel path validation and resolution
- DTS generation for each platform
- DTS compilation with dtc (if available)
- DTB roundtrip validation (compile and decompile)
- FPGA configuration defaults
- Platform configuration completeness
- DTC include paths
- AD9528 clock configuration mapping
- Framer/deframer configuration
"""

import pytest
import json
import os
import shutil
from pathlib import Path

# Import will fail until board class is implemented - this is expected for TDD
try:
    from adidt.boards.adrv9009_fmc import adrv9009_fmc

    ADRV9009_AVAILABLE = True
except ImportError:
    ADRV9009_AVAILABLE = False


# Helper function to check dtc availability
def is_dtc_available():
    """Check if dtc compiler is available on system."""
    return shutil.which("dtc") is not None


# Skip all tests if board class not implemented yet
pytestmark = pytest.mark.skipif(
    not ADRV9009_AVAILABLE, reason="adrv9009_fmc board class not yet implemented"
)


@pytest.fixture(scope="module")
def kernel_path():
    """Resolve kernel path or skip tests if not available."""
    env_path = os.environ.get("LINUX_KERNEL_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    default_path = os.path.abspath("./linux")
    if os.path.exists(default_path):
        return default_path

    pytest.skip(
        "Linux kernel source not found. Set LINUX_KERNEL_PATH or clone to ./linux"
    )


@pytest.fixture
def test_configs():
    """Load test configuration files."""
    config_dir = Path(__file__).parent / "configs"
    configs = {}
    for platform in ["zcu102", "zc706"]:
        config_file = config_dir / f"{platform}_config.json"
        with open(config_file, "r") as f:
            configs[platform] = json.load(f)
    return configs


class TestBoardInitialization:
    """Test board initialization and platform support."""

    def test_zcu102_initialization(self, kernel_path):
        """Test ZCU102 board initialization."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        assert board.platform == "zcu102"
        assert board.platform_config["arch"] == "arm64"
        assert board.platform_config["jesd_phy"] == "GTH"

    def test_zc706_initialization(self, kernel_path):
        """Test ZC706 board initialization."""
        board = adrv9009_fmc(platform="zc706", kernel_path=kernel_path)
        assert board.platform == "zc706"
        assert board.platform_config["arch"] == "arm"
        assert board.platform_config["jesd_phy"] == "GTX"

    def test_unsupported_platform_rejection(self, kernel_path):
        """Test that unsupported platforms are rejected."""
        with pytest.raises(ValueError) as exc_info:
            adrv9009_fmc(platform="vpk180", kernel_path=kernel_path)
        assert "not supported" in str(exc_info.value).lower()

    def test_platform_config_completeness(self):
        """Test that all platform configs have required keys."""
        required_keys = [
            "template_filename",
            "base_dts_file",
            "base_dts_include",
            "arch",
            "jesd_phy",
            "default_fpga_rx_pll",
            "default_fpga_tx_pll",
            "spi_bus",
            "output_dir",
        ]

        for platform, config in adrv9009_fmc.PLATFORM_CONFIGS.items():
            for key in required_keys:
                assert key in config, f"Platform {platform} missing key: {key}"


class TestKernelPathResolution:
    """Test kernel path resolution and validation."""

    def test_kernel_path_explicit_argument(self, kernel_path, tmp_path):
        """Test that explicit kernel_path argument has highest priority."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        assert board.kernel_path == os.path.abspath(kernel_path)

    def test_kernel_path_environment_variable(self, kernel_path, monkeypatch):
        """Test that LINUX_KERNEL_PATH environment variable works."""
        monkeypatch.setenv("LINUX_KERNEL_PATH", kernel_path)
        board = adrv9009_fmc(platform="zcu102", kernel_path=None)
        assert board.kernel_path == os.path.abspath(kernel_path)

    def test_kernel_path_validation_missing_path(self, tmp_path):
        """Test that missing kernel path raises FileNotFoundError."""
        fake_path = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError) as exc_info:
            adrv9009_fmc(platform="zcu102", kernel_path=str(fake_path))
        assert "not found" in str(exc_info.value).lower()

    def test_kernel_path_validation_missing_dts_file(self, tmp_path):
        """Test that missing base DTS file raises FileNotFoundError."""
        fake_kernel = tmp_path / "linux"
        fake_kernel.mkdir()

        with pytest.raises(FileNotFoundError) as exc_info:
            adrv9009_fmc(platform="zcu102", kernel_path=str(fake_kernel))
        assert "Base DTS file not found" in str(exc_info.value)


class TestDTSGeneration:
    """Test DTS file generation."""

    @pytest.mark.parametrize("platform", ["zcu102", "zc706"])
    def test_dts_generation(self, platform, kernel_path, test_configs, tmp_path):
        """Test DTS generation for each platform."""
        board = adrv9009_fmc(platform=platform, kernel_path=kernel_path)

        output_file = tmp_path / f"adrv9009_fmc_{platform}.dts"
        board.output_filename = str(output_file)

        cfg = test_configs[platform]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(cfg)
        generated_file = board.gen_dt(
            clock=clock,
            rx=rx,
            tx=tx,
            orx=orx,
            fpga=fpga,
            config_source=f"test_config_{platform}.json",
        )

        assert os.path.exists(generated_file)

        with open(generated_file, "r") as f:
            content = f.read()

        assert "SPDX-License-Identifier: GPL-2.0" in content
        assert "AUTOGENERATED BY PYADI-DT" in content
        assert f"Platform: {platform}" in content
        assert "ADRV9009" in content
        assert "ad9528" in content
        assert "adrv9009" in content.lower()

    def test_dts_includes_metadata(self, kernel_path, test_configs, tmp_path):
        """Test that generated DTS includes metadata."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        output_file = tmp_path / "test_metadata.dts"
        board.output_filename = str(output_file)

        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)
        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(cfg)

        board.gen_dt(
            clock=clock,
            rx=rx,
            tx=tx,
            orx=orx,
            fpga=fpga,
            config_source="test_config.json",
        )

        with open(output_file, "r") as f:
            content = f.read()

        assert "Generated from: test_config.json" in content
        assert "Platform: zcu102" in content

    def test_dts_includes_ad9528_clock(self, kernel_path, test_configs, tmp_path):
        """Test that generated DTS includes AD9528 clock configuration."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        output_file = tmp_path / "test_clock.dts"
        board.output_filename = str(output_file)

        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)
        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(cfg)

        board.gen_dt(
            clock=clock,
            rx=rx,
            tx=tx,
            orx=orx,
            fpga=fpga,
            config_source="test_config.json",
        )

        with open(output_file, "r") as f:
            content = f.read()

        assert "ad9528" in content
        assert "DEV_CLK" in content or "dev_clk" in content.lower()

    def test_dts_includes_transceiver(self, kernel_path, test_configs, tmp_path):
        """Test that generated DTS includes ADRV9009 transceiver config."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        output_file = tmp_path / "test_trx.dts"
        board.output_filename = str(output_file)

        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)
        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(cfg)

        board.gen_dt(
            clock=clock,
            rx=rx,
            tx=tx,
            orx=orx,
            fpga=fpga,
            config_source="test_config.json",
        )

        with open(output_file, "r") as f:
            content = f.read()

        assert "adrv9009" in content.lower()
        assert "jesd204-framer" in content or "framer" in content.lower()


class TestFPGAConfiguration:
    """Test FPGA configuration handling."""

    def test_fpga_defaults_applied_zcu102(self, kernel_path):
        """Test that ZCU102 FPGA defaults are applied."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        cfg = {}
        cfg = board.validate_and_default_fpga_config(cfg)

        assert cfg["fpga_rx"]["sys_clk_select"] == "XCVR_CPLL"
        assert cfg["fpga_tx"]["sys_clk_select"] == "XCVR_QPLL"

    def test_fpga_defaults_applied_zc706(self, kernel_path):
        """Test that ZC706 FPGA defaults are applied."""
        board = adrv9009_fmc(platform="zc706", kernel_path=kernel_path)
        cfg = {}
        cfg = board.validate_and_default_fpga_config(cfg)

        assert cfg["fpga_rx"]["sys_clk_select"] == "XCVR_CPLL"
        assert cfg["fpga_tx"]["sys_clk_select"] == "XCVR_QPLL"

    def test_fpga_explicit_values_preserved(self, kernel_path):
        """Test that explicit FPGA config values are preserved."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        cfg = {
            "fpga_rx": {
                "sys_clk_select": "XCVR_QPLL",
                "out_clk_select": "XCVR_PROGDIV_CLK",
            },
            "fpga_tx": {
                "sys_clk_select": "XCVR_CPLL",
                "out_clk_select": "XCVR_PROGDIV_CLK",
            },
        }
        cfg = board.validate_and_default_fpga_config(cfg)

        assert cfg["fpga_rx"]["sys_clk_select"] == "XCVR_QPLL"
        assert cfg["fpga_tx"]["sys_clk_select"] == "XCVR_CPLL"


class TestDTCIncludePaths:
    """Test DTC include path generation."""

    @pytest.mark.parametrize(
        "platform,expected_arch",
        [("zcu102", "arm64"), ("zc706", "arm")],
    )
    def test_dtc_include_paths(self, platform, expected_arch, kernel_path):
        """Test that DTC include paths are correct for each platform."""
        board = adrv9009_fmc(platform=platform, kernel_path=kernel_path)
        include_paths = board.get_dtc_include_paths()

        assert len(include_paths) >= 2
        assert any(f"arch/{expected_arch}/boot/dts" in p for p in include_paths)
        assert any("include" in p for p in include_paths)

        for path in include_paths:
            assert os.path.exists(path), f"Include path does not exist: {path}"


class TestTemplateFiles:
    """Test that template files exist."""

    @pytest.mark.parametrize(
        "platform,template_name",
        [
            ("zcu102", "adrv9009_fmc_zcu102.tmpl"),
            ("zc706", "adrv9009_fmc_zc706.tmpl"),
        ],
    )
    def test_template_exists(self, platform, template_name):
        """Test that all platform templates exist."""
        template_dir = (
            Path(__file__).parent.parent.parent / "adidt" / "templates" / "boards"
        )
        template_path = template_dir / template_name
        assert template_path.exists(), f"Template not found: {template_path}"


class TestDTSCompilation:
    """Test DTS compilation with dtc compiler."""

    @pytest.fixture(scope="class")
    def dtc_available(self):
        """Check if dtc compiler is available."""
        return is_dtc_available()

    @pytest.mark.parametrize("platform", ["zcu102", "zc706"])
    def test_dts_compilation(
        self, platform, kernel_path, test_configs, tmp_path, dtc_available
    ):
        """Test that generated DTS files compile without errors."""
        if not dtc_available:
            pytest.skip("dtc compiler not available")

        import subprocess

        board = adrv9009_fmc(platform=platform, kernel_path=kernel_path)
        output_file = tmp_path / f"adrv9009_fmc_{platform}.dts"
        board.output_filename = str(output_file)

        cfg = test_configs[platform]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(cfg)
        generated_file = board.gen_dt(
            clock=clock,
            rx=rx,
            tx=tx,
            orx=orx,
            fpga=fpga,
            config_source=f"test_config_{platform}.json",
        )

        assert os.path.exists(generated_file)

        dtb_file = tmp_path / f"adrv9009_fmc_{platform}.dtb"
        include_paths = board.get_dtc_include_paths()

        cpp_cmd = ["cpp", "-nostdinc", "-undef", "-x", "assembler-with-cpp"]
        for inc_path in include_paths:
            cpp_cmd.extend(["-I", inc_path])
        cpp_cmd.append(str(generated_file))

        cpp_result = subprocess.run(cpp_cmd, capture_output=True, text=True)
        if cpp_result.returncode != 0:
            pytest.fail(
                f"DTS preprocessing failed for {platform}:\nSTDERR: {cpp_result.stderr}"
            )

        dtc_cmd = ["dtc", "-@", "-I", "dts", "-O", "dtb"]
        for inc_path in include_paths:
            dtc_cmd.extend(["-i", inc_path])
        dtc_cmd.extend(
            [
                "-W",
                "no-unit_address_vs_reg",
                "-W",
                "no-reg_format",
                "-W",
                "no-avoid_default_addr_size",
            ]
        )
        dtc_cmd.extend(["-o", str(dtb_file), "-"])

        result = subprocess.run(
            dtc_cmd, input=cpp_result.stdout, capture_output=True, text=True
        )

        if result.returncode != 0:
            pytest.fail(
                f"DTS compilation failed for {platform}:\nSTDERR: {result.stderr}"
            )

        assert os.path.exists(dtb_file)
        assert os.path.getsize(dtb_file) > 0


class TestConfigurationMapping:
    """Test configuration mapping to board layout."""

    def test_clock_mapping(self, kernel_path, test_configs):
        """Test that AD9528 clock configuration is properly mapped."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(cfg)

        assert "map" in clock
        assert "pll1" in clock or "vcxo" in clock

    def test_framer_deframer_mapping(self, kernel_path, test_configs):
        """Test that framer/deframer configuration is properly mapped."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(cfg)

        # Check RX (framer) parameters
        assert "framer" in rx or "jesd" in rx
        assert "M" in rx.get("framer", rx.get("jesd", {}))

        # Check TX (deframer) parameters
        assert "deframer" in tx or "jesd" in tx

    def test_rx_tx_orx_profile_mapping(self, kernel_path, test_configs):
        """Test that RX/TX/ORX profiles are properly mapped."""
        board = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(cfg)

        # Check RX profile
        assert "profile" in rx or "fir" in str(rx).lower()

        # Check TX profile
        assert "profile" in tx or "fir" in str(tx).lower()

        # Check ORX profile
        assert "profile" in orx or "fir" in str(orx).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
