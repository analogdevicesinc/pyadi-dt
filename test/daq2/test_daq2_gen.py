"""
Test suite for FMCDAQ2 device tree generation functionality (extended platforms).

Tests cover:
- Board initialization for each platform (ZCU102, ZC706)
- Kernel path validation and resolution
- DTS generation for each platform
- DTS compilation with dtc (if available)
- DTB roundtrip validation (compile and decompile)
- FPGA configuration defaults
- Platform configuration completeness
- DTC include paths
- AD9523 clock configuration mapping
- AD9680 ADC and AD9144 DAC configuration
"""

import pytest
import json
import os
import shutil
from pathlib import Path

# Import will fail until board class is extended - check for PLATFORM_CONFIGS
try:
    from adidt.boards.daq2 import daq2

    # Check if PLATFORM_CONFIGS exists (indicates multi-platform support)
    DAQ2_MULTIPLATFORM = hasattr(daq2, "PLATFORM_CONFIGS")
except ImportError:
    DAQ2_MULTIPLATFORM = False


# Helper function to check dtc availability
def is_dtc_available():
    """Check if dtc compiler is available on system."""
    return shutil.which("dtc") is not None


# Skip all tests if board class not extended yet
pytestmark = pytest.mark.skipif(
    not DAQ2_MULTIPLATFORM,
    reason="daq2 board class not yet extended with multi-platform support",
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
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        assert board.platform == "zcu102"
        assert board.platform_config["arch"] == "arm64"
        assert board.platform_config["jesd_phy"] == "GTH"

    def test_zc706_initialization(self, kernel_path):
        """Test ZC706 board initialization."""
        board = daq2(platform="zc706", kernel_path=kernel_path)
        assert board.platform == "zc706"
        assert board.platform_config["arch"] == "arm"
        assert board.platform_config["jesd_phy"] == "GTX"

    def test_unsupported_platform_rejection(self, kernel_path):
        """Test that unsupported platforms are rejected."""
        with pytest.raises(ValueError) as exc_info:
            daq2(platform="vpk180", kernel_path=kernel_path)
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

        for platform, config in daq2.PLATFORM_CONFIGS.items():
            for key in required_keys:
                assert key in config, f"Platform {platform} missing key: {key}"


class TestKernelPathResolution:
    """Test kernel path resolution and validation."""

    def test_kernel_path_explicit_argument(self, kernel_path, tmp_path):
        """Test that explicit kernel_path argument has highest priority."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        assert board.kernel_path == os.path.abspath(kernel_path)

    def test_kernel_path_environment_variable(self, kernel_path, monkeypatch):
        """Test that LINUX_KERNEL_PATH environment variable works."""
        monkeypatch.setenv("LINUX_KERNEL_PATH", kernel_path)
        board = daq2(platform="zcu102", kernel_path=None)
        assert board.kernel_path == os.path.abspath(kernel_path)

    def test_kernel_path_validation_missing_path(self, tmp_path):
        """Test that missing kernel path raises FileNotFoundError."""
        fake_path = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError) as exc_info:
            daq2(platform="zcu102", kernel_path=str(fake_path))
        assert "not found" in str(exc_info.value).lower()

    def test_kernel_path_validation_missing_dts_file(self, tmp_path):
        """Test that missing base DTS file raises FileNotFoundError."""
        fake_kernel = tmp_path / "linux"
        fake_kernel.mkdir()

        with pytest.raises(FileNotFoundError) as exc_info:
            daq2(platform="zcu102", kernel_path=str(fake_kernel))
        assert "Base DTS file not found" in str(exc_info.value)


class TestDTSGeneration:
    """Test DTS file generation."""

    @pytest.mark.parametrize("platform", ["zcu102", "zc706"])
    def test_dts_generation(self, platform, kernel_path, test_configs, tmp_path):
        """Test DTS generation for each platform."""
        board = daq2(platform=platform, kernel_path=kernel_path)

        output_file = tmp_path / f"daq2_{platform}.dts"
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

        with open(generated_file, "r") as f:
            content = f.read()

        assert "SPDX-License-Identifier: GPL-2.0" in content
        assert "AUTOGENERATED BY PYADI-DT" in content
        assert f"Platform: {platform}" in content
        assert "FMCDAQ2" in content or "daq2" in content.lower()
        assert "ad9523" in content
        assert "ad9680" in content or "ad9144" in content

    def test_dts_includes_metadata(self, kernel_path, test_configs, tmp_path):
        """Test that generated DTS includes metadata."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        output_file = tmp_path / "test_metadata.dts"
        board.output_filename = str(output_file)

        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)
        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        board.gen_dt(
            clock=clock, adc=adc, dac=dac, fpga=fpga, config_source="test_config.json"
        )

        with open(output_file, "r") as f:
            content = f.read()

        assert "Generated from: test_config.json" in content
        assert "Platform: zcu102" in content

    def test_dts_includes_ad9523_clock(self, kernel_path, test_configs, tmp_path):
        """Test that generated DTS includes AD9523 clock configuration."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        output_file = tmp_path / "test_clock.dts"
        board.output_filename = str(output_file)

        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)
        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        board.gen_dt(
            clock=clock, adc=adc, dac=dac, fpga=fpga, config_source="test_config.json"
        )

        with open(output_file, "r") as f:
            content = f.read()

        assert "ad9523" in content
        assert "DAC_CLK" in content or "ADC_CLK" in content

    def test_dts_includes_ad9680_adc(self, kernel_path, test_configs, tmp_path):
        """Test that generated DTS includes AD9680 ADC configuration."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        output_file = tmp_path / "test_adc.dts"
        board.output_filename = str(output_file)

        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)
        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        board.gen_dt(
            clock=clock, adc=adc, dac=dac, fpga=fpga, config_source="test_config.json"
        )

        with open(output_file, "r") as f:
            content = f.read()

        assert "ad9680" in content

    def test_dts_includes_ad9144_dac(self, kernel_path, test_configs, tmp_path):
        """Test that generated DTS includes AD9144 DAC configuration."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        output_file = tmp_path / "test_dac.dts"
        board.output_filename = str(output_file)

        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)
        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        board.gen_dt(
            clock=clock, adc=adc, dac=dac, fpga=fpga, config_source="test_config.json"
        )

        with open(output_file, "r") as f:
            content = f.read()

        assert "ad9144" in content


class TestFPGAConfiguration:
    """Test FPGA configuration handling."""

    def test_fpga_defaults_applied_zcu102(self, kernel_path):
        """Test that ZCU102 FPGA defaults are applied."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        cfg = {}
        cfg = board.validate_and_default_fpga_config(cfg)

        assert cfg["fpga_adc"]["sys_clk_select"] == "XCVR_CPLL"
        assert cfg["fpga_dac"]["sys_clk_select"] == "XCVR_QPLL"

    def test_fpga_defaults_applied_zc706(self, kernel_path):
        """Test that ZC706 FPGA defaults are applied."""
        board = daq2(platform="zc706", kernel_path=kernel_path)
        cfg = {}
        cfg = board.validate_and_default_fpga_config(cfg)

        assert cfg["fpga_adc"]["sys_clk_select"] == "XCVR_CPLL"
        assert cfg["fpga_dac"]["sys_clk_select"] == "XCVR_QPLL"

    def test_fpga_explicit_values_preserved(self, kernel_path):
        """Test that explicit FPGA config values are preserved."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        cfg = {
            "fpga_adc": {
                "sys_clk_select": "XCVR_QPLL",
                "out_clk_select": "XCVR_PROGDIV_CLK",
            },
            "fpga_dac": {
                "sys_clk_select": "XCVR_CPLL",
                "out_clk_select": "XCVR_PROGDIV_CLK",
            },
        }
        cfg = board.validate_and_default_fpga_config(cfg)

        assert cfg["fpga_adc"]["sys_clk_select"] == "XCVR_QPLL"
        assert cfg["fpga_dac"]["sys_clk_select"] == "XCVR_CPLL"


class TestDTCIncludePaths:
    """Test DTC include path generation."""

    @pytest.mark.parametrize(
        "platform,expected_arch",
        [("zcu102", "arm64"), ("zc706", "arm")],
    )
    def test_dtc_include_paths(self, platform, expected_arch, kernel_path):
        """Test that DTC include paths are correct for each platform."""
        board = daq2(platform=platform, kernel_path=kernel_path)
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
            ("zcu102", "daq2_zcu102.tmpl"),
            ("zc706", "daq2_zc706.tmpl"),
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

        board = daq2(platform=platform, kernel_path=kernel_path)
        output_file = tmp_path / f"daq2_{platform}.dts"
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

        dtb_file = tmp_path / f"daq2_{platform}.dtb"
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
        """Test that AD9523 clock configuration is properly mapped."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        assert "map" in clock
        assert "DAC_CLK" in clock["map"] or "ADC_CLK" in clock["map"]

    def test_jesd_adc_mapping(self, kernel_path, test_configs):
        """Test that ADC JESD configuration is properly mapped."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        assert "jesd" in adc
        assert "M" in adc["jesd"]
        assert "L" in adc["jesd"]

    def test_jesd_dac_mapping(self, kernel_path, test_configs):
        """Test that DAC JESD configuration is properly mapped."""
        board = daq2(platform="zcu102", kernel_path=kernel_path)
        cfg = test_configs["zcu102"]
        cfg = board.validate_and_default_fpga_config(cfg)

        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        assert "jesd" in dac
        assert "link_mode" in dac["jesd"]


class TestAdijifConfigGeneration:
    """Test configuration generation via pyadi-jif (adijif) solver."""

    @pytest.fixture
    def adijif(self):
        """Import adijif or skip if not available."""
        return pytest.importorskip("adijif", reason="adijif (pyadi-jif) not installed")

    def _solve_fmcdaq2(self, adijif, sample_rate_hz=1_000_000_000):
        """Generate FMCDAQ2 config via adijif solver."""
        sys = adijif.system(["ad9680", "ad9144"], "ad9523_1", "xilinx", 125_000_000)
        sys.fpga.setup_by_dev_kit_name("zcu102")
        sys.fpga.ref_clock_constraint = "Unconstrained"

        rx_mode = adijif.utils.get_jesd_mode_from_params(
            sys.converter[0], L=4, M=2, Np=16, F=1
        )
        tx_mode = adijif.utils.get_jesd_mode_from_params(
            sys.converter[1], L=4, M=2, Np=16, F=1
        )
        assert rx_mode, "No matching RX JESD mode found"
        assert tx_mode, "No matching TX JESD mode found"
        rx_mode = [m for m in rx_mode if "DL" not in m["mode"]]
        tx_mode = [m for m in tx_mode if "DL" not in m["mode"]]

        sys.converter[0].set_quick_configuration_mode(rx_mode[0]["mode"], "jesd204b")
        sys.converter[1].set_quick_configuration_mode(tx_mode[0]["mode"], "jesd204b")
        sys.converter[0].sample_clock = sample_rate_hz
        sys.converter[1].sample_clock = sample_rate_hz

        return sys.solve()

    def _map_solver_to_board_config(self, conf):
        """Map adijif solver output to daq2 board class config format."""
        clk_src = conf["clock"]["output_clocks"]
        output_clocks = {
            "ADC_CLK": clk_src.get("AD9680_ref_clk", {}),
            "ADC_CLK_FMC": clk_src.get("zcu102_AD9680_ref_clk", {}),
            "ADC_SYSREF": clk_src.get("AD9680_sysref", {}),
            "CLKD_ADC_SYSREF": clk_src.get("AD9680_sysref", {}),
            "DAC_CLK": clk_src.get("AD9144_ref_clk", {}),
            "FMC_DAC_REF_CLK": clk_src.get("zcu102_AD9144_ref_clk", {}),
            "DAC_SYSREF": clk_src.get("AD9144_sysref", {}),
            "CLKD_DAC_SYSREF": clk_src.get("AD9144_sysref", {}),
        }
        return {
            "clock": {
                "vco": conf["clock"]["vco"],
                "vcxo": conf["clock"]["vcxo"],
                "m1": conf["clock"]["m1"],
                "output_clocks": output_clocks,
            },
            "converter_ADC": {
                "sample_clock": conf["jesd_AD9680"]["sample_clock"],
                "decimation": conf["converter_AD9680"]["decimation"],
            },
            "converter_DAC": {
                "sample_clock": conf["jesd_AD9144"]["sample_clock"],
                "interpolation": conf["converter_AD9144"]["interpolation"],
            },
            "jesd_ADC": {
                "jesd_class": conf["jesd_AD9680"]["jesd_class"],
                "converter_clock": conf["jesd_AD9680"]["converter_clock"],
                "sample_clock": conf["jesd_AD9680"]["sample_clock"],
                "L": conf["jesd_AD9680"]["L"],
                "M": conf["jesd_AD9680"]["M"],
                "S": conf["jesd_AD9680"]["S"],
                "F": conf["jesd_AD9680"].get("F", 1),
                "K": conf["jesd_AD9680"].get("K", 32),
                "Np": conf["jesd_AD9680"].get("Np", 16),
            },
            "jesd_DAC": {
                "jesd_class": conf["jesd_AD9144"]["jesd_class"],
                "converter_clock": conf["jesd_AD9144"]["converter_clock"],
                "sample_clock": conf["jesd_AD9144"]["sample_clock"],
                "L": conf["jesd_AD9144"]["L"],
                "M": conf["jesd_AD9144"]["M"],
                "S": conf["jesd_AD9144"]["S"],
                "F": conf["jesd_AD9144"].get("F", 1),
                "K": conf["jesd_AD9144"].get("K", 32),
                "Np": conf["jesd_AD9144"].get("Np", 16),
            },
            "fpga_adc": conf.get("fpga_adc", {}),
            "fpga_dac": conf.get("fpga_dac", {}),
        }

    def test_adijif_solver_produces_valid_config(self, adijif):
        """Test that adijif solver produces a valid FMCDAQ2 config."""
        conf = self._solve_fmcdaq2(adijif)
        assert "clock" in conf
        assert "jesd_AD9680" in conf
        assert "jesd_AD9144" in conf
        assert conf["clock"]["vcxo"] == 125_000_000
        assert int(conf["jesd_AD9680"]["L"]) == 4
        assert int(conf["jesd_AD9680"]["M"]) == 2

    def test_adijif_config_maps_to_board_layout(self, adijif):
        """Test that adijif solver output maps correctly to daq2 board layout."""
        conf = self._solve_fmcdaq2(adijif)
        cfg = self._map_solver_to_board_config(conf)

        board = daq2.__new__(daq2)
        board.platform = "zcu102"
        board.platform_config = daq2.PLATFORM_CONFIGS["zcu102"]

        cfg = board.validate_and_default_fpga_config(cfg)
        clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

        assert "map" in clock
        assert "ADC_CLK" in clock["map"]
        assert "DAC_CLK" in clock["map"]
        assert "jesd" in adc
        assert "jesd" in dac

    @pytest.mark.parametrize("sample_rate_hz", [500_000_000, 1_000_000_000])
    def test_adijif_to_board_model(self, adijif, sample_rate_hz):
        """Test the full adijif → to_board_model() → render pipeline."""
        from adidt.model.renderer import BoardModelRenderer

        conf = self._solve_fmcdaq2(adijif, sample_rate_hz=sample_rate_hz)
        cfg = self._map_solver_to_board_config(conf)

        board = daq2.__new__(daq2)
        board.platform = "zcu102"
        board.platform_config = daq2.PLATFORM_CONFIGS["zcu102"]

        model = board.to_board_model(cfg)

        assert model.name == "fmcdaq2_zcu102"
        assert len(model.components) == 3
        assert model.get_component("clock").part == "ad9523_1"
        assert model.get_component("adc").part == "ad9680"
        assert model.get_component("dac").part == "ad9144"

        # Verify clock channels come from solver (dynamic dividers)
        clock_ctx = model.get_component("clock").config
        channel_names = {ch["name"] for ch in clock_ctx["channels"]}
        assert "ADC_CLK" in channel_names
        assert "DAC_CLK" in channel_names

        # Render and verify output
        rendered = BoardModelRenderer().render(model)
        assert rendered["converters"], "No converter nodes rendered"
        assert rendered["jesd204_rx"], "No JESD204 RX nodes rendered"
        assert rendered["jesd204_tx"], "No JESD204 TX nodes rendered"

        # Check rendered content contains expected components
        all_nodes = "\n".join(node for nodes in rendered.values() for node in nodes)
        assert "ad9523" in all_nodes
        assert "ad9680" in all_nodes.lower() or "adc0_ad9680" in all_nodes
        assert "ad9144" in all_nodes.lower() or "dac0_ad9144" in all_nodes

    def test_board_model_editability_with_adijif(self, adijif):
        """Test that a BoardModel from adijif config can be edited before rendering."""
        from adidt.model.renderer import BoardModelRenderer

        conf = self._solve_fmcdaq2(adijif)
        cfg = self._map_solver_to_board_config(conf)

        board = daq2.__new__(daq2)
        board.platform = "zcu102"
        board.platform_config = daq2.PLATFORM_CONFIGS["zcu102"]

        model = board.to_board_model(cfg)

        # Edit: change VCXO frequency
        clock = model.get_component("clock")
        original_vcxo = clock.config["vcxo_hz"]
        clock.config["vcxo_hz"] = 100_000_000

        rendered = BoardModelRenderer().render(model)
        spi_node = rendered["converters"][0]
        assert "100000000" in spi_node
        assert str(original_vcxo) not in spi_node


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
