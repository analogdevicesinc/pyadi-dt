"""AD9081 MxFE board builder (HMC7044 + AD9081/AD9082/AD9083).

Handles boards with an HMC7044 clock distribution IC and AD9081 MxFE converter.
Topology match: converter IP ``axi_ad9081`` AND ``mxfe`` in JESD instance names.
"""

from __future__ import annotations

from typing import Any

from ...model.board_model import (
    BoardModel,
    ComponentModel,
    FpgaConfig,
    JesdLinkModel,
)
from ...model.contexts import (
    build_ad9081_mxfe_ctx,
    build_adxcvr_ctx,
    build_hmc7044_channel_ctx,
    build_hmc7044_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
    coerce_board_int,
)
from ...model.renderer import BoardModelRenderer
from ..topology import XsaTopology

# (M, L) -> (rx_link_mode, tx_link_mode)
_AD9081_LINK_MODE_BY_ML: dict[tuple[int, int], tuple[int, int]] = {
    (8, 4): (17, 18),
    (4, 8): (10, 11),
}


def _resolve_link_mode(
    ad9081_cfg: dict[str, Any],
    jesd_cfg: dict[str, Any],
    direction: str,
) -> int:
    """Determine the AD9081 link mode for *direction* from config or by inference."""
    from ..exceptions import ConfigError

    explicit = ad9081_cfg.get(f"{direction}_link_mode")
    if explicit is not None:
        return int(explicit)

    alt_explicit = jesd_cfg.get(direction, {}).get("mode")
    if alt_explicit is not None:
        return int(alt_explicit)

    m = int(jesd_cfg.get(direction, {}).get("M", 0))
    lanes = int(jesd_cfg.get(direction, {}).get("L", 0))
    modes = _AD9081_LINK_MODE_BY_ML.get((m, lanes))
    if modes is None:
        raise ConfigError(
            f"ad9081.{direction}_link_mode "
            f"(missing and could not infer for M={m}, L={lanes})"
        )
    return modes[0] if direction == "rx" else modes[1]


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


def _lane_map(lanes: int) -> str:
    """Return a space-separated 8-element lane-mapping string padded with 7."""
    lane_count = max(1, min(lanes, 8))
    values = list(range(lane_count)) + [7] * (8 - lane_count)
    return " ".join(str(v) for v in values)


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
    return _lane_map(lanes)


def _format_nested_block(block: str, prefix: str = "\t\t\t") -> str:
    """Re-indent each line of *block* with *prefix* and return the result."""
    lines = block.strip("\n").splitlines()
    if not lines:
        return ""
    return "".join(f"{prefix}{line.lstrip()}\n" for line in lines)


class AD9081Builder:
    """Board builder for AD9081/AD9082/AD9083 MxFE designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        has_ad9081 = any(c.ip_type == "axi_ad9081" for c in topology.converters)
        has_mxfe = any(
            "mxfe" in j.name.lower() for j in topology.jesd204_rx + topology.jesd204_tx
        )
        return has_ad9081 and has_mxfe

    def build_nodes(
        self,
        node_builder: Any,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        model = self.build_model(topology, cfg, ps_clk_label, ps_clk_index, gpio_label)
        rendered = BoardModelRenderer().render(model)
        nodes: list[str] = []
        nodes.extend(rendered["converters"])
        nodes.extend(rendered["jesd204_rx"])
        nodes.extend(rendered["jesd204_tx"])
        return nodes

    def build_model(
        self,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> BoardModel:
        """Construct a :class:`BoardModel` for an AD9081 MxFE design."""
        platform = topology.inferred_platform()

        # --- Extract config ---
        clock_cfg = cfg.get("clock", {})
        jesd_cfg = cfg.get("jesd", {})
        rx_cfg = jesd_cfg.get("rx", {})
        tx_cfg = jesd_cfg.get("tx", {})
        ad9081_cfg = cfg.get("ad9081", {})
        board_cfg = cfg.get("ad9081_board", {})

        def board_int(key: str, default: Any) -> int:
            return coerce_board_int(board_cfg.get(key, default), f"ad9081_board.{key}")

        # JESD parameters
        rx_f = int(rx_cfg.get("F", 4))
        rx_k = int(rx_cfg.get("K", 32))
        rx_m = int(rx_cfg.get("M", 8))
        rx_l = int(rx_cfg.get("L", 4))
        rx_s = int(rx_cfg.get("S", 1))
        tx_f = int(tx_cfg.get("F", 4))
        tx_k = int(tx_cfg.get("K", 32))
        tx_m = int(tx_cfg.get("M", 8))
        tx_l = int(tx_cfg.get("L", 4))
        tx_s = int(tx_cfg.get("S", 1))

        # Link modes
        rx_link_mode = _resolve_link_mode(ad9081_cfg, jesd_cfg, "rx")
        tx_link_mode = _resolve_link_mode(ad9081_cfg, jesd_cfg, "tx")

        # AD9081 datapath config
        adc_frequency_hz = int(ad9081_cfg.get("adc_frequency_hz", 4_000_000_000))
        dac_frequency_hz = int(ad9081_cfg.get("dac_frequency_hz", 12_000_000_000))
        rx_cddc_decimation = int(ad9081_cfg.get("rx_cddc_decimation", 4))
        rx_fddc_decimation = int(ad9081_cfg.get("rx_fddc_decimation", 4))
        tx_cduc_interpolation = int(ad9081_cfg.get("tx_cduc_interpolation", 8))
        tx_fduc_interpolation = int(ad9081_cfg.get("tx_fduc_interpolation", 6))

        # XCVR PLL selection
        rx_sys_clk_select = int(ad9081_cfg.get("rx_sys_clk_select", 3))
        tx_sys_clk_select = int(ad9081_cfg.get("tx_sys_clk_select", 3))
        rx_out_clk_select = int(ad9081_cfg.get("rx_out_clk_select", 4))
        tx_out_clk_select = int(ad9081_cfg.get("tx_out_clk_select", 4))

        # JESD link IDs
        rx_link_id = int(ad9081_cfg.get("rx_link_id", 2))
        tx_link_id = int(ad9081_cfg.get("tx_link_id", 0))

        # Converter / lane mapping
        rx_converter_select = _converter_select_rx(rx_m, rx_link_mode)
        tx_converter_select = _converter_select_tx(tx_m, tx_link_mode)
        rx_lane_map = _lane_map_for_mode("rx", rx_l, rx_link_mode)
        tx_lane_map = _lane_map_for_mode("tx", tx_l, tx_link_mode)

        # Board-level SPI / GPIO config
        clock_spi = str(board_cfg.get("clock_spi", "spi1"))
        clock_cs = board_int("clock_cs", 0)
        adc_spi = str(board_cfg.get("adc_spi", "spi0"))
        adc_cs = board_int("adc_cs", 0)
        reset_gpio = board_int("reset_gpio", 133)
        sysref_req_gpio = board_int("sysref_req_gpio", 121)
        rx2_enable_gpio = board_int("rx2_enable_gpio", 135)
        rx1_enable_gpio = board_int("rx1_enable_gpio", 134)
        tx2_enable_gpio = board_int("tx2_enable_gpio", 137)
        tx1_enable_gpio = board_int("tx1_enable_gpio", 136)

        # HMC7044 clock channel indices for device clocks
        rx_chan = int(clock_cfg.get("hmc7044_rx_channel", 10))
        tx_chan = int(clock_cfg.get("hmc7044_tx_channel", 6))

        # --- HMC7044 channel configuration ---
        _pll2 = 3_000_000_000
        custom_hmc7044_blocks = board_cfg.get("hmc7044_channel_blocks")
        if custom_hmc7044_blocks:
            raw_channels = "".join(
                _format_nested_block(str(block)) for block in custom_hmc7044_blocks
            )
            hmc7044_channels = None
        else:
            raw_channels = None
            hmc7044_channels = build_hmc7044_channel_ctx(
                _pll2,
                [
                    {"id": 0, "name": "CORE_CLK_RX", "divider": 12, "driver_mode": 2},
                    {"id": 2, "name": "DEV_REFCLK", "divider": 12, "driver_mode": 2},
                    {
                        "id": 3,
                        "name": "DEV_SYSREF",
                        "divider": 1536,
                        "driver_mode": 2,
                        "is_sysref": True,
                    },
                    {"id": 6, "name": "CORE_CLK_TX", "divider": 12, "driver_mode": 2},
                    {"id": 8, "name": "FPGA_REFCLK1", "divider": 6, "driver_mode": 2},
                    {
                        "id": 10,
                        "name": "CORE_CLK_RX_ALT",
                        "divider": 12,
                        "driver_mode": 2,
                    },
                    {"id": 12, "name": "FPGA_REFCLK2", "divider": 6, "driver_mode": 2},
                    {
                        "id": 13,
                        "name": "FPGA_SYSREF",
                        "divider": 1536,
                        "driver_mode": 2,
                        "is_sysref": True,
                    },
                ],
            )

        hmc7044_clock_output_names = [f"hmc7044_out{i}" for i in range(14)]

        hmc7044_ctx = build_hmc7044_ctx(
            label="hmc7044",
            cs=clock_cs,
            spi_max_hz=1_000_000,
            pll1_clkin_frequencies=[122_880_000, 10_000_000, 0, 0],
            vcxo_hz=122_880_000,
            pll2_output_hz=_pll2,
            clock_output_names=hmc7044_clock_output_names,
            channels=hmc7044_channels,
            raw_channels=raw_channels,
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

        # --- AD9081 MxFE device context ---
        mxfe_ctx = build_ad9081_mxfe_ctx(
            label="trx0_ad9081",
            cs=adc_cs,
            gpio_label=gpio_label,
            reset_gpio=reset_gpio,
            sysref_req_gpio=sysref_req_gpio,
            rx2_enable_gpio=rx2_enable_gpio,
            rx1_enable_gpio=rx1_enable_gpio,
            tx2_enable_gpio=tx2_enable_gpio,
            tx1_enable_gpio=tx1_enable_gpio,
            dev_clk_ref="hmc7044 2",
            rx_core_label="rx_mxfe_tpl_core_adc_tpl_core",
            tx_core_label="tx_mxfe_tpl_core_dac_tpl_core",
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
                spi_bus=clock_spi,
                spi_cs=clock_cs,
                config=hmc7044_ctx,
            ),
            ComponentModel(
                role="transceiver",
                part="ad9081",
                template="ad9081_mxfe.tmpl",
                spi_bus=adc_spi,
                spi_cs=adc_cs,
                config=mxfe_ctx,
            ),
        ]

        # --- JESD link labels (from topology) ---
        rx_jesd_labels = [
            j.name.replace("-", "_")
            for j in topology.jesd204_rx
            if "mxfe" in j.name.lower()
        ]
        tx_jesd_labels = [
            j.name.replace("-", "_")
            for j in topology.jesd204_tx
            if "mxfe" in j.name.lower()
        ]
        rx_jesd_label = (
            rx_jesd_labels[0] if rx_jesd_labels else "axi_mxfe_rx_jesd_rx_axi"
        )
        tx_jesd_label = (
            tx_jesd_labels[0] if tx_jesd_labels else "axi_mxfe_tx_jesd_tx_axi"
        )

        # --- RX JESD link ---
        rx_xcvr_ctx = build_adxcvr_ctx(
            label="axi_mxfe_rx_xcvr",
            sys_clk_select=rx_sys_clk_select,
            out_clk_select=rx_out_clk_select,
            clk_ref="hmc7044 12",
            use_div40=False,
            clock_output_names_str='"rx_gt_clk", "rx_out_clk"',
            use_lpm_enable=True,
            jesd_l=rx_l,
            jesd_m=rx_m,
            jesd_s=rx_s,
            jesd204_inputs=f"hmc7044 0 {rx_link_id}",
            is_rx=True,
        )
        rx_jesd_overlay_ctx = build_jesd204_overlay_ctx(
            label=rx_jesd_label,
            direction="rx",
            clocks_str=(
                f"<&{ps_clk_label} {ps_clk_index}>, "
                f"<&hmc7044 {rx_chan}>, "
                "<&axi_mxfe_rx_xcvr 0>"
            ),
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            clock_output_name=None,
            f=rx_f,
            k=rx_k,
            jesd204_inputs=f"axi_mxfe_rx_xcvr 0 {rx_link_id}",
        )
        rx_tpl_ctx = build_tpl_core_ctx(
            label="rx_mxfe_tpl_core_adc_tpl_core",
            compatible="adi,axi-ad9081-rx-1.0",
            direction="rx",
            dma_label="axi_mxfe_rx_dma",
            spibus_label="trx0_ad9081",
            jesd_label=rx_jesd_label,
            jesd_link_offset=0,
            link_id=rx_link_id,
            pl_fifo_enable=False,
        )
        rx_link = JesdLinkModel(
            direction="rx",
            jesd_label=rx_jesd_label,
            xcvr_label="axi_mxfe_rx_xcvr",
            core_label="rx_mxfe_tpl_core_adc_tpl_core",
            dma_label="axi_mxfe_rx_dma",
            link_params={
                "F": rx_f,
                "K": rx_k,
                "M": rx_m,
                "L": rx_l,
                "Np": 16,
                "S": rx_s,
            },
            xcvr_config=rx_xcvr_ctx,
            jesd_overlay_config=rx_jesd_overlay_ctx,
            tpl_core_config=rx_tpl_ctx,
        )

        # --- TX JESD link ---
        tx_xcvr_ctx = build_adxcvr_ctx(
            label="axi_mxfe_tx_xcvr",
            sys_clk_select=tx_sys_clk_select,
            out_clk_select=tx_out_clk_select,
            clk_ref="hmc7044 12",
            use_div40=False,
            clock_output_names_str='"tx_gt_clk", "tx_out_clk"',
            use_lpm_enable=False,
            jesd_l=tx_l,
            jesd_m=tx_m,
            jesd_s=tx_s,
            jesd204_inputs=f"hmc7044 0 {tx_link_id}",
            is_rx=False,
        )
        tx_jesd_overlay_ctx = build_jesd204_overlay_ctx(
            label=tx_jesd_label,
            direction="tx",
            clocks_str=(
                f"<&{ps_clk_label} {ps_clk_index}>, "
                f"<&hmc7044 {tx_chan}>, "
                "<&axi_mxfe_tx_xcvr 0>"
            ),
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            clock_output_name=None,
            f=tx_f,
            k=tx_k,
            jesd204_inputs=f"axi_mxfe_tx_xcvr 0 {tx_link_id}",
        )
        tx_tpl_ctx = build_tpl_core_ctx(
            label="tx_mxfe_tpl_core_dac_tpl_core",
            compatible="adi,axi-ad9081-tx-1.0",
            direction="tx",
            dma_label="axi_mxfe_tx_dma",
            spibus_label="trx0_ad9081",
            jesd_label=tx_jesd_label,
            jesd_link_offset=0,
            link_id=tx_link_id,
            pl_fifo_enable=False,
            sampl_clk_ref="trx0_ad9081 1",
            sampl_clk_name="sampl_clk",
        )
        tx_link = JesdLinkModel(
            direction="tx",
            jesd_label=tx_jesd_label,
            xcvr_label="axi_mxfe_tx_xcvr",
            core_label="tx_mxfe_tpl_core_dac_tpl_core",
            dma_label="axi_mxfe_tx_dma",
            link_params={
                "F": tx_f,
                "K": tx_k,
                "M": tx_m,
                "L": tx_l,
                "Np": 16,
                "S": tx_s,
            },
            xcvr_config=tx_xcvr_ctx,
            jesd_overlay_config=tx_jesd_overlay_ctx,
            tpl_core_config=tx_tpl_ctx,
        )

        # --- FPGA config ---
        _32BIT_PLATFORMS = {"vcu118", "zc706"}
        addr_cells = 1 if platform in _32BIT_PLATFORMS else 2

        fpga_config = FpgaConfig(
            platform=platform,
            addr_cells=addr_cells,
            ps_clk_label=ps_clk_label,
            ps_clk_index=ps_clk_index,
            gpio_label=gpio_label,
        )

        return BoardModel(
            name=f"ad9081_{platform}",
            platform=platform,
            components=components,
            jesd_links=[rx_link, tx_link],
            fpga_config=fpga_config,
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9081"}
