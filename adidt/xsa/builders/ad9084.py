"""AD9084 board builder (HMC7044 + ADF4382 + dual-link AD9084).

Handles the AD9084 "apollo" dual-link design with HMC7044 clock distribution,
optional ADF4382 PLL, HSCI, and per-link JESD204 device clocks.
Topology match: converter IP ``axi_ad9084``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...model.board_model import (
    BoardModel,
    ComponentModel,
    FpgaConfig,
    JesdLinkModel,
)
from ...devices.clocks import ADF4382, HMC7044, ClockChannel
from ...devices.converters import AD9084
from ..._utils import coerce_board_int
from ...devices.fpga_ip import (
    build_adxcvr_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
)
from ...model.renderer import BoardModelRenderer
from ..topology import XsaTopology


class AD9084Builder:
    """Board builder for AD9084 dual-link designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        return any(c.ip_type == "axi_ad9084" for c in topology.converters)

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
        """Construct a :class:`BoardModel` for an AD9084 dual-link design."""
        platform = topology.inferred_platform()

        jesd_cfg = cfg.get("jesd", {})
        rx_cfg = jesd_cfg.get("rx", {})
        tx_cfg = jesd_cfg.get("tx", {})
        rx_f = int(rx_cfg.get("F", 6))
        rx_k = int(rx_cfg.get("K", 32))
        tx_f = int(tx_cfg.get("F", 6))
        tx_k = int(tx_cfg.get("K", 32))
        clock_cfg = deepcopy(cfg.get("clock", {}))
        board_cfg = deepcopy(cfg.get("ad9084_board", {}))

        # Per-link device_clk from clock config
        rx_dev_clk_label = str(clock_cfg.get("rx_device_clk_label", "axi_hsci_clkgen"))
        rx_dev_clk_index = clock_cfg.get("rx_device_clk_index", 0)
        tx_dev_clk_label = str(clock_cfg.get("tx_device_clk_label", rx_dev_clk_label))
        tx_dev_clk_index = clock_cfg.get("tx_device_clk_index", rx_dev_clk_index)
        rx_b_dev_clk_index = clock_cfg.get("rx_b_device_clk_index", rx_dev_clk_index)
        tx_b_dev_clk_index = clock_cfg.get("tx_b_device_clk_index", tx_dev_clk_index)

        # XCVR PLL selection (defaults for VCU118 GTY)
        rx_sys_clk_select = int(board_cfg.get("rx_sys_clk_select", 3))
        tx_sys_clk_select = int(board_cfg.get("tx_sys_clk_select", 3))
        rx_out_clk_select = int(board_cfg.get("rx_out_clk_select", 4))
        tx_out_clk_select = int(board_cfg.get("tx_out_clk_select", 4))

        # JESD204 link IDs for the four links
        rx_a_link_id = int(board_cfg.get("rx_a_link_id", 0))
        rx_b_link_id = int(board_cfg.get("rx_b_link_id", 1))
        tx_a_link_id = int(board_cfg.get("tx_a_link_id", 2))
        tx_b_link_id = int(board_cfg.get("tx_b_link_id", 3))

        # SPI configuration
        converter_spi = str(board_cfg.get("converter_spi", "axi_spi_2"))
        converter_cs = int(board_cfg.get("converter_cs", 0))
        clock_spi = str(board_cfg.get("clock_spi", "axi_spi"))
        hmc7044_cs = int(board_cfg.get("hmc7044_cs", 0))

        # HMC7044 configuration
        vcxo_hz = int(board_cfg.get("vcxo_hz", 125_000_000))
        pll2_output_hz = int(board_cfg.get("pll2_output_hz", 2_500_000_000))

        # HMC7044 channel index that provides the FPGA reference clock
        fpga_refclk_channel = int(board_cfg.get("fpga_refclk_channel", 10))

        # Firmware / profile
        firmware_name = board_cfg.get("firmware_name")
        reset_gpio = board_cfg.get("reset_gpio")

        # --- Categorise JESD instances from topology ---
        rx_a_jesd = rx_b_jesd = tx_a_jesd = tx_b_jesd = None
        for j in topology.jesd204_rx:
            n = j.name.lower()
            if "_b_" in n or n.startswith("axi_apollo_rx_b"):
                rx_b_jesd = j
            else:
                rx_a_jesd = j
        for j in topology.jesd204_tx:
            n = j.name.lower()
            if "_b_" in n or n.startswith("axi_apollo_tx_b"):
                tx_b_jesd = j
            else:
                tx_a_jesd = j

        # --- Build link descriptors ---
        _links = []
        for jesd, direction, variant, link_id, sys_sel, out_sel in [
            (
                rx_a_jesd,
                "rx",
                "",
                rx_a_link_id,
                rx_sys_clk_select,
                rx_out_clk_select,
            ),
            (
                rx_b_jesd,
                "rx",
                "_b",
                rx_b_link_id,
                rx_sys_clk_select,
                rx_out_clk_select,
            ),
            (
                tx_a_jesd,
                "tx",
                "",
                tx_a_link_id,
                tx_sys_clk_select,
                tx_out_clk_select,
            ),
            (
                tx_b_jesd,
                "tx",
                "_b",
                tx_b_link_id,
                tx_sys_clk_select,
                tx_out_clk_select,
            ),
        ]:
            if jesd is None:
                continue
            prefix = jesd.name.replace(f"_jesd_{direction}_axi", "")
            jesd_label = jesd.name.replace("-", "_")
            xcvr_label = f"{prefix}_xcvr"
            dma_label = f"{prefix}_dma"
            if direction == "rx":
                if variant:
                    tpl_label = "rx_b_apollo_tpl_core_adc_tpl_core"
                else:
                    tpl_label = "rx_apollo_tpl_core_adc_tpl_core"
                tpl_compatible = "adi,axi-ad9081-rx-1.0"
            else:
                if variant:
                    tpl_label = "tx_b_apollo_tpl_core_dac_tpl_core"
                else:
                    tpl_label = "tx_apollo_tpl_core_dac_tpl_core"
                tpl_compatible = "adi,axi-ad9081-tx-1.0"
            _links.append(
                {
                    "direction": direction,
                    "variant": variant,
                    "link_id": link_id,
                    "sys_clk_select": sys_sel,
                    "out_clk_select": out_sel,
                    "jesd_label": jesd_label,
                    "xcvr_label": xcvr_label,
                    "dma_label": dma_label,
                    "tpl_label": tpl_label,
                    "tpl_compatible": tpl_compatible,
                }
            )

        ad9084_spi_label = "trx0_ad9084"

        # PS clock string for DMA overlays
        ps_clk_str = (
            f"<&{ps_clk_label}"
            + (f" {ps_clk_index}" if ps_clk_index is not None else "")
            + ">"
        )

        # --- Build JESD link models ---
        jesd_links = []
        for lk in _links:
            direction = lk["direction"]
            variant = lk["variant"]
            is_rx = direction == "rx"
            gt_prefix = "rx" if is_rx else "tx"

            # ADXCVR context
            xcvr_ctx = build_adxcvr_ctx(
                label=lk["xcvr_label"],
                sys_clk_select=lk["sys_clk_select"],
                out_clk_select=lk["out_clk_select"],
                clk_ref=f"hmc7044 {fpga_refclk_channel}",
                use_div40=False,
                div40_clk_ref=None,
                clock_output_names_str=(
                    f'"{gt_prefix}{variant}_gt_clk", "{gt_prefix}{variant}_out_clk"'
                ),
                use_lpm_enable=False,
                jesd_l=None,
                jesd_m=None,
                jesd_s=None,
                jesd204_inputs=f"hmc7044 0 {lk['link_id']}",
                is_rx=is_rx,
            )

            # JESD204 overlay context — 4-clock format
            if is_rx:
                dev_label = rx_dev_clk_label
                dev_idx = rx_b_dev_clk_index if variant else rx_dev_clk_index
            else:
                dev_label = tx_dev_clk_label
                dev_idx = tx_b_dev_clk_index if variant else tx_dev_clk_index

            axi_clk = ps_clk_str
            dev_idx_str = f" {dev_idx}" if dev_idx is not None else ""
            clocks_str = (
                f"{axi_clk}, <&{lk['xcvr_label']} 1>, "
                f"<&{dev_label}{dev_idx_str}>, <&{lk['xcvr_label']} 0>"
            )

            f_val = rx_f if is_rx else tx_f
            k_val = rx_k if is_rx else tx_k

            jesd_overlay_ctx = build_jesd204_overlay_ctx(
                label=lk["jesd_label"],
                direction=direction,
                clocks_str=clocks_str,
                clock_names_str='"s_axi_aclk", "link_clk", "device_clk", "lane_clk"',
                clock_output_name=None,
                f=f_val,
                k=k_val,
                jesd204_inputs=f"{lk['xcvr_label']} 0 {lk['link_id']}",
                converter_resolution=None,
                converters_per_device=None,
                bits_per_sample=None,
                control_bits_per_sample=None,
            )

            # TPL core context
            if direction == "tx":
                sampl_clk_ref = f"{ad9084_spi_label} 1"
                sampl_clk_name = "sampl_clk"
            else:
                sampl_clk_ref = None
                sampl_clk_name = None

            tpl_ctx = build_tpl_core_ctx(
                label=lk["tpl_label"],
                compatible=lk["tpl_compatible"],
                direction=direction,
                dma_label=lk["dma_label"],
                spibus_label=ad9084_spi_label,
                jesd_label=lk["jesd_label"],
                jesd_link_offset=0,
                link_id=lk["link_id"],
                pl_fifo_enable=direction == "tx",
                sampl_clk_ref=sampl_clk_ref,
                sampl_clk_name=sampl_clk_name,
            )

            jesd_links.append(
                JesdLinkModel(
                    direction=direction,
                    jesd_label=lk["jesd_label"],
                    xcvr_label=lk["xcvr_label"],
                    core_label=lk["tpl_label"],
                    dma_label=lk["dma_label"],
                    link_params={"F": f_val, "K": k_val},
                    xcvr_rendered=xcvr_ctx,
                    jesd_overlay_rendered=jesd_overlay_ctx,
                    tpl_core_rendered=tpl_ctx,
                    dma_clocks_str=ps_clk_str,
                )
            )

        # --- Build HMC7044 component ---
        custom_hmc7044_blocks = board_cfg.get("hmc7044_channel_blocks")
        if custom_hmc7044_blocks:
            raw_channels: str | None = "".join(
                _format_nested_block(str(block)) for block in custom_hmc7044_blocks
            )
            channels_map: dict[int, ClockChannel] = {}
        else:
            raw_channels = None
            _default_specs = [
                {"id": 1, "name": "ADF4030_REFIN", "divider": 20, "driver_mode": 2},
                {
                    "id": 3,
                    "name": "ADF4030_BSYNC0",
                    "divider": 256,
                    "driver_mode": 2,
                    "is_sysref": True,
                },
                {"id": 8, "name": "CORE_CLK_TX", "divider": 8, "driver_mode": 2},
                {"id": 9, "name": "CORE_CLK_RX", "divider": 8, "driver_mode": 2},
                {"id": 10, "name": "FPGA_REFCLK", "divider": 8, "driver_mode": 2},
                {"id": 11, "name": "CORE_CLK_RX_B", "divider": 8, "driver_mode": 2},
                {"id": 12, "name": "CORE_CLK_TX_B", "divider": 8, "driver_mode": 2},
                {
                    "id": 13,
                    "name": "FPGA_SYSREF",
                    "divider": 256,
                    "driver_mode": 2,
                    "is_sysref": True,
                },
            ]
            _specs = board_cfg.get("hmc7044_channels", _default_specs)
            channels_map = {spec["id"]: ClockChannel(**spec) for spec in _specs}

        adf4382_cs = board_cfg.get("adf4382_cs")
        clkin0_ref = "clkin_125" if adf4382_cs is not None else None

        hmc7044 = HMC7044(
            label="hmc7044",
            spi_max_hz=int(board_cfg.get("hmc7044_spi_max_hz", 1_000_000)),
            pll1_clkin_frequencies=board_cfg.get(
                "pll1_clkin_frequencies", [vcxo_hz, 10_000_000, 0, 0]
            ),
            vcxo_hz=vcxo_hz,
            pll2_output_hz=pll2_output_hz,
            channels=channels_map,
            raw_channels=raw_channels,
            jesd204_sysref_provider=True,
            jesd204_max_sysref_hz=int(
                board_cfg.get("jesd204_max_sysref_hz", 2_000_000)
            ),
            pll1_loop_bandwidth_hz=int(board_cfg.get("pll1_loop_bandwidth_hz", 200)),
            pll1_ref_prio_ctrl=board_cfg.get("pll1_ref_prio_ctrl", "0xE1"),
            pll1_ref_autorevert=board_cfg.get("pll1_ref_autorevert", True),
            pll1_charge_pump_ua=int(board_cfg.get("pll1_charge_pump_ua", 720)),
            pfd1_max_freq_hz=int(board_cfg.get("pfd1_max_freq_hz", 1_000_000)),
            sysref_timer_divider=int(board_cfg.get("sysref_timer_divider", 1024)),
            pulse_generator_mode=int(board_cfg.get("pulse_generator_mode", 0)),
            clkin0_buffer_mode=board_cfg.get("clkin0_buffer_mode", "0x07"),
            clkin1_buffer_mode=board_cfg.get("clkin1_buffer_mode", "0x07"),
            oscin_buffer_mode=board_cfg.get("oscin_buffer_mode", "0x15"),
            gpi_controls=board_cfg.get("gpi_controls", [0x00, 0x00, 0x00, 0x00]),
            gpo_controls=board_cfg.get("gpo_controls", [0x37, 0x33, 0x00, 0x00]),
            clkin0_ref=clkin0_ref,
        )
        hmc7044_rendered = hmc7044.render_dt(cs=hmc7044_cs)

        # --- Build components list ---
        # ADF4382 + HMC7044 share the same SPI bus.
        # ADF4382 must appear before HMC7044 for correct probe ordering.
        components: list[ComponentModel] = []

        if adf4382_cs is not None:
            adf4382_freq = int(
                clock_cfg.get("adf4382_output_frequency", 20_000_000_000)
            )
            adf4382 = ADF4382(
                label="adf4382",
                spi_max_hz=1_000_000,
                spi_3wire=True,
                power_up_frequency=adf4382_freq,
                clks_str="<&hmc7044 1>",
                clock_output_names_str='"adf4382_out_clk"',
            )
            components.append(
                ComponentModel(
                    role="clock_pll",
                    part="adf4382",
                    spi_bus=clock_spi,
                    spi_cs=int(adf4382_cs),
                    rendered=adf4382.render_dt(cs=int(adf4382_cs)),
                )
            )

        components.append(
            ComponentModel(
                role="clock",
                part="hmc7044",
                spi_bus=clock_spi,
                spi_cs=hmc7044_cs,
                rendered=hmc7044_rendered,
            )
        )

        # --- AD9084 converter ---
        tpl_inputs = []
        all_link_ids = []
        for lk in _links:
            tpl_inputs.append(f"<&{lk['tpl_label']} 0 {lk['link_id']}>")
            all_link_ids.append(str(lk["link_id"]))

        dev_clk_ref = board_cfg.get("dev_clk_ref")
        if not dev_clk_ref:
            dev_clk_ref = f"hmc7044 {int(board_cfg.get('dev_clk_channel', 9))}"
        dev_clk_scales = board_cfg.get("dev_clk_scales")

        ad9084 = AD9084(
            label=ad9084_spi_label,
            spi_max_hz=int(board_cfg.get("converter_spi_max_hz", 1_000_000)),
            reset_gpio=reset_gpio,
            dev_clk_scales=dev_clk_scales,
            firmware_name=firmware_name,
            subclass=board_cfg.get("subclass", 0),
            side_b_separate_tpl=bool(board_cfg.get("side_b_separate_tpl", True)),
            jrx0_physical_lane_mapping=board_cfg.get("jrx0_physical_lane_mapping"),
            jtx0_logical_lane_mapping=board_cfg.get("jtx0_logical_lane_mapping"),
            jrx1_physical_lane_mapping=board_cfg.get("jrx1_physical_lane_mapping"),
            jtx1_logical_lane_mapping=board_cfg.get("jtx1_logical_lane_mapping"),
            hsci_label=board_cfg.get("hsci_label"),
            hsci_auto_linkup=bool(board_cfg.get("hsci_auto_linkup", False)),
        )
        ad9084_rendered = ad9084.render_dt(
            cs=converter_cs,
            context={
                "gpio_label": gpio_label,
                "dev_clk_ref": dev_clk_ref,
                "link_ids": " ".join(all_link_ids),
                "jesd204_inputs": ", ".join(tpl_inputs),
            },
        )
        components.append(
            ComponentModel(
                role="transceiver",
                part="ad9084",
                spi_bus=converter_spi,
                spi_cs=converter_cs,
                rendered=ad9084_rendered,
            )
        )

        # --- Extra nodes (fixed clock, HSCI) ---
        extra_nodes: list[str] = []

        if adf4382_cs is not None:
            extra_nodes.append(
                "\tclkin_125: clock@0 {\n"
                "\t\t#clock-cells = <0>;\n"
                '\t\tcompatible = "fixed-clock";\n'
                "\t\tclock-frequency = <125000000>;\n"
                '\t\tclock-output-names = "clkin_125";\n'
                "\t};"
            )

        hsci_label = board_cfg.get("hsci_label")
        if hsci_label:
            hsci_speed = int(board_cfg.get("hsci_speed_mhz", 800))
            hsci_clk_label = next(
                (c.name.replace("-", "_") for c in topology.clkgens),
                "axi_hsci_clkgen",
            )
            extra_nodes.append(
                f"\t&{hsci_label} {{\n"
                "\t\t/delete-property/ compatible;\n"
                '\t\tcompatible = "adi,axi-hsci-1.0.a";\n'
                f"\t\tclocks = <&{hsci_clk_label} 0>;\n"
                '\t\tclock-names = "pclk";\n'
                f"\t\tadi,hsci-interface-speed-mhz = <{hsci_speed}>;\n"
                "\t};"
            )

        # --- Determine addr_cells from platform ---
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
            name=f"ad9084_{platform}",
            platform=platform,
            components=components,
            jesd_links=jesd_links,
            fpga_config=fpga_config,
            extra_nodes=extra_nodes,
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9084"}


def _format_nested_block(block: str, prefix: str = "\t\t\t") -> str:
    """Re-indent each line of *block* with *prefix* and return the result."""
    lines = block.strip("\n").splitlines()
    if not lines:
        return ""
    return "".join(f"{prefix}{line.lstrip()}\n" for line in lines)
