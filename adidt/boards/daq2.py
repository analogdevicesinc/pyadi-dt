import os
from datetime import datetime
from .layout import layout


class daq2(layout):

    clock = "ad9523_1"

    adc = "ad9680"
    dac = "ad9144"

    # Default kernel source path
    DEFAULT_KERNEL_PATH = "./linux"

    # Platform-specific configurations
    PLATFORM_CONFIGS = {
        "zcu102": {
            "template_filename": "daq2_zcu102.tmpl",
            "base_dts_file": "arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-fmcdaq2.dts",
            "base_dts_include": "zynqmp-zcu102-rev10-fmcdaq2.dts",
            "arch": "arm64",
            "jesd_phy": "GTH",
            "default_fpga_adc_pll": "XCVR_CPLL",
            "default_fpga_dac_pll": "XCVR_QPLL",
            "spi_bus": "spi1",
            "output_dir": "generated_dts",
        },
        "zc706": {
            "template_filename": "daq2_zc706.tmpl",
            "base_dts_file": "arch/arm/boot/dts/xilinx/zynq-zc706.dts",
            "base_dts_include": "zynq-zc706.dts",
            "arch": "arm",
            "jesd_phy": "GTX",
            "default_fpga_adc_pll": "XCVR_CPLL",
            "default_fpga_dac_pll": "XCVR_QPLL",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
    }

    template_filename = "daq2.tmpl"
    output_filename = "daq2.dts"

    def __init__(self, platform="zcu102", kernel_path=None):
        """Initialize DAQ2 board.

        Args:
            platform (str): Target platform ('zcu102')
            kernel_path (str, optional): Path to Linux kernel source tree.
                If None, validation is skipped for backward compatibility.

        Raises:
            ValueError: If platform is not supported
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
        base_name = f"daq2_{platform}.dts"
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
            # Explicit kernel_path argument - always validate, raise on error
            self._validate_kernel_path()
        elif self._kernel_path_from_env:
            # Environment variable set - always validate, raise on error
            self._validate_kernel_path()
        elif os.path.exists(self.kernel_path):
            # Default path exists - try to validate but allow failure for backward compatibility
            try:
                self._validate_kernel_path()
            except FileNotFoundError:
                # For backward compatibility with existing code that doesn't need kernel path
                pass
        # else: kernel path doesn't exist and wasn't explicitly requested - skip validation

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
                f"  1. Pass kernel_path parameter to daq2()\n"
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
        # Apply defaults if not specified
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

    def make_ints(self, cfg, keys):
        for key in keys:
            if key in cfg and isinstance(cfg[key], float) and cfg[key].is_integer():
                cfg[key] = int(cfg[key])
        return cfg

    def map_jesd_structs(self, cfg):
        adc = cfg["converter_ADC"]
        adc["jesd"] = cfg["jesd_ADC"]
        if "jesd_class" in adc["jesd"]:
            adc["jesd"]["jesd_class_int"] = self.map_jesd_subclass(
                adc["jesd"]["jesd_class"]
            )
        else:
            adc["jesd"]["jesd_class_int"] = adc["jesd"].get("subclass", 1)

        dac = cfg["converter_DAC"]
        dac["jesd"] = cfg["jesd_DAC"]
        if "jesd_class" in dac["jesd"]:
            dac["jesd"]["jesd_class_int"] = self.map_jesd_subclass(
                dac["jesd"]["jesd_class"]
            )
        else:
            dac["jesd"]["jesd_class_int"] = dac["jesd"].get("subclass", 1)

        adc["jesd"] = self.make_ints(adc["jesd"], ["converter_clock", "sample_clock"])
        dac["jesd"] = self.make_ints(dac["jesd"], ["converter_clock", "sample_clock"])

        return adc, dac

    def map_clocks_to_board_layout(self, cfg):

        # Fix ups
        for key in ["vco", "vcxo"]:
            if key in cfg["clock"] and isinstance(cfg["clock"][key], float) and cfg["clock"][key].is_integer():
                cfg["clock"][key] = int(cfg["clock"][key])

        map = {}
        clk = cfg["clock"]["output_clocks"]

        # AD9680 side
        map["ADC_CLK"] = {
            "source_port": 13,
            "divider": clk["ADC_CLK"]["divider"],
        }
        map["ADC_CLK_FMC"] = {
            "source_port": 4,
            "divider": clk["ADC_CLK_FMC"]["divider"],
        }
        map["ADC_SYSREF"] = {
            "source_port": 5,
            "divider": clk["ADC_SYSREF"]["divider"],
        }
        map["CLKD_ADC_SYSREF"] = {
            "source_port": 6,
            "divider": clk["CLKD_ADC_SYSREF"]["divider"],
        }

        # AD9144 side
        map["DAC_CLK"] = {"source_port": 1, "divider": clk["DAC_CLK"]["divider"]}
        map["FMC_DAC_REF_CLK"] = {
            "source_port": 9,
            "divider": clk["FMC_DAC_REF_CLK"]["divider"],
        }
        map["DAC_SYSREF"] = {
            "source_port": 8,
            "divider": clk["DAC_SYSREF"]["divider"],
        }
        map["CLKD_DAC_SYSREF"] = {
            "source_port": 7,
            "divider": clk["CLKD_DAC_SYSREF"]["divider"],
        }

        ccfg = {"map": map, "clock": cfg["clock"]}

        # Check all clocks are mapped
        # FIXME

        # Check no source_port is mapped to more than one clock
        # FIXME

        adc, dac = self.map_jesd_structs(cfg)
        adc['fpga_sys_clk_select'] = cfg['fpga_adc']['sys_clk_select']
        adc['fpga_out_clk_select'] = cfg['fpga_adc']['out_clk_select']
        dac['fpga_sys_clk_select'] = cfg['fpga_dac']['sys_clk_select']
        dac['fpga_out_clk_select'] = cfg['fpga_dac']['out_clk_select']

        # Create fpga dict matching AD9081 pattern
        fpga = {}
        fpga["fpga_adc"] = cfg["fpga_adc"]
        fpga["fpga_dac"] = cfg["fpga_dac"]

        # Normalize QPLL0 naming for kernel compatibility (if needed)
        if fpga["fpga_dac"]["sys_clk_select"] == "XCVR_QPLL0":
            fpga["fpga_dac"]["sys_clk_select"] = "XCVR_QPLL"
        if fpga["fpga_adc"]["sys_clk_select"] == "XCVR_QPLL0":
            fpga["fpga_adc"]["sys_clk_select"] = "XCVR_QPLL"

        return ccfg, adc, dac, fpga

    def gen_dt_preprocess(self, **kwargs):
        """Add metadata to template rendering context.

        Args:
            kwargs: Template rendering context

        Returns:
            dict: Updated context with metadata
        """
        kwargs["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        kwargs["platform"] = self.platform
        kwargs["config_source"] = kwargs.get("config_source", "unknown")
        return kwargs

