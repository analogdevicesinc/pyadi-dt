# adidt/xsa/node_builder.py
"""Build ADI device-driver DTS overlay nodes from an XSA topology and config."""

import warnings
from typing import Any

from .builders import BoardBuilder
from .builders.ad9081 import AD9081Builder
from .builders.ad9084 import AD9084Builder
from .builders.ad9172 import AD9172Builder
from .builders.adrv937x import ADRV937xBuilder
from .builders.adrv9009 import ADRV9009Builder
from .builders.fmcdaq2 import FMCDAQ2Builder
from .builders.fmcdaq3 import FMCDAQ3Builder
from ..config.pipeline_config import PipelineConfig
from ..parse.topology import XsaTopology, Jesd204Instance, ClkgenInstance, ConverterInstance


class NodeBuilder:
    """Builds ADI DTS node strings from XsaTopology + pyadi-jif JSON config."""

    _DEFAULT_BUILDERS: list[BoardBuilder] = [
        ADRV9009Builder(),
        ADRV937xBuilder(),
        AD9081Builder(),
        AD9084Builder(),
        FMCDAQ2Builder(),
        FMCDAQ3Builder(),
        AD9172Builder(),
    ]

    _AD9081_LINK_MODE_BY_ML: dict[tuple[int, int], tuple[int, int]] = {
        # (M, L): (rx_link_mode, tx_link_mode)
        (8, 4): (17, 18),
        (4, 8): (10, 11),
    }
    _ADRV90XX_KEYWORDS = ("adrv9009", "adrv9025", "adrv9026")

    @classmethod
    def _is_adrv90xx_name(cls, value: str) -> bool:
        """Return True if *value* contains an ADRV9009/9025/9026 keyword."""
        lower = value.lower()
        return any(key in lower for key in cls._ADRV90XX_KEYWORDS)

    # Platforms using single-cell (32-bit) addressing in amba_pl
    _32BIT_PLATFORMS = {"vcu118", "zc706"}

    def build(
        self, topology: XsaTopology, cfg: PipelineConfig | dict[str, Any]
    ) -> dict[str, list[str]]:
        """Render ADI DTS nodes.

        Args:
            topology: Parsed XSA topology.
            cfg: Pipeline configuration as a :class:`PipelineConfig` or raw dict.
                Dicts are used as-is for backward compatibility.  ``PipelineConfig``
                instances are converted to dict via :meth:`PipelineConfig.to_dict`.

        Returns:
            Dict with keys "jesd204_rx", "jesd204_tx", "converters".
        """
        if isinstance(cfg, PipelineConfig):
            cfg = cfg.to_dict()
        platform = topology.inferred_platform()
        self._addr_cells = 1 if platform in self._32BIT_PLATFORMS else 2
        clock_map = self._build_clock_map(topology)
        ps_clk_label, ps_clk_index, gpio_label = self._platform_ps_labels(topology)
        result: dict[str, list[str]] = {
            "clkgens": [],
            "jesd204_rx": [],
            "jesd204_tx": [],
            "converters": [],
        }

        # Determine which builders match this topology + config.
        matched_builders: list[BoardBuilder] = [
            b for b in self._DEFAULT_BUILDERS if b.matches(topology, cfg)
        ]
        # Aggregate skip info from matched builders.
        skip_generic_jesd = any(b.skips_generic_jesd() for b in matched_builders)
        skip_ip_types: set[str] = set()
        for b in matched_builders:
            skip_ip_types.update(b.skip_ip_types())

        # Helper: should this JESD/clkgen instance be skipped by generic rendering?
        def _skip_instance(name: str) -> bool:
            if not skip_generic_jesd:
                return False
            lower = name.lower()
            # ADRV9009 builder skips its own named instances
            if self._is_adrv90xx_name(name):
                return True
            # ADRV937x builder skips ad9371/adrv937 named instances
            if any(k in lower for k in ("ad9371", "adrv937")) and any(
                isinstance(b, ADRV937xBuilder) for b in matched_builders
            ):
                return True
            # AD9081 builder skips mxfe-named instances
            if "mxfe" in lower and "axi_ad9081" in skip_ip_types:
                return True
            # AD9084, FMCDAQ2, FMCDAQ3 skip all generic JESD rendering
            if "axi_ad9084" in skip_ip_types:
                return True
            if {"axi_ad9680", "axi_ad9144"}.issubset(skip_ip_types):
                return True
            if {"axi_ad9680", "axi_ad9152"}.issubset(skip_ip_types):
                return True
            return False

        # Also check for AD9172 TX skip (skips generic TX but not RX).
        is_ad9172_matched = any(isinstance(b, AD9172Builder) for b in matched_builders)

        rx_labels: list[str] = []
        tx_labels: list[str] = []

        # Only render clkgens that some JESD instance in the topology actually
        # references as its link clock.  ZC706 reference designs ship an
        # ``axi_hdmi_clkgen`` for the HDMI output that has nothing to do with
        # the converter chain; the base DTS already declares it via #include
        # and re-rendering it here makes the merger emit a noisy
        # ``Replaced included node with duplicate label`` warning.
        used_clkgen_names: set[str] = set()
        for jesd_inst in (*topology.jesd204_rx, *topology.jesd204_tx):
            clkgen = clock_map.get(jesd_inst.link_clk)
            if clkgen is not None:
                used_clkgen_names.add(clkgen.name)

        for clkgen in topology.clkgens:
            if clkgen.name not in used_clkgen_names:
                continue
            if self._is_adrv90xx_name(clkgen.name) and any(
                isinstance(b, ADRV9009Builder) for b in matched_builders
            ):
                continue
            if any(k in clkgen.name.lower() for k in ("ad9371", "adrv937")) and any(
                isinstance(b, ADRV937xBuilder) for b in matched_builders
            ):
                continue
            result["clkgens"].append(
                self._render_clkgen(clkgen, ps_clk_label, ps_clk_index)
            )

        for inst in topology.jesd204_rx:
            if _skip_instance(inst.name):
                continue
            clkgen_label, device_clk_label, device_clk_index = self._resolve_clock(
                inst, clock_map, cfg, "rx", ps_clk_label, ps_clk_index
            )
            jesd_input_label, jesd_input_link_id = self._resolve_jesd_input(
                inst, cfg, "rx", clkgen_label
            )
            result["jesd204_rx"].append(
                self._render_jesd(
                    inst,
                    cfg.get("jesd", {}).get("rx", {}),
                    clkgen_label,
                    device_clk_label,
                    device_clk_index,
                    jesd_input_label,
                    jesd_input_link_id,
                    ps_clk_label,
                    ps_clk_index,
                )
            )
            rx_labels.append(inst.name.replace("-", "_"))

        for inst in topology.jesd204_tx:
            if _skip_instance(inst.name):
                continue
            if is_ad9172_matched:
                continue
            clkgen_label, device_clk_label, device_clk_index = self._resolve_clock(
                inst, clock_map, cfg, "tx", ps_clk_label, ps_clk_index
            )
            jesd_input_label, jesd_input_link_id = self._resolve_jesd_input(
                inst, cfg, "tx", clkgen_label
            )
            result["jesd204_tx"].append(
                self._render_jesd(
                    inst,
                    cfg.get("jesd", {}).get("tx", {}),
                    clkgen_label,
                    device_clk_label,
                    device_clk_index,
                    jesd_input_label,
                    jesd_input_link_id,
                    ps_clk_label,
                    ps_clk_index,
                )
            )
            tx_labels.append(inst.name.replace("-", "_"))

        for conv in topology.converters:
            if conv.ip_type in skip_ip_types:
                continue
            rx_label = rx_labels[0] if rx_labels else "jesd_rx"
            tx_label = tx_labels[0] if tx_labels else "jesd_tx"
            result["converters"].append(
                self._render_converter(conv, rx_label, tx_label)
            )

        # Dispatch to matched builders for board-specific node generation.
        for builder in matched_builders:
            result["converters"].extend(
                builder.build_nodes(
                    self, topology, cfg, ps_clk_label, ps_clk_index, gpio_label
                )
            )

        return result

    @staticmethod
    def _is_ad9172_design(topology: XsaTopology) -> bool:
        """Return True if the topology contains an AD9172/AD9162 DAC design."""
        if any(c.ip_type == "axi_ad9162" for c in topology.converters):
            return True
        names = " ".join(
            j.name.lower() for j in topology.jesd204_rx + topology.jesd204_tx
        )
        return "ad9172" in names or "ad9162" in names

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    _addr_cells: int = 2

    def _wrap_spi_bus(self, label: str, children: str) -> str:
        """Wrap pre-rendered child node strings in an &label { status = "okay"; ... } overlay."""
        if not children.endswith("\n"):
            children += "\n"
        return (
            f"\t&{label} {{\n"
            '\t\tstatus = "okay";\n'
            "\t\t#address-cells = <1>;\n"
            "\t\t#size-cells = <0>;\n"
            f"{children}"
            "\t};"
        )

    # ------------------------------------------------------------------
    # Clock resolution (generic rendering path)
    # ------------------------------------------------------------------

    def _build_clock_map(self, topology: XsaTopology) -> dict[str, ClkgenInstance]:
        """Return a mapping of output clock net name -> ClkgenInstance for fast clock resolution."""
        return {net: cg for cg in topology.clkgens for net in cg.output_clks}

    def _resolve_clock(
        self,
        inst: Jesd204Instance,
        clock_map: dict[str, ClkgenInstance],
        cfg: dict[str, Any],
        direction: str,
        ps_clk_label: str,
        ps_clk_index: int,
    ) -> tuple[str, str, int]:
        """Resolve the clkgen label, device-clock label, and device-clock index for a JESD instance.

        Returns:
            ``(clkgen_label, device_clk_label, device_clk_index)``
        """
        clkgen = clock_map.get(inst.link_clk)
        unresolved_clk = clkgen is None
        if unresolved_clk:
            warnings.warn(
                f"unresolved clock net '{inst.link_clk}' for {inst.name}; "
                "using literal net name as clock label",
                UserWarning,
                stacklevel=3,
            )
            clkgen_label = inst.link_clk
        else:
            clkgen_label = clkgen.name.replace("-", "_")

        clock_cfg = cfg.get("clock", {})
        device_clk_label = clock_cfg.get(f"{direction}_device_clk_label", "hmc7044")
        if device_clk_label == "clkgen":
            if unresolved_clk:
                # External clock nets from HWH are not valid DTS labels.
                # Fall back to a known PS clock phandle to keep DTS valid.
                return (clkgen_label, ps_clk_label, ps_clk_index)
            device_clk_label = clkgen_label

        if device_clk_label == "hmc7044":
            device_clk_index = clock_cfg.get(f"hmc7044_{direction}_channel", 0)
        else:
            device_clk_index = clock_cfg.get(f"{direction}_device_clk_index", 0)

        return (clkgen_label, device_clk_label, device_clk_index)

    def _resolve_jesd_input(
        self,
        inst: Jesd204Instance,
        cfg: dict[str, Any],
        direction: str,
        clkgen_label: str,
    ) -> tuple[str, int]:
        """Resolve the ``jesd204-inputs`` phandle label and link-id for a JESD instance.

        Returns:
            ``(jesd_input_label, link_id)``
        """
        clock_cfg = cfg.get("clock", {})
        override_label = clock_cfg.get(f"{direction}_jesd_input_label")
        if override_label:
            return (
                override_label,
                int(clock_cfg.get(f"{direction}_jesd_input_link_id", 0)),
            )

        name = inst.name.replace("-", "_")
        if "_jesd_rx_axi" in name:
            guessed = name.replace("_jesd_rx_axi", "_xcvr")
        elif "_jesd_tx_axi" in name:
            guessed = name.replace("_jesd_tx_axi", "_xcvr")
        elif "_rx_os_jesd" in name:
            guessed = name.replace("_rx_os_jesd", "_rx_os_xcvr")
        elif "_rx_jesd" in name:
            guessed = name.replace("_rx_jesd", "_rx_xcvr")
        elif "_tx_jesd" in name:
            guessed = name.replace("_tx_jesd", "_tx_xcvr")
        else:
            guessed = clkgen_label
        return (guessed, int(clock_cfg.get(f"{direction}_jesd_input_link_id", 0)))

    # ------------------------------------------------------------------
    # Generic rendering path
    # ------------------------------------------------------------------

    def _render_jesd(
        self,
        inst: Jesd204Instance,
        jesd_params: dict[str, Any],
        clkgen_label: str,
        device_clk_label: str,
        device_clk_index: int,
        jesd_input_label: str,
        jesd_input_link_id: int,
        ps_clk_label: str,
        ps_clk_index: int | None,
    ) -> str:
        """Render an AXI JESD204 FSM link IP DTS node."""
        from ..exceptions import ConfigError

        for key in ("F", "K"):
            if key not in jesd_params:
                raise ConfigError(f"jesd.{inst.direction}.{key}")
        name = inst.name.replace("-", "_")
        reg_addr = self._fmt_reg_addr(inst.base_addr)
        reg_size = self._fmt_reg_size(0x1000)
        ps_ref = (
            f"<&{ps_clk_label} {ps_clk_index}>"
            if ps_clk_index is not None
            else f"<&{ps_clk_label}>"
        )
        irq_line = (
            f"\t\tinterrupts = <0 {inst.irq} IRQ_TYPE_LEVEL_HIGH>;\n"
            if inst.irq is not None
            else ""
        )
        return (
            f"\t{name}: axi-jesd204-{inst.direction}@{inst.base_addr:08x} {{\n"
            f'\t\tcompatible = "adi,axi-jesd204-{inst.direction}-1.0";\n'
            f"\t\treg = <{reg_addr} {reg_size}>;\n"
            f"{irq_line}"
            f"\t\tclocks = {ps_ref}, <&{device_clk_label} {device_clk_index}>, "
            f"<&{jesd_input_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            f'\t\tclock-output-names = "{name}_lane_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{jesd_input_label} 0 {jesd_input_link_id}>;\n"
            "\n"
            "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\tadi,octets-per-frame = <{jesd_params['F']}>;\n"
            "\t\t/* JESD204 framing: K = frames per multiframe "
            "(subclass 1: 17\u2013256, must be multiple of 4) */\n"
            f"\t\tadi,frames-per-multiframe = <{jesd_params['K']}>;\n"
            "\n"
            "\t\t#sound-dai-cells = <0>;\n"
            "\t};"
        )

    def _render_converter(
        self, conv: ConverterInstance, rx_label: str, tx_label: str
    ) -> str:
        """Render a per-IP-type DTS node for *conv*; fallback to a stub comment."""
        spi_cs = conv.spi_cs if conv.spi_cs is not None else 0
        if conv.ip_type == "axi_ad9081":
            return (
                f"\t{conv.name}: ad9081@{spi_cs} {{\n"
                f'\t\tcompatible = "adi,ad9081";\n'
                f"\t\treg = <{spi_cs}>;\n"
                "\t\tspi-max-frequency = <1000000>;\n"
                "\n"
                "\t\tjesd204-device;\n"
                "\t\t#jesd204-cells = <2>;\n"
                "\t\tjesd204-top-device = <0>;\n"
                "\t\tjesd204-link-ids = <1 0>;\n"
                "\n"
                f"\t\tjesd204-inputs = <&{rx_label} 0 1>;\n"
                "\t};"
            )
        return f"\t/* {conv.name}: no template for {conv.ip_type} */"

    def _render_clkgen(
        self,
        inst: ClkgenInstance,
        ps_clk_label: str,
        ps_clk_index: int,
    ) -> str:
        """Render an AXI clkgen IP overlay node."""
        name = inst.name.replace("-", "_")
        reg_addr = self._fmt_reg_addr(inst.base_addr)
        reg_size = self._fmt_reg_size(0x10000)
        ps_ref = (
            f"<&{ps_clk_label} {ps_clk_index}>"
            if ps_clk_index is not None
            else f"<&{ps_clk_label}>"
        )
        return (
            f"\t{name}: axi-clkgen@{inst.base_addr:08x} {{\n"
            f'\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
            f"\t\treg = <{reg_addr} {reg_size}>;\n"
            "\t\t#clock-cells = <1>;\n"
            f"\t\tclocks = {ps_ref}, {ps_ref};\n"
            '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
            f'\t\tclock-output-names = "{name}_0", "{name}_1";\n'
            "\t};"
        )

    def _fmt_reg_addr(self, addr: int) -> str:
        """Format an ``addr`` cell-array using this builder's addr-cells count."""
        return f"0x{addr:08x}" if self._addr_cells == 1 else f"0x0 0x{addr:08x}"

    def _fmt_reg_size(self, size: int) -> str:
        """Format a ``size`` cell-array using this builder's addr-cells count."""
        return f"0x{size:x}" if self._addr_cells == 1 else f"0x0 0x{size:x}"

    # ------------------------------------------------------------------
    # Platform detection
    # ------------------------------------------------------------------

    @staticmethod
    def _platform_ps_labels(topology: XsaTopology) -> tuple[str, int | None, str]:
        """Return ``(ps_clk_label, ps_clk_index, gpio_label)`` appropriate for the topology's platform."""
        platform = topology.inferred_platform()
        if platform == "zc706":
            return ("clkc", 15, "gpio0")
        if platform == "vcu118":
            # MicroBlaze/VCU118: AXI bus clock is a fixed-clock with #clock-cells = <0>
            return ("clk_bus_0", None, "axi_gpio")
        if platform in {"vpk180", "vck190"}:
            return ("versal_clk", 65, "gpio")
        return ("zynqmp_clk", 71, "gpio")

    # ------------------------------------------------------------------
    # Helpers that may be used by builders via import
    # ------------------------------------------------------------------

    @staticmethod
    def _format_nested_block(block: str, prefix: str = "\t\t\t") -> str:
        """Re-indent each line of *block* with *prefix* and return the result."""
        lines = block.strip("\n").splitlines()
        if not lines:
            return ""
        return "".join(f"{prefix}{line.lstrip()}\n" for line in lines)

    @staticmethod
    def _ad9081_converter_select(rx_m: int, rx_link_mode: int) -> str:
        """Return the ``adi,converter-select`` phandle list string for the AD9081 RX path."""
        # M4/L8 (mode 18) follows the upstream ADI mapping used by the
        # zynqmp-zcu102-rev10-ad9081 reference design.
        if rx_link_mode == 18 and rx_m == 4:
            return (
                "<&ad9081_rx_fddc_chan0 0>, <&ad9081_rx_fddc_chan0 1>, "
                "<&ad9081_rx_fddc_chan1 0>, <&ad9081_rx_fddc_chan1 1>"
            )
        # For M=8 keep the existing IQ-pair mapping used by the reference flow.
        if rx_m >= 8:
            return (
                "<&ad9081_rx_fddc_chan0 0>, <&ad9081_rx_fddc_chan0 1>, "
                "<&ad9081_rx_fddc_chan1 0>, <&ad9081_rx_fddc_chan1 1>, "
                "<&ad9081_rx_fddc_chan2 0>, <&ad9081_rx_fddc_chan2 1>, "
                "<&ad9081_rx_fddc_chan3 0>, <&ad9081_rx_fddc_chan3 1>"
            )
        # For reduced-M modes (e.g. M=4), map one converter per channel.
        return ", ".join(
            f"<&ad9081_rx_fddc_chan{i} 0>" for i in range(max(1, min(rx_m, 8)))
        )
