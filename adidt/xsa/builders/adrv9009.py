"""ADRV9009/9025/9026 board builder.

Handles ADRV9009, ADRV9025, and ADRV9026 transceiver designs, including both
standard single-chip and dual-chip FMComms8 layouts.
Topology match: converter IP or JESD instance names containing ``adrv9009``,
``adrv9025``, or ``adrv9026``.
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
    build_ad9528_1_ctx,
    build_adrv9009_device_ctx,
    build_adxcvr_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
    coerce_board_int,
    fmt_hz,
)
from ...model.renderer import BoardModelRenderer
from ..topology import XsaTopology

_ADRV90XX_KEYWORDS = ("adrv9009", "adrv9025", "adrv9026")


def _is_adrv90xx_name(value: str) -> bool:
    """Return True if *value* contains an ADRV9009/9025/9026 keyword."""
    lower = value.lower()
    return any(key in lower for key in _ADRV90XX_KEYWORDS)


def _topology_instance_names(topology: XsaTopology) -> set[str]:
    """Return all IP instance names from the topology, with hyphens as underscores."""
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


def _is_fmcomms8_layout(topology_names: set[str]) -> bool:
    """Return True if topology indicates a dual-chip FMComms8 layout."""
    return any(
        "tpl_core" in name.lower()
        and "adrv9009" in name.lower()
        and (
            "fmc" in name.lower()
            or "obs" in name.lower()
            or "rx" in name.lower()
            or "tx" in name.lower()
        )
        for name in topology_names
    )


def _pick_matching_label(
    topology_names: set[str], default: str, required_tokens: tuple[str, ...]
) -> str:
    """Return the first topology name containing all *required_tokens*, or *default*."""
    if default in topology_names:
        return default
    candidates = sorted(
        n
        for n in topology_names
        if all(token in n.lower() for token in required_tokens)
    )
    return candidates[0] if candidates else default


def _format_nested_block(block: str, prefix: str = "\t\t\t") -> str:
    """Re-indent each line of *block* with *prefix* and return the result."""
    lines = block.strip("\n").splitlines()
    if not lines:
        return ""
    return "".join(f"{prefix}{line.lstrip()}\n" for line in lines)


def _fmt_gpi_gpo(controls: list) -> str:
    """Format a list of int/hex values as a space-separated hex string for DTS."""
    return " ".join(f"0x{int(v):02x}" for v in controls)


class ADRV9009Builder:
    """Board builder for ADRV9009/9025/9026 transceiver designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        if any(
            c.ip_type in {"axi_adrv9009", "axi_adrv9025", "axi_adrv9026"}
            or _is_adrv90xx_name(c.name)
            for c in topology.converters
        ):
            return True
        return any(
            _is_adrv90xx_name(j.name) for j in topology.jesd204_rx + topology.jesd204_tx
        )

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
        if model is None:
            return []
        renderer = BoardModelRenderer()
        rendered = renderer.render(model)
        # The renderer produces converters (SPI bus + DMA + TPL + ADXCVR)
        # and JESD overlay nodes.  ADRV9009 additionally needs misc_clk,
        # clkgen, raw XCVR, and two-pass TPL core nodes which are stored
        # in model.metadata["extra_nodes_before"] / "extra_nodes_after".
        #
        # When a raw clock chip node is present (custom ad9528 channel blocks),
        # the renderer's SPI bus only wraps the PHY.  We replace it with a
        # manually-assembled SPI bus that includes both the raw clock chip
        # and the PHY.
        raw_clk = model.metadata.get("raw_clock_chip_node")
        if raw_clk is not None:
            spi_bus = model.metadata.get("spi_bus", "spi0")
            # The renderer produced an SPI bus with only the PHY; replace it
            # with one that includes the raw clock chip node before the PHY.
            phy_comp = model.get_component("transceiver")
            if phy_comp and rendered["converters"]:
                from jinja2 import Environment, FileSystemLoader
                import os

                loc = os.path.join(
                    os.path.dirname(os.path.realpath(__file__)),
                    "..",
                    "..",
                    "templates",
                    "xsa",
                )
                env = Environment(loader=FileSystemLoader(loc))
                phy_rendered = env.get_template(phy_comp.template).render(
                    phy_comp.config
                )
                spi_node = renderer._wrap_spi_bus(spi_bus, raw_clk + phy_rendered)
                # Replace the first converter entry (the SPI bus)
                rendered["converters"][0] = spi_node

        nodes: list[str] = []
        nodes.extend(model.metadata.get("extra_nodes_before", []))
        nodes.extend(rendered["converters"])
        nodes.extend(rendered["jesd204_rx"])
        nodes.extend(rendered["jesd204_tx"])
        nodes.extend(model.metadata.get("extra_nodes_after", []))
        return nodes

    def build_model(
        self,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> BoardModel | None:
        """Construct a :class:`BoardModel` for an ADRV9009/9025/9026 design.

        Returns None if no ADRV90xx instances are found in the topology.
        """
        board_cfg = cfg.get("adrv9009_board", {})
        platform = topology.inferred_platform()

        labels = _topology_instance_names(topology)
        is_fmcomms8 = _is_fmcomms8_layout(labels)

        if not any(_is_adrv90xx_name(lbl) for lbl in labels):
            return None

        is_adrv9025_family = any(
            "adrv9025" in lbl.lower() or "adrv9026" in lbl.lower() for lbl in labels
        )
        phy_family = "adrv9025" if is_adrv9025_family else "adrv9009"
        phy_compatible = f'"adi,{phy_family}", "{phy_family}"'

        # --- Discover JESD label names from topology ---
        rx_jesd_label = next(
            (
                lbl
                for lbl in sorted(labels)
                if "_rx_jesd_rx_axi" in lbl and "_rx_os_" not in lbl
            ),
            next(
                (
                    lbl
                    for lbl in sorted(labels)
                    if "_rx_jesd" in lbl and "_rx_os_" not in lbl
                ),
                None,
            ),
        )
        rx_os_jesd_label = next(
            (lbl for lbl in sorted(labels) if "_rx_os_jesd_rx_axi" in lbl),
            next(
                (lbl for lbl in sorted(labels) if "_obs_jesd_rx_axi" in lbl),
                next(
                    (
                        lbl
                        for lbl in sorted(labels)
                        if "_rx_os_jesd" in lbl or "_obs_jesd" in lbl
                    ),
                    None,
                ),
            ),
        )
        tx_jesd_label = next(
            (lbl for lbl in sorted(labels) if "_tx_jesd_tx_axi" in lbl),
            next((lbl for lbl in sorted(labels) if "_tx_jesd" in lbl), None),
        )
        if not rx_jesd_label or not tx_jesd_label:
            return None

        # --- JESD parameters ---
        jesd_cfg = cfg.get("jesd", {})
        rx_f = int(jesd_cfg.get("rx", {}).get("F", 4))
        rx_k = int(jesd_cfg.get("rx", {}).get("K", 32))
        tx_k = int(jesd_cfg.get("tx", {}).get("K", 32))
        tx_m = int(jesd_cfg.get("tx", {}).get("M", 4))

        # --- Derive clkgen / xcvr / core labels from JESD labels ---
        rx_clkgen_label = rx_jesd_label.replace("_jesd_rx_axi", "_clkgen").replace(
            "_rx_jesd", "_rx_clkgen"
        )
        tx_clkgen_label = tx_jesd_label.replace("_jesd_tx_axi", "_clkgen").replace(
            "_tx_jesd", "_tx_clkgen"
        )
        rx_xcvr_label = rx_jesd_label.replace("_jesd_rx_axi", "_xcvr").replace(
            "_rx_jesd", "_rx_xcvr"
        )
        tx_xcvr_label = tx_jesd_label.replace("_jesd_tx_axi", "_xcvr").replace(
            "_tx_jesd", "_tx_xcvr"
        )

        has_rx_clkgen = not is_fmcomms8
        has_tx_clkgen = not is_fmcomms8

        if rx_os_jesd_label:
            rx_os_xcvr_label = rx_os_jesd_label.replace(
                "_jesd_rx_axi", "_xcvr"
            ).replace("_rx_os_jesd", "_rx_os_xcvr")
            rx_os_clkgen_label = rx_os_jesd_label.replace(
                "_jesd_rx_axi", "_clkgen"
            ).replace("_rx_os_jesd", "_rx_os_clkgen")
        else:
            rx_os_xcvr_label = "axi_adrv9009_rx_os_xcvr"
            rx_os_clkgen_label = "axi_adrv9009_rx_os_clkgen"

        has_rx_os_clkgen = bool(rx_os_jesd_label) and not is_fmcomms8

        # --- TPL core labels ---
        rx_core_label = "axi_adrv9009_core_rx"
        rx_os_core_label = "axi_adrv9009_core_rx_obs"
        tx_core_label = "axi_adrv9009_core_tx"
        if is_fmcomms8:
            rx_core_label = _pick_matching_label(
                labels, rx_core_label, ("adrv9009", "tpl_core", "rx", "adc")
            )
            rx_os_core_label = _pick_matching_label(
                labels, rx_os_core_label, ("adrv9009", "tpl_core", "obs", "adc")
            )
            tx_core_label = _pick_matching_label(
                labels, tx_core_label, ("adrv9009", "tpl_core", "tx", "dac")
            )

        # --- Board config values ---
        misc_clk_hz = int(board_cfg.get("misc_clk_hz", 245760000))
        spi_bus = str(board_cfg.get("spi_bus", "spi0"))
        clk_cs = int(board_cfg.get("clk_cs", 0))
        trx_cs = int(board_cfg.get("trx_cs", 1))
        trx_reset_gpio = int(board_cfg.get("trx_reset_gpio", 130))
        trx_sysref_req_gpio = int(board_cfg.get("trx_sysref_req_gpio", 136))
        trx_spi_max_frequency = int(board_cfg.get("trx_spi_max_frequency", 25000000))

        if is_fmcomms8:
            phy_compatible = '"adrv9009-x2"'

        # --- Clock chip configuration ---
        raw_clock_chip_node: str | None = None
        custom_clock_chip_blocks = None
        if is_fmcomms8:
            clock_chip_label = "hmc7044_fmc"
            hmc7044_rx_channel = int(board_cfg.get("hmc7044_rx_channel", 9))
            hmc7044_tx_channel = int(board_cfg.get("hmc7044_tx_channel", 8))
            hmc7044_xcvr_channel = int(board_cfg.get("hmc7044_xcvr_channel", 5))
            hmc7044_tx_xcvr_channel = int(board_cfg.get("hmc7044_tx_xcvr_channel", 4))
            hmc7044_trx0_dev_channel = int(board_cfg.get("hmc7044_trx0_dev_channel", 0))
            hmc7044_trx0_sysref_dev_channel = int(
                board_cfg.get("hmc7044_trx0_sysref_dev_channel", 1)
            )
            hmc7044_trx0_sysref_fmc_channel = int(
                board_cfg.get("hmc7044_trx0_sysref_fmc_channel", 6)
            )
            hmc7044_trx1_dev_channel = int(board_cfg.get("hmc7044_trx1_dev_channel", 2))
            hmc7044_trx1_sysref_dev_channel = int(
                board_cfg.get("hmc7044_trx1_sysref_dev_channel", 3)
            )
            hmc7044_trx1_sysref_fmc_channel = int(
                board_cfg.get("hmc7044_trx1_sysref_fmc_channel", 7)
            )
            trx2_cs = int(board_cfg.get("trx2_cs", trx_cs + 1))
            trx2_reset_gpio = int(board_cfg.get("trx2_reset_gpio", 135))
            hmc7044_pll1_clkin_freqs = board_cfg.get(
                "hmc7044_pll1_clkin_frequencies",
                [30720000, 30720000, 30720000, 19200000],
            )
            hmc7044_vcxo_freq = int(board_cfg.get("hmc7044_vcxo_frequency", 122880000))
            hmc7044_pll2_out_freq = int(
                board_cfg.get("hmc7044_pll2_output_frequency", 2949120000)
            )
            hmc7044_gpi_controls = board_cfg.get(
                "hmc7044_gpi_controls", [0x00, 0x00, 0x00, 0x11]
            )
            hmc7044_gpo_controls = board_cfg.get(
                "hmc7044_gpo_controls", [0x1F, 0x2B, 0x00, 0x00]
            )

            tx_clkgen_ref = f"<&{clock_chip_label} {hmc7044_tx_channel}>"
            rx_clkgen_ref = f"<&{clock_chip_label} {hmc7044_rx_channel}>"
            rx_os_clkgen_ref = f"<&{clock_chip_label} {hmc7044_tx_channel}>"
            rx_xcvr_clkgen_ref = f"<&{clock_chip_label} {hmc7044_xcvr_channel}>"
            rx_xcvr_div40_clk_ref = f"<&{clock_chip_label} {hmc7044_rx_channel}>"
            tx_xcvr_clkgen_ref = f"<&{clock_chip_label} {hmc7044_tx_xcvr_channel}>"
            tx_xcvr_div40_clk_ref = f"<&{clock_chip_label} {hmc7044_tx_channel}>"
            rx_os_xcvr_clkgen_ref = f"<&{clock_chip_label} {hmc7044_tx_xcvr_channel}>"
            rx_os_xcvr_div40_clk_ref = f"<&{clock_chip_label} {hmc7044_tx_channel}>"

            trx_clocks = [
                f"<&{clock_chip_label} {hmc7044_trx0_dev_channel}>",
                f"<&{clock_chip_label} {hmc7044_xcvr_channel}>",
                f"<&{clock_chip_label} {hmc7044_trx0_sysref_dev_channel}>",
                f"<&{clock_chip_label} {hmc7044_trx0_sysref_fmc_channel}>",
            ]
            trx1_clocks = [
                f"<&{clock_chip_label} {hmc7044_trx1_dev_channel}>",
                f"<&{clock_chip_label} {hmc7044_xcvr_channel}>",
                f"<&{clock_chip_label} {hmc7044_trx1_sysref_dev_channel}>",
                f"<&{clock_chip_label} {hmc7044_trx1_sysref_fmc_channel}>",
            ]
            ad9528_vcxo_freq = None
        else:
            clock_chip_label = "clk0_ad9528"
            tx_clkgen_ref = "<&clk0_ad9528 13>"
            rx_clkgen_ref = "<&clk0_ad9528 13>"
            rx_os_clkgen_ref = "<&clk0_ad9528 13>"
            rx_xcvr_clkgen_ref = "<&clk0_ad9528 1>"
            rx_xcvr_div40_clk_ref = "<&clk0_ad9528 1>"
            tx_xcvr_clkgen_ref = "<&clk0_ad9528 1>"
            tx_xcvr_div40_clk_ref = "<&clk0_ad9528 1>"
            rx_os_xcvr_clkgen_ref = "<&clk0_ad9528 1>"
            rx_os_xcvr_div40_clk_ref = "<&clk0_ad9528 1>"
            trx_clocks = [
                "<&clk0_ad9528 13>",
                "<&clk0_ad9528 1>",
                "<&clk0_ad9528 12>",
                "<&clk0_ad9528 3>",
            ]
            ad9528_vcxo_freq = int(board_cfg.get("ad9528_vcxo_freq", 122880000))
            custom_clock_chip_blocks = board_cfg.get("ad9528_channel_blocks")
            trx2_cs = None
            trx2_reset_gpio = None
            trx1_clocks = trx_clocks

        # --- DMA labels ---
        rx_dma_label = next(
            (
                lbl
                for lbl in labels
                if "_rx_dma" in lbl and "_obs_" not in lbl and "_os_" not in lbl
            ),
            "axi_adrv9009_rx_dma",
        )
        tx_dma_label = next(
            (lbl for lbl in labels if "_tx_dma" in lbl),
            "axi_adrv9009_tx_dma",
        )
        rx_os_dma_label = next(
            (lbl for lbl in labels if "_obs_dma" in lbl or "_rx_os_dma" in lbl),
            "axi_adrv9009_rx_os_dma",
        )

        # --- Device clock references (clkgen or direct) ---
        rx_device_clk_ref = f"<&{rx_clkgen_label}>" if has_rx_clkgen else rx_clkgen_ref
        tx_device_clk_ref = f"<&{tx_clkgen_label}>" if has_tx_clkgen else tx_clkgen_ref
        rx_os_device_clk_ref = (
            f"<&{rx_os_clkgen_label}>" if has_rx_os_clkgen else rx_os_clkgen_ref
        )
        rx_xcvr_conv_clk_ref = (
            f"<&{rx_clkgen_label}>" if has_rx_clkgen else rx_xcvr_clkgen_ref
        )
        rx_xcvr_div40_ref = (
            f"<&{rx_clkgen_label}>" if has_rx_clkgen else rx_xcvr_div40_clk_ref
        )
        tx_xcvr_conv_clk_ref = (
            f"<&{tx_clkgen_label}>" if has_tx_clkgen else tx_xcvr_clkgen_ref
        )
        tx_xcvr_div40_ref = (
            f"<&{tx_clkgen_label}>" if has_tx_clkgen else tx_xcvr_div40_clk_ref
        )
        rx_os_xcvr_conv_clk_ref = (
            f"<&{rx_os_clkgen_label}>" if has_rx_os_clkgen else rx_os_xcvr_clkgen_ref
        )
        rx_os_xcvr_div40_ref = (
            f"<&{rx_os_clkgen_label}>" if has_rx_os_clkgen else rx_os_xcvr_div40_clk_ref
        )

        # --- Link IDs and JESD inputs ---
        rx_link_id = int(board_cfg.get("rx_link_id", 1))
        rx_os_link_id = int(board_cfg.get("rx_os_link_id", 2))
        tx_link_id = int(board_cfg.get("tx_link_id", 0))
        tx_octets_per_frame = int(board_cfg.get("tx_octets_per_frame", 2))
        rx_os_octets_per_frame = int(board_cfg.get("rx_os_octets_per_frame", 2))

        trx_link_ids = [str(rx_link_id), str(tx_link_id)]
        trx_jesd_inputs = [
            f"<&{rx_xcvr_label} 0 {rx_link_id}>",
            f"<&{tx_xcvr_label} 0 {tx_link_id}>",
        ]
        if rx_os_jesd_label:
            trx_link_ids.insert(1, str(rx_os_link_id))
            trx_jesd_inputs.insert(1, f"<&{rx_os_xcvr_label} 0 {rx_os_link_id}>")

        trx_clock_names = [
            '"dev_clk"',
            '"fmc_clk"',
            '"sysref_dev_clk"',
            '"sysref_fmc_clk"',
        ]

        trx_clocks_value = ", ".join(trx_clocks)
        trx1_clocks_value = ", ".join(trx1_clocks) if is_fmcomms8 else trx_clocks_value
        trx_clock_names_value = ", ".join(trx_clock_names)
        trx_link_ids_value = " ".join(trx_link_ids)
        trx_inputs_value = ", ".join(trx_jesd_inputs)

        # --- Profile properties ---
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
        trx_profile_props = board_cfg.get(
            "trx_profile_props", default_trx_profile_props
        )
        trx_profile_props_block = "".join(
            f"\t\t\t{prop}\n" for prop in trx_profile_props
        )

        # --- Build clock chip component ---
        if is_fmcomms8:
            custom_clock_chip_blocks = board_cfg.get("hmc7044_channel_blocks")
            hmc7044_clock_output_names = [
                "hmc7044_fmc_out0_DEV_REFCLK_C",
                "hmc7044_fmc_out1_DEV_SYSREF_C",
                "hmc7044_fmc_out2_DEV_REFCLK_D",
                "hmc7044_fmc_out3_DEV_SYSREF_D",
                "hmc7044_fmc_out4_JESD_REFCLK_TX_OBS_CD",
                "hmc7044_fmc_out5_JESD_REFCLK_RX_CD",
                "hmc7044_fmc_out6_FPGA_SYSREF_TX_OBS_CD",
                "hmc7044_fmc_out7_FPGA_SYSREF_RX_CD",
                "hmc7044_fmc_out8_CORE_CLK_TX_OBS_CD",
                "hmc7044_fmc_out9_CORE_CLK_RX_CD",
                "hmc7044_fmc_out10",
                "hmc7044_fmc_out11",
                "hmc7044_fmc_out12",
                "hmc7044_fmc_out13",
            ]
            if custom_clock_chip_blocks:
                raw_channels_block = "".join(
                    _format_nested_block(str(block))
                    for block in custom_clock_chip_blocks
                )
            else:
                raw_channels_block = _build_default_hmc7044_channels(
                    hmc7044_pll2_out_freq
                )
            clock_output_names_str = ", ".join(
                f'"{n}"' for n in hmc7044_clock_output_names
            )
            clock_ctx = {
                "label": clock_chip_label,
                "cs": clk_cs,
                "spi_max_hz": 10000000,
                "clkin0_ref": None,
                "pll1_clkin_frequencies": hmc7044_pll1_clkin_freqs,
                "vcxo_hz": hmc7044_vcxo_freq,
                "pll2_output_hz": hmc7044_pll2_out_freq,
                "clock_output_names_str": clock_output_names_str,
                "jesd204_sysref_provider": True,
                "jesd204_max_sysref_hz": 2000000,
                "pll1_loop_bandwidth_hz": 200,
                "pll1_ref_prio_ctrl": "0x1E",
                "pll1_ref_autorevert": False,
                "pll1_charge_pump_ua": None,
                "pfd1_max_freq_hz": None,
                "sysref_timer_divider": 3840,
                "pulse_generator_mode": 7,
                "clkin0_buffer_mode": "0x07",
                "clkin1_buffer_mode": "0x09",
                "clkin2_buffer_mode": "0x05",
                "clkin3_buffer_mode": "0x11",
                "oscin_buffer_mode": "0x15",
                "gpi_controls_str": _fmt_gpi_gpo(hmc7044_gpi_controls),
                "gpo_controls_str": _fmt_gpi_gpo(hmc7044_gpo_controls),
                "sync_pin_mode": 1,
                "high_perf_mode_dist_enable": True,
                "channels": None,
                "raw_channels": raw_channels_block,
            }
            clock_component = ComponentModel(
                role="clock",
                part="hmc7044",
                template="hmc7044.tmpl",
                spi_bus=spi_bus,
                spi_cs=clk_cs,
                config=clock_ctx,
            )
        else:
            if custom_clock_chip_blocks:
                # When custom channel blocks are provided, build a raw clock
                # chip node stored in metadata (ad9528_1.tmpl only supports
                # structured channel dicts).
                clock_component = None
                custom_channels_block = "".join(
                    _format_nested_block(str(block))
                    for block in custom_clock_chip_blocks
                )
                _vcxo = ad9528_vcxo_freq or int(
                    board_cfg.get("ad9528_vcxo_freq", 122880000)
                )
                _clock_output_names = (
                    '"ad9528-1_out0", "ad9528-1_out1", "ad9528-1_out2", '
                    '"ad9528-1_out3", "ad9528-1_out4", "ad9528-1_out5", '
                    '"ad9528-1_out6", "ad9528-1_out7", "ad9528-1_out8", '
                    '"ad9528-1_out9", "ad9528-1_out10", "ad9528-1_out11", '
                    '"ad9528-1_out12", "ad9528-1_out13";'
                )
                raw_clock_chip_node = (
                    f"\t\t{clock_chip_label}: ad9528-1@{clk_cs} {{\n"
                    '\t\t\tcompatible = "adi,ad9528";\n'
                    f"\t\t\treg = <{clk_cs}>;\n"
                    "\t\t\t#address-cells = <1>;\n"
                    "\t\t\t#size-cells = <0>;\n"
                    "\t\t\tspi-max-frequency = <10000000>;\n"
                    "\t\t\tadi,refa-enable;\n"
                    "\t\t\tadi,refa-diff-rcv-enable;\n"
                    "\t\t\tadi,refa-r-div = <1>;\n"
                    "\t\t\tadi,osc-in-cmos-neg-inp-enable;\n"
                    "\t\t\tadi,pll1-feedback-div = <4>;\n"
                    "\t\t\tadi,pll1-charge-pump-current-nA = <5000>;\n"
                    "\t\t\tadi,pll2-vco-div-m1 = <3>;\n"
                    "\t\t\tadi,pll2-n2-div = <10>;\n"
                    "\t\t\tadi,pll2-r1-div = <1>;\n"
                    "\t\t\tadi,pll2-charge-pump-current-nA = <805000>;\n"
                    "\t\t\tadi,sysref-src = <2>;\n"
                    "\t\t\tadi,sysref-pattern-mode = <1>;\n"
                    "\t\t\tadi,sysref-k-div = <512>;\n"
                    "\t\t\tadi,sysref-request-enable;\n"
                    "\t\t\tadi,sysref-nshot-mode = <3>;\n"
                    "\t\t\tadi,sysref-request-trigger-mode = <0>;\n"
                    "\t\t\tadi,status-mon-pin0-function-select = <1>;\n"
                    "\t\t\tadi,status-mon-pin1-function-select = <7>;\n"
                    f"\t\t\tadi,vcxo-freq = <{_vcxo}>;\n"
                    f"\t\t\tclock-output-names = {_clock_output_names}\n"
                    "\t\t\t#clock-cells = <1>;\n"
                    f"{custom_channels_block}"
                    "\t\t};\n"
                )
            else:
                clock_ctx = build_ad9528_1_ctx(
                    label=clock_chip_label,
                    cs=clk_cs,
                    vcxo_hz=ad9528_vcxo_freq,
                )
                clock_component = ComponentModel(
                    role="clock",
                    part="ad9528_1",
                    template="ad9528_1.tmpl",
                    spi_bus=spi_bus,
                    spi_cs=clk_cs,
                    config=clock_ctx,
                )
                raw_clock_chip_node = None

        # --- Build PHY device component ---
        phy_ctx = build_adrv9009_device_ctx(
            phy_family=phy_family,
            phy_compatible=phy_compatible,
            trx_cs=trx_cs,
            spi_max_hz=trx_spi_max_frequency,
            gpio_label=gpio_label,
            trx_reset_gpio=trx_reset_gpio,
            trx_sysref_req_gpio=trx_sysref_req_gpio,
            trx_clocks_value=trx_clocks_value,
            trx_clock_names_value=trx_clock_names_value,
            trx_link_ids_value=trx_link_ids_value,
            trx_inputs_value=trx_inputs_value,
            trx_profile_props_block=trx_profile_props_block,
            is_fmcomms8=is_fmcomms8,
            trx2_cs=trx2_cs if is_fmcomms8 else None,
            trx2_reset_gpio=trx2_reset_gpio if is_fmcomms8 else None,
            trx1_clocks_value=trx1_clocks_value if is_fmcomms8 else None,
        )
        phy_component = ComponentModel(
            role="transceiver",
            part=phy_family,
            template="adrv9009.tmpl",
            spi_bus=spi_bus,
            spi_cs=trx_cs,
            config=phy_ctx,
        )

        # --- Build component list ---
        components: list[ComponentModel] = []
        if clock_component is not None:
            components.append(clock_component)
        components.append(phy_component)

        # --- Build JESD link models (empty configs -- rendered as raw nodes) ---
        # ADRV9009 XCVR/TPL nodes use raw f-strings because they differ
        # significantly from the generic adxcvr.tmpl / tpl_core.tmpl patterns.
        # We create JesdLinkModel entries with empty configs so the renderer
        # produces only the DMA overlay nodes and JESD overlay nodes.
        # The XCVR/TPL nodes are added as extra raw nodes in metadata.

        rx_jesd_overlay_ctx = build_jesd204_overlay_ctx(
            label=rx_jesd_label,
            direction="rx",
            clocks_str=(
                f"<&{ps_clk_label} {ps_clk_index}>, "
                f"{rx_device_clk_ref}, <&{rx_xcvr_label} 0>"
            ),
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            clock_output_name=None,
            f=rx_f,
            k=rx_k,
            jesd204_inputs=f"{rx_xcvr_label} 0 {rx_link_id}",
        )
        tx_jesd_overlay_ctx = build_jesd204_overlay_ctx(
            label=tx_jesd_label,
            direction="tx",
            clocks_str=(
                f"<&{ps_clk_label} {ps_clk_index}>, "
                f"{tx_device_clk_ref}, <&{tx_xcvr_label} 0>"
            ),
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            clock_output_name=None,
            f=tx_octets_per_frame,
            k=tx_k,
            jesd204_inputs=f"{tx_xcvr_label} 0 {tx_link_id}",
            converter_resolution=14,
            converters_per_device=tx_m,
            bits_per_sample=16,
            control_bits_per_sample=2,
        )

        jesd_links: list[JesdLinkModel] = [
            JesdLinkModel(
                direction="rx",
                jesd_label=rx_jesd_label,
                xcvr_label=rx_xcvr_label,
                core_label=rx_core_label,
                dma_label=rx_dma_label,
                link_params={"F": rx_f, "K": rx_k},
                jesd_overlay_config=rx_jesd_overlay_ctx,
                # XCVR and TPL rendered as raw nodes
                xcvr_config={},
                tpl_core_config={},
            ),
            JesdLinkModel(
                direction="tx",
                jesd_label=tx_jesd_label,
                xcvr_label=tx_xcvr_label,
                core_label=tx_core_label,
                dma_label=tx_dma_label,
                link_params={"F": tx_octets_per_frame, "K": tx_k, "M": tx_m},
                jesd_overlay_config=tx_jesd_overlay_ctx,
                xcvr_config={},
                tpl_core_config={},
            ),
        ]

        # --- Build raw extra nodes ---
        phy_label = f"trx0_{phy_family}"

        # XCVR nodes (raw - no sys_clk_select/out_clk_select)
        rx_xcvr_node = (
            f"\t&{rx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {rx_xcvr_conv_clk_ref}, {rx_xcvr_div40_ref};\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_gt_clk", "rx_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};"
        )
        rx_os_xcvr_node = (
            f"\t&{rx_os_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {rx_os_xcvr_conv_clk_ref}, {rx_os_xcvr_div40_ref};\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_os_gt_clk", "rx_os_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};"
        )
        tx_xcvr_node = (
            f"\t&{tx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {tx_xcvr_conv_clk_ref}, {tx_xcvr_div40_ref};\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "tx_gt_clk", "tx_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};"
        )

        # TPL core first pass (compatible + dma, no spibus-connected)
        rx_core_first = (
            f"\t&{rx_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-rx-1.0";\n'
            "\t\tadi,axi-decimation-core-available;\n"
            f"\t\tdmas = <&{rx_dma_label} 0>;\n"
            '\t\tdma-names = "rx";\n'
            "\t};"
        )
        rx_os_core_first = (
            f"\t&{rx_os_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-obs-1.0";\n'
            f"\t\tdmas = <&{rx_os_dma_label} 0>;\n"
            '\t\tdma-names = "rx";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};"
        )
        tx_core_first = (
            f"\t&{tx_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-tx-1.0";\n'
            "\t\tadi,axi-interpolation-core-available;\n"
            f"\t\tdmas = <&{tx_dma_label} 0>;\n"
            '\t\tdma-names = "tx";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};"
        )

        # TPL core second pass (spibus-connected + phy clocks)
        rx_core_second = (
            f"\t&{rx_core_label} {{\n\t\tspibus-connected = <&{phy_label}>;\n\t}};"
        )
        rx_os_core_second = (
            f"\t&{rx_os_core_label} {{\n"
            f"\t\tclocks = <&{phy_label} 1>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};"
        )
        tx_core_second = (
            f"\t&{tx_core_label} {{\n"
            f"\t\tspibus-connected = <&{phy_label}>;\n"
            f"\t\tclocks = <&{phy_label} 2>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};"
        )

        # Misc clock node
        misc_clk_node = (
            "\t&misc_clk_0 {\n"
            '\t\tcompatible = "fixed-clock";\n'
            "\t\t#clock-cells = <0>;\n"
            f"\t\tclock-frequency = <{misc_clk_hz}>;\n"
            "\t};"
        )

        # --- Assemble extra_nodes_before (ordered before renderer output) ---
        extra_before: list[str] = [misc_clk_node]
        if has_rx_clkgen:
            extra_before.append(
                f"\t&{rx_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f'\t\tclock-output-names = "{rx_clkgen_label}";\n'
                '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
                "\t};"
            )
        if has_tx_clkgen:
            extra_before.append(
                f"\t&{tx_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f'\t\tclock-output-names = "{tx_clkgen_label}";\n'
                '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
                "\t};"
            )
        if has_rx_os_clkgen:
            extra_before.append(
                f"\t&{rx_os_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f'\t\tclock-output-names = "{rx_os_clkgen_label}";\n'
                '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
                "\t};"
            )

        # ORX JESD overlay (if present)
        rx_os_jesd_overlay_str = None
        if rx_os_jesd_label:
            rx_os_jesd_overlay_ctx = build_jesd204_overlay_ctx(
                label=rx_os_jesd_label,
                direction="rx",
                clocks_str=(
                    f"<&{ps_clk_label} {ps_clk_index}>, "
                    f"{rx_os_device_clk_ref}, <&{rx_os_xcvr_label} 0>"
                ),
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name=None,
                f=rx_os_octets_per_frame,
                k=rx_k,
                jesd204_inputs=(f"{rx_os_xcvr_label} 0 {rx_os_link_id}"),
            )
            # Add ORX as a third JESD link
            jesd_links.insert(
                1,
                JesdLinkModel(
                    direction="rx",
                    jesd_label=rx_os_jesd_label,
                    xcvr_label=rx_os_xcvr_label,
                    core_label=rx_os_core_label,
                    dma_label=rx_os_dma_label,
                    link_params={
                        "F": rx_os_octets_per_frame,
                        "K": rx_k,
                    },
                    jesd_overlay_config=rx_os_jesd_overlay_ctx,
                    xcvr_config={},
                    tpl_core_config={},
                ),
            )

        # DMA nodes for all 3 directions
        def _dma_node(label: str) -> str:
            return (
                f"\t&{label} {{\n"
                "\t\t/delete-property/ compatible;\n"
                '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
                "\t\t#dma-cells = <1>;\n"
                "\t\t#clock-cells = <0>;\n"
                "\t};"
            )

        extra_before.extend(
            [
                _dma_node(rx_dma_label),
                _dma_node(tx_dma_label),
                _dma_node(rx_os_dma_label),
                rx_xcvr_node,
                rx_os_xcvr_node,
                tx_xcvr_node,
                rx_core_first,
                rx_os_core_first,
                tx_core_first,
            ]
        )

        # extra_nodes_after: TPL core second pass nodes
        extra_after: list[str] = [
            rx_core_second,
            rx_os_core_second,
            tx_core_second,
        ]

        # --- Platform config ---
        _32BIT_PLATFORMS = {"vcu118", "zc706"}
        addr_cells = 1 if platform in _32BIT_PLATFORMS else 2

        fpga_config = FpgaConfig(
            platform=platform,
            addr_cells=addr_cells,
            ps_clk_label=ps_clk_label,
            ps_clk_index=ps_clk_index,
            gpio_label=gpio_label,
        )

        # Determine if there's a raw clock chip node (custom ad9528 blocks)
        has_raw_clock = (
            not is_fmcomms8
            and clock_component is None
            and raw_clock_chip_node is not None
        )

        return BoardModel(
            name=f"adrv9009_{platform}",
            platform=platform,
            components=components,
            jesd_links=jesd_links,
            fpga_config=fpga_config,
            metadata={
                "extra_nodes_before": extra_before,
                "extra_nodes_after": extra_after,
                "raw_clock_chip_node": raw_clock_chip_node if has_raw_clock else None,
                "spi_bus": spi_bus,
            },
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_adrv9009", "axi_adrv9025", "axi_adrv9026"}


def _build_default_hmc7044_channels(pll2_out_freq: int) -> str:
    """Build the default HMC7044 channel block string for FMComms8."""
    return (
        "\t\t\thmc7044_fmc_c0: channel@0 {\n"
        "\t\t\t\treg = <0>;\n"
        '\t\t\t\tadi,extended-name = "DEV_REFCLK_C";\n'
        f"\t\t\t\tadi,divider = <12>; // {fmt_hz(pll2_out_freq // 12)}\n"
        "\t\t\t\tadi,driver-mode = <1>;\n"
        "\t\t\t\tadi,coarse-digital-delay = <15>;\n"
        "\t\t\t};\n"
        "\t\t\thmc7044_fmc_c1: channel@1 {\n"
        "\t\t\t\treg = <1>;\n"
        '\t\t\t\tadi,extended-name = "DEV_SYSREF_C";\n'
        f"\t\t\t\tadi,divider = <3840>; // {fmt_hz(pll2_out_freq // 3840)}\n"
        "\t\t\t\tadi,driver-mode = <2>;\n"
        "\t\t\t\tadi,startup-mode-dynamic-enable;\n"
        "\t\t\t\tadi,high-performance-mode-disable;\n"
        "\t\t\t};\n"
        "\t\t\thmc7044_fmc_c2: channel@2 {\n"
        "\t\t\t\treg = <2>;\n"
        '\t\t\t\tadi,extended-name = "DEV_REFCLK_D";\n'
        f"\t\t\t\tadi,divider = <12>; // {fmt_hz(pll2_out_freq // 12)}\n"
        "\t\t\t\tadi,driver-mode = <1>;\n"
        "\t\t\t\tadi,coarse-digital-delay = <15>;\n"
        "\t\t\t};\n"
        "\t\t\thmc7044_fmc_c3: channel@3 {\n"
        "\t\t\t\treg = <3>;\n"
        '\t\t\t\tadi,extended-name = "DEV_SYSREF_D";\n'
        f"\t\t\t\tadi,divider = <3840>; // {fmt_hz(pll2_out_freq // 3840)}\n"
        "\t\t\t\tadi,driver-mode = <2>;\n"
        "\t\t\t\tadi,startup-mode-dynamic-enable;\n"
        "\t\t\t\tadi,high-performance-mode-disable;\n"
        "\t\t\t};\n"
        "\t\t\thmc7044_fmc_c4: channel@4 {\n"
        "\t\t\t\treg = <4>;\n"
        '\t\t\t\tadi,extended-name = "JESD_REFCLK_TX_OBS_CD";\n'
        f"\t\t\t\tadi,divider = <12>; // {fmt_hz(pll2_out_freq // 12)}\n"
        "\t\t\t\tadi,driver-mode = <1>;\n"
        "\t\t\t};\n"
        "\t\t\thmc7044_fmc_c5: channel@5 {\n"
        "\t\t\t\treg = <5>;\n"
        '\t\t\t\tadi,extended-name = "JESD_REFCLK_RX_CD";\n'
        f"\t\t\t\tadi,divider = <12>; // {fmt_hz(pll2_out_freq // 12)}\n"
        "\t\t\t\tadi,driver-mode = <1>;\n"
        "\t\t\t};\n"
        "\t\t\thmc7044_fmc_c6: channel@6 {\n"
        "\t\t\t\treg = <6>;\n"
        '\t\t\t\tadi,extended-name = "FPGA_SYSREF_TX_OBS_CD";\n'
        f"\t\t\t\tadi,divider = <3840>; // {fmt_hz(pll2_out_freq // 3840)}\n"
        "\t\t\t\tadi,driver-mode = <2>;\n"
        "\t\t\t\tadi,startup-mode-dynamic-enable;\n"
        "\t\t\t\tadi,high-performance-mode-disable;\n"
        "\t\t\t};\n"
        "\t\t\thmc7044_fmc_c7: channel@7 {\n"
        "\t\t\t\treg = <7>;\n"
        '\t\t\t\tadi,extended-name = "FPGA_SYSREF_RX_CD";\n'
        f"\t\t\t\tadi,divider = <3840>; // {fmt_hz(pll2_out_freq // 3840)}\n"
        "\t\t\t\tadi,driver-mode = <2>;\n"
        "\t\t\t\tadi,startup-mode-dynamic-enable;\n"
        "\t\t\t\tadi,high-performance-mode-disable;\n"
        "\t\t\t};\n"
        "\t\t\thmc7044_fmc_c8: channel@8 {\n"
        "\t\t\t\treg = <8>;\n"
        '\t\t\t\tadi,extended-name = "CORE_CLK_TX_OBS_CD";\n'
        f"\t\t\t\tadi,divider = <24>; // {fmt_hz(pll2_out_freq // 24)}\n"
        "\t\t\t\tadi,driver-mode = <2>;\n"
        "\t\t\t};\n"
        "\t\t\thmc7044_fmc_c9: channel@9 {\n"
        "\t\t\t\treg = <9>;\n"
        '\t\t\t\tadi,extended-name = "CORE_CLK_RX_CD";\n'
        f"\t\t\t\tadi,divider = <12>; // {fmt_hz(pll2_out_freq // 12)}\n"
        "\t\t\t\tadi,driver-mode = <2>;\n"
        "\t\t\t};\n"
    )
