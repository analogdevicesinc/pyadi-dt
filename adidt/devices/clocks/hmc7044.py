"""HMC7044 14-output JESD204B/C clock distribution model.

Declarative rendering: the pydantic field aliases are the DT property
names.  Class-level ``compatible`` / ``dt_header`` / ``dt_flags``
attributes cover the fixed properties, and
:meth:`HMC7044.extra_dt_lines` handles the one coupled pair
(``clocks`` + ``clock-names`` for ``clkin0``).  No Jinja2 template, no
hand-written context dict.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtSkip, DtSubnodes
from ..base import ClockOutput
from .base import ClockChannel, ClockDevice


HMC7044_NUM_CHANNELS: int = 14


from ..._utils import fmt_gpi_gpo as _fmt_hex_bytes, fmt_hz as _fmt_hz  # noqa: E402


class HMC7044(ClockDevice):
    """HMC7044 clock distributor / JESD204 SYSREF source."""

    part: ClassVar[str] = "hmc7044"
    template: ClassVar[str] = ""  # declarative — no Jinja2 template

    # Class-level DT constants.
    compatible: ClassVar[str] = "adi,hmc7044"
    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#clock-cells": 1,
        "#jesd204-cells": 2,
    }
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device",)

    label: str = "hmc7044"

    # --- SPI ------------------------------------------------------------
    spi_max_hz: int = Field(1_000_000, alias="spi-max-frequency")

    # ``clkin0_ref`` drives a coupled (clocks, clock-names) pair emitted
    # by :meth:`extra_dt_lines`; it is not a bare DT property.
    clkin0_ref: Annotated[str | None, DtSkip()] = None

    # --- PLL1 -----------------------------------------------------------
    pll1_clkin_frequencies: list[int] = Field(
        default_factory=lambda: [0, 0, 0, 0],
        alias="adi,pll1-clkin-frequencies",
    )
    pll1_ref_prio_ctrl: int | str | None = Field(None, alias="adi,pll1-ref-prio-ctrl")
    pll1_ref_autorevert: bool = Field(False, alias="adi,pll1-ref-autorevert-enable")
    pll1_loop_bandwidth_hz: int | None = Field(None, alias="adi,pll1-loop-bandwidth-hz")
    pll1_charge_pump_ua: int | None = Field(
        None, alias="adi,pll1-charge-pump-current-ua"
    )
    pfd1_max_freq_hz: int | None = Field(
        None, alias="adi,pfd1-maximum-limit-frequency-hz"
    )

    # --- VCXO / PLL2 ----------------------------------------------------
    vcxo_hz: int = Field(..., alias="adi,vcxo-frequency")
    pll2_output_hz: int = Field(..., alias="adi,pll2-output-frequency")

    # --- Timing / SYSREF ------------------------------------------------
    sysref_timer_divider: int | None = Field(None, alias="adi,sysref-timer-divider")
    pulse_generator_mode: int | None = Field(None, alias="adi,pulse-generator-mode")
    jesd204_sysref_provider: bool = Field(True, alias="jesd204-sysref-provider")
    jesd204_max_sysref_hz: int = Field(
        2_000_000, alias="adi,jesd204-max-sysref-frequency-hz"
    )

    # --- Buffer modes ---------------------------------------------------
    clkin0_buffer_mode: int | str | None = Field(None, alias="adi,clkin0-buffer-mode")
    clkin1_buffer_mode: int | str | None = Field(None, alias="adi,clkin1-buffer-mode")
    clkin2_buffer_mode: int | str | None = Field(None, alias="adi,clkin2-buffer-mode")
    clkin3_buffer_mode: int | str | None = Field(None, alias="adi,clkin3-buffer-mode")
    oscin_buffer_mode: int | str | None = Field(None, alias="adi,oscin-buffer-mode")

    # --- GPIO / sync ----------------------------------------------------
    # GPI/GPO controls render as ``<0x00 0x11 ...>`` so we keep them as
    # a pre-formatted hex string and emit verbatim via a raw alias.
    gpi_controls: Annotated[list[int] | None, DtSkip()] = None
    gpo_controls: Annotated[list[int] | None, DtSkip()] = None

    sync_pin_mode: int | None = Field(None, alias="adi,sync-pin-mode")
    high_perf_mode_dist_enable: bool = Field(
        False, alias="adi,high-performance-mode-clock-dist-enable"
    )

    # --- Output naming --------------------------------------------------
    clock_output_names: list[str] = Field(
        default_factory=lambda: [
            f"hmc7044_out{i}" for i in range(HMC7044_NUM_CHANNELS)
        ],
        alias="clock-output-names",
    )

    # --- Channels -------------------------------------------------------
    channels: Annotated[
        dict[int, ClockChannel],
        DtSubnodes(node_name="channel", label_template="{parent}_c{key}"),
    ] = Field(default_factory=dict)

    # --- XSA-provided raw channel block (escape hatch) -----------------
    raw_channels: Annotated[str | None, DtSkip()] = None

    # --- Overrides ------------------------------------------------------
    def _build_clock_outputs(self) -> list[ClockOutput]:
        """Always expose 14 channels, filling from :attr:`channels` when set."""
        outputs: list[ClockOutput] = []
        for i in range(HMC7044_NUM_CHANNELS):
            ch = self.channels.get(i)
            if ch is not None:
                outputs.append(
                    ClockOutput(
                        self,
                        index=i,
                        name=ch.name,
                        divider=ch.divider,
                        driver_mode=ch.driver_mode,
                        is_sysref=ch.is_sysref,
                    )
                )
            else:
                outputs.append(ClockOutput(self, index=i))
        return outputs

    # --- Rendering ------------------------------------------------------
    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        """Emit coupled / formatted properties the field walker can't handle."""
        lines: list[str] = []
        if self.clkin0_ref is not None:
            lines.append(f"clocks = <&{self.clkin0_ref}>;")
            lines.append('clock-names = "clkin0";')
        if self.gpi_controls:
            lines.append(f"adi,gpi-controls = <{_fmt_hex_bytes(self.gpi_controls)}>;")
        if self.gpo_controls:
            lines.append(f"adi,gpo-controls = <{_fmt_hex_bytes(self.gpo_controls)}>;")
        return lines

    def render_dt(self, *, cs: int) -> str:
        """Render this device as a DT node string.

        When :attr:`raw_channels` is set (XSA escape hatch), the per-
        channel sub-nodes are suppressed and the raw block is spliced
        in in their place.
        """
        if self.raw_channels is not None:
            # Emit without children, then splice the raw block in before `};`.
            from copy import copy

            stripped = copy(self)
            object.__setattr__(stripped, "channels", {})
            return render_node(
                stripped,
                label=self.label,
                node_name=f"hmc7044@{cs}",
                reg=cs,
                trailing_block=self.raw_channels,
            )
        return render_node(
            self,
            label=self.label,
            node_name=f"hmc7044@{cs}",
            reg=cs,
        )

    def to_component_model(
        self, *, spi_bus: str, spi_cs: int, extra: dict[str, Any] | None = None
    ):
        """Produce a :class:`ComponentModel` with a pre-rendered DT node string.

        The renderer still receives a ``ComponentModel`` so
        ``BoardModelRenderer`` can group components by SPI bus, but the
        ``rendered`` field carries the final DT text — no Jinja2
        template lookup happens for this device.
        """
        from adidt.model.board_model import ComponentModel

        return ComponentModel(
            role=self.role,
            part=self.part,
            spi_bus=spi_bus,
            spi_cs=spi_cs,
            rendered=self.render_dt(cs=spi_cs),
        )
