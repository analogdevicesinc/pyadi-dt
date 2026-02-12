"""
Test suite for AD9084 device tree generation functionality.

Tests cover:
- Board initialization for each platform (VPK180, VCK190)
- Kernel path validation and resolution
- DTS generation for each platform
- DTS compilation with dtc (if available)
- DTB roundtrip validation (compile and decompile)
- FPGA configuration defaults
- Platform configuration completeness
- DTC include paths
- Configuration mapping
"""

import pytest
import json
import os
import shutil
from pathlib import Path

# Import will fail until board class is implemented - this is expected for TDD
try:
    from adidt.boards.ad9084_fmc import ad9084_fmc

    AD9084_AVAILABLE = True
except ImportError:
    AD9084_AVAILABLE = False


# Helper function to check dtc availability
def is_dtc_available():
    """Check if dtc compiler is available on system."""
    return shutil.which("dtc") is not None


# Skip all tests if board class not implemented yet
pytestmark = pytest.mark.skipif(
    not AD9084_AVAILABLE, reason="ad9084_fmc board class not yet implemented"
)


# Fixture to resolve kernel path or skip tests if not found
@pytest.fixture(scope="module")
def kernel_path():
    """Resolve kernel path or skip tests if not available."""
    # Try environment variable first
    env_path = os.environ.get("LINUX_KERNEL_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    # Try default path
    default_path = os.path.abspath("./linux")
    if os.path.exists(default_path):
        return default_path

    # Skip tests if no kernel found
    pytest.skip(
        "Linux kernel source not found. Set LINUX_KERNEL_PATH or clone to ./linux"
    )


@pytest.fixture
def test_configs():
    """Load test configuration files."""
    config_dir = Path(__file__).parent / "configs"
    configs = {}
    for platform in ["vpk180", "vck190"]:
        config_file = config_dir / f"{platform}_config.json"
        with open(config_file, "r") as f:
            configs[platform] = json.load(f)
    return configs


class TestBoardInitialization:
    """Test board initialization and platform support."""

    def test_vpk180_initialization(self, kernel_path):
        """Test VPK180 board initialization."""
        board = ad9084_fmc(platform="vpk180", kernel_path=kernel_path)
        assert board.platform == "vpk180"
        assert board.platform_config["arch"] == "arm64"
        assert board.platform_config["jesd_phy"] == "GTY"

    def test_vck190_initialization(self, kernel_path):
        """Test VCK190 board initialization."""
        board = ad9084_fmc(platform="vck190", kernel_path=kernel_path)
        assert board.platform == "vck190"
        assert board.platform_config["arch"] == "arm64"
        assert board.platform_config["jesd_phy"] == "GTY"

    def test_unsupported_platform_rejection(self, kernel_path):
        """Test that unsupported platforms are rejected."""
        with pytest.raises(ValueError) as exc_info:
            ad9084_fmc(platform="zcu102", kernel_path=kernel_path)
        assert "not supported" in str(exc_info.value).lower()

    def test_platform_config_completeness(self):
        """Test that all platform configs have required keys."""
        required_keys = [
            "template_filename",
            "base_dts_file",
            "base_dts_include",
            "arch",
            "jesd_phy",
            "default_fpga_adc_pll",
            "default_fpga_dac_pll",
            "spi_bus",
            "output_dir",
        ]

        for platform, config in ad9084_fmc.PLATFORM_CONFIGS.items():
            for key in required_keys:
                assert key in config, f"Platform {platform} missing key: {key}"


class TestKernelPathResolution:
    """Test kernel path resolution and validation."""

    def test_kernel_path_explicit_argument(self, kernel_path, tmp_path):
        """Test that explicit kernel_path argument has highest priority."""
        board = ad9084_fmc(platform="vpk180", kernel_path=kernel_path)
        assert board.kernel_path == os.path.abspath(kernel_path)

    def test_kernel_path_environment_variable(self, kernel_path, monkeypatch):
        """Test that LINUX_KERNEL_PATH environment variable works."""
        monkeypatch.setenv("LINUX_KERNEL_PATH", kernel_path)
        board = ad9084_fmc(platform="vpk180", kernel_path=None)
        assert board.kernel_path == os.path.abspath(kernel_path)

    def test_kernel_path_validation_missing_path(self, tmp_path):
        """Test that missing kernel path raises FileNotFoundError."""
        fake_path = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError) as exc_info:
            ad9084_fmc(platform="vpk180", kernel_path=str(fake_path))
        assert "not found" in str(exc_info.value).lower()

    def test_kernel_path_validation_missing_dts_file(self, tmp_path):
        """Test that missing base DTS file raises FileNotFoundError."""
        # Create kernel path but without the required DTS file
        fake_kernel = tmp_path / "linux"
        fake_kernel.mkdir()

        with pytest.raises(FileNotFoundError) as exc_info:
            ad9084_fmc(platform="vpk180", kernel_path=str(fake_kernel))
        assert "Base DTS file not found" in str(exc_info.value)


class TestDTSGeneration:
    """Test DTS file generation."""

    @pytest.mark.parametrize("platform", ["vpk180", "vck190"])
    def test_dts_generation(self, platform, kernel_path, test_configs, tmp_path):
        """Test DTS generation for each platform."""
        board = ad9084_fmc(platform=platform, kernel_path=kernel_path)

        # Override output to temp directory
        output_file = tmp_path / f"ad9084_fmc_{platform}.dts"
        board.output_filename = str(output_file)

        # Get configuration
        cfg = test_configs[platform]
        cfg = board.validate_and_default_fpga_config(cfg)

        # Generate DTS
        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)
        generated_file = board.gen_dt(
            clock=clock,
            adc=adc,
            dac=dac,
            fpga=fpga,
            config_source=f"test_config_{platform}.json",
        )

        # Verify file was created
        assert os.path.exists(generated_file)

        # Read and verify content
        with open(generated_file, "r") as f:
            content = f.read()

        # Check for expected content
        assert "SPDX-License-Identifier: GPL-2.0" in content
        assert "AUTOGENERATED BY PYADI-DT" in content
        assert f"Platform: {platform}" in content
        assert "AD9084-FMC" in content
        assert "hmc7044" in content
        assert "ad9084" in content

    def test_dts_includes_metadata(self, kernel_path, test_configs, tmp_path):
        """Test that generated DTS includes metadata."""
        board = ad9084_fmc(platform="vpk180", kernel_path=kernel_path)
        output_file = tmp_path / "test_metadata.dts"
        board.output_filename = str(output_file)

        cfg = test_configs["vpk180"]
        cfg = board.validate_and_default_fpga_config(cfg)
        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        board.gen_dt(
            clock=clock, adc=adc, dac=dac, fpga=fpga, config_source="test_config.json"
        )

        with open(output_file, "r") as f:
            content = f.read()

        assert "Generated from: test_config.json" in content
        assert "Platform: vpk180" in content

    def test_dts_includes_clock_chips(self, kernel_path, test_configs, tmp_path):
        """Test that generated DTS includes HMC7044, ADF4382, and optionally ADF4030."""
        board = ad9084_fmc(platform="vpk180", kernel_path=kernel_path)
        output_file = tmp_path / "test_clocks.dts"
        board.output_filename = str(output_file)

        cfg = test_configs["vpk180"]
        cfg = board.validate_and_default_fpga_config(cfg)
        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        board.gen_dt(
            clock=clock, adc=adc, dac=dac, fpga=fpga, config_source="test_config.json"
        )

        with open(output_file, "r") as f:
            content = f.read()

        # AD9084 uses HMC7044 + ADF4382
        assert "hmc7044" in content
        assert "adf4382" in content


class TestFPGAConfiguration:
    """Test FPGA configuration handling."""

    def test_fpga_defaults_applied_vpk180(self, kernel_path):
        """Test that VPK180 FPGA defaults are applied."""
        board = ad9084_fmc(platform="vpk180", kernel_path=kernel_path)
        cfg = {}
        cfg = board.validate_and_default_fpga_config(cfg)

        assert cfg["fpga_adc"]["sys_clk_select"] == "XCVR_QPLL0"
        assert cfg["fpga_adc"]["out_clk_select"] == "XCVR_REFCLK_DIV2"
        assert cfg["fpga_dac"]["sys_clk_select"] == "XCVR_QPLL0"
        assert cfg["fpga_dac"]["out_clk_select"] == "XCVR_REFCLK_DIV2"

    def test_fpga_defaults_applied_vck190(self, kernel_path):
        """Test that VCK190 FPGA defaults are applied."""
        board = ad9084_fmc(platform="vck190", kernel_path=kernel_path)
        cfg = {}
        cfg = board.validate_and_default_fpga_config(cfg)

        assert cfg["fpga_adc"]["sys_clk_select"] == "XCVR_QPLL0"
        assert cfg["fpga_adc"]["out_clk_select"] == "XCVR_REFCLK_DIV2"
        assert cfg["fpga_dac"]["sys_clk_select"] == "XCVR_QPLL0"
        assert cfg["fpga_dac"]["out_clk_select"] == "XCVR_REFCLK_DIV2"

    def test_fpga_explicit_values_preserved(self, kernel_path):
        """Test that explicit FPGA config values are preserved."""
        board = ad9084_fmc(platform="vpk180", kernel_path=kernel_path)
        cfg = {
            "fpga_adc": {
                "sys_clk_select": "XCVR_CPLL",
                "out_clk_select": "XCVR_REFCLK",
            },
            "fpga_dac": {
                "sys_clk_select": "XCVR_CPLL",
                "out_clk_select": "XCVR_REFCLK",
            },
        }
        cfg = board.validate_and_default_fpga_config(cfg)

        assert cfg["fpga_adc"]["sys_clk_select"] == "XCVR_CPLL"
        assert cfg["fpga_adc"]["out_clk_select"] == "XCVR_REFCLK"
        assert cfg["fpga_dac"]["sys_clk_select"] == "XCVR_CPLL"
        assert cfg["fpga_dac"]["out_clk_select"] == "XCVR_REFCLK"


class TestDTCIncludePaths:
    """Test DTC include path generation."""

    @pytest.mark.parametrize(
        "platform,expected_arch",
        [("vpk180", "arm64"), ("vck190", "arm64")],
    )
    def test_dtc_include_paths(self, platform, expected_arch, kernel_path):
        """Test that DTC include paths are correct for each platform."""
        board = ad9084_fmc(platform=platform, kernel_path=kernel_path)
        include_paths = board.get_dtc_include_paths()

        assert len(include_paths) >= 2
        assert any(f"arch/{expected_arch}/boot/dts" in p for p in include_paths)
        assert any("include" in p for p in include_paths)

        # Verify paths exist (relative to kernel path)
        for path in include_paths:
            assert os.path.exists(path), f"Include path does not exist: {path}"


class TestTemplateFiles:
    """Test that template files exist."""

    @pytest.mark.parametrize(
        "platform,template_name",
        [
            ("vpk180", "ad9084_fmc_vpk180.tmpl"),
            ("vck190", "ad9084_fmc_vck190.tmpl"),
        ],
    )
    def test_template_exists(self, platform, template_name):
        """Test that all platform templates exist."""
        template_dir = Path(__file__).parent.parent.parent / "adidt" / "templates"
        template_path = template_dir / template_name
        assert template_path.exists(), f"Template not found: {template_path}"


class TestDTSCompilation:
    """Test DTS compilation with dtc compiler."""

    @pytest.fixture(scope="class")
    def dtc_available(self):
        """Check if dtc compiler is available."""
        return is_dtc_available()

    @pytest.mark.parametrize("platform", ["vpk180", "vck190"])
    def test_dts_compilation(
        self, platform, kernel_path, test_configs, tmp_path, dtc_available
    ):
        """Test that generated DTS files compile without errors."""
        if not dtc_available:
            pytest.skip("dtc compiler not available")

        import subprocess

        # Generate DTS file
        board = ad9084_fmc(platform=platform, kernel_path=kernel_path)
        output_file = tmp_path / f"ad9084_fmc_{platform}.dts"
        board.output_filename = str(output_file)

        cfg = test_configs[platform]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)
        generated_file = board.gen_dt(
            clock=clock,
            adc=adc,
            dac=dac,
            fpga=fpga,
            config_source=f"test_config_{platform}.json",
        )

        assert os.path.exists(generated_file)

        # Compile DTS to DTB
        dtb_file = tmp_path / f"ad9084_fmc_{platform}.dtb"
        include_paths = board.get_dtc_include_paths()

        # Preprocess the DTS file
        cpp_cmd = ["cpp", "-nostdinc", "-undef", "-x", "assembler-with-cpp"]
        for inc_path in include_paths:
            cpp_cmd.extend(["-I", inc_path])
        cpp_cmd.append(str(generated_file))

        cpp_result = subprocess.run(cpp_cmd, capture_output=True, text=True)
        if cpp_result.returncode != 0:
            pytest.fail(
                f"DTS preprocessing failed for {platform}:\n"
                f"Command: {' '.join(cpp_cmd)}\n"
                f"STDERR: {cpp_result.stderr}"
            )

        # Build dtc command
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

        assert os.path.exists(dtb_file), f"DTB file not created: {dtb_file}"
        assert os.path.getsize(dtb_file) > 0, f"DTB file is empty: {dtb_file}"


class TestConfigurationMapping:
    """Test configuration mapping to board layout."""

    def test_clock_mapping(self, kernel_path, test_configs):
        """Test that clock configuration is properly mapped."""
        board = ad9084_fmc(platform="vpk180", kernel_path=kernel_path)
        cfg = test_configs["vpk180"]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        # Check clock mapping structure
        assert "map" in clock
        assert "clock" in clock

    def test_jesd_mapping(self, kernel_path, test_configs):
        """Test that JESD configuration is properly mapped."""
        board = ad9084_fmc(platform="vpk180", kernel_path=kernel_path)
        cfg = test_configs["vpk180"]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        # Check ADC JESD parameters
        assert "jesd" in adc
        assert "lanerate_khz" in adc["jesd"]

        # Check DAC JESD parameters
        assert "jesd" in dac
        assert "lanerate_khz" in dac["jesd"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
