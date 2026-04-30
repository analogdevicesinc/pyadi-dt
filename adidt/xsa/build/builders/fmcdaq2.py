"""FMCDAQ2 board builder (AD9523-1 + AD9680 + AD9144).

Handles boards with an AD9523-1 clock generator, AD9680 ADC, and AD9144 DAC
on a shared SPI bus.  Topology match: ``has_converter_types("axi_ad9680", "axi_ad9144")``.
"""

from __future__ import annotations

from typing import Any

from ....model.board_model import (
    BoardModel,
    ComponentModel,
    FpgaConfig,
    JesdLinkModel,
)
from ....devices.clocks import AD9523_1, AD9523Channel
from ....devices.converters import AD9144, AD9680
from ...._utils import coerce_board_int, fmt_hz
from ....devices.fpga_ip import (
    build_adxcvr_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
)
from ....model.renderer import BoardModelRenderer
from ...parse.topology import XsaTopology


class FMCDAQ2Builder:
    """Board builder for FMCDAQ2 designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        return topology.is_fmcdaq2_design()

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
        # Flatten all categories into a single list (same as old _build_fmcdaq2_nodes)
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
        """Construct a :class:`BoardModel` for an FMCDAQ2 design.

        This is the unified entry point — both the XSA pipeline and the
        manual board-class workflow can produce the same model.
        """
        board_cfg = cfg.get("fmcdaq2_board", {})
        platform = topology.inferred_platform()

        def board_int(key: str, default: Any) -> int:
            return coerce_board_int(board_cfg.get(key, default), f"fmcdaq2_board.{key}")

        # --- Extract config values (same as old _build_fmcdaq2_cfg) ---
        spi_bus = str(board_cfg.get("spi_bus", "spi0"))
        clock_cs = board_int("clock_cs", 0)
        adc_cs = board_int("adc_cs", 2)
        dac_cs = board_int("dac_cs", 1)
        clock_vcxo_hz = board_int("clock_vcxo_hz", 125_000_000)
        clock_spi_max = board_int("clock_spi_max_frequency", 10_000_000)
        adc_spi_max = board_int("adc_spi_max_frequency", 1_000_000)
        dac_spi_max = board_int("dac_spi_max_frequency", 1_000_000)
        adc_dma_label = str(board_cfg.get("adc_dma_label", "axi_ad9680_dma"))
        dac_dma_label = str(board_cfg.get("dac_dma_label", "axi_ad9144_dma"))
        adc_core_label = str(board_cfg.get("adc_core_label", "axi_ad9680_core"))
        dac_core_label = str(board_cfg.get("dac_core_label", "axi_ad9144_core"))
        adc_xcvr_label = str(board_cfg.get("adc_xcvr_label", "axi_ad9680_adxcvr"))
        dac_xcvr_label = str(board_cfg.get("dac_xcvr_label", "axi_ad9144_adxcvr"))
        adc_jesd_label = str(board_cfg.get("adc_jesd_label", "axi_ad9680_jesd204_rx"))
        dac_jesd_label = str(board_cfg.get("dac_jesd_label", "axi_ad9144_jesd204_tx"))
        adc_jesd_link_id = board_int("adc_jesd_link_id", 0)
        dac_jesd_link_id = board_int("dac_jesd_link_id", 0)
        gpio_controller = str(board_cfg.get("gpio_controller", gpio_label))
        adc_device_clk_idx = board_int("adc_device_clk_idx", 13)
        adc_sysref_clk_idx = board_int("adc_sysref_clk_idx", 5)
        adc_xcvr_ref_clk_idx = board_int("adc_xcvr_ref_clk_idx", 4)
        adc_sampling_frequency_hz = board_int(
            "adc_sampling_frequency_hz", 1_000_000_000
        )
        dac_device_clk_idx = board_int("dac_device_clk_idx", 1)
        dac_xcvr_ref_clk_idx = board_int("dac_xcvr_ref_clk_idx", 9)

        # JESD parameters
        jesd_cfg = cfg.get("jesd", {})
        rx_jesd = jesd_cfg.get("rx", {})
        tx_jesd = jesd_cfg.get("tx", {})
        rx_l = int(rx_jesd.get("L", 4))
        rx_m = int(rx_jesd.get("M", 2))
        rx_f = int(rx_jesd.get("F", 1))
        rx_k = int(rx_jesd.get("K", 32))
        rx_np = int(rx_jesd.get("Np", 16))
        rx_s = int(rx_jesd.get("S", 1))
        tx_l = int(tx_jesd.get("L", 4))
        tx_m = int(tx_jesd.get("M", 2))
        tx_f = int(tx_jesd.get("F", 1))
        tx_k = int(tx_jesd.get("K", 32))
        tx_np = int(tx_jesd.get("Np", 16))
        tx_s = int(tx_jesd.get("S", 1))

        # FPGA PLL select
        sys_clk_map = {"XCVR_CPLL": 0, "XCVR_QPLL1": 2, "XCVR_QPLL": 3, "XCVR_QPLL0": 3}
        out_clk_map = {"XCVR_REFCLK": 4, "XCVR_REFCLK_DIV2": 4}
        fpga_adc = cfg.get("fpga_adc", {})
        fpga_dac = cfg.get("fpga_dac", {})
        adc_sys_clk_select = int(
            sys_clk_map.get(str(fpga_adc.get("sys_clk_select", "XCVR_CPLL")).upper(), 0)
        )
        dac_sys_clk_select = int(
            sys_clk_map.get(str(fpga_dac.get("sys_clk_select", "XCVR_QPLL")).upper(), 3)
        )
        adc_out_clk_select = int(
            out_clk_map.get(
                str(fpga_adc.get("out_clk_select", "XCVR_REFCLK_DIV2")).upper(), 4
            )
        )
        dac_out_clk_select = int(
            out_clk_map.get(
                str(fpga_dac.get("out_clk_select", "XCVR_REFCLK_DIV2")).upper(), 4
            )
        )

        # Optional GPIO indices
        sync_gpio = board_cfg.get("clk_sync_gpio")
        status0_gpio = board_cfg.get("clk_status0_gpio")
        status1_gpio = board_cfg.get("clk_status1_gpio")
        txen_gpio = board_cfg.get("dac_txen_gpio")
        reset_gpio = board_cfg.get("dac_reset_gpio")
        irq_gpio = board_cfg.get("dac_irq_gpio")
        powerdown_gpio = board_cfg.get("adc_powerdown_gpio")
        fastdetect_a_gpio = board_cfg.get("adc_fastdetect_a_gpio")
        fastdetect_b_gpio = board_cfg.get("adc_fastdetect_b_gpio")

        if sync_gpio is not None:
            sync_gpio = coerce_board_int(sync_gpio, "fmcdaq2_board.clk_sync_gpio")
        if status0_gpio is not None:
            status0_gpio = coerce_board_int(
                status0_gpio, "fmcdaq2_board.clk_status0_gpio"
            )
        if status1_gpio is not None:
            status1_gpio = coerce_board_int(
                status1_gpio, "fmcdaq2_board.clk_status1_gpio"
            )
        if txen_gpio is not None:
            txen_gpio = coerce_board_int(txen_gpio, "fmcdaq2_board.dac_txen_gpio")
        if reset_gpio is not None:
            reset_gpio = coerce_board_int(reset_gpio, "fmcdaq2_board.dac_reset_gpio")
        if irq_gpio is not None:
            irq_gpio = coerce_board_int(irq_gpio, "fmcdaq2_board.dac_irq_gpio")
        if powerdown_gpio is not None:
            powerdown_gpio = coerce_board_int(
                powerdown_gpio, "fmcdaq2_board.adc_powerdown_gpio"
            )
        if fastdetect_a_gpio is not None:
            fastdetect_a_gpio = coerce_board_int(
                fastdetect_a_gpio, "fmcdaq2_board.adc_fastdetect_a_gpio"
            )
        if fastdetect_b_gpio is not None:
            fastdetect_b_gpio = coerce_board_int(
                fastdetect_b_gpio, "fmcdaq2_board.adc_fastdetect_b_gpio"
            )

        # --- Build devices ---
        _m1 = 1_000_000_000  # adi,pll2-m1-freq distribution frequency
        # Each spec tuple is (id, name, divider).  Using a typed tuple
        # here instead of a dict-of-mixed-types keeps the `int // int`
        # below type-checkable — a heterogeneous-value dict infers
        # ``int | str`` for lookups and the divider expression fails
        # ``ty check`` with ``unsupported-operator``.
        ad9523_channel_specs: list[tuple[int, str, int]] = [
            (1, "DAC_CLK", 1),
            (4, "ADC_CLK_FMC", 2),
            (5, "ADC_SYSREF", 128),
            (6, "CLKD_ADC_SYSREF", 128),
            (7, "CLKD_DAC_SYSREF", 128),
            (8, "DAC_SYSREF", 128),
            (9, "FMC_DAC_REF_CLK", 2),
            (13, "ADC_CLK", 1),
        ]
        ad9523_channels = {
            ch_id: AD9523Channel(
                id=ch_id,
                name=name,
                divider=divider,
                freq_str=fmt_hz(_m1 // divider),
            )
            for ch_id, name, divider in ad9523_channel_specs
        }
        clock_gpio_lines = []
        for prop, val in (
            ("sync-gpios", sync_gpio),
            ("status0-gpios", status0_gpio),
            ("status1-gpios", status1_gpio),
        ):
            if val is not None:
                clock_gpio_lines.append(
                    {"prop": prop, "controller": gpio_controller, "index": int(val)}
                )
        ad9523 = AD9523_1(
            label="clk0_ad9523",
            spi_max_hz=clock_spi_max,
            vcxo_hz=clock_vcxo_hz,
            channels=ad9523_channels,
        )
        # Inject GPIO lines (device expects model objects; dicts auto-validate).
        from ....devices.clocks.ad952x import _GpioLine

        ad9523.gpio_lines = [_GpioLine(**gl) for gl in clock_gpio_lines]
        clock_rendered = ad9523.render_dt(cs=clock_cs)

        adc_clks_str = (
            f"<&{adc_jesd_label}>, "
            f"<&clk0_ad9523 {adc_device_clk_idx}>, "
            f"<&clk0_ad9523 {adc_sysref_clk_idx}>"
        )
        adc_gpio_lines = []
        for prop, val in (
            ("powerdown-gpios", powerdown_gpio),
            ("fastdetect-a-gpios", fastdetect_a_gpio),
            ("fastdetect-b-gpios", fastdetect_b_gpio),
        ):
            if val is not None:
                adc_gpio_lines.append(
                    {"prop": prop, "controller": gpio_controller, "index": int(val)}
                )
        ad9680 = AD9680(
            label="adc0_ad9680",
            spi_max_hz=adc_spi_max,
            m=rx_m,
            l=rx_l,
            f=rx_f,
            k=rx_k,
            np=rx_np,
            sampling_frequency_hz=adc_sampling_frequency_hz,
            clks_str=adc_clks_str,
            clk_names_str='"jesd_adc_clk", "adc_clk", "adc_sysref"',
        )
        adc_rendered = ad9680.render_dt(
            cs=adc_cs,
            context={
                "jesd204_link_ids": str(adc_jesd_link_id),
                "jesd204_inputs": f"{adc_core_label} 0 {adc_jesd_link_id}",
                "gpio_lines": adc_gpio_lines,
            },
        )

        dac_gpio_lines = []
        for prop, val in (
            ("txen-gpios", txen_gpio),
            ("reset-gpios", reset_gpio),
            ("irq-gpios", irq_gpio),
        ):
            if val is not None:
                dac_gpio_lines.append(
                    {"prop": prop, "controller": gpio_controller, "index": int(val)}
                )
        ad9144 = AD9144(
            label="dac0_ad9144",
            spi_max_hz=dac_spi_max,
            jesd204_top_device=1,
            clk_ref=f"clk0_ad9523 {dac_device_clk_idx}",
        )
        dac_rendered = ad9144.render_dt(
            cs=dac_cs,
            context={
                "jesd204_link_ids": str(dac_jesd_link_id),
                "jesd204_inputs": f"{dac_core_label} 1 {dac_jesd_link_id}",
                "gpio_lines": dac_gpio_lines,
            },
        )

        components = [
            ComponentModel(
                role="clock",
                part="ad9523_1",
                spi_bus=spi_bus,
                spi_cs=clock_cs,
                rendered=clock_rendered,
            ),
            ComponentModel(
                role="adc",
                part="ad9680",
                spi_bus=spi_bus,
                spi_cs=adc_cs,
                rendered=adc_rendered,
            ),
            ComponentModel(
                role="dac",
                part="ad9144",
                spi_bus=spi_bus,
                spi_cs=dac_cs,
                rendered=dac_rendered,
            ),
        ]

        # --- Build JESD link models ---
        # RX link (ADC)
        rx_xcvr_ctx = build_adxcvr_ctx(
            label=adc_xcvr_label,
            sys_clk_select=adc_sys_clk_select,
            out_clk_select=adc_out_clk_select,
            clk_ref=f"clk0_ad9523 {adc_xcvr_ref_clk_idx}",
            use_div40=True,
            div40_clk_ref=f"clk0_ad9523 {adc_xcvr_ref_clk_idx}",
            clock_output_names_str='"adc_gt_clk", "rx_out_clk"',
            use_lpm_enable=True,
            jesd_l=rx_l,
            jesd_m=rx_m,
            jesd_s=rx_s,
            jesd204_inputs=None,
            is_rx=True,
        )
        rx_jesd_overlay_ctx = build_jesd204_overlay_ctx(
            label=adc_jesd_label,
            direction="rx",
            clocks_str=f"<&{ps_clk_label} {ps_clk_index}>, <&{adc_xcvr_label} 1>, <&{adc_xcvr_label} 0>",
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            clock_output_name="jesd_adc_lane_clk",
            f=rx_f,
            k=rx_k,
            jesd204_inputs=f"{adc_xcvr_label} 0 {adc_jesd_link_id}",
            converter_resolution=None,
            converters_per_device=None,
            bits_per_sample=None,
            control_bits_per_sample=None,
        )
        rx_tpl_ctx = build_tpl_core_ctx(
            label=adc_core_label,
            compatible="adi,axi-ad9680-1.0",
            direction="rx",
            dma_label=adc_dma_label,
            spibus_label="adc0_ad9680",
            jesd_label=adc_jesd_label,
            jesd_link_offset=0,
            link_id=adc_jesd_link_id,
            pl_fifo_enable=False,
        )
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
            xcvr_rendered=rx_xcvr_ctx,
            jesd_overlay_rendered=rx_jesd_overlay_ctx,
            tpl_core_rendered=rx_tpl_ctx,
        )

        # TX link (DAC)
        tx_xcvr_ctx = build_adxcvr_ctx(
            label=dac_xcvr_label,
            sys_clk_select=dac_sys_clk_select,
            out_clk_select=dac_out_clk_select,
            clk_ref=f"clk0_ad9523 {dac_xcvr_ref_clk_idx}",
            use_div40=True,
            div40_clk_ref=f"clk0_ad9523 {dac_xcvr_ref_clk_idx}",
            clock_output_names_str='"dac_gt_clk", "tx_out_clk"',
            use_lpm_enable=True,
            jesd_l=tx_l,
            jesd_m=tx_m,
            jesd_s=tx_s,
            jesd204_inputs=None,
            is_rx=False,
        )
        tx_jesd_overlay_ctx = build_jesd204_overlay_ctx(
            label=dac_jesd_label,
            direction="tx",
            clocks_str=f"<&{ps_clk_label} {ps_clk_index}>, <&{dac_xcvr_label} 1>, <&{dac_xcvr_label} 0>",
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            clock_output_name="jesd_dac_lane_clk",
            f=tx_f,
            k=tx_k,
            jesd204_inputs=f"{dac_xcvr_label} 1 {dac_jesd_link_id}",
            converter_resolution=14,
            converters_per_device=tx_m,
            bits_per_sample=tx_np,
            control_bits_per_sample=2,
        )
        tx_tpl_ctx = build_tpl_core_ctx(
            label=dac_core_label,
            compatible="adi,axi-ad9144-1.0",
            direction="tx",
            dma_label=dac_dma_label,
            spibus_label="dac0_ad9144",
            jesd_label=dac_jesd_label,
            jesd_link_offset=1,
            link_id=dac_jesd_link_id,
            pl_fifo_enable=True,
        )
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
            xcvr_rendered=tx_xcvr_ctx,
            jesd_overlay_rendered=tx_jesd_overlay_ctx,
            tpl_core_rendered=tx_tpl_ctx,
        )

        # Determine addr_cells from platform
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
            name=f"fmcdaq2_{platform}",
            platform=platform,
            components=components,
            jesd_links=[rx_link, tx_link],
            fpga_config=fpga_config,
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9680", "axi_ad9144"}
