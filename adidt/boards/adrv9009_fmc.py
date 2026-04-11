"""ADRV9009 FMC board device tree generation support (JSON-based).

This module provides JSON-based device tree generation for the ADRV9009
evaluation board on ZCU102 and ZC706 platforms.

The ADRV9009 is a highly integrated RF transceiver that uses:
- AD9528 as the clock generator
- JESD204B for high-speed data interface

This is the JSON-based implementation using JSON configuration (like AD9081).

Reference: linux/arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-adrv9009.dts
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .layout import layout
from ..model.board_model import BoardModel, ComponentModel, FpgaConfig, JesdLinkModel
from ..model.contexts import (
    build_ad9528_1_ctx,
    build_adrv9009_device_ctx,
    build_adxcvr_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
    fmt_hz,
)


class adrv9009_fmc(layout):
    """ADRV9009 FMC board layout for JSON-based DT generation"""

    # Clock chip
    clock = "AD9528"

    # Transceiver
    transceiver = "ADRV9009"

    FPGA_LINK_KEYS = ["fpga_rx", "fpga_tx", "fpga_orx"]
    FPGA_DEFAULT_OUT_CLK = "XCVR_REFCLK"

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

    def __init__(self, platform: str = "zcu102", kernel_path: str | None = None) -> None:
        super().__init__(platform=platform, kernel_path=kernel_path)
        self.use_plugin_mode = False

    def to_board_model(self, cfg: dict) -> "BoardModel":
        """Build a :class:`BoardModel` from configuration.

        This maps the configuration through the existing board layout
        methods and produces a unified model that can be inspected,
        modified, and rendered via :class:`BoardModelRenderer`.

        Args:
            cfg (dict): Configuration dictionary (same dict passed to
                ``map_clocks_to_board_layout``).

        Returns:
            BoardModel: Editable board model.
        """
        cfg = self.validate_and_default_fpga_config(cfg)
        ccfg, rx, tx, orx, fpga = self.map_clocks_to_board_layout(cfg)

        spi_bus = self.platform_config.get("spi_bus", "spi0")
        vcxo_hz = int(ccfg.get("vcxo", 122_880_000))

        # --- Build clock channels from solver output ---
        channels = []
        for name, info in ccfg["map"].items():
            divider = int(info["divider"])
            ch_freq = vcxo_hz * 10 // divider if divider > 0 else 0
            is_sysref = "SYSREF" in name.upper()
            channels.append(
                {
                    "id": info["channel"],
                    "name": name,
                    "divider": divider,
                    "freq_str": fmt_hz(ch_freq) if not is_sysref else "",
                    "signal_source": 2 if is_sysref else 0,
                    "is_sysref": is_sysref,
                }
            )

        clock_ctx = build_ad9528_1_ctx(
            label="clk0_ad9528",
            cs=0,
            spi_max_hz=10_000_000,
            vcxo_hz=vcxo_hz,
            channels=channels,
        )

        # --- JESD parameters from framer/deframer configs ---
        rx_framer = rx.get("framer", {})
        tx_deframer = tx.get("deframer", {})
        orx_framer = orx.get("framer", {})

        rx_f = int(rx_framer.get("F", 4))
        rx_k = int(rx_framer.get("K", 32))
        rx_m = int(rx_framer.get("M", 4))
        rx_l = int(rx_framer.get("L", 2))
        rx_np = int(rx_framer.get("Np", 16))
        rx_s = int(rx_framer.get("S", 1))

        tx_f = int(tx_deframer.get("F", 4))
        tx_k = int(tx_deframer.get("K", 32))
        tx_m = int(tx_deframer.get("M", 4))
        tx_l = int(tx_deframer.get("L", 2))
        tx_np = int(tx_deframer.get("Np", 16))
        tx_s = int(tx_deframer.get("S", 1))

        orx_f = int(orx_framer.get("F", 4))
        orx_k = int(orx_framer.get("K", 32))
        orx_m = int(orx_framer.get("M", 2))
        orx_l = int(orx_framer.get("L", 2))
        orx_np = int(orx_framer.get("Np", 16))
        orx_s = int(orx_framer.get("S", 1))

        # --- FPGA PLL select mapping ---
        sys_clk_map = {
            "XCVR_CPLL": 0,
            "XCVR_QPLL1": 2,
            "XCVR_QPLL": 3,
            "XCVR_QPLL0": 3,
        }
        out_clk_map = {"XCVR_REFCLK": 4, "XCVR_REFCLK_DIV2": 4}

        rx_sys = int(sys_clk_map.get(str(fpga["fpga_rx"]["sys_clk_select"]).upper(), 0))
        tx_sys = int(sys_clk_map.get(str(fpga["fpga_tx"]["sys_clk_select"]).upper(), 3))
        orx_sys = int(
            sys_clk_map.get(str(fpga["fpga_orx"]["sys_clk_select"]).upper(), 0)
        )
        rx_out = int(
            out_clk_map.get(
                str(fpga["fpga_rx"].get("out_clk_select", "XCVR_REFCLK")).upper(),
                4,
            )
        )
        tx_out = int(
            out_clk_map.get(
                str(fpga["fpga_tx"].get("out_clk_select", "XCVR_REFCLK")).upper(),
                4,
            )
        )
        orx_out = int(
            out_clk_map.get(
                str(fpga["fpga_orx"].get("out_clk_select", "XCVR_REFCLK")).upper(),
                4,
            )
        )

        # --- IP labels ---
        clock_chip_label = "clk0_ad9528"
        rx_jesd_label = "axi_adrv9009_rx_jesd"
        tx_jesd_label = "axi_adrv9009_tx_jesd"
        orx_jesd_label = "axi_adrv9009_rx_os_jesd"
        rx_xcvr_label = "axi_adrv9009_rx_xcvr"
        tx_xcvr_label = "axi_adrv9009_tx_xcvr"
        orx_xcvr_label = "axi_adrv9009_rx_os_xcvr"
        rx_core_label = "axi_adrv9009_core_rx"
        tx_core_label = "axi_adrv9009_core_tx"
        orx_core_label = "axi_adrv9009_core_rx_obs"
        rx_dma_label = "axi_adrv9009_rx_dma"
        tx_dma_label = "axi_adrv9009_tx_dma"
        orx_dma_label = "axi_adrv9009_rx_os_dma"
        phy_label = "trx0_adrv9009"

        # --- Link IDs ---
        rx_link_id = 1
        tx_link_id = 0
        orx_link_id = 2

        # --- Transceiver clocks and JESD204 inputs ---
        trx_clocks_value = (
            f"<&{clock_chip_label} 13>, <&{clock_chip_label} 1>, "
            f"<&{clock_chip_label} 12>, <&{clock_chip_label} 3>"
        )
        trx_clock_names_value = (
            '"dev_clk", "fmc_clk", "sysref_dev_clk", "sysref_fmc_clk"'
        )
        trx_link_ids_value = f"{rx_link_id} {orx_link_id} {tx_link_id}"
        trx_inputs_value = (
            f"<&{rx_xcvr_label} 0 {rx_link_id}>, "
            f"<&{orx_xcvr_label} 0 {orx_link_id}>, "
            f"<&{tx_xcvr_label} 0 {tx_link_id}>"
        )

        # --- Profile properties block ---
        default_trx_profile_props = [
            "adi,rx-profile-rx-fir-num-fir-coefs = <48>;",
            "adi,rx-profile-rx-fir-coefs = /bits/ 16 <(-2) (23) (46) (-17) (-104) (10) (208) (23) (-370) (-97) (607) (240) (-942) (-489) (1407) (910) (-2065) (-1637) (3058) (2995) (-4912) (-6526) (9941) (30489) (30489) (9941) (-6526) (-4912) (2995) (3058) (-1637) (-2065) (910) (1407) (-489) (-942) (240) (607) (-97) (-370) (23) (208) (10) (-104) (-17) (46) (23) (-2)>;",
            "adi,rx-profile-rx-adc-profile = /bits/ 16 <182 142 173 90 1280 982 1335 96 1369 48 1012 18 48 48 37 208 0 0 0 0 52 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905>;",
            "adi,orx-profile-rx-fir-num-fir-coefs = <24>;",
            "adi,orx-profile-rx-fir-coefs = /bits/ 16 <(-10) (7) (-10) (-12) (6) (-12) (16) (-16) (1) (63) (-431) (17235) (-431) (63) (1) (-16) (16) (-12) (6) (-12) (-10) (7) (-10) (0)>;",
            "adi,orx-profile-orx-low-pass-adc-profile = /bits/ 16 <185 141 172 90 1280 942 1332 90 1368 46 1016 19 48 48 37 208 0 0 0 0 52 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905>;",
            "adi,orx-profile-orx-band-pass-adc-profile = /bits/ 16 <0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0>;",
            "adi,orx-profile-orx-merge-filter = /bits/ 16 <0 0 0 0 0 0 0 0 0 0 0 0>;",
            "adi,tx-profile-tx-fir-num-fir-coefs = <40>;",
            "adi,tx-profile-tx-fir-coefs = /bits/ 16 <(-14) (5) (-9) (6) (-4) (19) (-29) (27) (-30) (46) (-63) (77) (-103) (150) (-218) (337) (-599) (1266) (-2718) (19537) (-2718) (1266) (-599) (337) (-218) (150) (-103) (77) (-63) (46) (-30) (27) (-29) (19) (-4) (6) (-9) (5) (-14) (0)>;",
            "adi,tx-profile-loop-back-adc-profile = /bits/ 16 <206 132 168 90 1280 641 1307 53 1359 28 1039 30 48 48 37 210 0 0 0 0 53 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905>;",
        ]
        trx_profile_props = cfg.get("trx_profile_props", default_trx_profile_props)
        trx_profile_props_block = "".join(
            f"\t\t\t{prop}\n" for prop in trx_profile_props
        )

        # --- Build transceiver device context ---
        phy_ctx = build_adrv9009_device_ctx(
            phy_family="adrv9009",
            phy_compatible='"adi,adrv9009", "adrv9009"',
            trx_cs=1,
            spi_max_hz=25_000_000,
            gpio_label="gpio",
            trx_reset_gpio=130,
            trx_sysref_req_gpio=136,
            trx_clocks_value=trx_clocks_value,
            trx_clock_names_value=trx_clock_names_value,
            trx_link_ids_value=trx_link_ids_value,
            trx_inputs_value=trx_inputs_value,
            trx_profile_props_block=trx_profile_props_block,
            is_fmcomms8=False,
        )

        components = [
            ComponentModel(
                role="clock",
                part="ad9528_1",
                template="ad9528_1.tmpl",
                spi_bus=spi_bus,
                spi_cs=0,
                config=clock_ctx,
            ),
            ComponentModel(
                role="transceiver",
                part="adrv9009",
                template="adrv9009.tmpl",
                spi_bus=spi_bus,
                spi_cs=1,
                config=phy_ctx,
            ),
        ]

        # --- Platform clocking ---
        ps_clk_label = "zynqmp_clk"
        ps_clk_index = 71

        # --- RX link ---
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
                clk_ref=f"{clock_chip_label} 1",
                clock_output_names_str='"rx_gt_clk", "rx_out_clk"',
                jesd_l=rx_l,
                jesd_m=rx_m,
                jesd_s=rx_s,
                is_rx=True,
            ),
            jesd_overlay_config=build_jesd204_overlay_ctx(
                label=rx_jesd_label,
                direction="rx",
                clocks_str=(
                    f"<&{ps_clk_label} {ps_clk_index}>, "
                    f"<&{rx_xcvr_label} 1>, <&{rx_xcvr_label} 0>"
                ),
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name="jesd_rx_lane_clk",
                f=rx_f,
                k=rx_k,
                jesd204_inputs=f"{rx_xcvr_label} 0 {rx_link_id}",
            ),
            tpl_core_config=build_tpl_core_ctx(
                label=rx_core_label,
                compatible="adi,axi-adrv9009-rx-1.0",
                direction="rx",
                dma_label=rx_dma_label,
                spibus_label=phy_label,
                jesd_label=rx_jesd_label,
                jesd_link_offset=0,
                link_id=rx_link_id,
            ),
        )

        # --- TX link ---
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
                clk_ref=f"{clock_chip_label} 1",
                clock_output_names_str='"tx_gt_clk", "tx_out_clk"',
                jesd_l=tx_l,
                jesd_m=tx_m,
                jesd_s=tx_s,
                is_rx=False,
            ),
            jesd_overlay_config=build_jesd204_overlay_ctx(
                label=tx_jesd_label,
                direction="tx",
                clocks_str=(
                    f"<&{ps_clk_label} {ps_clk_index}>, "
                    f"<&{tx_xcvr_label} 1>, <&{tx_xcvr_label} 0>"
                ),
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name="jesd_tx_lane_clk",
                f=tx_f,
                k=tx_k,
                jesd204_inputs=f"{tx_xcvr_label} 0 {tx_link_id}",
                converter_resolution=14,
                converters_per_device=tx_m,
                bits_per_sample=tx_np,
                control_bits_per_sample=2,
            ),
            tpl_core_config=build_tpl_core_ctx(
                label=tx_core_label,
                compatible="adi,axi-adrv9009-tx-1.0",
                direction="tx",
                dma_label=tx_dma_label,
                spibus_label=phy_label,
                jesd_label=tx_jesd_label,
                jesd_link_offset=1,
                link_id=tx_link_id,
                pl_fifo_enable=True,
            ),
        )

        # --- ORX link ---
        orx_link = JesdLinkModel(
            direction="rx",
            jesd_label=orx_jesd_label,
            xcvr_label=orx_xcvr_label,
            core_label=orx_core_label,
            dma_label=orx_dma_label,
            link_params={
                "F": orx_f,
                "K": orx_k,
                "M": orx_m,
                "L": orx_l,
                "Np": orx_np,
                "S": orx_s,
            },
            xcvr_config=build_adxcvr_ctx(
                label=orx_xcvr_label,
                sys_clk_select=orx_sys,
                out_clk_select=orx_out,
                clk_ref=f"{clock_chip_label} 1",
                clock_output_names_str='"rx_os_gt_clk", "rx_os_out_clk"',
                jesd_l=orx_l,
                jesd_m=orx_m,
                jesd_s=orx_s,
                is_rx=True,
            ),
            jesd_overlay_config=build_jesd204_overlay_ctx(
                label=orx_jesd_label,
                direction="rx",
                clocks_str=(
                    f"<&{ps_clk_label} {ps_clk_index}>, "
                    f"<&{orx_xcvr_label} 1>, <&{orx_xcvr_label} 0>"
                ),
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name="jesd_rx_os_lane_clk",
                f=orx_f,
                k=orx_k,
                jesd204_inputs=f"{orx_xcvr_label} 0 {orx_link_id}",
            ),
            tpl_core_config=build_tpl_core_ctx(
                label=orx_core_label,
                compatible="adi,axi-adrv9009-obs-1.0",
                direction="rx",
                dma_label=orx_dma_label,
                spibus_label=phy_label,
                jesd_label=orx_jesd_label,
                jesd_link_offset=0,
                link_id=orx_link_id,
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
            name=f"adrv9009_fmc_{self.platform}",
            platform=self.platform,
            components=components,
            jesd_links=[rx_link, tx_link, orx_link],
            fpga_config=fpga_config,
            metadata={
                "base_dts_include": self.platform_config["base_dts_include"],
                "config_source": "jif_solver",
            },
        )

    def gen_dt_preprocess(self, **kwargs: Any) -> dict[str, Any]:
        """Add metadata to template rendering context."""
        kwargs["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        kwargs["platform"] = self.platform
        kwargs["base_dts_include"] = self.platform_config["base_dts_include"]
        kwargs["spi_bus"] = self.platform_config["spi_bus"]
        kwargs["config_source"] = kwargs.get("config_source", "unknown")
        return kwargs

    def map_clocks_to_board_layout(self, cfg: dict) -> tuple:
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
        rx.update(
            {
                "profile": rx_prof,
                "framer": cfg.get("jesd204", {}).get("framer_a", {}),
            }
        )

        # TX configuration (deframer)
        tx_prof = cfg.get("tx_profile", {})
        tx = extract_profile_fields(tx_prof)
        tx.update(
            {
                "profile": tx_prof,
                "deframer": cfg.get("jesd204", {}).get("deframer_a", {}),
            }
        )

        # ORX configuration (framer B)
        orx_prof = cfg.get("orx_profile", {})
        orx = extract_profile_fields(orx_prof)
        orx.update(
            {
                "profile": orx_prof,
                "framer": cfg.get("jesd204", {}).get("framer_b", {}),
            }
        )

        # FPGA configuration
        fpga = {
            "fpga_rx": cfg.get("fpga_rx", {}),
            "fpga_tx": cfg.get("fpga_tx", {}),
            "fpga_orx": cfg.get("fpga_orx", {}),
        }

        return ccfg, rx, tx, orx, fpga
