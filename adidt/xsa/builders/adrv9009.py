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
from ...devices.clocks import AD9528_1, AD9528_1Channel
from ...devices.clocks.ad952x import _GpioLine
from ..._utils import coerce_board_int, fmt_hz
from ...devices.fpga_ip import (
    build_adxcvr_ctx,
    build_jesd204_overlay_ctx,
    build_tpl_core_ctx,
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
    """Return True if topology indicates a dual-chip FMComms8 layout.

    FMComms8 designs mark the observation-receiver TPL core with an
    ``obs`` substring (for example
    ``obs_adrv9009_fmc_tpl_core_adc_tpl_core`` or
    ``adrv9009_tpl_core_obs_adc_tpl_core``).  Single-chip
    ZCU102+ADRV9009 designs use ``rx_os`` on the JESD / DMA side and
    never put ``obs`` on their TPL core, so any ADRV9009 TPL core
    whose label carries ``obs`` reliably identifies FMComms8.
    """
    lowered = [n.lower() for n in topology_names]
    for name in lowered:
        if "fmcomms8" in name or "adrv9009-x2" in name or "adrv9009_x2" in name:
            return True
        if "adrv9009" in name and ("_fmc_c_" in name or "_fmc_d_" in name):
            return True
        if "adrv9009" in name and "tpl_core" in name and "obs" in name:
            return True
    return False


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


from ..._utils import fmt_gpi_gpo as _fmt_gpi_gpo  # noqa: E402


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
            if phy_comp and phy_comp.rendered and rendered["converters"]:
                spi_node = renderer._wrap_spi_bus(spi_bus, raw_clk + phy_comp.rendered)
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
        phy_compatible_list = [f"adi,{phy_family}", phy_family]

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

        # Determine if ORX path exists in the topology by checking for the
        # ORX JESD label AND the ORX TPL core label in the sdtgen base DTS.
        has_rx_os = bool(rx_os_jesd_label)
        if has_rx_os:
            assert rx_os_jesd_label is not None  # narrowing for type checker
            rx_os_xcvr_label = rx_os_jesd_label.replace(
                "_jesd_rx_axi", "_xcvr"
            ).replace("_rx_os_jesd", "_rx_os_xcvr")
            rx_os_clkgen_label = rx_os_jesd_label.replace(
                "_jesd_rx_axi", "_clkgen"
            ).replace("_rx_os_jesd", "_rx_os_clkgen")
        else:
            rx_os_xcvr_label = ""
            rx_os_clkgen_label = ""

        has_rx_os_clkgen = has_rx_os and not is_fmcomms8

        # --- TPL core labels ---
        # Prefer XSA-discovered labels; ``_pick_matching_label`` falls
        # back to the passed default on no match.  Doing this on both
        # paths fixes the standard ZCU102+ADRV9009 project, whose base
        # DTS emits ``{rx,rx_os,tx}_adrv9009_tpl_core_{adc,dac}_tpl_core``
        # rather than the legacy ``axi_adrv9009_core_{rx,rx_obs,tx}``
        # names that were hardcoded when this builder was FMComms8-only.
        rx_core_label = _pick_matching_label(
            labels, "axi_adrv9009_core_rx", ("adrv9009", "tpl_core", "rx", "adc")
        )
        # Standard ZCU102+ADRV9009 names the observation TPL core
        # ``rx_os_adrv9009_tpl_core_adc_tpl_core``; FMComms8 projects
        # use ``obs`` in the label instead.  Match whichever is
        # present in the XSA, falling back to the legacy hardcoded
        # default only if neither is found.
        rx_os_core_label = ""
        if has_rx_os:
            for tokens in (
                ("adrv9009", "tpl_core", "rx_os", "adc"),
                ("adrv9009", "tpl_core", "obs", "adc"),
            ):
                candidate = _pick_matching_label(
                    labels, "axi_adrv9009_core_rx_obs", tokens
                )
                if candidate != "axi_adrv9009_core_rx_obs":
                    rx_os_core_label = candidate
                    break
            if not rx_os_core_label:
                rx_os_core_label = "axi_adrv9009_core_rx_obs"
        tx_core_label = _pick_matching_label(
            labels, "axi_adrv9009_core_tx", ("adrv9009", "tpl_core", "tx", "dac")
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
            phy_compatible_list = ["adrv9009-x2"]

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
        # The xcvr "conv" clock is the GT reference (QPLL input).  On
        # single-chip ZC706/ZCU102 + ADRV9009 (AD9528-based) production
        # wires this directly from AD9528 ch1 — a single "conv" input
        # with no "div40".  Routing it through axi_clkgen pinned the MMCM
        # output at 122.88 MHz for the GT, so the framework's
        # ``clk_set_rate(device_clk, 61.44 MHz)`` on TX/RX_OS returned
        # -EBUSY and the link stayed "Link is disabled".  The dual-chip
        # FMComms8 path is different: it uses distinct HMC7044 channels
        # for ``conv`` and ``div40`` (e.g. ch5/ch9 for RX) and needs both
        # clocks declared, so we preserve the legacy dual-clock shape
        # there.
        rx_xcvr_conv_clk_ref = rx_xcvr_clkgen_ref
        tx_xcvr_conv_clk_ref = tx_xcvr_clkgen_ref
        rx_os_xcvr_conv_clk_ref = rx_os_xcvr_clkgen_ref
        if is_fmcomms8:
            rx_xcvr_div40_ref: str | None = rx_xcvr_div40_clk_ref
            tx_xcvr_div40_ref: str | None = tx_xcvr_div40_clk_ref
            rx_os_xcvr_div40_ref: str | None = rx_os_xcvr_div40_clk_ref
        else:
            rx_xcvr_div40_ref = None
            tx_xcvr_div40_ref = None
            rx_os_xcvr_div40_ref = None

        # --- Link IDs and JESD inputs ---
        rx_link_id = int(board_cfg.get("rx_link_id", 1))
        rx_os_link_id = int(board_cfg.get("rx_os_link_id", 2))
        tx_link_id = int(board_cfg.get("tx_link_id", 0))
        tx_octets_per_frame = int(board_cfg.get("tx_octets_per_frame", 2))
        rx_os_octets_per_frame = int(board_cfg.get("rx_os_octets_per_frame", 2))

        trx_link_ids = [str(rx_link_id), str(tx_link_id)]
        # adrv9009-phy is the JESD framework top-device; its
        # ``jesd204-inputs`` defines the topology graph the framework
        # walks to find downstream devices.  For the ZC706 ADRV9009
        # path (non-FMComms8) we point at the AXI JESD cores (RX,
        # RX_OS) and the TX TPL DAC to mirror the Kuiper production
        # topology: AD9528 → xcvr → axi-jesd204 → (RX: phy, TX: TX TPL
        # → phy).  Without the TX TPL DAC in the topology the
        # framework can't call clk_set_rate on the TX clkgen for the
        # per-link rate (61.44 MHz vs 122.88 MHz for RX).
        if not is_fmcomms8 and rx_jesd_label and tx_jesd_label:
            trx_jesd_inputs = [
                f"<&{rx_jesd_label} 0 {rx_link_id}>",
                f"<&{tx_core_label} 0 {tx_link_id}>",
            ]
            if rx_os_jesd_label:
                trx_link_ids.insert(1, str(rx_os_link_id))
                trx_jesd_inputs.insert(1, f"<&{rx_os_jesd_label} 0 {rx_os_link_id}>")
        else:
            # FMComms8 / fallback: keep the original xcvr-pointing topology.
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

        # Prepend JESD lane-clock refs so the adrv9009 driver defers
        # probe (and FSM start) until axi-jesd204-{rx,tx,rx_os} have
        # bound and registered their lane clocks.  Without these the
        # adrv9009 starts the FSM as soon as AD9528 is ready, which can
        # complete `opt_post_running_stage` BEFORE axi-jesd204 platform
        # devices even probe; a later axi_jesd204_rx_probe then calls
        # jesd204_fsm_start on a link in opt_post_running and crashes
        # with a NULL deref in jesd204_validate_lnk_state.  Matches the
        # Kuiper production zynq-zc706-adv7511-adrv9009 DT.
        if not is_fmcomms8 and rx_jesd_label and tx_jesd_label:
            jesd_clock_refs = [f"<&{rx_jesd_label}>", f"<&{tx_jesd_label}>"]
            jesd_clock_names = ['"jesd_rx_clk"', '"jesd_tx_clk"']
            if rx_os_jesd_label:
                jesd_clock_refs.insert(1, f"<&{rx_os_jesd_label}>")
                jesd_clock_names.insert(1, '"jesd_rx_os_clk"')
            trx_clocks = jesd_clock_refs + trx_clocks
            trx1_clocks = jesd_clock_refs + trx1_clocks
            trx_clock_names = jesd_clock_names + trx_clock_names

        trx_clocks_value = ", ".join(trx_clocks)
        trx1_clocks_value = ", ".join(trx1_clocks) if is_fmcomms8 else trx_clocks_value
        trx_clock_names_value = ", ".join(trx_clock_names)
        trx_link_ids_value = " ".join(trx_link_ids)
        trx_inputs_value = ", ".join(trx_jesd_inputs)

        # --- Profile properties ---
        # Talise framer/deframer config per-link.  Without these the
        # Talise driver uses built-in defaults that may not match the
        # HDL's compile-time JESD link parameters, causing ILAS to fail
        # and the AXI JESD core's ``status`` sysfs to report
        # ``Link is disabled`` even though the framework FSM reaches
        # ``opt_post_running_stage``.  Values lifted verbatim from the
        # Kuiper production ``zynq-zc706-adv7511-adrv9009`` DT.
        # framer-a → RX (M=4 L=2 F=4 Np=16 K=32)
        # framer-b → RX_OS (M=2 L=2 F=2 Np=16 K=32)
        # deframer-a → TX (M=4 L=4 F=2 Np=16 K=32)
        default_jesd_framer_deframer_props = [
            'adi,jesd204-framer-a-bank-id = <0x01>;',
            'adi,jesd204-framer-a-device-id = <0x00>;',
            'adi,jesd204-framer-a-lane0-id = <0x00>;',
            'adi,jesd204-framer-a-m = <0x04>;',
            'adi,jesd204-framer-a-k = <0x20>;',
            'adi,jesd204-framer-a-f = <0x04>;',
            'adi,jesd204-framer-a-np = <0x10>;',
            'adi,jesd204-framer-a-scramble = <0x01>;',
            'adi,jesd204-framer-a-external-sysref = <0x01>;',
            'adi,jesd204-framer-a-serializer-lanes-enabled = <0x03>;',
            'adi,jesd204-framer-a-serializer-lane-crossbar = <0xe4>;',
            'adi,jesd204-framer-a-lmfc-offset = <0x1f>;',
            'adi,jesd204-framer-a-new-sysref-on-relink = <0x00>;',
            'adi,jesd204-framer-a-syncb-in-select = <0x00>;',
            'adi,jesd204-framer-a-over-sample = <0x00>;',
            'adi,jesd204-framer-a-syncb-in-lvds-mode = <0x01>;',
            'adi,jesd204-framer-a-syncb-in-lvds-pn-invert = <0x00>;',
            'adi,jesd204-framer-a-enable-manual-lane-xbar = <0x00>;',
            'adi,jesd204-framer-b-bank-id = <0x00>;',
            'adi,jesd204-framer-b-device-id = <0x00>;',
            'adi,jesd204-framer-b-lane0-id = <0x00>;',
            'adi,jesd204-framer-b-m = <0x02>;',
            'adi,jesd204-framer-b-k = <0x20>;',
            'adi,jesd204-framer-b-f = <0x02>;',
            'adi,jesd204-framer-b-np = <0x10>;',
            'adi,jesd204-framer-b-scramble = <0x01>;',
            'adi,jesd204-framer-b-external-sysref = <0x01>;',
            'adi,jesd204-framer-b-serializer-lanes-enabled = <0x0c>;',
            'adi,jesd204-framer-b-serializer-lane-crossbar = <0xe4>;',
            'adi,jesd204-framer-b-lmfc-offset = <0x1f>;',
            'adi,jesd204-framer-b-new-sysref-on-relink = <0x00>;',
            'adi,jesd204-framer-b-syncb-in-select = <0x01>;',
            'adi,jesd204-framer-b-over-sample = <0x00>;',
            'adi,jesd204-framer-b-syncb-in-lvds-mode = <0x01>;',
            'adi,jesd204-framer-b-syncb-in-lvds-pn-invert = <0x00>;',
            'adi,jesd204-framer-b-enable-manual-lane-xbar = <0x00>;',
            'adi,jesd204-deframer-a-bank-id = <0x00>;',
            'adi,jesd204-deframer-a-device-id = <0x00>;',
            'adi,jesd204-deframer-a-lane0-id = <0x00>;',
            'adi,jesd204-deframer-a-m = <0x04>;',
            'adi,jesd204-deframer-a-k = <0x20>;',
            'adi,jesd204-deframer-a-scramble = <0x01>;',
            'adi,jesd204-deframer-a-external-sysref = <0x01>;',
            'adi,jesd204-deframer-a-deserializer-lanes-enabled = <0x0f>;',
            'adi,jesd204-deframer-a-deserializer-lane-crossbar = <0xe4>;',
            'adi,jesd204-deframer-a-lmfc-offset = <0x11>;',
            'adi,jesd204-deframer-a-new-sysref-on-relink = <0x00>;',
            'adi,jesd204-deframer-a-syncb-out-select = <0x00>;',
            'adi,jesd204-deframer-a-np = <0x10>;',
            'adi,jesd204-deframer-a-syncb-out-lvds-mode = <0x01>;',
            'adi,jesd204-deframer-a-syncb-out-lvds-pn-invert = <0x00>;',
            'adi,jesd204-deframer-a-syncb-out-cmos-slew-rate = <0x00>;',
            'adi,jesd204-deframer-a-syncb-out-cmos-drive-level = <0x00>;',
            'adi,jesd204-deframer-a-enable-manual-lane-xbar = <0x00>;',
            'adi,jesd204-ser-amplitude = <0x0f>;',
            'adi,jesd204-ser-pre-emphasis = <0x01>;',
            'adi,jesd204-ser-invert-lane-polarity = <0x00>;',
            'adi,jesd204-des-invert-lane-polarity = <0x00>;',
            'adi,jesd204-des-eq-setting = <0x01>;',
            'adi,jesd204-sysref-lvds-mode = <0x01>;',
            'adi,jesd204-sysref-lvds-pn-invert = <0x00>;',
        ]
        # Talise RX/ORX/TX profile properties copied verbatim from the
        # production Kuiper ``zynq-zc706-adv7511-adrv9009`` DT.  The
        # ``*-rate_khz`` entries (0x1e000 = 122880) are what the kernel
        # JESD204 framework reads into ``lnk->sample_rate`` when computing
        # per-link device/lane clocks — omitting them makes Talise pick
        # built-in defaults whose rates don't match the HDL's MMCM
        # configuration, producing a ``Link is disabled`` state.
        default_trx_profile_props = default_jesd_framer_deframer_props + [
            "adi,rx-profile-rx-fir-gain_db = <0xfffffffa>;",
            "adi,rx-profile-rx-fir-num-fir-coefs = <0x30>;",
            "adi,rx-profile-rx-fir-coefs = <0xfff8ffea 0x200032 0xffbcff96 0x8d00c7 0xfefefea0 0x1ae023c 0xfd4dfc79 0x42d0570 0xf994f784 0xa090df6 0xeef4e427 0x248b7977 0x7977248b 0xe427eef4 0xdf60a09 0xf784f994 0x570042d 0xfc79fd4d 0x23c01ae 0xfea0fefe 0xc7008d 0xff96ffbc 0x320020 0xffeafff8>;",
            "adi,rx-profile-rx-fir-decimation = <0x02>;",
            "adi,rx-profile-rx-dec5-decimation = <0x04>;",
            "adi,rx-profile-rhb1-decimation = <0x02>;",
            "adi,rx-profile-rx-output-rate_khz = <0x1e000>;",
            "adi,rx-profile-rf-bandwidth_hz = <0x5f5e100>;",
            "adi,rx-profile-rx-bbf3d-bcorner_khz = <0x186a0>;",
            "adi,rx-profile-rx-adc-profile = <0x1090092 0xb5005a 0x500016e 0x4e9001b 0x4ea0011 0x2ce0027 0x30002e 0x1b00a1 0x00 0x00 0x280000 0x70006 0x2a0000 0x70006 0x2a0000 0x19001b 0x00 0x19001b 0x00 0xa5002c 0x1f0389>;",
            "adi,rx-profile-rx-ddc-mode = <0x00>;",
            "adi,orx-profile-rx-fir-gain_db = <0xfffffffa>;",
            "adi,orx-profile-rx-fir-num-fir-coefs = <0x30>;",
            "adi,orx-profile-rx-fir-coefs = <0xfff7ffee 0x1f002a 0xffbfffa7 0x8400a8 0xff10fed6 0x18c01e6 0xfd88fcfe 0x3c8048b 0xfa06f8ba 0x9410beb 0xf01ee8a1 0x25d97486 0x748625d9 0xe8a1f01e 0xbeb0941 0xf8bafa06 0x48b03c8 0xfcfefd88 0x1e6018c 0xfed6ff10 0xa80084 0xffa7ffbf 0x2a001f 0xffeefff7>;",
            "adi,orx-profile-rx-fir-decimation = <0x02>;",
            "adi,orx-profile-rx-dec5-decimation = <0x04>;",
            "adi,orx-profile-rhb1-decimation = <0x02>;",
            "adi,orx-profile-orx-output-rate_khz = <0x1e000>;",
            "adi,orx-profile-rf-bandwidth_hz = <0x5f5e100>;",
            "adi,orx-profile-rx-bbf3d-bcorner_khz = <0x36ee8>;",
            "adi,orx-profile-orx-low-pass-adc-profile = <0x1090092 0xb5005a 0x500016e 0x4e9001b 0x4ea0011 0x2ce0027 0x30002e 0x1b00a1 0x00 0x00 0x280000 0x70006 0x2a0000 0x70006 0x2a0000 0x19001b 0x00 0x19001b 0x00 0xa5002c 0x1f0389>;",
            "adi,orx-profile-orx-band-pass-adc-profile = <0x1090092 0xb5005a 0x500016e 0x4e9001b 0x4ea0011 0x2ce0027 0x30002e 0x1b00a1 0x00 0x00 0x280000 0x70006 0x2a0000 0x70006 0x2a0000 0x19001b 0x00 0x19001b 0x00 0xa5002c 0x1f0389>;",
            "adi,orx-profile-orx-ddc-mode = <0x00>;",
            "adi,orx-profile-orx-merge-filter = <0x00 0x00 0x00 0x00 0x00 0x00>;",
            "adi,tx-profile-tx-fir-gain_db = <0x06>;",
            "adi,tx-profile-tx-fir-num-fir-coefs = <0x50>;",
            "adi,tx-profile-tx-fir-coefs = <0x00 0x01 0xfffd 0x10007 0xfffdfff3 0x70019 0xfff2ffd6 0x1b0045 0xffd2ff95 0x4a00a0 0xff8dff1b 0xb80150 0xfef8fe2c 0x17e028d 0xfde6fc78 0x2f204f5 0xfbe0f8ce 0x5ce0b3f 0xf811ed12 0xee83f5d 0x3f5d0ee8 0xed12f811 0xb3f05ce 0xf8cefbe0 0x4f502f2 0xfc78fde6 0x28d017e 0xfe2cfef8 0x15000b8 0xff1bff8d 0xa0004a 0xff95ffd2 0x45001b 0xffd6fff2 0x190007 0xfff3fffd 0x70001 0xfffd0000 0x10000 0x00>;",
            "adi,tx-profile-dac-div = <0x01>;",
            "adi,tx-profile-tx-fir-interpolation = <0x02>;",
            "adi,tx-profile-thb1-interpolation = <0x02>;",
            "adi,tx-profile-thb2-interpolation = <0x02>;",
            "adi,tx-profile-thb3-interpolation = <0x02>;",
            "adi,tx-profile-tx-int5-interpolation = <0x01>;",
            "adi,tx-profile-tx-input-rate_khz = <0x1e000>;",
            "adi,tx-profile-primary-sig-bandwidth_hz = <0x2faf080>;",
            "adi,tx-profile-rf-bandwidth_hz = <0x5f5e100>;",
            "adi,tx-profile-tx-dac3d-bcorner_khz = <0x2da78>;",
            "adi,tx-profile-tx-bbf3d-bcorner_khz = <0xdac0>;",
            "adi,tx-profile-loop-back-adc-profile = <0x1090092 0xb5005a 0x500016e 0x4e9001b 0x4ea0011 0x2ce0027 0x30002e 0x1b00a1 0x00 0x00 0x280000 0x70006 0x2a0000 0x70006 0x2a0000 0x19001b 0x00 0x19001b 0x00 0xa5002c 0x1f0389>;",
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
            from ...devices.clocks import HMC7044

            hmc7044_dev = HMC7044(
                label=clock_chip_label,
                spi_max_hz=10_000_000,
                pll1_clkin_frequencies=hmc7044_pll1_clkin_freqs,
                vcxo_hz=hmc7044_vcxo_freq,
                pll2_output_hz=hmc7044_pll2_out_freq,
                clock_output_names=hmc7044_clock_output_names,
                raw_channels=raw_channels_block,
                jesd204_sysref_provider=True,
                jesd204_max_sysref_hz=2_000_000,
                pll1_loop_bandwidth_hz=200,
                pll1_ref_prio_ctrl="0x1E",
                pll1_ref_autorevert=False,
                sysref_timer_divider=3840,
                pulse_generator_mode=7,
                clkin0_buffer_mode="0x07",
                clkin1_buffer_mode="0x09",
                clkin2_buffer_mode="0x05",
                clkin3_buffer_mode="0x11",
                oscin_buffer_mode="0x15",
                gpi_controls=hmc7044_gpi_controls,
                gpo_controls=hmc7044_gpo_controls,
                sync_pin_mode=1,
                high_perf_mode_dist_enable=True,
            )
            clock_component = ComponentModel(
                role="clock",
                part="hmc7044",
                spi_bus=spi_bus,
                spi_cs=clk_cs,
                rendered=hmc7044_dev.render_dt(cs=clk_cs),
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
                assert ad9528_vcxo_freq is not None
                ch_freq = ad9528_vcxo_freq * 10 // 10
                # Channel divider 10 (matches Kuiper production zynq-zc706
                # ADRV9009 DT). Output rate = VCXO * pll1_fb * pll2_n2 /
                # (pll2_r1 * pll2_vco_div_m1 * channel_divider) ≈ 122.88 MHz
                # for VCXO=122.88. Earlier divider=5 produced 245.76, which
                # caused the FPGA MMCM to pass 245.76 MHz to the JESD core
                # and ``axi-jesd204-rx/tx/status`` reported "Link is
                # disabled" because the framework expects 122.88 / 61.44.
                ad9528_1_specs = [
                    {
                        "id": 13,
                        "name": "DEV_CLK",
                        "divider": 10,
                        "signal_source": 0,
                        "is_sysref": False,
                        "freq_str": fmt_hz(ch_freq),
                    },
                    {
                        "id": 1,
                        "name": "FMC_CLK",
                        "divider": 10,
                        "signal_source": 0,
                        "is_sysref": False,
                        "freq_str": fmt_hz(ch_freq),
                    },
                    {
                        "id": 12,
                        "name": "DEV_SYSREF",
                        "divider": 10,
                        "signal_source": 2,
                        "is_sysref": False,
                    },
                    {
                        "id": 3,
                        "name": "FMC_SYSREF",
                        "divider": 10,
                        "signal_source": 2,
                        "is_sysref": False,
                    },
                ]
                # Mark AD9528 as jesd204-device + sysref-provider so the
                # axi-jesd204-{rx,tx} platform driver can resolve its
                # ``jesd204-inputs`` chain.  Without these the AXI JESD
                # core stays in deferred-probe forever and the
                # ``/sys/.../axi-jesd204-*/status`` file is never created.
                # ``reset-gpios`` mirrors the Kuiper production DT
                # (gpio0:113 on ZC706 + ADRV9009).
                ad9528_reset_gpio = int(board_cfg.get("ad9528_reset_gpio", 113))
                ad9528 = AD9528_1(
                    label=clock_chip_label,
                    vcxo_hz=ad9528_vcxo_freq,
                    channels={s["id"]: AD9528_1Channel(**s) for s in ad9528_1_specs},
                    gpio_lines=[
                        _GpioLine(
                            prop="reset-gpios",
                            controller=gpio_label,
                            index=ad9528_reset_gpio,
                        ),
                    ],
                    jesd204_sysref_provider=True,
                )
                clock_component = ComponentModel(
                    role="clock",
                    part="ad9528_1",
                    spi_bus=spi_bus,
                    spi_cs=clk_cs,
                    rendered=ad9528.render_dt(cs=clk_cs),
                )
                raw_clock_chip_node = None

        # --- Build PHY device component ---
        from ...devices.transceivers import ADRV9009

        shared_ctx: dict[str, Any] = {
            "gpio_label": gpio_label,
            "clocks_value": trx_clocks_value,
            "clock_names_value": trx_clock_names_value,
            "link_ids": trx_link_ids_value,
            "jesd204_inputs": trx_inputs_value,
            "profile_props": trx_profile_props,
        }

        phy_dev = ADRV9009(
            label=f"trx0_{phy_family}",
            node_name_base=f"{phy_family}-phy",
            compatible_strings=phy_compatible_list,
            spi_max_hz=trx_spi_max_frequency,
            reset_gpio=trx_reset_gpio,
            sysref_req_gpio=trx_sysref_req_gpio,
        )
        phy_rendered = phy_dev.render_dt(cs=trx_cs, context=shared_ctx)

        if is_fmcomms8:
            # Second chip: its own clocks, cs, reset; no sysref-req-gpios.
            # ``trx2_cs`` is always an int on the is_fmcomms8 branch (see
            # the earlier ``trx2_cs = int(board_cfg.get(...))`` assignment);
            # narrow the type here so downstream callers of ``render_dt``
            # see a concrete ``int``.
            assert trx2_cs is not None
            phy2_dev = ADRV9009(
                label=f"trx1_{phy_family}",
                node_name_base=f"{phy_family}-phy",
                compatible_strings=[phy_family],
                spi_max_hz=trx_spi_max_frequency,
                reset_gpio=trx2_reset_gpio,
                sysref_req_gpio=None,
            )
            phy2_ctx = dict(shared_ctx)
            phy2_ctx["clocks_value"] = trx1_clocks_value
            phy_rendered = (
                phy_rendered + "\n" + phy2_dev.render_dt(cs=trx2_cs, context=phy2_ctx)
            )

        phy_component = ComponentModel(
            role="transceiver",
            part=phy_family,
            spi_bus=spi_bus,
            spi_cs=trx_cs,
            rendered=phy_rendered,
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
            clock_output_name="jesd_rx_lane_clk",
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
            clock_output_name="jesd_tx_lane_clk",
            f=tx_octets_per_frame,
            k=tx_k,
            jesd204_inputs=f"{tx_xcvr_label} 0 {tx_link_id}",
            converter_resolution=16,
            converters_per_device=tx_m,
            bits_per_sample=16,
            control_bits_per_sample=0,
        )

        jesd_links: list[JesdLinkModel] = [
            JesdLinkModel(
                direction="rx",
                jesd_label=rx_jesd_label,
                xcvr_label=rx_xcvr_label,
                core_label=rx_core_label,
                dma_label=rx_dma_label,
                link_params={"F": rx_f, "K": rx_k},
                jesd_overlay_rendered=rx_jesd_overlay_ctx,
                # XCVR and TPL rendered as raw nodes
            ),
            JesdLinkModel(
                direction="tx",
                jesd_label=tx_jesd_label,
                xcvr_label=tx_xcvr_label,
                core_label=tx_core_label,
                dma_label=tx_dma_label,
                link_params={"F": tx_octets_per_frame, "K": tx_k, "M": tx_m},
                jesd_overlay_rendered=tx_jesd_overlay_ctx,
            ),
        ]

        # --- Build raw extra nodes ---
        phy_label = f"trx0_{phy_family}"

        # XCVR nodes - need adi,sys-clk-select / adi,out-clk-select (and
        # adi,use-lpm-enable on RX/RX_OS) so axi-jesd204-{rx,tx} drivers
        # can probe; without these the platform driver waits indefinitely
        # in deferred-probe and the /sys/bus/.../axi-jesd204-*/status
        # file is never created.  RX uses sys-clk-select=0, TX uses
        # sys-clk-select=3; both use out-clk-select=3.  Mirrors the
        # working ADRV937xBuilder pattern (adidt/xsa/builders/adrv937x.py).
        # Single-chip ADRV9009 (AD9528-based ZC706/ZCU102) declares a
        # single "conv" clock matching production; FMComms8 keeps the
        # legacy "conv" + "div40" pair pointing at two distinct HMC7044
        # channels.
        def _xcvr_clocks(conv: str, div40: str | None) -> tuple[str, str]:
            if div40 is None:
                return f"{conv}", '"conv"'
            return f"{conv}, {div40}", '"conv", "div40"'

        rx_clk_vals, rx_clk_names = _xcvr_clocks(rx_xcvr_conv_clk_ref, rx_xcvr_div40_ref)
        tx_clk_vals, tx_clk_names = _xcvr_clocks(tx_xcvr_conv_clk_ref, tx_xcvr_div40_ref)
        rx_os_clk_vals, rx_os_clk_names = _xcvr_clocks(
            rx_os_xcvr_conv_clk_ref, rx_os_xcvr_div40_ref
        )

        rx_xcvr_node = (
            f"\t&{rx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {rx_clk_vals};\n"
            f"\t\tclock-names = {rx_clk_names};\n"
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_gt_clk", "rx_out_clk";\n'
            "\t\tadi,sys-clk-select = <0>;\n"
            "\t\tadi,out-clk-select = <3>;\n"
            "\t\tadi,use-lpm-enable;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{clock_chip_label} 0 {rx_link_id}>;\n"
            "\t};"
        )
        rx_os_xcvr_node = ""
        if has_rx_os:
            rx_os_xcvr_node = (
                f"\t&{rx_os_xcvr_label} {{\n"
                '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
                f"\t\tclocks = {rx_os_clk_vals};\n"
                f"\t\tclock-names = {rx_os_clk_names};\n"
                "\t\t#clock-cells = <1>;\n"
                '\t\tclock-output-names = "rx_os_gt_clk", "rx_os_out_clk";\n'
                "\t\tadi,sys-clk-select = <0>;\n"
                "\t\tadi,out-clk-select = <3>;\n"
                "\t\tadi,use-lpm-enable;\n"
                "\t\tjesd204-device;\n"
                "\t\t#jesd204-cells = <2>;\n"
                f"\t\tjesd204-inputs = <&{clock_chip_label} 0 {rx_os_link_id}>;\n"
                "\t};"
            )
        tx_xcvr_node = (
            f"\t&{tx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {tx_clk_vals};\n"
            f"\t\tclock-names = {tx_clk_names};\n"
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "tx_gt_clk", "tx_out_clk";\n'
            "\t\tadi,sys-clk-select = <3>;\n"
            "\t\tadi,out-clk-select = <3>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{clock_chip_label} 0 {tx_link_id}>;\n"
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
        rx_os_core_first = ""
        if has_rx_os:
            rx_os_core_first = (
                f"\t&{rx_os_core_label} {{\n"
                '\t\tcompatible = "adi,axi-adrv9009-obs-1.0";\n'
                f"\t\tdmas = <&{rx_os_dma_label} 0>;\n"
                '\t\tdma-names = "rx";\n'
                f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>;\n"
                '\t\tclock-names = "sampl_clk";\n'
                "\t};"
            )
        # TX TPL DAC needs to participate in the JESD framework graph
        # (jesd204-device + jesd204-inputs pointing at axi-jesd204-tx)
        # so the framework can call clk_set_rate on the TX clkgen MMCM
        # to produce the per-link rate (61.44 MHz for L=4) instead of
        # passing through the input rate.  Production DT also has
        # ``adi,axi-pl-fifo-enable`` for the PL DDR FIFO bypass mode.
        tx_core_first = (
            f"\t&{tx_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-tx-1.0";\n'
            "\t\tadi,axi-interpolation-core-available;\n"
            f"\t\tdmas = <&{tx_dma_label} 0>;\n"
            '\t\tdma-names = "tx";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{tx_jesd_label} 0 {tx_link_id}>;\n"
            "\t};"
        )

        # TPL core second pass (spibus-connected + phy clocks)
        rx_core_second = (
            f"\t&{rx_core_label} {{\n\t\tspibus-connected = <&{phy_label}>;\n\t}};"
        )
        rx_os_core_second = ""
        if has_rx_os:
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
        # axi-clkgen needs `clocks = <s_axi_aclk, clkin1>` so the MMCM
        # driver can program the right output rate.  ``ps_clk_label``
        # provides the PS AXI bus clock (`<&clkc 15>` on Zynq-7000);
        # ``rx_xcvr_clkgen_ref`` etc. give the AD9528/HMC7044 channel
        # that physically drives the FPGA clkin1 pin.  Matches the
        # Kuiper production DT.
        s_axi_aclk_ref = f"<&{ps_clk_label} {ps_clk_index}>"
        if has_rx_clkgen:
            extra_before.append(
                f"\t&{rx_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f"\t\tclocks = {s_axi_aclk_ref}, {rx_xcvr_clkgen_ref};\n"
                '\t\tclock-names = "s_axi_aclk", "clkin1";\n'
                f'\t\tclock-output-names = "{rx_clkgen_label}";\n'
                "\t};"
            )
        if has_tx_clkgen:
            extra_before.append(
                f"\t&{tx_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f"\t\tclocks = {s_axi_aclk_ref}, {tx_xcvr_clkgen_ref};\n"
                '\t\tclock-names = "s_axi_aclk", "clkin1";\n'
                f'\t\tclock-output-names = "{tx_clkgen_label}";\n'
                "\t};"
            )
        if has_rx_os_clkgen:
            extra_before.append(
                f"\t&{rx_os_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f"\t\tclocks = {s_axi_aclk_ref}, {rx_os_xcvr_clkgen_ref};\n"
                '\t\tclock-names = "s_axi_aclk", "clkin1";\n'
                f'\t\tclock-output-names = "{rx_os_clkgen_label}";\n'
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
                clock_output_name="jesd_rx_os_lane_clk",
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
                    jesd_overlay_rendered=rx_os_jesd_overlay_ctx,
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

        extra_before.append(_dma_node(rx_dma_label))
        extra_before.append(_dma_node(tx_dma_label))
        if has_rx_os:
            extra_before.append(_dma_node(rx_os_dma_label))
        extra_before.append(rx_xcvr_node)
        if has_rx_os:
            extra_before.append(rx_os_xcvr_node)
        extra_before.append(tx_xcvr_node)
        extra_before.append(rx_core_first)
        if has_rx_os:
            extra_before.append(rx_os_core_first)
        extra_before.append(tx_core_first)

        # extra_nodes_after: TPL core second pass nodes
        extra_after: list[str] = [rx_core_second]
        if has_rx_os:
            extra_after.append(rx_os_core_second)
        extra_after.append(tx_core_second)

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
