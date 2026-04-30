"""Top-level hardware-composition orchestrator.

:class:`System` ties a set of :class:`EvalBoard` / :class:`FpgaBoard`
instances together with explicit connection records (SPI buses, JESD204
links).  It produces a :class:`BoardModel` that feeds the existing
:class:`BoardModelRenderer`, so legacy board builders and the new
device-centric API share one rendering path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ._naming import jesd_labels, out_clk_select, sys_clk_select
from .devices.base import ClockOutput, Device, GtLane, SpiPort
from .devices.converters import ConverterDevice
from .devices.converters.base import ConverterSide, Jesd204Settings
from .eval.base import EvalBoard
from .fpga.base import FpgaBoard
from .model.board_model import (
    BoardModel,
    ComponentModel,
    FpgaConfig,
    JesdLinkModel,
)


@dataclass
class _SpiConnection:
    """Record of one ``connect_spi`` call."""

    bus_index: int
    primary: SpiPort
    secondary: SpiPort
    cs: int


@dataclass
class _JesdLink:
    """Record of one ``add_link`` call (raw — rendered at to_board_model time)."""

    source: Any
    sink: Any
    sink_reference_clock: ClockOutput | None = None
    sink_core_clock: ClockOutput | None = None
    sink_sysref: ClockOutput | None = None
    source_reference_clock: ClockOutput | None = None
    source_core_clock: ClockOutput | None = None
    source_sysref: ClockOutput | None = None


@dataclass
class System:
    """Orchestrator composing eval / FPGA boards and connections.

    Attributes:
        name: Design name (used as :attr:`BoardModel.name`).
        components: Eval boards and FPGA boards handed to the System.
    """

    name: str
    components: list[EvalBoard | FpgaBoard] = field(default_factory=list)

    _spi: list[_SpiConnection] = field(default_factory=list, init=False, repr=False)
    _links: list[_JesdLink] = field(default_factory=list, init=False, repr=False)
    _jesd_label_overrides: dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )

    # ------------------------------------------------------------------
    # Connection API
    # ------------------------------------------------------------------

    def connect_spi(
        self,
        *,
        bus_index: int,
        primary: SpiPort,
        secondary: SpiPort,
        cs: int,
    ) -> None:
        """Record that *secondary* is wired to *primary* at chip-select *cs*."""
        self._spi.append(
            _SpiConnection(
                bus_index=bus_index, primary=primary, secondary=secondary, cs=cs
            )
        )

    def add_link(
        self,
        *,
        source: Any,
        sink: Any,
        sink_reference_clock: ClockOutput | None = None,
        sink_core_clock: ClockOutput | None = None,
        sink_sysref: ClockOutput | None = None,
        source_reference_clock: ClockOutput | None = None,
        source_core_clock: ClockOutput | None = None,
        source_sysref: ClockOutput | None = None,
    ) -> None:
        """Record a JESD204 link.

        The *source* is the JESD data producer (ADC → FPGA for RX; FPGA
        → DAC for TX).  The *sink* is the data consumer.  Clock arguments
        carry :class:`ClockOutput` handles to the physical clock lines.

        JESD framing parameters are read directly off the converter side
        (``converter.adc.jesd204_settings`` / ``converter.dac.jesd204_settings``)
        when the link is rendered.  To override, mutate those settings
        before calling :meth:`generate_dts` / :meth:`to_board_model`.
        """
        self._links.append(
            _JesdLink(
                source=source,
                sink=sink,
                sink_reference_clock=sink_reference_clock,
                sink_core_clock=sink_core_clock,
                sink_sysref=sink_sysref,
                source_reference_clock=source_reference_clock,
                source_core_clock=source_core_clock,
                source_sysref=source_sysref,
            )
        )

    # ------------------------------------------------------------------
    # XSA awareness
    # ------------------------------------------------------------------

    def apply_xsa_topology(self, topology: Any) -> None:
        """Pull FPGA-side IP instance names out of an XSA topology.

        Production Vivado designs name the AXI JESD204 RX/TX cores
        after their original block-design instance (typically
        ``axi_jesd204_rx_0`` / ``axi_jesd204_tx_0``), which does not
        match the ``axi_mxfe_{rx,tx}_jesd_{rx,tx}_axi`` convention
        that :func:`adidt._naming.jesd_labels` emits.  Without the
        real labels, the overlays produced by :meth:`generate_dts`
        target non-existent DT nodes and the kernel's JESD204 driver
        never binds.

        Mirrors the extraction in
        :meth:`adidt.xsa.build.builders.ad9081.AD9081Builder.build_model`:
        prefer MxFE-named instances when multiple exist, else fall
        back to the first instance on each side.  Missing sides are
        left as-is (the default naming applies).
        """
        rx_override = self._pick_jesd_label(getattr(topology, "jesd204_rx", ()))
        tx_override = self._pick_jesd_label(getattr(topology, "jesd204_tx", ()))
        if rx_override:
            self._jesd_label_overrides["rx"] = rx_override
        if tx_override:
            self._jesd_label_overrides["tx"] = tx_override

    @staticmethod
    def _pick_jesd_label(instances: Any) -> str | None:
        """Pick the best JESD204 IP instance label from *instances*.

        Prefer MxFE-named instances; fall back to the first entry.
        Dashes in instance names become underscores to match DT label
        conventions (identical to the AD9081Builder behaviour).
        """
        items = list(instances or ())
        if not items:
            return None
        mxfe = [j for j in items if "mxfe" in j.name.lower()]
        chosen = mxfe[0] if mxfe else items[0]
        return chosen.name.replace("-", "_")

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _all_devices(self) -> Iterable[Device]:
        """Yield every device reachable from :attr:`components`."""
        seen: set[int] = set()
        for comp in self.components:
            if isinstance(comp, EvalBoard):
                for d in comp.devices():
                    if id(d) not in seen:
                        seen.add(id(d))
                        yield d
            elif isinstance(comp, Device):
                if id(comp) not in seen:
                    seen.add(id(comp))
                    yield comp

    def _fpga(self) -> FpgaBoard:
        for comp in self.components:
            if isinstance(comp, FpgaBoard):
                return comp
        raise ValueError(f"System {self.name!r} has no FpgaBoard component")

    def _spi_location(self, device: Device) -> tuple[str, int]:
        """Return ``(bus_label, cs)`` for *device*."""
        for conn in self._spi:
            if conn.secondary.device is device:
                master = conn.primary
                label = getattr(master, "label", None) or f"spi{conn.bus_index}"
                return label, conn.cs
        raise ValueError(
            f"device {device!r} was not wired with connect_spi(); "
            "cannot determine SPI bus / chip-select"
        )

    # ------------------------------------------------------------------
    # BoardModel assembly
    # ------------------------------------------------------------------

    def to_board_model(self) -> BoardModel:
        """Build a :class:`BoardModel` from devices + connection records."""
        fpga = self._fpga()
        fpga_config = FpgaConfig(
            platform=fpga.PLATFORM,
            addr_cells=fpga.ADDR_CELLS,
            ps_clk_label=fpga.PS_CLK_LABEL,
            ps_clk_index=fpga.PS_CLK_INDEX,
            gpio_label=fpga.GPIO_LABEL,
        )

        # Build ComponentModels for every non-FPGA device.
        components: list[ComponentModel] = []
        for dev in self._all_devices():
            if isinstance(dev, FpgaBoard):
                continue
            spi_bus, spi_cs = self._spi_location(dev)
            extra = self._extra_ctx_for(dev)
            components.append(
                dev.to_component_model(spi_bus=spi_bus, spi_cs=spi_cs, extra=extra)
            )

        jesd_links = [self._build_jesd_link(link, fpga) for link in self._links]

        return BoardModel(
            name=self.name,
            platform=fpga.PLATFORM,
            components=components,
            jesd_links=jesd_links,
            fpga_config=fpga_config,
            metadata={"config_source": "adidt.system"},
        )

    def _extra_ctx_for(self, device: Device) -> dict[str, Any]:
        """Resolve System-level data the device needs to render."""
        if not isinstance(device, ConverterDevice):
            return {}

        # ``hasattr`` can't be narrowed by ty; use ``getattr`` with a
        # default and a local null-check instead so both the runtime
        # and type-checker see the same invariant.
        rx_side = getattr(device, "adc", None)
        tx_side = getattr(device, "dac", None)
        rx_link_id = int(rx_side.jesd204_settings.link_id) if rx_side is not None else 0
        tx_link_id = int(tx_side.jesd204_settings.link_id) if tx_side is not None else 0

        rx_prefix, tx_prefix = self._jesd_prefixes(device)
        rx = jesd_labels(rx_prefix, "rx")
        tx = jesd_labels(tx_prefix, "tx")

        dev_clk = self._find_sink_reference_clock(device)
        dev_clk_ref = (
            f"{dev_clk.device.label} {dev_clk.index}" if dev_clk is not None else ""
        )
        fpga = self._fpga()
        return {
            "gpio_label": fpga.GPIO_LABEL,
            "dev_clk_ref": dev_clk_ref,
            "rx_core_label": rx["core_label"],
            "tx_core_label": tx["core_label"],
            "rx_link_id": rx_link_id,
            "tx_link_id": tx_link_id,
        }

    def _jesd_prefixes(self, converter: ConverterDevice) -> tuple[str, str]:
        """Return ``(rx_prefix, tx_prefix)`` used to build JESD IP labels.

        MxFE devices historically use a shared ``mxfe_rx`` / ``mxfe_tx``
        prefix pair; simple ADC/DAC parts use ``<part>``.
        """
        if converter.part in ("ad9081", "ad9084", "ad9082"):
            return "mxfe_rx", "mxfe_tx"
        return converter.part, converter.part

    def _find_sink_reference_clock(
        self, converter: ConverterDevice
    ) -> ClockOutput | None:
        """Find the clock driving the converter's dev-clock input.

        Matches links whose endpoint is the converter itself *or*
        either of its split sides (``adc`` / ``dac``).  For MxFE
        devices (AD9081, AD9084, AD9082) links target the per-side
        :class:`ConverterSide`, not the parent — comparing only
        against the parent misses every match and the emitted DT
        drops the ``clocks = <&hmc7044 N>`` property, which makes the
        kernel driver's dev_clk lookup fail at probe time (ENOENT).
        """
        # Pydantic devices aren't hashable, so identity-compare via a list.
        sides = [converter]
        for side_name in ("adc", "dac"):
            side = getattr(converter, side_name, None)
            if side is not None:
                sides.append(side)
        for link in self._links:
            if link.sink_reference_clock is None:
                continue
            if any(link.sink is s for s in sides) or any(
                link.source is s for s in sides
            ):
                return link.sink_reference_clock
        return None

    def _build_jesd_link(self, link: _JesdLink, fpga: FpgaBoard) -> JesdLinkModel:
        """Translate a recorded :class:`_JesdLink` into a :class:`JesdLinkModel`."""
        from .devices.fpga_ip import Adxcvr, Jesd204Overlay, TplCore

        converter, direction, is_rx = self._direction_of(link)
        prefixes = self._jesd_prefixes(converter)
        labels = jesd_labels(prefixes[0] if is_rx else prefixes[1], direction)
        if direction in self._jesd_label_overrides:
            labels["jesd_label"] = self._jesd_label_overrides[direction]

        # For converters with separate ADC/DAC sides (e.g., AD9081/MxFE),
        # use the respective side. For single transceivers (e.g., ADRV9009),
        # use the converter directly.  Resolve via ``getattr`` so the
        # type-checker sees the same optionality the runtime treats it
        # with via ``hasattr``.
        split_side: ConverterSide | None = getattr(
            converter, "adc" if is_rx else "dac", None
        )
        # ``jesd204_settings`` is declared on ``ConverterSide`` (MxFE-style
        # split-sided parts) and added by concrete ``ConverterDevice``
        # subclasses like ``ADRV9009`` — not the base ``ConverterDevice``.
        # Use ``getattr`` to stay structural and keep ty happy when the
        # fallback path leaves us holding a ``ConverterDevice`` instance.
        params: Jesd204Settings = getattr(
            split_side if split_side is not None else converter,
            "jesd204_settings",
        )
        link_id = int(params.link_id)

        sys_clk = sys_clk_select(
            getattr(
                fpga,
                "DEFAULT_FPGA_ADC_PLL" if is_rx else "DEFAULT_FPGA_DAC_PLL",
                "XCVR_QPLL",
            )
        )
        out_clk = out_clk_select("XCVR_REFCLK_DIV2")

        # Clock phandles.
        ref_clk = link.sink_reference_clock if is_rx else link.source_reference_clock
        core_clk = link.sink_core_clock if is_rx else link.source_core_clock

        xcvr_clk_ref = f"{ref_clk.device.label} {ref_clk.index}" if ref_clk else ""
        core_clk_phandle = (
            f"<&{core_clk.device.label} {core_clk.index}>" if core_clk else ""
        )

        clock_output_names_str = (
            '"rx_gt_clk", "rx_out_clk"' if is_rx else '"tx_gt_clk", "tx_out_clk"'
        )

        adxcvr = Adxcvr(
            label=labels["xcvr_label"],
            sys_clk_select=sys_clk,
            out_clk_select=out_clk,
            use_lpm_enable=is_rx,
            clk_ref=xcvr_clk_ref,
            use_div40=False,
            clock_output_names_str=clock_output_names_str,
            jesd_l=int(params.L),
            jesd_m=int(params.M),
            jesd_s=int(params.S),
            jesd204_inputs=f"{ref_clk.device.label} 0 {link_id}" if ref_clk else None,
        )

        ps_clk_ref = (
            f"<&{fpga.PS_CLK_LABEL} {fpga.PS_CLK_INDEX}>"
            if fpga.PS_CLK_INDEX is not None
            else f"<&{fpga.PS_CLK_LABEL}>"
        )
        clocks_parts = [ps_clk_ref]
        if core_clk_phandle:
            clocks_parts.append(core_clk_phandle)
        clocks_parts.append(f"<&{labels['xcvr_label']} 0>")
        clocks_str = ", ".join(clocks_parts)

        jesd_overlay = Jesd204Overlay(
            label=labels["jesd_label"],
            compatible_str=f"adi,axi-jesd204-{direction}-1.0",
            f=int(params.F),
            k=int(params.K),
            direction=direction,
            clocks_str=clocks_str,
            clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
            jesd204_inputs=f"{labels['xcvr_label']} 0 {link_id}",
        )

        tpl_core = TplCore(
            label=labels["core_label"],
            compatible_str=f"adi,axi-{converter.part}-{direction}-1.0",
            direction=direction,
            dma_label=labels["dma_label"],
            spibus_label=converter.label,
            jesd_label=labels["jesd_label"],
            jesd_link_offset=0,
            link_id=link_id,
            sampl_clk_ref=None if is_rx else f"{converter.label} 1",
            sampl_clk_name=None if is_rx else "sampl_clk",
        )

        return JesdLinkModel(
            direction=direction,
            jesd_label=labels["jesd_label"],
            xcvr_label=labels["xcvr_label"],
            core_label=labels["core_label"],
            dma_label=labels["dma_label"],
            link_params={
                "F": int(params.F),
                "K": int(params.K),
                "M": int(params.M),
                "L": int(params.L),
                "Np": int(params.Np),
                "S": int(params.S),
            },
            xcvr_rendered=adxcvr.render(),
            jesd_overlay_rendered=jesd_overlay.render(),
            tpl_core_rendered=tpl_core.render(),
        )

    def _resolve_converter(self, endpoint: Any) -> tuple[ConverterDevice, str] | None:
        """Map *endpoint* to its owning converter + side (``"rx"`` / ``"tx"``).

        Accepts either a :class:`ConverterDevice` (returns ``("rx", ...)``
        or ``("tx", ...)`` depending on downstream context — caller checks)
        or a :class:`ConverterSide` (an ADC or DAC sub-model).
        """
        if isinstance(endpoint, ConverterDevice):
            return endpoint, ""
        if isinstance(endpoint, ConverterSide):
            for dev in self._all_devices():
                if isinstance(dev, ConverterDevice):
                    if getattr(dev, "adc", None) is endpoint:
                        return dev, "rx"
                    if getattr(dev, "dac", None) is endpoint:
                        return dev, "tx"
        return None

    def _direction_of(self, link: _JesdLink) -> tuple[ConverterDevice, str, bool]:
        """Return ``(converter, direction_str, is_rx)`` for a recorded link."""
        # Source side: producer → ADC → FPGA (rx).
        src = self._resolve_converter(link.source)
        if src is not None:
            converter, side = src
            direction = side or "rx"
            return converter, direction, direction == "rx"
        # Sink side: FPGA → DAC (tx).
        sink = self._resolve_converter(link.sink)
        if sink is not None:
            converter, side = sink
            direction = side or "tx"
            return converter, direction, direction == "rx"
        raise ValueError(
            "could not determine link direction; neither endpoint resolves to a converter"
        )

    # ------------------------------------------------------------------
    # DTS emission
    # ------------------------------------------------------------------

    def generate_dts(self) -> str:
        """Return a fully-rendered DTS overlay string."""
        from datetime import datetime

        from .model.renderer import BoardModelRenderer

        model = self.to_board_model()
        nodes = BoardModelRenderer().render(model)
        all_nodes: list[str] = []
        for key in ("clkgens", "jesd204_rx", "jesd204_tx", "converters"):
            all_nodes.extend(nodes.get(key, []))
        lines = [
            "// SPDX-License-Identifier: GPL-2.0",
            f"// AUTOGENERATED BY PYADI-DT {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"// Platform: {model.platform}",
            f"// Design:   {model.name}",
            "",
            "/dts-v1/;",
            "/plugin/;",
            "",
            "\n\n".join(all_nodes),
            "",
        ]
        return "\n".join(lines)

    def generate_dts_overlay(self) -> str:
        """Alias for :meth:`generate_dts`; both produce overlay-mode DTS."""
        return self.generate_dts()
