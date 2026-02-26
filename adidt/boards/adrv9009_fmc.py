"""ADRV9009 FMC board device tree generation support (JSON-based).

This module provides JSON-based device tree generation for the ADRV9009
evaluation board on ZCU102 and ZC706 platforms.

The ADRV9009 is a highly integrated RF transceiver that uses:
- AD9528 as the clock generator
- JESD204B for high-speed data interface

This is a NEW implementation using JSON configuration (like AD9081),
distinct from the existing profile-based implementations in adrv9009_pcbz.py.

Reference: linux/arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-adrv9009.dts
"""

from .layout import layout
import os
from datetime import datetime


class adrv9009_fmc(layout):
    """ADRV9009 FMC board layout for JSON-based DT generation"""

    # Clock chip
    clock = "AD9528"

    # Transceiver
    transceiver = "ADRV9009"

    # Default kernel source path
    DEFAULT_KERNEL_PATH = "./linux"

    # Platform-specific configurations
    PLATFORM_CONFIGS = {
        "zcu102": {
            "template_filename": "adrv9009_fmc_zcu102.tmpl",
            "base_dts_file": "arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev1.0.dts",
            "base_dts_include": "zynqmp-zcu102-rev1.0.dts",
            "arch": "arm64",
            "jesd_phy": "GTH",
            "default_fpga_rx_pll": "XCVR_CPLL",
            "default_fpga_tx_pll": "XCVR_QPLL",
            "default_fpga_orx_pll": "XCVR_CPLL",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
            "clock_ref": "zynqmp_clk 71",
        },
        "zc706": {
            "template_filename": "adrv9009_fmc_zc706.tmpl",
            "base_dts_file": "arch/arm/boot/dts/xilinx/zynq-zc706.dts",
            "base_dts_include": "zynq-zc706.dts",
            "arch": "arm",
            "jesd_phy": "GTX",
            "default_fpga_rx_pll": "XCVR_CPLL",
            "default_fpga_tx_pll": "XCVR_QPLL",
            "default_fpga_orx_pll": "XCVR_CPLL",
            "spi_bus": "spi1",
            "output_dir": "generated_dts",
            "clock_ref": "clkc 16",
        },
    }

    template_filename = "adrv9009_fmc_zcu102.tmpl"
    output_filename = "adrv9009_fmc_zcu102.dts"
    use_plugin_mode = False

    def __init__(self, platform="zcu102", kernel_path=None):
        """Initialize ADRV9009 FMC board.

        Args:
            platform (str): Target platform ('zcu102' or 'zc706')
            kernel_path (str, optional): Path to Linux kernel source tree.

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
        base_name = f"adrv9009_fmc_{platform}.dts"
        self.output_filename = os.path.join(
            self.platform_config["output_dir"], base_name
        )

        # Store original kernel_path argument
        self._kernel_path_explicit = kernel_path is not None
        self._kernel_path_from_env = kernel_path is None and bool(
            os.environ.get("LINUX_KERNEL_PATH")
        )

        # Resolve kernel path
        self.kernel_path = self._resolve_kernel_path(kernel_path)

        # Validate kernel path
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
        """Resolve kernel source path using 3-tier priority system."""
        if kernel_path:
            return os.path.abspath(kernel_path)

        env_path = os.environ.get("LINUX_KERNEL_PATH")
        if env_path:
            return os.path.abspath(env_path)

        return os.path.abspath(self.DEFAULT_KERNEL_PATH)

    def _validate_kernel_path(self):
        """Validate that kernel path exists and contains required DTS file."""
        if not os.path.exists(self.kernel_path):
            raise FileNotFoundError(
                f"Kernel source path not found: {self.kernel_path}\n"
                f"Set kernel path via:\n"
                f"  1. Pass kernel_path parameter to adrv9009_fmc()\n"
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
        """Get list of include paths for dtc compilation."""
        arch = self.platform_config["arch"]
        paths = [
            os.path.join(self.kernel_path, f"arch/{arch}/boot/dts"),
            os.path.join(self.kernel_path, f"arch/{arch}/boot/dts/xilinx"),
            os.path.join(self.kernel_path, "include"),
        ]
        return paths

    def validate_and_default_fpga_config(self, cfg):
        """Validate and apply platform defaults for FPGA configuration."""
        if "fpga_rx" not in cfg:
            cfg["fpga_rx"] = {}
        if "fpga_tx" not in cfg:
            cfg["fpga_tx"] = {}
        if "fpga_orx" not in cfg:
            cfg["fpga_orx"] = {}

        # Apply defaults for RX
        if "sys_clk_select" not in cfg["fpga_rx"]:
            cfg["fpga_rx"]["sys_clk_select"] = self.platform_config[
                "default_fpga_rx_pll"
            ]
        if "out_clk_select" not in cfg["fpga_rx"]:
            cfg["fpga_rx"]["out_clk_select"] = "XCVR_REFCLK"

        # Apply defaults for TX
        if "sys_clk_select" not in cfg["fpga_tx"]:
            cfg["fpga_tx"]["sys_clk_select"] = self.platform_config[
                "default_fpga_tx_pll"
            ]
        if "out_clk_select" not in cfg["fpga_tx"]:
            cfg["fpga_tx"]["out_clk_select"] = "XCVR_REFCLK"

        # Apply defaults for ORX
        if "sys_clk_select" not in cfg["fpga_orx"]:
            cfg["fpga_orx"]["sys_clk_select"] = self.platform_config[
                "default_fpga_orx_pll"
            ]
        if "out_clk_select" not in cfg["fpga_orx"]:
            cfg["fpga_orx"]["out_clk_select"] = "XCVR_REFCLK"

        return cfg

    def gen_dt_preprocess(self, **kwargs):
        """Add metadata to template rendering context."""
        kwargs["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        kwargs["platform"] = self.platform
        kwargs["base_dts_include"] = self.platform_config["base_dts_include"]
        kwargs["spi_bus"] = self.platform_config["spi_bus"]
        kwargs["config_source"] = kwargs.get("config_source", "unknown")
        return kwargs

    def map_clocks_to_board_layout(self, cfg):
        """Map configuration to board clock connection layout.

        The ADRV9009 uses AD9528 as the clock generator with outputs:
        - Channel 13: DEV_CLK (device clock)
        - Channel 1: FMC_CLK (FPGA clock)
        - Channel 12: DEV_SYSREF (device sysref)
        - Channel 3: FMC_SYSREF (FPGA sysref)

        Args:
            cfg (dict): Configuration dictionary

        Returns:
            tuple: (clock_config, rx_config, tx_config, orx_config, fpga_config)
        """
        # Clock configuration
        clock_cfg = cfg.get("clock", {})

        # Build clock mapping from config
        map = {}
        output_clocks = clock_cfg.get("output_clocks", {})

        for name, clk_cfg in output_clocks.items():
            map[name] = {
                "channel": clk_cfg["channel"],
                "divider": clk_cfg["divider"],
            }

        ccfg = {
            "map": map,
            "vcxo": clock_cfg.get("vcxo", 122880000),
            "pll1": clock_cfg.get("pll1", {}),
            "pll2": clock_cfg.get("pll2", {}),
            "sysref": clock_cfg.get("sysref", {}),
        }

        # Helper to extract profile fields
        def extract_profile_fields(prof_data):
            fields = {}
            if not prof_data:
                return fields
            
            # Keep original fields
            fields.update(prof_data)
            
            # Map common fields to standardized names
            mapping = {
                "rxFirDecimation": "fir_decimation",
                "rxDec5Decimation": "dec5_decimation",
                "rhb1Decimation": "rhb1_decimation",
                "rxOutputRate_kHz": "output_rate_khz",
                "orxOutputRate_kHz": "output_rate_khz",
                "rfBandwidth_Hz": "rf_bandwidth_hz",
                "rxDdcMode": "ddc_mode",
                "orxDdcMode": "ddc_mode",
                "rxBbf3dBCorner_kHz": "rx_bbf3d_bcorner_khz",
                "txFirInterpolation": "fir_interpolation",
                "thb1Interpolation": "thb1_interpolation",
                "thb2Interpolation": "thb2_interpolation",
                "thb3Interpolation": "thb3_interpolation",
                "txInputRate_kHz": "input_rate_khz",
                "rxChannels": "channels",
                "txChannels": "channels",
                "obsRxChannels": "channels",
            }
            
            for src, dst in mapping.items():
                if src in prof_data:
                    fields[dst] = prof_data[src]
            
            # Handle gain separately as it might be in filter
            if "filter" in prof_data and "@gain_dB" in prof_data["filter"]:
                fields["fir_gain_db"] = prof_data["filter"]["@gain_dB"]
            
            return fields

        # RX configuration (framer)
        rx_prof = cfg.get("rx_profile", {})
        rx = extract_profile_fields(rx_prof)
        rx.update({
            "profile": rx_prof,
            "framer": cfg.get("jesd204", {}).get("framer_a", {}),
        })

        # TX configuration (deframer)
        tx_prof = cfg.get("tx_profile", {})
        tx = extract_profile_fields(tx_prof)
        tx.update({
            "profile": tx_prof,
            "deframer": cfg.get("jesd204", {}).get("deframer_a", {}),
        })

        # ORX configuration (framer B)
        orx_prof = cfg.get("orx_profile", {})
        orx = extract_profile_fields(orx_prof)
        orx.update({
            "profile": orx_prof,
            "framer": cfg.get("jesd204", {}).get("framer_b", {}),
        })

        # FPGA configuration
        fpga = {
            "fpga_rx": cfg.get("fpga_rx", {}),
            "fpga_tx": cfg.get("fpga_tx", {}),
            "fpga_orx": cfg.get("fpga_orx", {}),
        }

        return ccfg, rx, tx, orx, fpga
