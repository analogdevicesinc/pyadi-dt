from datetime import datetime

import numpy as np

from ..model.board_model import BoardModel, ComponentModel, FpgaConfig, JesdLinkModel
from ..model.contexts import (
    build_ad9081_mxfe_ctx,
    build_adxcvr_ctx,
    build_hmc7044_channel_ctx,
    build_hmc7044_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
)
from .layout import layout


class ad9081_fmc(layout):
    """AD9081 FMC board layout map for clocks and DSP"""

    clock = "HMC7044"

    adc = "ad9081_rx"
    dac = "ad9081_tx"

    FPGA_LINK_KEYS = ["fpga_adc", "fpga_dac"]

    # Platform-specific configurations
    PLATFORM_CONFIGS = {
        "zcu102": {
            "template_filename": "ad9081_fmc_zcu102.tmpl",
            "base_dts_file": "arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev1.0.dts",
            "base_dts_include": "zynqmp-zcu102-rev1.0.dts",
            "arch": "arm64",
            "jesd_phy": "GTH",
            "default_fpga_adc_pll": "XCVR_QPLL",
            "default_fpga_dac_pll": "XCVR_QPLL",
            "spi_bus": "spi1",
            "output_dir": "generated_dts",
        },
        "vpk180": {
            "template_filename": "ad9081_fmc_vpk180.tmpl",
            "base_dts_file": "arch/arm64/boot/dts/xilinx/versal-vpk180-revA.dts",
            "base_dts_include": "versal-vpk180-revA.dts",
            "arch": "arm64",
            "jesd_phy": "GTY",
            "default_fpga_adc_pll": "XCVR_QPLL0",
            "default_fpga_dac_pll": "XCVR_QPLL0",
            "spi_bus": "spi1",
            "output_dir": "generated_dts",
        },
        "zc706": {
            "template_filename": "ad9081_fmc_zc706.tmpl",
            "base_dts_file": "arch/arm/boot/dts/zynq-zc706.dts",
            "base_dts_include": "zynq-zc706.dts",
            "arch": "arm",
            "jesd_phy": "GTX",
            "default_fpga_adc_pll": "XCVR_QPLL",
            "default_fpga_dac_pll": "XCVR_QPLL",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
    }

    def __init__(self, platform="zcu102", kernel_path=None):
        super().__init__(platform=platform, kernel_path=kernel_path)
        self.use_plugin_mode = False

    def map_jesd_structs(self, cfg: dict) -> tuple:
        """Map JIF configuration to integer structs.

        Args:
            cfg (dict): JIF configuration.

        Returns:
            dict: ADC JESD structs.
            dict: DAC JESD structs.
        """
        adc = cfg["converter"]
        adc["jesd"] = cfg["jesd_adc"]
        adc["jesd"]["jesd_class_int"] = self.map_jesd_subclass(
            adc["jesd"]["jesd_class"]
        )
        dac = cfg["converter"].copy()
        dac["jesd"] = cfg["jesd_dac"]
        dac["jesd"]["jesd_class_int"] = self.map_jesd_subclass(
            dac["jesd"]["jesd_class"]
        )

        adc["jesd"] = self.make_ints(adc["jesd"], ["converter_clock", "sample_clock"])
        dac["jesd"] = self.make_ints(dac["jesd"], ["converter_clock", "sample_clock"])

        adc["datapath"] = cfg["datapath_adc"]
        dac["datapath"] = cfg["datapath_dac"]

        return adc, dac

    # ------------------------------------------------------------------
    # Helper functions for AD9081 lane / converter mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _lane_map(lanes: int) -> str:
        """Return a space-separated 8-element lane-mapping string padded with 7."""
        lane_count = max(1, min(lanes, 8))
        values = list(range(lane_count)) + [7] * (8 - lane_count)
        return " ".join(str(v) for v in values)

    @staticmethod
    def _lane_map_for_mode(direction: str, lanes: int, link_mode: int) -> str:
        """Return the board-specific ``adi,logical-lane-mapping`` string."""
        if direction == "tx" and link_mode == 17 and lanes == 8:
            return "0 2 7 6 1 5 4 3"
        if direction == "rx" and link_mode == 18 and lanes == 8:
            return "2 0 7 6 5 4 3 1"
        if direction == "tx" and link_mode == 9 and lanes == 4:
            return "0 2 7 7 1 7 7 3"
        if direction == "rx" and link_mode == 10 and lanes == 4:
            return "2 0 7 7 7 7 3 1"
        lane_count = max(1, min(lanes, 8))
        values = list(range(lane_count)) + [7] * (8 - lane_count)
        return " ".join(str(v) for v in values)

    @staticmethod
    def _converter_select_rx(rx_m: int, rx_link_mode: int) -> str:
        """Return the ``adi,converter-select`` phandle list for AD9081 RX."""
        if rx_link_mode == 18 and rx_m == 4:
            return (
                "<&ad9081_rx_fddc_chan0 0>, <&ad9081_rx_fddc_chan0 1>, "
                "<&ad9081_rx_fddc_chan1 0>, <&ad9081_rx_fddc_chan1 1>"
            )
        if rx_m >= 8:
            return (
                "<&ad9081_rx_fddc_chan0 0>, <&ad9081_rx_fddc_chan0 1>, "
                "<&ad9081_rx_fddc_chan1 0>, <&ad9081_rx_fddc_chan1 1>, "
                "<&ad9081_rx_fddc_chan2 0>, <&ad9081_rx_fddc_chan2 1>, "
                "<&ad9081_rx_fddc_chan3 0>, <&ad9081_rx_fddc_chan3 1>"
            )
        return ", ".join(
            f"<&ad9081_rx_fddc_chan{i} 0>" for i in range(max(1, min(rx_m, 8)))
        )

    @staticmethod
    def _converter_select_tx(tx_m: int, tx_link_mode: int) -> str:
        """Return the ``adi,converter-select`` phandle list for AD9081 TX."""
        if tx_link_mode == 17 and tx_m == 4:
            return (
                "<&ad9081_tx_fddc_chan0 0>, <&ad9081_tx_fddc_chan0 1>, "
                "<&ad9081_tx_fddc_chan1 0>, <&ad9081_tx_fddc_chan1 1>"
            )
        if tx_m >= 8:
            return (
                "<&ad9081_tx_fddc_chan0 0>, <&ad9081_tx_fddc_chan0 1>, "
                "<&ad9081_tx_fddc_chan1 0>, <&ad9081_tx_fddc_chan1 1>, "
                "<&ad9081_tx_fddc_chan2 0>, <&ad9081_tx_fddc_chan2 1>, "
                "<&ad9081_tx_fddc_chan3 0>, <&ad9081_tx_fddc_chan3 1>"
            )
        return ", ".join(
            f"<&ad9081_tx_fddc_chan{i} 0>" for i in range(max(1, min(tx_m, 8)))
        )

    # ------------------------------------------------------------------
    # Board model builder
    # ------------------------------------------------------------------

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

        # --- HMC7044 clock channels from solver output ---
        pll2_hz = int(ccfg["clock"]["vco"])
        hmc7044_channels = build_hmc7044_channel_ctx(
            pll2_hz,
            [
                {
                    "id": info["source_port"],
                    "name": name,
                    "divider": int(info["divider"]),
                    "driver_mode": 2,
                    "is_sysref": name in ("DEV_SYSREF", "FPGA_SYSREF"),
                }
                for name, info in ccfg["map"].items()
            ],
        )

        hmc7044_clock_output_names = [f"hmc7044_out{i}" for i in range(14)]

        clock_ctx = build_hmc7044_ctx(
            label="hmc7044",
            cs=0,
            spi_max_hz=1_000_000,
            pll1_clkin_frequencies=[int(ccfg["clock"]["vcxo"]), 0, 0, 0],
            vcxo_hz=int(ccfg["clock"]["vcxo"]),
            pll2_output_hz=pll2_hz,
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
        )

        # --- JESD parameters ---
        rx_m = int(adc["jesd"].get("M", 8))
        rx_l = int(adc["jesd"].get("L", 4))
        rx_f = int(adc["jesd"].get("F", 2))
        rx_k = int(adc["jesd"].get("K", 32))
        rx_np = int(adc["jesd"].get("Np", 16))
        rx_s = int(adc["jesd"].get("S", 1))
        rx_link_mode = int(adc["jesd"].get("jesd_mode", 9))

        tx_m = int(dac["jesd"].get("M", 8))
        tx_l = int(dac["jesd"].get("L", 4))
        tx_f = int(dac["jesd"].get("F", 4))
        tx_k = int(dac["jesd"].get("K", 32))
        tx_np = int(dac["jesd"].get("Np", 16))
        tx_s = int(dac["jesd"].get("S", 1))
        tx_link_mode = int(dac["jesd"].get("jesd_mode", 10))

        # --- Datapath config ---
        adc_frequency_hz = int(adc["jesd"].get("converter_clock", 4_000_000_000))
        dac_frequency_hz = int(dac["jesd"].get("converter_clock", 12_000_000_000))

        rx_cddc_decimation = int(adc["datapath"]["cddc"]["decimations"][0])
        rx_fddc_decimation = int(adc["datapath"]["fddc"]["decimations"][0])
        tx_cduc_interpolation = int(dac["datapath"]["cduc"]["interpolation"])
        tx_fduc_interpolation = int(dac["datapath"]["fduc"]["interpolation"])

        # --- Converter / lane mapping ---
        rx_converter_select = self._converter_select_rx(rx_m, rx_link_mode)
        tx_converter_select = self._converter_select_tx(tx_m, tx_link_mode)
        rx_lane_map = self._lane_map_for_mode("rx", rx_l, rx_link_mode)
        tx_lane_map = self._lane_map_for_mode("tx", tx_l, tx_link_mode)

        # --- JESD link IDs ---
        rx_link_id = 2
        tx_link_id = 0

        # --- AD9081 MxFE device context ---
        rx_core_label = "rx_mxfe_tpl_core_adc_tpl_core"
        tx_core_label = "tx_mxfe_tpl_core_dac_tpl_core"

        mxfe_ctx = build_ad9081_mxfe_ctx(
            label="trx0_ad9081",
            cs=1,
            gpio_label="gpio",
            reset_gpio=133,
            sysref_req_gpio=121,
            rx2_enable_gpio=135,
            rx1_enable_gpio=134,
            tx2_enable_gpio=137,
            tx1_enable_gpio=136,
            dev_clk_ref="hmc7044 2",
            rx_core_label=rx_core_label,
            tx_core_label=tx_core_label,
            rx_link_id=rx_link_id,
            tx_link_id=tx_link_id,
            dac_frequency_hz=dac_frequency_hz,
            tx_cduc_interpolation=tx_cduc_interpolation,
            tx_fduc_interpolation=tx_fduc_interpolation,
            tx_converter_select=tx_converter_select,
            tx_lane_map=tx_lane_map,
            tx_link_mode=tx_link_mode,
            tx_m=tx_m,
            tx_f=tx_f,
            tx_k=tx_k,
            tx_l=tx_l,
            tx_s=tx_s,
            adc_frequency_hz=adc_frequency_hz,
            rx_cddc_decimation=rx_cddc_decimation,
            rx_fddc_decimation=rx_fddc_decimation,
            rx_converter_select=rx_converter_select,
            rx_lane_map=rx_lane_map,
            rx_link_mode=rx_link_mode,
            rx_m=rx_m,
            rx_f=rx_f,
            rx_k=rx_k,
            rx_l=rx_l,
            rx_s=rx_s,
        )

        # --- Components ---
        components = [
            ComponentModel(
                role="clock",
                part="hmc7044",
                template="hmc7044.tmpl",
                spi_bus=spi_bus,
                spi_cs=0,
                config=clock_ctx,
            ),
            ComponentModel(
                role="transceiver",
                part="ad9081",
                template="ad9081_mxfe.tmpl",
                spi_bus=spi_bus,
                spi_cs=1,
                config=mxfe_ctx,
            ),
        ]

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

        # --- JESD link labels ---
        rx_jesd_label = "axi_mxfe_rx_jesd_rx_axi"
        tx_jesd_label = "axi_mxfe_tx_jesd_tx_axi"
        rx_xcvr_label = "axi_mxfe_rx_xcvr"
        tx_xcvr_label = "axi_mxfe_tx_xcvr"
        rx_dma_label = "axi_mxfe_rx_dma"
        tx_dma_label = "axi_mxfe_tx_dma"

        ps_clk_label = "zynqmp_clk"
        ps_clk_index = 71

        # --- RX JESD link ---
        rx_link = JesdLinkModel(
            direction="rx",
            jesd_label=rx_jesd_label,
            xcvr_label=rx_xcvr_label,
            core_label=rx_core_label,
            dma_label=rx_dma_label,
            link_params={
                "F": rx_f,
                "K": rx_k,
                "M": rx_m,
                "L": rx_l,
                "Np": rx_np,
                "S": rx_s,
            },
            xcvr_config=build_adxcvr_ctx(
                label=rx_xcvr_label,
                sys_clk_select=rx_sys,
                out_clk_select=rx_out,
                clk_ref="hmc7044 12",
                use_div40=False,
                clock_output_names_str='"rx_gt_clk", "rx_out_clk"',
                use_lpm_enable=True,
                jesd_l=rx_l,
                jesd_m=rx_m,
                jesd_s=rx_s,
                jesd204_inputs=f"hmc7044 0 {rx_link_id}",
                is_rx=True,
            ),
            jesd_overlay_config=build_jesd204_overlay_ctx(
                label=rx_jesd_label,
                direction="rx",
                clocks_str=(
                    f"<&{ps_clk_label} {ps_clk_index}>, "
                    "<&hmc7044 10>, "
                    f"<&{rx_xcvr_label} 0>"
                ),
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name=None,
                f=rx_f,
                k=rx_k,
                jesd204_inputs=f"{rx_xcvr_label} 0 {rx_link_id}",
            ),
            tpl_core_config=build_tpl_core_ctx(
                label=rx_core_label,
                compatible="adi,axi-ad9081-rx-1.0",
                direction="rx",
                dma_label=rx_dma_label,
                spibus_label="trx0_ad9081",
                jesd_label=rx_jesd_label,
                jesd_link_offset=0,
                link_id=rx_link_id,
                pl_fifo_enable=False,
            ),
        )

        # --- TX JESD link ---
        tx_link = JesdLinkModel(
            direction="tx",
            jesd_label=tx_jesd_label,
            xcvr_label=tx_xcvr_label,
            core_label=tx_core_label,
            dma_label=tx_dma_label,
            link_params={
                "F": tx_f,
                "K": tx_k,
                "M": tx_m,
                "L": tx_l,
                "Np": tx_np,
                "S": tx_s,
            },
            xcvr_config=build_adxcvr_ctx(
                label=tx_xcvr_label,
                sys_clk_select=tx_sys,
                out_clk_select=tx_out,
                clk_ref="hmc7044 12",
                use_div40=False,
                clock_output_names_str='"tx_gt_clk", "tx_out_clk"',
                use_lpm_enable=False,
                jesd_l=tx_l,
                jesd_m=tx_m,
                jesd_s=tx_s,
                jesd204_inputs=f"hmc7044 0 {tx_link_id}",
                is_rx=False,
            ),
            jesd_overlay_config=build_jesd204_overlay_ctx(
                label=tx_jesd_label,
                direction="tx",
                clocks_str=(
                    f"<&{ps_clk_label} {ps_clk_index}>, "
                    "<&hmc7044 6>, "
                    f"<&{tx_xcvr_label} 0>"
                ),
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name=None,
                f=tx_f,
                k=tx_k,
                jesd204_inputs=f"{tx_xcvr_label} 0 {tx_link_id}",
            ),
            tpl_core_config=build_tpl_core_ctx(
                label=tx_core_label,
                compatible="adi,axi-ad9081-tx-1.0",
                direction="tx",
                dma_label=tx_dma_label,
                spibus_label="trx0_ad9081",
                jesd_label=tx_jesd_label,
                jesd_link_offset=0,
                link_id=tx_link_id,
                pl_fifo_enable=False,
                sampl_clk_ref="trx0_ad9081 1",
                sampl_clk_name="sampl_clk",
            ),
        )

        # --- FPGA config ---
        fpga_config = FpgaConfig(
            platform=self.platform,
            addr_cells=2,
            ps_clk_label=ps_clk_label,
            ps_clk_index=ps_clk_index,
            gpio_label="gpio",
        )

        return BoardModel(
            name=f"ad9081_fmc_{self.platform}",
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
        kwargs["base_dts_include"] = self.platform_config["base_dts_include"]
        kwargs["config_source"] = kwargs.get("config_source", "unknown")
        return kwargs

    def map_clocks_to_board_layout(self, cfg: dict) -> tuple:
        """Map JIF configuration to board clock connection layout.

        Args:
            cfg (dict): JIF configuration.

        Returns:
            dict: Board clock connection layout.
        """
        # Fix ups
        for key in ["vco", "vcxo"]:
            if isinstance(cfg["clock"][key], float) and cfg["clock"][key].is_integer():
                cfg["clock"][key] = int(cfg["clock"][key])

        map = {}
        clk = cfg["clock"]["output_clocks"]

        # Common
        map["DEV_REFCLK"] = {
            "source_port": 2,
            "divider": clk["AD9081_ref_clk"]["divider"],
        }
        map["DEV_SYSREF"] = {
            "source_port": 3,
            "divider": np.max(
                [clk["adc_sysref"]["divider"], clk["dac_sysref"]["divider"]]
            ),
        }
        map["FPGA_SYSREF"] = {
            "source_port": 13,
            "divider": np.max(
                [clk["adc_fpga_ref_clk"]["divider"], clk["dac_sysref"]["divider"]]
            ),
        }

        # RX side
        map["CORE_CLK_RX"] = {
            "source_port": 0,
            "divider": clk["adc_fpga_link_out_clk"]["divider"],
        }
        map["CORE_CLK_RX_ALT"] = {
            "source_port": 10,
            "divider": clk["adc_fpga_link_out_clk"]["divider"] * 1,
        }
        map["FPGA_REFCLK1"] = {
            "source_port": 8,
            "divider": clk["adc_fpga_ref_clk"]["divider"],
        }

        # Tx side
        map["CORE_CLK_TX"] = {
            "source_port": 6,
            "divider": clk["dac_fpga_link_out_clk"]["divider"],
        }
        map["FPGA_REFCLK2"] = {
            "source_port": 12,
            "divider": clk["dac_fpga_ref_clk"]["divider"],
        }

        ccfg = {"map": map, "clock": cfg["clock"]}

        fpga = {}
        fpga["fpga_adc"] = cfg["fpga_adc"]
        fpga["fpga_dac"] = cfg["fpga_dac"]

        # Check all clocks are mapped
        # FIXME

        # Check no source_port is mapped to more than one clock
        # FIXME
        adc, dac = self.map_jesd_structs(cfg)

        # Section disables
        adc["fddc_enabled"] = any(cfg["datapath_adc"]["fddc"]["enabled"])
        dac["fduc_enabled"] = any(cfg["datapath_dac"]["fduc"]["enabled"])

        # Change QPLL0 to naming in kernel
        if fpga["fpga_dac"]["sys_clk_select"] == "XCVR_QPLL0":
            fpga["fpga_dac"]["sys_clk_select"] = "XCVR_QPLL"
        if fpga["fpga_adc"]["sys_clk_select"] == "XCVR_QPLL0":
            fpga["fpga_adc"]["sys_clk_select"] = "XCVR_QPLL"

        return ccfg, adc, dac, fpga
