"""Base class for clock distribution / generation devices."""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .._fields import DtSkip
from ..base import ClockOutput, Device, SpiPort


class ClockChannel(BaseModel):
    """One output channel on a clock device.

    Field aliases are DT property names consumed by the declarative
    renderer (:func:`adidt.devices._dt_render.render_node`).  Not every
    clock family uses every field; devices that don't need a field
    leave it unset and the renderer omits it.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    # ``id`` doubles as the DT unit-address (``reg = <id>;``) and the
    # dict key on the parent device; the renderer emits it from the
    # parent's ``DtSubnodes`` binding, so skip it at the field level.
    id: Annotated[int, DtSkip()]

    name: str | None = Field(None, alias="adi,extended-name")
    divider: int = Field(1, alias="adi,divider")
    driver_mode: int = Field(2, alias="adi,driver-mode")
    is_sysref: bool = Field(False, alias="adi,jesd204-sysref-chan")
    coarse_digital_delay: int | None = Field(None, alias="adi,coarse-digital-delay")
    startup_mode_dynamic: bool = Field(False, alias="adi,startup-mode-dynamic-enable")
    high_perf_mode_disable: bool = Field(
        False, alias="adi,high-performance-mode-disable"
    )

    # Python-only extras (not DT properties).
    freq_str: Annotated[str | None, DtSkip()] = None
    signal_source: Annotated[int | None, DtSkip()] = None


class ClockDevice(Device):
    """Base class for clock distribution chips.

    Subclasses populate :attr:`clk_out` with :class:`ClockOutput` handles
    so downstream devices can be wired via
    ``system.add_link(sink_reference_clock=clock.clk_out[i])`` or via
    named aliases assigned by an eval-board.

    Attributes:
        channels: Per-channel configuration records, keyed by channel id.
    """

    role: ClassVar[str] = "clock"

    channels: dict[int, ClockChannel] = Field(default_factory=dict)

    _spi: SpiPort = PrivateAttr()
    _clk_out: list[ClockOutput] = PrivateAttr(default_factory=list)

    def model_post_init(self, context: object) -> None:  # noqa: D401
        """Initialize non-field runtime attributes after pydantic build."""
        self._spi = SpiPort(self)
        self._clk_out = self._build_clock_outputs()

    @property
    def spi(self) -> SpiPort:
        """SPI slave port used to configure this chip."""
        return self._spi

    @property
    def clk_out(self) -> list[ClockOutput]:
        """Per-output clock handles for downstream connections."""
        return self._clk_out

    def _build_clock_outputs(self) -> list[ClockOutput]:
        """Construct the ``clk_out`` list.

        Default: one :class:`ClockOutput` per entry in :attr:`channels`
        ordered by channel id.  Subclasses override when the hardware
        exposes a fixed number of outputs regardless of population.
        """
        return [
            ClockOutput(
                self,
                index=ch.id,
                name=ch.name,
                divider=ch.divider,
                driver_mode=ch.driver_mode,
                is_sysref=ch.is_sysref,
            )
            for ch in sorted(self.channels.values(), key=lambda c: c.id)
        ]
