"""AD9172 board builder (HMC7044 + AD9172 DAC).

Handles boards with an HMC7044 clock distribution IC and AD9172/AD9162 DAC.
Topology match: converter IP ``axi_ad9162`` or ``ad9172``/``ad9162`` in JESD names,
or ``"ad9172_board"`` key in config.
"""

from __future__ import annotations

from typing import Any

from ...model.board_model import (
    BoardModel,
    ComponentModel,
    FpgaConfig,
    JesdLinkModel,
)
from ...devices.clocks import HMC7044, ClockChannel
from ...devices.converters import AD9172
from ..._utils import coerce_board_int
from ...devices.fpga_ip import (
    build_adxcvr_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
)
from ...model.renderer import BoardModelRenderer
from ..topology import XsaTopology


class AD9172Builder:
    """Board builder for AD9172 DAC designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        if any(c.ip_type == "axi_ad9162" for c in topology.converters):
            return True
        names = " ".join(
            j.name.lower() for j in topology.jesd204_rx + topology.jesd204_tx
        )
        if "ad9172" in names or "ad9162" in names:
            return True
        return "ad9172_board" in cfg

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
        # Flatten all categories into a single list (same as old _build_ad9172_nodes)
        nodes: list[str] = []
        nodes.extend(rendered["converters"])
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
        """Construct a :class:`BoardModel` for an AD9172 DAC design.

        This is the unified entry point -- both the XSA pipeline and the
        manual board-class workflow can produce the same model.
        """
        board_cfg = cfg.get("ad9172_board", {})
        platform = topology.inferred_platform()

        def board_int(key: str, default: Any) -> int:
            return coerce_board_int(board_cfg.get(key, default), f"ad9172_board.{key}")

        # --- Extract config values (same fields as old _AD9172Cfg) ---
        spi_bus = str(board_cfg.get("spi_bus", "spi0"))
        clock_cs = board_int("clock_cs", 0)
        dac_cs = board_int("dac_cs", 1)
        clock_spi_max = board_int("clock_spi_max_frequency", 10_000_000)
        dac_spi_max = board_int("dac_spi_max_frequency", 1_000_000)
        dac_jesd_link_id = board_int("dac_jesd_link_id", 0)
        hmc7044_ref_clk_hz = board_int("hmc7044_ref_clk_hz", 122_880_000)
        hmc7044_vcxo_hz = board_int("hmc7044_vcxo_hz", 122_880_000)
        hmc7044_out_freq_hz = board_int("hmc7044_out_freq_hz", 2_949_120_000)
        ad9172_dac_rate_khz = board_int("ad9172_dac_rate_khz", 11_796_480)
        ad9172_jesd_link_mode = board_int("ad9172_jesd_link_mode", 4)
        ad9172_dac_interpolation = board_int("ad9172_dac_interpolation", 8)
        ad9172_channel_interpolation = board_int("ad9172_channel_interpolation", 4)
        ad9172_clock_output_divider = board_int("ad9172_clock_output_divider", 4)

        # JESD TX parameters
        tx_jesd = cfg.get("jesd", {}).get("tx", {})
        tx_l = int(tx_jesd.get("L", 4))
        tx_m = int(tx_jesd.get("M", 4))
        tx_f = int(tx_jesd.get("F", 2))
        tx_k = int(tx_jesd.get("K", 32))
        tx_np = int(tx_jesd.get("Np", 16))

        # --- Infer labels from topology ---
        dac_jesd_label = str(board_cfg.get("dac_jesd_label", "axi_ad9172_jesd_tx_axi"))
        dac_xcvr_label = str(board_cfg.get("dac_xcvr_label", "axi_ad9172_adxcvr"))
        dac_core_label = str(board_cfg.get("dac_core_label", "axi_ad9172_core"))
        if topology.jesd204_tx:
            inferred_tx = topology.jesd204_tx[0].name.replace("-", "_")
            dac_jesd_label = str(board_cfg.get("dac_jesd_label", inferred_tx))
            topology_names = _topology_instance_names(topology)
            inferred_xcvr = _infer_ad9172_xcvr_label(dac_jesd_label)
            inferred_core = _infer_ad9172_core_label(dac_jesd_label)
            if topology_names:
                inferred_xcvr = _pick_existing_ad9172_label(
                    topology_names, inferred_xcvr, dac_jesd_label, ("xcvr",)
                )
                inferred_core = _pick_existing_ad9172_label(
                    topology_names,
                    inferred_core,
                    dac_jesd_label,
                    ("transport", "tpl", "core"),
                )
            dac_xcvr_label = str(board_cfg.get("dac_xcvr_label", inferred_xcvr))
            dac_core_label = str(board_cfg.get("dac_core_label", inferred_core))

        # --- Build HMC7044 clock context ---
        _channel_specs = [
            {
                "id": 2,
                "name": "DAC_CLK",
                "divider": 8,
                "driver_mode": 1,
                "is_sysref": False,
            },
            {
                "id": 3,
                "name": "DAC_SYSREF",
                "divider": 512,
                "driver_mode": 1,
                "is_sysref": True,
            },
            {
                "id": 12,
                "name": "FPGA_CLK",
                "divider": 8,
                "driver_mode": 2,
                "is_sysref": False,
            },
            {
                "id": 13,
                "name": "FPGA_SYSREF",
                "divider": 512,
                "driver_mode": 2,
                "is_sysref": True,
            },
        ]
        hmc7044 = HMC7044(
            label="hmc7044",
            spi_max_hz=clock_spi_max,
            pll1_clkin_frequencies=[hmc7044_ref_clk_hz, 0, 0, 0],
            vcxo_hz=hmc7044_vcxo_hz,
            pll2_output_hz=hmc7044_out_freq_hz,
            channels={spec["id"]: ClockChannel(**spec) for spec in _channel_specs},
            pll1_loop_bandwidth_hz=200,
            sysref_timer_divider=1024,
            pulse_generator_mode=0,
            clkin0_buffer_mode="0x15",
            oscin_buffer_mode="0x15",
            gpi_controls=[0x00, 0x00, 0x00, 0x00],
            gpo_controls=[0x1F, 0x2B, 0x00, 0x00],
        )
        hmc7044_rendered = hmc7044.render_dt(cs=clock_cs)

        # --- Build AD9172 device ---
        ad9172 = AD9172(
            label="dac0_ad9172",
            spi_max_hz=dac_spi_max,
            clk_ref="hmc7044 2",
            dac_rate_khz=ad9172_dac_rate_khz,
            jesd_link_mode=ad9172_jesd_link_mode,
            dac_interpolation=ad9172_dac_interpolation,
            channel_interpolation=ad9172_channel_interpolation,
            clock_output_divider=ad9172_clock_output_divider,
            jesd_link_ids=[0],
        )
        ad9172_rendered = ad9172.render_dt(
            cs=dac_cs,
            context={"jesd204_inputs": f"{dac_core_label} 0 {dac_jesd_link_id}"},
        )

        components = [
            ComponentModel(
                role="clock",
                part="hmc7044",
                spi_bus=spi_bus,
                spi_cs=clock_cs,
                rendered=hmc7044_rendered,
            ),
            ComponentModel(
                role="dac",
                part="ad9172",
                spi_bus=spi_bus,
                spi_cs=dac_cs,
                rendered=ad9172_rendered,
            ),
        ]

        # --- Build TX JESD link ---
        tx_xcvr_ctx = build_adxcvr_ctx(
            label=dac_xcvr_label,
            sys_clk_select=3,
            out_clk_select=4,
            clk_ref="hmc7044 12",
            use_div40=False,
            div40_clk_ref=None,
            clock_output_names_str='"dac_gt_clk", "tx_out_clk"',
            use_lpm_enable=True,
            jesd_l=None,
            jesd_m=None,
            jesd_s=None,
            jesd204_inputs="hmc7044 0 0",
            is_rx=False,
        )
        tx_jesd_overlay_ctx = build_jesd204_overlay_ctx(
            label=dac_jesd_label,
            direction="tx",
            clocks_str=(
                f"<&{ps_clk_label} {ps_clk_index}>, "
                f"<&{dac_xcvr_label} 1>, "
                f"<&{dac_xcvr_label} 0>"
            ),
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            clock_output_name="jesd_dac_lane_clk",
            f=tx_f,
            k=tx_k,
            jesd204_inputs=f"{dac_xcvr_label} 0 {dac_jesd_link_id}",
            converter_resolution=None,
            converters_per_device=tx_m,
            bits_per_sample=tx_np,
            control_bits_per_sample=0,
        )
        tx_tpl_ctx = build_tpl_core_ctx(
            label=dac_core_label,
            compatible="adi,axi-ad9172-1.0",
            direction="tx",
            dma_label=None,
            spibus_label="dac0_ad9172",
            jesd_label=dac_jesd_label,
            jesd_link_offset=0,
            link_id=dac_jesd_link_id,
            pl_fifo_enable=True,
        )
        tx_link = JesdLinkModel(
            direction="tx",
            jesd_label=dac_jesd_label,
            xcvr_label=dac_xcvr_label,
            core_label=dac_core_label,
            dma_label=None,
            link_params={
                "F": tx_f,
                "K": tx_k,
                "M": tx_m,
                "L": tx_l,
                "Np": tx_np,
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
            name=f"ad9172_{platform}",
            platform=platform,
            components=components,
            jesd_links=[tx_link],
            fpga_config=fpga_config,
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9162"}


# ---------------------------------------------------------------------------
# Label inference helpers (extracted from NodeBuilder)
# ---------------------------------------------------------------------------


def _topology_instance_names(topology: XsaTopology) -> set[str]:
    """Return the union of all IP instance names from the topology."""
    names: set[str] = set()
    names.update(i.name.replace("-", "_") for i in topology.jesd204_tx)
    names.update(i.name.replace("-", "_") for i in topology.jesd204_rx)
    names.update(i.name.replace("-", "_") for i in topology.clkgens)
    names.update(i.name.replace("-", "_") for i in topology.converters)
    for conn in topology.signal_connections:
        names.update(n.replace("-", "_") for n in conn.producers)
        names.update(n.replace("-", "_") for n in conn.consumers)
        names.update(n.replace("-", "_") for n in conn.bidirectional)
    return names


def _infer_ad9172_xcvr_label(tx_label: str) -> str:
    """Derive the XCVR label from the TX JESD label."""
    if "_link_tx_axi" in tx_label:
        return tx_label.replace("_link_tx_axi", "_xcvr")
    if "_jesd_tx_axi" in tx_label:
        return tx_label.replace("_jesd_tx_axi", "_adxcvr")
    return tx_label.replace("_jesd", "_adxcvr")


def _infer_ad9172_core_label(tx_label: str) -> str:
    """Derive the DAC TPL core label from the TX JESD label."""
    if "_link_tx_axi" in tx_label:
        return tx_label.replace("_link_tx_axi", "_transport_dac_tpl_core")
    if "_jesd_tx_axi" in tx_label:
        return tx_label.replace("_jesd_tx_axi", "_core")
    return tx_label.replace("_jesd_tx_axi", "_core").replace("_jesd", "_core")


def _ad9172_prefix_from_tx_label(tx_label: str) -> str:
    """Strip known AD9172 TX-JESD suffixes from *tx_label*."""
    for suffix in (
        "_link_tx_axi",
        "_jesd_tx_axi",
        "_jesd204_tx_axi",
        "_jesd_tx",
    ):
        if tx_label.endswith(suffix):
            return tx_label[: -len(suffix)]
    return tx_label


def _pick_existing_ad9172_label(
    topology_names: set[str],
    default: str,
    tx_label: str,
    required_keywords: tuple[str, ...],
) -> str:
    """Return the best topology name matching the TX label prefix and keywords."""
    if default in topology_names:
        return default
    prefix = _ad9172_prefix_from_tx_label(tx_label).lower()
    candidates = sorted(
        n
        for n in topology_names
        if prefix in n.lower()
        and all(keyword in n.lower() for keyword in required_keywords)
    )
    if candidates:
        return candidates[0]
    return default
