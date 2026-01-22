"""AD9084 FMC board device tree generation support.

This module provides device tree generation for the AD9084-FMCA-EBZ evaluation
board on Versal platforms (VPK180, VCK190).

The AD9084 is a high-performance multi-channel RF transceiver that uses:
- HMC7044 as the primary clock generator
- ADF4382 as the device clock PLL
- ADF4030 (AION) for JESD204C sysref distribution

Reference: linux/arch/arm64/boot/dts/xilinx/versal-vpk180-reva-ad9084.dts
"""

from .layout import layout
import os
from datetime import datetime


class ad9084_fmc(layout):
    """AD9084 FMC board layout map for clocks and DSP"""

    # Clock chips
    clock = "HMC7044"
    ext_clock = "ADF4382"
    sysref_provider = "ADF4030"

    # Converters
    adc = "ad9084_rx"
    dac = "ad9084_tx"

    # Default kernel source path
    DEFAULT_KERNEL_PATH = "./linux"

    # Platform-specific configurations
    PLATFORM_CONFIGS = {
        "vpk180": {
            "template_filename": "ad9084_fmc_vpk180.tmpl",
            "base_dts_file": "arch/arm64/boot/dts/xilinx/versal-vpk180-revA.dts",
            "base_dts_include": "versal-vpk180-revA.dts",
            "arch": "arm64",
            "jesd_phy": "GTY",
            "default_fpga_adc_pll": "XCVR_QPLL0",
            "default_fpga_dac_pll": "XCVR_QPLL0",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
        "vck190": {
            "template_filename": "ad9084_fmc_vck190.tmpl",
            "base_dts_file": "arch/arm64/boot/dts/xilinx/versal-vck190-revA.dts",
            "base_dts_include": "versal-vck190-revA.dts",
            "arch": "arm64",
            "jesd_phy": "GTY",
            "default_fpga_adc_pll": "XCVR_QPLL0",
            "default_fpga_dac_pll": "XCVR_QPLL0",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
    }

    template_filename = "ad9084_fmc_vpk180.tmpl"
    output_filename = "ad9084_fmc_vpk180.dts"
    use_plugin_mode = False

    def __init__(self, platform="vpk180", kernel_path=None):
        """Initialize AD9084 FMC board.

        Args:
            platform (str): Target platform ('vpk180' or 'vck190')
            kernel_path (str, optional): Path to Linux kernel source tree.
                If None, uses LINUX_KERNEL_PATH env var or default path.

        Raises:
            ValueError: If platform is not supported
            FileNotFoundError: If kernel path is invalid (when explicitly provided)
        """
        if platform not in self.PLATFORM_CONFIGS:
            supported = ", ".join(self.PLATFORM_CONFIGS.keys())
            raise ValueError(
                f"Platform '{platform}' not supported. Supported platforms: {supported}"
            )

        self.platform = platform
        self.platform_config = self.PLATFORM_CONFIGS[platform]

        # Set template and output based on platform
        self.template_filename = self.platform_config["template_filename"]
        base_name = f"ad9084_fmc_{platform}.dts"
        self.output_filename = os.path.join(
            self.platform_config["output_dir"], base_name
        )

        # Store original kernel_path argument to determine validation strategy
        self._kernel_path_explicit = kernel_path is not None
        self._kernel_path_from_env = kernel_path is None and bool(
            os.environ.get("LINUX_KERNEL_PATH")
        )

        # Resolve kernel path
        self.kernel_path = self._resolve_kernel_path(kernel_path)

        # Validate kernel path based on how it was provided
        if self._kernel_path_explicit:
            self._validate_kernel_path()
        elif self._kernel_path_from_env:
            self._validate_kernel_path()
        elif os.path.exists(self.kernel_path):
            try:
                self._validate_kernel_path()
            except FileNotFoundError:
                pass

    def _resolve_kernel_path(self, kernel_path=None):
        """Resolve kernel source path using 3-tier priority system.

        Priority:
        1. Argument passed to __init__ (highest)
        2. LINUX_KERNEL_PATH environment variable
        3. DEFAULT_KERNEL_PATH constant (lowest)

        Args:
            kernel_path (str, optional): Explicit kernel path

        Returns:
            str: Resolved kernel path
        """
        if kernel_path:
            return os.path.abspath(kernel_path)

        env_path = os.environ.get("LINUX_KERNEL_PATH")
        if env_path:
            return os.path.abspath(env_path)

        return os.path.abspath(self.DEFAULT_KERNEL_PATH)

    def _validate_kernel_path(self):
        """Validate that kernel path exists and contains required DTS file.

        Raises:
            FileNotFoundError: If kernel path or base DTS file not found
        """
        if not os.path.exists(self.kernel_path):
            raise FileNotFoundError(
                f"Kernel source path not found: {self.kernel_path}\n"
                f"Set kernel path via:\n"
                f"  1. Pass kernel_path parameter to ad9084_fmc()\n"
                f"  2. Set LINUX_KERNEL_PATH environment variable\n"
                f"  3. Clone kernel source to {self.DEFAULT_KERNEL_PATH}"
            )

        base_dts_path = os.path.join(
            self.kernel_path, self.platform_config["base_dts_file"]
        )
        if not os.path.exists(base_dts_path):
            raise FileNotFoundError(
                f"Base DTS file not found: {base_dts_path}\n"
                f"Platform '{self.platform}' requires: {self.platform_config['base_dts_file']}"
            )

    def get_dtc_include_paths(self):
        """Get list of include paths for dtc compilation.

        Returns:
            list: Include paths for dtc -i option
        """
        arch = self.platform_config["arch"]
        paths = [
            os.path.join(self.kernel_path, f"arch/{arch}/boot/dts"),
            os.path.join(self.kernel_path, f"arch/{arch}/boot/dts/xilinx"),
            os.path.join(self.kernel_path, "include"),
        ]
        return paths

    def validate_and_default_fpga_config(self, cfg):
        """Validate and apply platform defaults for FPGA configuration.

        Args:
            cfg (dict): Configuration dictionary

        Returns:
            dict: Configuration with FPGA defaults applied
        """
        if "fpga_adc" not in cfg:
            cfg["fpga_adc"] = {}
        if "fpga_dac" not in cfg:
            cfg["fpga_dac"] = {}

        # Apply platform defaults for ADC
        if "sys_clk_select" not in cfg["fpga_adc"]:
            cfg["fpga_adc"]["sys_clk_select"] = self.platform_config[
                "default_fpga_adc_pll"
            ]
        if "out_clk_select" not in cfg["fpga_adc"]:
            cfg["fpga_adc"]["out_clk_select"] = "XCVR_REFCLK_DIV2"

        # Apply platform defaults for DAC
        if "sys_clk_select" not in cfg["fpga_dac"]:
            cfg["fpga_dac"]["sys_clk_select"] = self.platform_config[
                "default_fpga_dac_pll"
            ]
        if "out_clk_select" not in cfg["fpga_dac"]:
            cfg["fpga_dac"]["out_clk_select"] = "XCVR_REFCLK_DIV2"

        return cfg

    def gen_dt_preprocess(self, **kwargs):
        """Add metadata to template rendering context.

        Args:
            kwargs: Template rendering context

        Returns:
            dict: Updated context with metadata
        """
        kwargs["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        kwargs["platform"] = self.platform
        kwargs["base_dts_include"] = self.platform_config["base_dts_include"]
        kwargs["config_source"] = kwargs.get("config_source", "unknown")
        return kwargs

    def map_clocks_to_board_layout(self, cfg):
        """Map configuration to board clock connection layout.

        The AD9084 uses HMC7044 as the primary clock generator with the
        following channel assignments:
        - Channel 1: ADF4030_REFIN (125 MHz)
        - Channel 3: ADF4030_BSYNC0 (9.765 MHz)
        - Channel 8: CORE_CLK_TX (312.5 MHz)
        - Channel 9: CORE_CLK_RX (312.5 MHz)
        - Channel 10: FPGA_REFCLK (312.5 MHz)
        - Channel 11: CORE_CLK_RX_B (312.5 MHz)
        - Channel 12: CORE_CLK_TX_B (312.5 MHz)

        Args:
            cfg (dict): Configuration dictionary

        Returns:
            tuple: (clock_config, adc_config, dac_config, fpga_config)
        """
        # Fix up clock values
        clock_cfg = cfg.get("clock", {})
        for key in ["hmc7044_vcxo", "hmc7044_vco"]:
            if key in clock_cfg:
                if isinstance(clock_cfg[key], float) and clock_cfg[key].is_integer():
                    clock_cfg[key] = int(clock_cfg[key])

        # Build clock mapping from config
        map = {}
        output_clocks = clock_cfg.get("output_clocks", {})

        for name, clk_cfg in output_clocks.items():
            map[name] = {
                "source_port": clk_cfg["source_port"],
                "divider": clk_cfg["divider"],
            }

        ccfg = {
            "map": map,
            "clock": clock_cfg,
        }

        # ADC configuration
        adc = {
            "jesd": cfg.get("jesd_rx", {}),
        }

        # DAC configuration
        dac = {
            "jesd": cfg.get("jesd_tx", {}),
        }

        # Device profile and lane mapping
        adc["device_profile"] = cfg.get("device_profile", "")
        dac["device_profile"] = cfg.get("device_profile", "")

        lane_mapping = cfg.get("lane_mapping", {})
        adc["lane_mapping"] = lane_mapping
        dac["lane_mapping"] = lane_mapping

        # FPGA configuration
        fpga = {
            "fpga_adc": cfg.get("fpga_adc", {}),
            "fpga_dac": cfg.get("fpga_dac", {}),
        }

        return ccfg, adc, dac, fpga
