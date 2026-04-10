"""AD9084 FMC board device tree generation support.

This module provides device tree generation for the AD9084-FMCA-EBZ evaluation
board on Versal platforms (VPK180, VCK190).

The AD9084 is a high-performance multi-channel RF transceiver that uses:
- HMC7044 as the primary clock generator
- ADF4382 as the device clock PLL
- ADF4030 (AION) for JESD204C sysref distribution

Reference: linux/arch/arm64/boot/dts/xilinx/versal-vpk180-reva-ad9084.dts
"""

from datetime import datetime

from .layout import layout
from ..model.board_model import BoardModel, ComponentModel, FpgaConfig, JesdLinkModel
from ..model.contexts import (
    build_ad9084_ctx,
    build_adf4382_ctx,
    build_adxcvr_ctx,
    build_hmc7044_channel_ctx,
    build_hmc7044_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
)


class ad9084_fmc(layout):
    """AD9084 FMC board layout map for clocks and DSP"""

    # Clock chips
    clock = "HMC7044"
    ext_clock = "ADF4382"
    sysref_provider = "ADF4030"

    # Converters
    adc = "ad9084_rx"
    dac = "ad9084_tx"

    FPGA_LINK_KEYS = ["fpga_adc", "fpga_dac"]

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
        "vcu118": {
            "template_filename": "ad9084_fmc_vcu118.tmpl",
            # base_dts_file is None: VCU118 DTS is placed directly in the kernel tree
            # The generated DTS includes the existing hardware base DTS from the kernel
            "base_dts_file": None,
            "base_dts_include": "vcu118_ad9084_204C_M4_L8_NP16_20p0_4x4.dts",
            "arch": "microblaze",
            "jesd_phy": "GTY",
            "default_fpga_adc_pll": "XCVR_QPLL1",
            "default_fpga_dac_pll": "XCVR_QPLL1",
            "spi_bus": "axi_spi_2",
            "output_dir": None,  # Set directly via output_filename in tests
        },
    }

    def __init__(self, platform="vpk180", kernel_path=None):
        super().__init__(platform=platform, kernel_path=kernel_path)
        self.use_plugin_mode = False

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

    def to_board_model(self, cfg: dict) -> "BoardModel":
        """Build a :class:`BoardModel` from board configuration.

        This maps the configuration through the existing board layout
        methods and produces a unified model that can be inspected,
        modified, and rendered via :class:`BoardModelRenderer`.

        Args:
            cfg (dict): Board configuration (same dict passed to
                ``map_clocks_to_board_layout``).

        Returns:
            BoardModel: Editable board model.
        """
        cfg = self.validate_and_default_fpga_config(cfg)
        ccfg, adc, dac, fpga = self.map_clocks_to_board_layout(cfg)

        clock_spi: str = str(self.platform_config.get("spi_bus", "spi0"))
        converter_spi = clock_spi

        # --- HMC7044 clock chip ---
        clock_cfg = ccfg["clock"]
        vcxo_hz = int(clock_cfg.get("hmc7044_vcxo", 125_000_000))
        pll2_output_hz = int(clock_cfg.get("hmc7044_vco", 2_500_000_000))

        hmc7044_channels = build_hmc7044_channel_ctx(
            pll2_output_hz,
            [
                {"id": info["source_port"], "name": name, "divider": info["divider"]}
                for name, info in ccfg["map"].items()
            ],
        )

        hmc7044_clock_output_names = [f"hmc7044_out{i}" for i in range(14)]

        # Determine if ADF4382 is present
        has_adf4382 = "adf4382_output_frequency" in clock_cfg
        clkin0_ref = "clkin_125" if has_adf4382 else None

        hmc7044_ctx = build_hmc7044_ctx(
            label="hmc7044",
            cs=0,
            spi_max_hz=1_000_000,
            pll1_clkin_frequencies=[vcxo_hz, 10_000_000, 0, 0],
            vcxo_hz=vcxo_hz,
            pll2_output_hz=pll2_output_hz,
            clock_output_names=hmc7044_clock_output_names,
            channels=hmc7044_channels,
            jesd204_sysref_provider=True,
            jesd204_max_sysref_hz=2_000_000,
            pll1_loop_bandwidth_hz=200,
            pll1_ref_prio_ctrl="0xE1",
            pll1_ref_autorevert=True,
            pll1_charge_pump_ua=720,
            pfd1_max_freq_hz=1_000_000,
            sysref_timer_divider=1024,
            pulse_generator_mode=0,
            clkin0_buffer_mode="0x07",
            clkin1_buffer_mode="0x07",
            oscin_buffer_mode="0x15",
            gpi_controls=[0x00, 0x00, 0x00, 0x00],
            gpo_controls=[0x37, 0x33, 0x00, 0x00],
            clkin0_ref=clkin0_ref,
        )

        # --- Build components list ---
        components: list[ComponentModel] = []

        # ADF4382 must appear before HMC7044 for correct probe ordering
        if has_adf4382:
            adf4382_freq = int(
                clock_cfg.get("adf4382_output_frequency", 20_000_000_000)
            )
            adf4382_ctx = build_adf4382_ctx(
                label="adf4382",
                cs=1,
                spi_max_hz=1_000_000,
                clks_str="<&hmc7044 1>",
                clock_output_names_str='"adf4382_out_clk"',
                power_up_frequency=adf4382_freq,
                spi_3wire=True,
            )
            components.append(
                ComponentModel(
                    role="clock_pll",
                    part="adf4382",
                    template="adf4382.tmpl",
                    spi_bus=clock_spi,
                    spi_cs=1,
                    config=adf4382_ctx,
                )
            )

        components.append(
            ComponentModel(
                role="clock",
                part="hmc7044",
                template="hmc7044.tmpl",
                spi_bus=clock_spi,
                spi_cs=0,
                config=hmc7044_ctx,
            )
        )

        # --- FPGA PLL select mapping ---
        sys_clk_map = {
            "XCVR_CPLL": 0,
            "XCVR_QPLL1": 2,
            "XCVR_QPLL": 3,
            "XCVR_QPLL0": 3,
        }
        out_clk_map = {"XCVR_REFCLK": 4, "XCVR_REFCLK_DIV2": 4}

        rx_sys = int(
            sys_clk_map.get(str(fpga["fpga_adc"]["sys_clk_select"]).upper(), 3)
        )
        tx_sys = int(
            sys_clk_map.get(str(fpga["fpga_dac"]["sys_clk_select"]).upper(), 3)
        )
        rx_out = int(
            out_clk_map.get(
                str(fpga["fpga_adc"].get("out_clk_select", "XCVR_REFCLK_DIV2")).upper(),
                4,
            )
        )
        tx_out = int(
            out_clk_map.get(
                str(fpga["fpga_dac"].get("out_clk_select", "XCVR_REFCLK_DIV2")).upper(),
                4,
            )
        )

        # --- JESD parameters ---
        jesd_rx = adc.get("jesd", {})
        jesd_tx = dac.get("jesd", {})
        rx_f = int(jesd_rx.get("F", 6))
        rx_k = int(jesd_rx.get("K", 32))
        tx_f = int(jesd_tx.get("F", 6))
        tx_k = int(jesd_tx.get("K", 32))

        # FPGA reference clock channel (typically channel 10)
        fpga_refclk_channel = 10

        # Versal platforms use versal_clk as PS clock
        _32BIT_PLATFORMS = {"vcu118", "zc706"}
        if self.platform in _32BIT_PLATFORMS:
            ps_clk_label = "clkc"
            ps_clk_index = None
            addr_cells = 1
        else:
            ps_clk_label = "versal_clk"
            ps_clk_index = 65
            addr_cells = 2

        ps_clk_str = (
            f"<&{ps_clk_label}"
            + (f" {ps_clk_index}" if ps_clk_index is not None else "")
            + ">"
        )

        gpio_label = "gpio"
        ad9084_spi_label = "trx0_ad9084"

        # --- Build JESD link models ---
        # AD9084 has four links: rx_a, rx_b, tx_a, tx_b
        link_defs = [
            {
                "direction": "rx",
                "variant": "",
                "link_id": 0,
                "sys_sel": rx_sys,
                "out_sel": rx_out,
                "jesd_label": "rx_apollo_jesd_rx_axi",
                "xcvr_label": "rx_apollo_xcvr",
                "dma_label": "rx_apollo_dma",
                "tpl_label": "rx_apollo_tpl_core_adc_tpl_core",
                "tpl_compatible": "adi,axi-ad9081-rx-1.0",
                "dev_clk_label": "axi_hsci_clkgen",
                "dev_clk_index": 0,
            },
            {
                "direction": "rx",
                "variant": "_b",
                "link_id": 1,
                "sys_sel": rx_sys,
                "out_sel": rx_out,
                "jesd_label": "rx_b_apollo_jesd_rx_axi",
                "xcvr_label": "rx_b_apollo_xcvr",
                "dma_label": "rx_b_apollo_dma",
                "tpl_label": "rx_b_apollo_tpl_core_adc_tpl_core",
                "tpl_compatible": "adi,axi-ad9081-rx-1.0",
                "dev_clk_label": "axi_hsci_clkgen",
                "dev_clk_index": 0,
            },
            {
                "direction": "tx",
                "variant": "",
                "link_id": 2,
                "sys_sel": tx_sys,
                "out_sel": tx_out,
                "jesd_label": "tx_apollo_jesd_tx_axi",
                "xcvr_label": "tx_apollo_xcvr",
                "dma_label": "tx_apollo_dma",
                "tpl_label": "tx_apollo_tpl_core_dac_tpl_core",
                "tpl_compatible": "adi,axi-ad9081-tx-1.0",
                "dev_clk_label": "axi_hsci_clkgen",
                "dev_clk_index": 0,
            },
            {
                "direction": "tx",
                "variant": "_b",
                "link_id": 3,
                "sys_sel": tx_sys,
                "out_sel": tx_out,
                "jesd_label": "tx_b_apollo_jesd_tx_axi",
                "xcvr_label": "tx_b_apollo_xcvr",
                "dma_label": "tx_b_apollo_dma",
                "tpl_label": "tx_b_apollo_tpl_core_dac_tpl_core",
                "tpl_compatible": "adi,axi-ad9081-tx-1.0",
                "dev_clk_label": "axi_hsci_clkgen",
                "dev_clk_index": 0,
            },
        ]

        jesd_links = []
        for lk in link_defs:
            direction = str(lk["direction"])
            variant = str(lk["variant"])
            is_rx = direction == "rx"
            gt_prefix = "rx" if is_rx else "tx"

            # Extract typed values from link dict
            _xcvr = str(lk["xcvr_label"])
            _jesd = str(lk["jesd_label"])
            _tpl = str(lk["tpl_label"])
            _tpl_compat = str(lk["tpl_compatible"])
            _dma = str(lk["dma_label"])
            _link_id = int(lk["link_id"])
            _sys_sel = int(lk["sys_sel"])
            _out_sel = int(lk["out_sel"])

            xcvr_ctx = build_adxcvr_ctx(
                label=_xcvr,
                sys_clk_select=_sys_sel,
                out_clk_select=_out_sel,
                clk_ref=f"hmc7044 {fpga_refclk_channel}",
                use_div40=False,
                div40_clk_ref=None,
                clock_output_names_str=(
                    f'"{gt_prefix}{variant}_gt_clk", "{gt_prefix}{variant}_out_clk"'
                ),
                use_lpm_enable=False,
                jesd204_inputs=f"hmc7044 0 {_link_id}",
                is_rx=is_rx,
            )

            # JESD204 overlay context -- 4-clock format for AD9084
            dev_label = str(lk["dev_clk_label"])
            dev_idx = lk["dev_clk_index"]
            dev_idx_str = f" {dev_idx}" if dev_idx is not None else ""
            clocks_str = (
                f"{ps_clk_str}, <&{_xcvr} 1>, <&{dev_label}{dev_idx_str}>, <&{_xcvr} 0>"
            )

            f_val = rx_f if is_rx else tx_f
            k_val = rx_k if is_rx else tx_k

            jesd_overlay_ctx = build_jesd204_overlay_ctx(
                label=_jesd,
                direction=direction,
                clocks_str=clocks_str,
                clock_names_str='"s_axi_aclk", "link_clk", "device_clk", "lane_clk"',
                clock_output_name=None,
                f=f_val,
                k=k_val,
                jesd204_inputs=f"{_xcvr} 0 {_link_id}",
            )

            # TPL core context
            if direction == "tx":
                sampl_clk_ref = f"{ad9084_spi_label} 1"
                sampl_clk_name = "sampl_clk"
            else:
                sampl_clk_ref = None
                sampl_clk_name = None

            tpl_ctx = build_tpl_core_ctx(
                label=_tpl,
                compatible=_tpl_compat,
                direction=direction,
                dma_label=_dma,
                spibus_label=ad9084_spi_label,
                jesd_label=_jesd,
                jesd_link_offset=0,
                link_id=_link_id,
                pl_fifo_enable=direction == "tx",
                sampl_clk_ref=sampl_clk_ref,
                sampl_clk_name=sampl_clk_name,
            )

            jesd_links.append(
                JesdLinkModel(
                    direction=direction,
                    jesd_label=_jesd,
                    xcvr_label=_xcvr,
                    core_label=_tpl,
                    dma_label=_dma,
                    link_params={"F": f_val, "K": k_val},
                    xcvr_config=xcvr_ctx,
                    jesd_overlay_config=jesd_overlay_ctx,
                    tpl_core_config=tpl_ctx,
                    dma_clocks_str=ps_clk_str,
                )
            )

        # --- AD9084 converter ---
        tpl_inputs = []
        all_link_ids = []
        for lk in link_defs:
            tpl_inputs.append(f"<&{lk['tpl_label']} 0 {lk['link_id']}>")
            all_link_ids.append(str(lk["link_id"]))

        dev_clk_ref = f"hmc7044 9"
        firmware_name = cfg.get("device_profile")

        lane_mapping = cfg.get("lane_mapping", {})
        rx_physical = lane_mapping.get("rx_physical")
        tx_logical = lane_mapping.get("tx_logical")

        ad9084_ctx = build_ad9084_ctx(
            label=ad9084_spi_label,
            cs=0,
            spi_max_hz=1_000_000,
            gpio_label=gpio_label,
            reset_gpio=None,
            dev_clk_ref=dev_clk_ref,
            firmware_name=firmware_name,
            subclass=int(adc.get("jesd", {}).get("subclass", 0)),
            side_b_separate_tpl=True,
            jrx0_physical_lane_mapping=(
                " ".join(str(v) for v in rx_physical) if rx_physical else None
            ),
            jtx0_logical_lane_mapping=(
                " ".join(str(v) for v in tx_logical) if tx_logical else None
            ),
            link_ids=" ".join(all_link_ids),
            jesd204_inputs=", ".join(tpl_inputs),
        )
        components.append(
            ComponentModel(
                role="transceiver",
                part="ad9084",
                template="ad9084.tmpl",
                spi_bus=converter_spi,
                spi_cs=0,
                config=ad9084_ctx,
            )
        )

        # --- Extra nodes (fixed clock for ADF4382 reference) ---
        extra_nodes: list[str] = []
        if has_adf4382:
            extra_nodes.append(
                "\tclkin_125: clock@0 {\n"
                "\t\t#clock-cells = <0>;\n"
                '\t\tcompatible = "fixed-clock";\n'
                "\t\tclock-frequency = <125000000>;\n"
                '\t\tclock-output-names = "clkin_125";\n'
                "\t};"
            )

        fpga_config = FpgaConfig(
            platform=self.platform,
            addr_cells=addr_cells,
            ps_clk_label=ps_clk_label,
            ps_clk_index=ps_clk_index,
            gpio_label=gpio_label,
        )

        return BoardModel(
            name=f"ad9084_{self.platform}",
            platform=self.platform,
            components=components,
            jesd_links=jesd_links,
            fpga_config=fpga_config,
            extra_nodes=extra_nodes,
            metadata={
                "base_dts_include": self.platform_config["base_dts_include"],
                "config_source": "jif_solver",
            },
        )

    def map_clocks_to_board_layout(self, cfg: dict) -> tuple:
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
