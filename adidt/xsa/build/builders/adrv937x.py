"""ADRV937x (AD9371) board builder.

Topology match: converter IP or JESD instance names containing ``ad9371``
or ``adrv937``.  The DT rendering logic is duplicated from ADRV9009Builder
(non-FMComms8 path) to keep the two builders independent.
"""

from __future__ import annotations

from typing import Any

from ....model.board_model import (
    BoardModel,
    ComponentModel,
    FpgaConfig,
    JesdLinkModel,
)
from ....devices.clocks import AD9528_1_ADRV9371
from ....devices.clocks.ad952x import AD9528_1Channel, _GpioLine
from ....devices.fpga_ip import build_jesd204_overlay_ctx
from ....model.renderer import BoardModelRenderer
from ...parse.topology import XsaTopology

_ADRV937X_KEYWORDS = ("ad9371", "adrv937")


# Default Mykonos (AD9371) initial device profile — baked into the DT
# as ``adi,*-profile-*`` / ``adi,clocks-*`` properties on
# ``ad9371-phy@1`` when the caller doesn't supply a per-profile
# override.
#
# The AD9371 driver consumes these at probe to configure the Mykonos
# ARM before userspace ever sees the chip; the values must encode a
# configuration whose JESD framing (M, L, F, K, Np, CS, CF) matches
# the FPGA's compiled-in ``axi-jesd204-{tx,rx}`` overlays, otherwise
# the deframer reports an ILAS mismatch at link-up and the TPL DMA
# sits idle.  Because "matching" is HDL-build-specific (see the
# ``TX_JESD_*`` / ``RX_JESD_*`` knobs in
# ``analogdevicesinc/hdl/projects/adrv937x/zc706/README.md``), this
# module ships an empty default and expects the per-board profile
# JSON (e.g. ``adidt/xsa/profiles/adrv937x_zc706.json``) to supply a
# full ``trx_profile_props`` list.  Callers without a profile JSON
# can still override via ``board_cfg["trx_profile_props"]``.
_DEFAULT_MYKONOS_PROFILE_PROPS: tuple[str, ...] = ()


# AD9528 output-channel map baked into the DT so the clock distributor
# driver configures dividers + signal sources before the Mykonos driver
# requests ``dev_clk`` at 122.88 MHz.  Each AD9528_1Channel renders to
# an ``adi,channels/channel@N`` subnode.  Values mirror the Kuiper
# zc706-adrv9371 reference DT.
def _default_ad9528_channels() -> dict[int, AD9528_1Channel]:
    return {
        13: AD9528_1Channel(id=13, name="DEV_CLK", divider=10, signal_source=0),
        1: AD9528_1Channel(id=1, name="FMC_CLK", divider=10, signal_source=0),
        12: AD9528_1Channel(id=12, name="DEV_SYSREF", divider=10, signal_source=2),
        3: AD9528_1Channel(id=3, name="FMC_SYSREF", divider=10, signal_source=2),
    }


def _is_adrv937x_name(value: str) -> bool:
    lower = value.lower()
    return any(key in lower for key in _ADRV937X_KEYWORDS)


def _topology_instance_names(topology: XsaTopology) -> set[str]:
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


def _pick_matching_label(
    topology_names: set[str], default: str, required_tokens: tuple[str, ...]
) -> str:
    if default in topology_names:
        return default
    candidates = sorted(
        n
        for n in topology_names
        if all(token in n.lower() for token in required_tokens)
    )
    return candidates[0] if candidates else default


class ADRV937xBuilder:
    """Board builder for ADRV937x (AD9371) transceiver designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        if any(
            c.ip_type in {"axi_ad9371", "axi_adrv9371"} or _is_adrv937x_name(c.name)
            for c in topology.converters
        ):
            return True
        return any(
            _is_adrv937x_name(j.name) for j in topology.jesd204_rx + topology.jesd204_tx
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9371", "axi_adrv9371"}

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
        """Construct a BoardModel for an ADRV937x (AD9371) design.

        Returns None if no ADRV937x instances are found in the topology.
        """
        board_cfg = cfg.get("adrv9009_board", {})
        platform = topology.inferred_platform()

        labels = _topology_instance_names(topology)

        if not any(_is_adrv937x_name(lbl) for lbl in labels):
            return None

        phy_compatible_list = ["adi,ad9371"]

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
        tx_jesd_label = next(
            (lbl for lbl in sorted(labels) if "_tx_jesd_tx_axi" in lbl),
            next((lbl for lbl in sorted(labels) if "_tx_jesd" in lbl), None),
        )
        rx_os_jesd_label = next(
            (lbl for lbl in sorted(labels) if "_rx_os_jesd_rx_axi" in lbl),
            next(
                (lbl for lbl in sorted(labels) if "_rx_os_jesd" in lbl),
                None,
            ),
        )
        if not rx_jesd_label or not tx_jesd_label:
            return None

        # --- Derive clkgen / xcvr labels ---
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
        rx_os_clkgen_label = (
            rx_os_jesd_label.replace("_jesd_rx_axi", "_clkgen").replace(
                "_rx_os_jesd", "_rx_os_clkgen"
            )
            if rx_os_jesd_label
            else None
        )
        rx_os_xcvr_label = (
            rx_os_jesd_label.replace("_jesd_rx_axi", "_xcvr").replace(
                "_rx_os_jesd", "_rx_os_xcvr"
            )
            if rx_os_jesd_label
            else None
        )
        rx_os_core_label = _pick_matching_label(
            labels,
            "axi_ad9371_core_rx_obs",
            ("ad9371", "tpl_core", "rx_os", "adc"),
        )
        rx_os_dma_label = next(
            (lbl for lbl in labels if "_rx_os_dma" in lbl or "_obs_dma" in lbl),
            None,
        )

        # --- TPL core labels (ZC706 sdtgen emits rx_ad9371_tpl_core_adc_tpl_core etc.) ---
        rx_core_label = _pick_matching_label(
            labels,
            "axi_ad9371_core_rx",
            ("ad9371", "tpl_core", "rx", "adc"),
        )
        tx_core_label = _pick_matching_label(
            labels,
            "axi_ad9371_core_tx",
            ("ad9371", "tpl_core", "tx", "dac"),
        )

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

        # --- Board config values (shared with ADRV9009 profile format) ---
        misc_clk_hz = int(board_cfg.get("misc_clk_hz", 245760000))
        spi_bus = str(board_cfg.get("spi_bus", "spi0"))
        clk_cs = int(board_cfg.get("clk_cs", 0))
        trx_cs = int(board_cfg.get("trx_cs", 1))
        # GPIO defaults match the Kuiper ``zc706-adrv9371`` reference DT
        # (EMIO pin numbering relative to Zynq GPIO controller base=54):
        # - AD9371 reset   = 106 (``trx_reset_gpio``)
        # - AD9371 sysref  = 112 (``trx_sysref_req_gpio``)
        # - AD9528 reset   = 113 (``ad9528_reset_gpio``)
        trx_reset_gpio = int(board_cfg.get("trx_reset_gpio", 106))
        trx_sysref_req_gpio = int(board_cfg.get("trx_sysref_req_gpio", 112))
        ad9528_reset_gpio = int(board_cfg.get("ad9528_reset_gpio", 113))
        trx_spi_max_frequency = int(board_cfg.get("trx_spi_max_frequency", 25000000))
        ad9528_vcxo_freq = int(board_cfg.get("ad9528_vcxo_freq", 122880000))

        rx_link_id = int(board_cfg.get("rx_link_id", 1))
        tx_link_id = int(board_cfg.get("tx_link_id", 0))
        rx_os_link_id = int(board_cfg.get("rx_os_link_id", 2))
        tx_octets_per_frame = int(board_cfg.get("tx_octets_per_frame", 2))
        rx_os_octets_per_frame = int(board_cfg.get("rx_os_octets_per_frame", 2))
        rx_os_k = int(board_cfg.get("rx_os_k", 32))

        # JESD framing parameters (from pipeline cfg, not board_cfg)
        jesd_cfg = cfg.get("jesd", {})
        rx_f = int(jesd_cfg.get("rx", {}).get("F", 4))
        rx_k = int(jesd_cfg.get("rx", {}).get("K", 32))
        tx_k = int(jesd_cfg.get("tx", {}).get("K", 32))
        tx_m = int(jesd_cfg.get("tx", {}).get("M", 4))

        # --- Clock chip (AD9528_1, single-chip path only) ---
        clock_chip_label = "clk0_ad9528"
        ad9528_dev = AD9528_1_ADRV9371(
            label=clock_chip_label,
            spi_max_hz=10_000_000,
            vcxo_hz=ad9528_vcxo_freq,
            channels=_default_ad9528_channels(),
            gpio_lines=[
                _GpioLine(
                    prop="reset-gpios",
                    controller=gpio_label,
                    index=ad9528_reset_gpio,
                ),
            ],
            # Mark AD9528 as the JESD204 topology's SYSREF provider.
            # Without this the AD9371 driver's
            # ``opt_post_running_stage`` callback can't find a sysref
            # source in the jesd204 graph and rolls back with -EFAULT.
            # Matches the Kuiper zc706-adrv9371 reference DT.
            jesd204_sysref_provider=True,
            jesd204_max_sysref_hz=int(
                board_cfg.get("ad9528_jesd204_max_sysref_hz", 78125)
            ),
        )
        clock_component = ComponentModel(
            role="clock",
            part="ad9528_1",
            spi_bus=spi_bus,
            spi_cs=clk_cs,
            rendered=ad9528_dev.render_dt(cs=clk_cs),
        )

        # --- PHY component (ADRV9009 device rendered as ADRV9371) ---
        from ....devices.transceivers import ADRV9009

        phy_dev = ADRV9009(
            label="trx0_ad9371",
            node_name_base="ad9371-phy",
            compatible_strings=phy_compatible_list,
            spi_max_hz=trx_spi_max_frequency,
            reset_gpio=trx_reset_gpio,
            sysref_req_gpio=trx_sysref_req_gpio,
        )
        # JESD lane-clock references — needed so the Mykonos deframer
        # checks its profile-derived expected framing against the actual
        # HDL link clock instead of a silent zero fallback.  Matches
        # the Kuiper ``zynq-zc706-adv7511-adrv937x`` reference DT.
        if rx_os_jesd_label and rx_os_xcvr_label and rx_os_clkgen_label:
            trx_clocks_value = (
                f"<&{rx_jesd_label}>, <&{tx_jesd_label}>, <&{rx_os_jesd_label}>, "
                "<&clk0_ad9528 13>, <&clk0_ad9528 1>, "
                "<&clk0_ad9528 12>, <&clk0_ad9528 3>"
            )
            trx_clock_names_value = (
                '"jesd_rx_clk", "jesd_tx_clk", "jesd_rx_os_clk", '
                '"dev_clk", "fmc_clk", "sysref_dev_clk", "sysref_fmc_clk"'
            )
        else:
            # Fallback for topologies without an RX_OBS JESD core.
            trx_clocks_value = (
                f"<&{rx_jesd_label}>, <&{tx_jesd_label}>, "
                "<&clk0_ad9528 13>, <&clk0_ad9528 1>, "
                "<&clk0_ad9528 12>, <&clk0_ad9528 3>"
            )
            trx_clock_names_value = (
                '"jesd_rx_clk", "jesd_tx_clk", '
                '"dev_clk", "fmc_clk", "sysref_dev_clk", "sysref_fmc_clk"'
            )
        # Match Kuiper's working FSM-mode topology
        # (``zynq-zc706-adv7511-adrv9371-jesd204-fsm.dts``):
        # AD9371 → {RX JESD core, RX_OBS JESD core, TX TPL DAC core}
        # → ... → xcvrs → AD9528 (terminal sysref provider).
        # The TX side passes through the TPL DAC core
        # (``axi_ad9371_core_tx`` upstream / ``tx_core_label`` here)
        # before reaching the JESD-TX core, so cf_axi_dds's
        # ``jesd204_post_running_stage`` callback runs and emits the
        # ``cf_axi_dds_start_sync`` that arms the DAC data path —
        # without it the JESD-TX framer transmits no valid 8b/10b
        # symbols and the AD9371 deframer never decodes an ILAS
        # sequence (mismatch mask 0xc7f8 + deframerStatus 0x21 with
        # FS-lost set / valid-checksum clear).
        if rx_os_jesd_label and rx_os_xcvr_label:
            trx_link_ids_value = f"{tx_link_id} {rx_link_id} {rx_os_link_id}"
            trx_inputs_value = (
                f"<&{rx_jesd_label} 0 {rx_link_id}>, "
                f"<&{rx_os_jesd_label} 0 {rx_os_link_id}>, "
                f"<&{tx_core_label} 0 {tx_link_id}>"
            )
        else:
            ad9528_sysref_link_id = 2
            trx_link_ids_value = f"{rx_link_id} {tx_link_id} {ad9528_sysref_link_id}"
            trx_inputs_value = (
                f"<&{rx_xcvr_label} 0 {rx_link_id}>, "
                f"<&{tx_xcvr_label} 0 {tx_link_id}>, "
                f"<&{clock_chip_label} 0 {ad9528_sysref_link_id}>"
            )
        profile_props = tuple(
            board_cfg.get("trx_profile_props", _DEFAULT_MYKONOS_PROFILE_PROPS)
        )
        phy_context = {
            "gpio_label": gpio_label,
            "clocks_value": trx_clocks_value,
            "clock_names_value": trx_clock_names_value,
            "link_ids": trx_link_ids_value,
            "jesd204_inputs": trx_inputs_value,
            "profile_props": profile_props,
        }
        phy_component = ComponentModel(
            role="transceiver",
            part="adrv9009",
            spi_bus=spi_bus,
            spi_cs=trx_cs,
            rendered=phy_dev.render_dt(cs=trx_cs, context=phy_context),
        )

        # --- Clock references for ADXCVR/clkgen (AD9528 output channels) ---
        rx_clkgen_ref = "<&clk0_ad9528 13>"
        tx_clkgen_ref = "<&clk0_ad9528 13>"
        rx_xcvr_conv_clk_ref = f"<&{rx_clkgen_label}>"
        rx_xcvr_div40_ref = f"<&{rx_clkgen_label}>"
        tx_xcvr_conv_clk_ref = f"<&{tx_clkgen_label}>"
        tx_xcvr_div40_ref = f"<&{tx_clkgen_label}>"

        # --- JESD204 overlay rendered nodes ---
        rx_jesd_overlay = build_jesd204_overlay_ctx(
            label=rx_jesd_label,
            direction="rx",
            clocks_str=(
                f"<&{ps_clk_label} {ps_clk_index}>, "
                f"<&{rx_clkgen_label}>, <&{rx_xcvr_label} 0>"
            ),
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            clock_output_name="jesd_rx_lane_clk",
            f=rx_f,
            k=rx_k,
            # JESD core → xcvr (matches Kuiper ref).
            jesd204_inputs=f"{rx_xcvr_label} 0 {rx_link_id}",
        )
        # Converter resolution / control bits match Kuiper's working
        # reference DT (``N=14, CS=2``), which reflects the AD9371's
        # physical 14-bit sample + 2 control bits packed into the
        # 16-bit serdes slot.  The HDL TPL descriptor register
        # advertises ``N=16, CS=0`` separately (FPGA-side reporting);
        # the ADI driver uses these DT values for the ILAS sequence
        # it transmits, so they must match what the Mykonos deframer
        # derives from its profile — not what the HDL TPL register
        # advertises.
        tx_jesd_overlay = build_jesd204_overlay_ctx(
            label=tx_jesd_label,
            direction="tx",
            clocks_str=(
                f"<&{ps_clk_label} {ps_clk_index}>, "
                f"<&{tx_clkgen_label}>, <&{tx_xcvr_label} 0>"
            ),
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            clock_output_name="jesd_tx_lane_clk",
            f=tx_octets_per_frame,
            k=tx_k,
            jesd204_inputs=f"{tx_xcvr_label} 0 {tx_link_id}",
            converter_resolution=14,
            converters_per_device=tx_m,
            bits_per_sample=16,
            control_bits_per_sample=2,
        )
        # Full RX_OBS JESD overlay (compatible + jesd204-device +
        # jesd204-inputs → rx_os_xcvr).  Now that the xcvrs chain to
        # AD9528 via their own ``jesd204-inputs``, the topology walker
        # reaches the sysref provider through the xcvr chain and
        # AD9528 stays probed.
        rx_os_jesd_overlay = (
            build_jesd204_overlay_ctx(
                label=rx_os_jesd_label,
                direction="rx",
                clocks_str=(
                    f"<&{ps_clk_label} {ps_clk_index}>, "
                    f"<&{rx_os_clkgen_label}>, <&{rx_os_xcvr_label} 0>"
                ),
                clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                clock_output_name="jesd_rx_os_lane_clk",
                f=rx_os_octets_per_frame,
                k=rx_os_k,
                jesd204_inputs=f"{rx_os_xcvr_label} 0 {rx_os_link_id}",
            )
            if rx_os_jesd_label and rx_os_xcvr_label and rx_os_clkgen_label
            else None
        )
        rx_os_clkgen_node = (
            (
                f"\t&{rx_os_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f'\t\tclock-output-names = "{rx_os_clkgen_label}";\n'
                '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
                "\t};"
            )
            if rx_os_clkgen_label
            else None
        )

        # IRQ overrides for the AXI DMACs:
        # The sdtgen-generated DT extracts ``interrupts = <0 31 4>``
        # (rx), ``<0 32 4>`` (tx), ``<0 33 4>`` (rx_obs) from the XSA
        # — but the bitstream loaded from Kuiper's
        # ``release:zynq-zc706-adv7511-adrv937x/BOOT.BIN`` actually
        # routes those IRQ wires to SPI 57 / 56 / 55 (= GIC IRQ
        # 89 / 88 / 87).  Confirmed on bq by reading
        # ``GICD ICDISPR[2] = 0x02000000`` (IRQ 89 pending) while the
        # DMAC asserted its IRQ output (``IRQ_PENDING=0x3``,
        # ``TRANSFER_DONE=3``) but ``/proc/interrupts`` for the
        # DT-declared IRQ stayed at 0.  Override to match Kuiper's
        # reference DT (``zynq-zc706-adv7511-adrv9371.dts``).
        # SPI 57/56 = GIC IRQ 89/88. ``4`` = ``IRQ_TYPE_LEVEL_HIGH``
        # written as a literal so the overlay DTSO doesn't need the
        # ``<dt-bindings/interrupt-controller/irq.h>`` include.
        # (rx_obs DMA is SPI 55 / GIC IRQ 87 if/when that path is
        # wired up — currently OBS is gated by a separate
        # missing-#dma-cells issue at the OBS TPL ADC node.)
        rx_dma_interrupts = "<0 57 4>"
        tx_dma_interrupts = "<0 56 4>"

        jesd_links = [
            JesdLinkModel(
                direction="rx",
                jesd_label=rx_jesd_label,
                xcvr_label=rx_xcvr_label,
                dma_label=rx_dma_label,
                core_label=rx_core_label,
                link_params={"F": rx_f, "K": rx_k},
                dma_interrupts_str=rx_dma_interrupts,
                jesd_overlay_rendered=rx_jesd_overlay,
            ),
            JesdLinkModel(
                direction="tx",
                jesd_label=tx_jesd_label,
                xcvr_label=tx_xcvr_label,
                dma_label=tx_dma_label,
                core_label=tx_core_label,
                link_params={"F": tx_octets_per_frame, "K": tx_k, "M": tx_m},
                dma_interrupts_str=tx_dma_interrupts,
                jesd_overlay_rendered=tx_jesd_overlay,
            ),
        ]

        # --- Raw XCVR overlay nodes ---
        # Kuiper's working reference wires all three xcvrs directly to
        # AD9528 channel 1 (FMC_CLK) as their single ``conv`` clock
        # and declares ``jesd204-inputs = <&AD9528 0 link_id>`` on
        # each xcvr so the jesd204-topology walker reaches the
        # AD9528 sysref-provider via the xcvr chain.  TX uses
        # ``sys-clk-select = <3>`` (not 0) and omits
        # ``adi,use-lpm-enable``.
        rx_xcvr_node = (
            f"\t&{rx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = <&{clock_chip_label} 1>;\n"
            '\t\tclock-names = "conv";\n'
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
        tx_xcvr_node = (
            f"\t&{tx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = <&{clock_chip_label} 1>;\n"
            '\t\tclock-names = "conv";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "tx_gt_clk", "tx_out_clk";\n'
            "\t\tadi,sys-clk-select = <3>;\n"
            "\t\tadi,out-clk-select = <3>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{clock_chip_label} 0 {tx_link_id}>;\n"
            "\t};"
        )
        rx_os_xcvr_node = (
            (
                f"\t&{rx_os_xcvr_label} {{\n"
                '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
                f"\t\tclocks = <&{clock_chip_label} 1>;\n"
                '\t\tclock-names = "conv";\n'
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
            if rx_os_xcvr_label
            else None
        )

        # --- TPL core first pass (compatible + dma) ---
        phy_label = "trx0_ad9371"
        rx_core_first = (
            f"\t&{rx_core_label} {{\n"
            '\t\tcompatible = "adi,axi-ad9371-rx-1.0";\n'
            "\t\tadi,axi-decimation-core-available;\n"
            f"\t\tdmas = <&{rx_dma_label} 0>;\n"
            '\t\tdma-names = "rx";\n'
            "\t};"
        )
        tx_core_first = (
            f"\t&{tx_core_label} {{\n"
            '\t\tcompatible = "adi,axi-ad9371-tx-1.0";\n'
            "\t\tadi,axi-interpolation-core-available;\n"
            f"\t\tdmas = <&{tx_dma_label} 0>;\n"
            '\t\tdma-names = "tx";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};"
        )

        # --- TPL core second pass (spibus-connected + phy clocks) ---
        rx_core_second = (
            f"\t&{rx_core_label} {{\n\t\tspibus-connected = <&{phy_label}>;\n\t}};"
        )
        # FSM-mode: TPL DAC core is the AD9371's TX-link entry into
        # the JESD204 graph.  ``jesd204-inputs`` chains it to the
        # AXI JESD-TX core so the framework walks
        # AD9371 → TPL DAC → JESD-TX → xcvr → AD9528.  Matches
        # ``&axi_ad9371_core_tx`` overrides in
        # ``zynq-zc706-adv7511-adrv9371-jesd204-fsm.dts``.
        tx_core_second = (
            f"\t&{tx_core_label} {{\n"
            f"\t\tspibus-connected = <&{phy_label}>;\n"
            f"\t\tclocks = <&{phy_label} 2>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{tx_jesd_label} 0 {tx_link_id}>;\n"
            "\t};"
        )
        # RX_OBS TPL core overlay — converts sdtgen's
        # ``xlnx,ad-ip-jesd204-tpl-adc-1.0`` into the ADI observation
        # driver (``adi,axi-ad9371-obs-1.0``) that Kuiper's reference
        # DT uses.  Without this, the obs path stays bound to the
        # Xilinx generic driver, Mykonos's ``ObsRxFramer`` never
        # receives a valid link clock, and ILAS verification fails on
        # all 9 fields (mask 0xc7f8).  Xcvr / clkgen / JESD overlays
        # for the obs path are deliberately NOT added here — they
        # cascade into jesd204-topology-walker conflicts with AD9528
        # on this branch.
        rx_os_core_overlay = (
            (
                f"\t&{rx_os_core_label} {{\n"
                "\t\t/delete-property/ compatible;\n"
                '\t\tcompatible = "adi,axi-ad9371-obs-1.0";\n'
                f"\t\tdmas = <&{rx_os_dma_label} 0>;\n"
                '\t\tdma-names = "rx";\n'
                f"\t\tspibus-connected = <&{phy_label}>;\n"
                f"\t\tclocks = <&{phy_label} 1>;\n"
                '\t\tclock-names = "sampl_clk";\n'
                "\t};"
            )
            if rx_os_core_label and rx_os_dma_label
            else None
        )

        # --- Clkgen overlay nodes ---
        rx_clkgen_node = (
            f"\t&{rx_clkgen_label} {{\n"
            '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
            "\t\t#clock-cells = <0>;\n"
            f'\t\tclock-output-names = "{rx_clkgen_label}";\n'
            '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
            "\t};"
        )
        tx_clkgen_node = (
            f"\t&{tx_clkgen_label} {{\n"
            '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
            "\t\t#clock-cells = <0>;\n"
            f'\t\tclock-output-names = "{tx_clkgen_label}";\n'
            '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
            "\t};"
        )

        # --- Misc fixed-clock node (provides reference clock) ---
        misc_clk_node = (
            "\t&misc_clk_0 {\n"
            '\t\tcompatible = "fixed-clock";\n'
            "\t\t#clock-cells = <0>;\n"
            f"\t\tclock-frequency = <{misc_clk_hz}>;\n"
            "\t};"
        )

        extra_before: list[str] = [
            misc_clk_node,
            rx_clkgen_node,
            tx_clkgen_node,
            rx_xcvr_node,
            tx_xcvr_node,
            rx_core_first,
            tx_core_first,
        ]
        if rx_os_clkgen_node:
            extra_before.append(rx_os_clkgen_node)
        if rx_os_xcvr_node:
            extra_before.append(rx_os_xcvr_node)
        if rx_os_jesd_overlay:
            extra_before.append(rx_os_jesd_overlay)
        if rx_os_core_overlay:
            extra_before.append(rx_os_core_overlay)
        extra_after: list[str] = [
            rx_core_second,
            tx_core_second,
        ]

        _32BIT_PLATFORMS = {"vcu118", "zc706"}
        addr_cells = 1 if platform in _32BIT_PLATFORMS else 2

        fpga_cfg = FpgaConfig(
            platform=platform or "unknown",
            addr_cells=addr_cells,
            ps_clk_label=ps_clk_label,
            ps_clk_index=ps_clk_index,
            gpio_label=gpio_label,
        )

        model = BoardModel(
            name=f"adrv937x_{platform or 'unknown'}",
            platform=platform or "unknown",
            components=[clock_component, phy_component],
            jesd_links=jesd_links,
            fpga_config=fpga_cfg,
            metadata={
                "extra_nodes_before": extra_before,
                "extra_nodes_after": extra_after,
                "spi_bus": spi_bus,
            },
        )
        return model
