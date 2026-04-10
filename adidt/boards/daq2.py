from datetime import datetime
from .layout import layout
from ..model.board_model import BoardModel, ComponentModel, FpgaConfig, JesdLinkModel
from ..model.contexts import (
    build_ad9523_1_ctx,
    build_ad9680_ctx,
    build_ad9144_ctx,
    build_adxcvr_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
    fmt_hz,
)


class daq2(layout):
    clock = "ad9523_1"

    adc = "ad9680"
    dac = "ad9144"

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

    def __init__(self, platform="zcu102", kernel_path=None):
        super().__init__(platform=platform, kernel_path=kernel_path)
        self.use_plugin_mode = False

    def validate_and_default_fpga_config(self, cfg: dict) -> dict:
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

    def map_jesd_structs(self, cfg: dict) -> tuple:
        """Extract and annotate ADC and DAC JESD configuration dicts from the solver output.

        Args:
            cfg (dict): Solver configuration containing converter_ADC/DAC and jesd_ADC/DAC keys.

        Returns:
            tuple: (adc dict, dac dict) each with a populated 'jesd' sub-dict.
        """
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

    def map_clocks_to_board_layout(self, cfg: dict) -> tuple:
        """Map JIF solver configuration to the DAQ2 board clock and JESD layout.

        Args:
            cfg (dict): JIF solver configuration.

        Returns:
            tuple: (clock_config, adc_config, dac_config, fpga_config)
        """
        # Fix ups
        for key in ["vco", "vcxo"]:
            if (
                key in cfg["clock"]
                and isinstance(cfg["clock"][key], float)
                and cfg["clock"][key].is_integer()
            ):
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
        adc["fpga_sys_clk_select"] = cfg["fpga_adc"]["sys_clk_select"]
        adc["fpga_out_clk_select"] = cfg["fpga_adc"]["out_clk_select"]
        dac["fpga_sys_clk_select"] = cfg["fpga_dac"]["sys_clk_select"]
        dac["fpga_out_clk_select"] = cfg["fpga_dac"]["out_clk_select"]

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

    def to_board_model(self, cfg: dict) -> "BoardModel":
        """Build a :class:`BoardModel` from JIF solver configuration.

        This maps the solver output through the existing board layout
        methods and produces a unified model that can be inspected,
        modified, and rendered via :class:`BoardModelRenderer`.

        Args:
            cfg (dict): JIF solver configuration (same dict passed to
                ``map_clocks_to_board_layout``).

        Returns:
            BoardModel: Editable board model.
        """
        cfg = self.validate_and_default_fpga_config(cfg)
        ccfg, adc, dac, fpga = self.map_clocks_to_board_layout(cfg)

        spi_bus = self.platform_config.get("spi_bus", "spi1")

        # --- Build clock channels from solver output ---
        _m1 = 1_000_000_000
        channels = []
        for name, info in ccfg["map"].items():
            divider = int(info["divider"])
            channels.append(
                {
                    "id": info["source_port"],
                    "name": name,
                    "divider": divider,
                    "freq_str": fmt_hz(_m1 // divider) if divider > 0 else "",
                }
            )

        clock_ctx = build_ad9523_1_ctx(
            label="clk0_ad9523",
            cs=0,
            spi_max_hz=10_000_000,
            vcxo_hz=int(ccfg["clock"]["vcxo"]),
            gpio_controller="gpio",
            sync_gpio=116,
            status0_gpio=110,
            status1_gpio=111,
            channels=channels,
        )

        # ADC context — board class uses 3 clocks (jesd, device, sysref)
        adc_jesd_label = "axi_ad9680_jesd204_rx"
        adc_core_label = "axi_ad9680_core"
        adc_clks_str = f"<&{adc_jesd_label}>, <&clk0_ad9523 13>, <&clk0_ad9523 5>"
        adc_ctx = build_ad9680_ctx(
            label="adc0_ad9680",
            cs=2,
            spi_max_hz=1_000_000,
            use_spi_3wire=False,
            clks_str=adc_clks_str,
            clk_names_str='"jesd_adc_clk", "adc_clk", "adc_sysref"',
            sampling_frequency_hz=1_000_000_000,
            rx_m=int(adc["jesd"].get("M", 2)),
            rx_l=int(adc["jesd"].get("L", 4)),
            rx_f=int(adc["jesd"].get("F", 1)),
            rx_k=int(adc["jesd"].get("K", 32)),
            rx_np=int(adc["jesd"].get("Np", 16)),
            jesd204_top_device=0,
            jesd204_link_ids=[0],
            jesd204_inputs=f"{adc_core_label} 0 0",
            gpio_controller="gpio",
            powerdown_gpio=120,
            fastdetect_a_gpio=113,
            fastdetect_b_gpio=114,
        )

        # DAC context
        dac_jesd_label = "axi_ad9144_jesd204_tx"
        dac_core_label = "axi_ad9144_core"
        dac_ctx = build_ad9144_ctx(
            label="dac0_ad9144",
            cs=1,
            spi_max_hz=1_000_000,
            clk_ref="clk0_ad9523 1",
            jesd204_top_device=1,
            jesd204_link_ids=[0],
            jesd204_inputs=f"{dac_core_label} 1 0",
            gpio_controller="gpio",
            txen_gpio=119,
            reset_gpio=118,
            irq_gpio=112,
        )

        components = [
            ComponentModel(
                role="clock",
                part="ad9523_1",
                template="ad9523_1.tmpl",
                spi_bus=spi_bus,
                spi_cs=0,
                config=clock_ctx,
            ),
            ComponentModel(
                role="adc",
                part="ad9680",
                template="ad9680.tmpl",
                spi_bus=spi_bus,
                spi_cs=2,
                config=adc_ctx,
            ),
            ComponentModel(
                role="dac",
                part="ad9144",
                template="ad9144.tmpl",
                spi_bus=spi_bus,
                spi_cs=1,
                config=dac_ctx,
            ),
        ]

        # --- FPGA PLL select mapping ---
        sys_clk_map = {"XCVR_CPLL": 0, "XCVR_QPLL1": 2, "XCVR_QPLL": 3, "XCVR_QPLL0": 3}
        out_clk_map = {"XCVR_REFCLK": 4, "XCVR_REFCLK_DIV2": 4}
        adc_sys = int(
            sys_clk_map.get(str(fpga["fpga_adc"]["sys_clk_select"]).upper(), 0)
        )
        dac_sys = int(
            sys_clk_map.get(str(fpga["fpga_dac"]["sys_clk_select"]).upper(), 3)
        )
        adc_out = int(
            out_clk_map.get(
                str(fpga["fpga_adc"].get("out_clk_select", "XCVR_REFCLK_DIV2")).upper(),
                4,
            )
        )
        dac_out = int(
            out_clk_map.get(
                str(fpga["fpga_dac"].get("out_clk_select", "XCVR_REFCLK_DIV2")).upper(),
                4,
            )
        )

        rx_l = int(adc["jesd"].get("L", 4))
        rx_m = int(adc["jesd"].get("M", 2))
        rx_f = int(adc["jesd"].get("F", 1))
        rx_k = int(adc["jesd"].get("K", 32))
        rx_np = int(adc["jesd"].get("Np", 16))
        rx_s = int(adc["jesd"].get("S", 1))
        tx_l = int(dac["jesd"].get("L", 4))
        tx_m = int(dac["jesd"].get("M", 2))
        tx_f = int(dac["jesd"].get("F", 1))
        tx_k = int(dac["jesd"].get("K", 32))
        tx_np = int(dac["jesd"].get("Np", 16))
        tx_s = int(dac["jesd"].get("S", 1))

        adc_xcvr_label = "axi_ad9680_adxcvr"
        dac_xcvr_label = "axi_ad9144_adxcvr"
        adc_dma_label = "axi_ad9680_dma"
        dac_dma_label = "axi_ad9144_dma"

        ps_clk_label = "zynqmp_clk"
        ps_clk_index = 71

        # RX link
        rx_link = JesdLinkModel(
            direction="rx",
            jesd_label=adc_jesd_label,
            xcvr_label=adc_xcvr_label,
            core_label=adc_core_label,
            dma_label=adc_dma_label,
            link_params={
                "F": rx_f,
                "K": rx_k,
                "M": rx_m,
                "L": rx_l,
                "Np": rx_np,
                "S": rx_s,
            },
            xcvr_config=build_adxcvr_ctx(
                label=adc_xcvr_label,
                sys_clk_select=adc_sys,
                out_clk_select=adc_out,
                clk_ref="clk0_ad9523 4",
                clock_output_names_str='"adc_gt_clk", "rx_out_clk"',
                jesd_l=rx_l,
                jesd_m=rx_m,
                jesd_s=rx_s,
                is_rx=True,
            ),
            jesd_overlay_config=build_jesd204_overlay_ctx(
                label=adc_jesd_label,
                direction="rx",
                clocks_str=f"<&{ps_clk_label} {ps_clk_index}>, <&{adc_xcvr_label} 1>, <&{adc_xcvr_label} 0>",
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name="jesd_adc_lane_clk",
                f=rx_f,
                k=rx_k,
                jesd204_inputs=f"{adc_xcvr_label} 0 0",
            ),
            tpl_core_config=build_tpl_core_ctx(
                label=adc_core_label,
                compatible="adi,axi-ad9680-1.0",
                direction="rx",
                dma_label=adc_dma_label,
                spibus_label="adc0_ad9680",
                jesd_label=adc_jesd_label,
                jesd_link_offset=0,
                link_id=0,
            ),
        )

        # TX link
        tx_link = JesdLinkModel(
            direction="tx",
            jesd_label=dac_jesd_label,
            xcvr_label=dac_xcvr_label,
            core_label=dac_core_label,
            dma_label=dac_dma_label,
            link_params={
                "F": tx_f,
                "K": tx_k,
                "M": tx_m,
                "L": tx_l,
                "Np": tx_np,
                "S": tx_s,
            },
            xcvr_config=build_adxcvr_ctx(
                label=dac_xcvr_label,
                sys_clk_select=dac_sys,
                out_clk_select=dac_out,
                clk_ref="clk0_ad9523 9",
                clock_output_names_str='"dac_gt_clk", "tx_out_clk"',
                jesd_l=tx_l,
                jesd_m=tx_m,
                jesd_s=tx_s,
                is_rx=False,
            ),
            jesd_overlay_config=build_jesd204_overlay_ctx(
                label=dac_jesd_label,
                direction="tx",
                clocks_str=f"<&{ps_clk_label} {ps_clk_index}>, <&{dac_xcvr_label} 1>, <&{dac_xcvr_label} 0>",
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name="jesd_dac_lane_clk",
                f=tx_f,
                k=tx_k,
                jesd204_inputs=f"{dac_xcvr_label} 1 0",
                converter_resolution=14,
                converters_per_device=tx_m,
                bits_per_sample=tx_np,
                control_bits_per_sample=2,
            ),
            tpl_core_config=build_tpl_core_ctx(
                label=dac_core_label,
                compatible="adi,axi-ad9144-1.0",
                direction="tx",
                dma_label=dac_dma_label,
                spibus_label="dac0_ad9144",
                jesd_label=dac_jesd_label,
                jesd_link_offset=1,
                link_id=0,
                pl_fifo_enable=True,
            ),
        )

        fpga_config = FpgaConfig(
            platform=self.platform,
            addr_cells=2,
            ps_clk_label=ps_clk_label,
            ps_clk_index=ps_clk_index,
            gpio_label="gpio",
        )

        return BoardModel(
            name=f"fmcdaq2_{self.platform}",
            platform=self.platform,
            components=components,
            jesd_links=[rx_link, tx_link],
            fpga_config=fpga_config,
            metadata={
                "base_dts_include": self.platform_config["base_dts_include"],
                "config_source": "jif_solver",
            },
        )

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
