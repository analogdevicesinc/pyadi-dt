"""Base classes for typed hardware device models.

:class:`Device` is a pydantic ``BaseModel``; subclasses declare DT properties
as typed fields with ``Field(alias="adi,...")`` so the same attribute name is
both Pythonic and reversible back to the original DT property.

:class:`Port` instances expose the physical interfaces of a device (SPI pins,
clock outputs, GT lanes).  The :class:`adidt.system.System` records which
ports connect to which by holding references to these objects; it does not
mutate the devices themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from adidt.model.board_model import ComponentModel


class Device(BaseModel):
    """Base class for a hardware device modeled as a pydantic schema.

    Attributes:
        label: DT node label (e.g. ``"hmc7044"``).  Used to resolve phandles
            during rendering.
        part: Short part identifier used by :class:`ComponentModel`
            (e.g. ``"hmc7044"``, ``"ad9081"``).  Typically set as a
            ``ClassVar`` on each subclass.
        template: Jinja2 template filename under ``adidt/templates/xsa/``.
            Typically set as a ``ClassVar`` on each subclass.
        role: Logical role passed through to :class:`ComponentModel`
            (e.g. ``"clock"``, ``"transceiver"``).  Class-level default.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        extra="forbid",
    )

    label: str

    part: ClassVar[str] = ""
    template: ClassVar[str] = ""
    role: ClassVar[str] = ""

    def to_component_model(
        self,
        *,
        spi_bus: str,
        spi_cs: int,
        extra: dict[str, Any] | None = None,
    ) -> "ComponentModel":
        """Produce a :class:`ComponentModel` consumable by the renderer.

        *extra* carries System-resolved context (phandle labels, dev-clk
        references) that the device cannot know on its own.  Subclasses
        forward it to :meth:`build_context`.
        """
        from adidt.model.board_model import ComponentModel

        return ComponentModel(
            role=self.role,
            part=self.part,
            template=self.template,
            spi_bus=spi_bus,
            spi_cs=spi_cs,
            config=self.build_context(cs=spi_cs, extra=extra or {}),
        )

    def build_context(
        self, *, cs: int, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return the Jinja2 template context for this device.

        Default: dump fields by alias.  Subclasses override for
        template-specific glue (pre-formatted strings, aggregates, etc.).
        """
        return self.model_dump(by_alias=True)


class Port:
    """Marker base for a physical interface on a device."""

    __slots__ = ("device",)

    def __init__(self, device: Device) -> None:
        self.device = device


class SpiPort(Port):
    """SPI interface on a device.

    For a secondary (peripheral) device, this represents the chip's SPI
    slave port.  For a primary (an FPGA), :class:`adidt.fpga.SpiMaster`
    fills the corresponding role.
    """

    __slots__ = ()


class ClockOutput:
    """One clock-output channel on a :class:`ClockDevice`.

    Attributes:
        device: The clock device that owns this output.
        index: Hardware output index (channel number) on the clock chip.
        name: Optional board-level alias (e.g. ``"DEV_REFCLK"``).  Named
            aliases are assigned by an ``EvalBoard`` when it pins outputs
            to specific downstream devices.
        divider: Optional divider value.  Filled by the user or the JIF
            solver; :meth:`adidt.system.System.to_board_model` reads it
            when emitting the channel node.
    """

    __slots__ = ("device", "index", "name", "divider", "driver_mode", "is_sysref")

    def __init__(
        self,
        device: "Device",
        index: int,
        *,
        name: str | None = None,
        divider: int | None = None,
        driver_mode: int = 2,
        is_sysref: bool = False,
    ) -> None:
        self.device = device
        self.index = index
        self.name = name
        self.divider = divider
        self.driver_mode = driver_mode
        self.is_sysref = is_sysref

    def __repr__(self) -> str:  # pragma: no cover - trivial
        label = getattr(self.device, "label", "?")
        alias = f" {self.name!r}" if self.name else ""
        return f"ClockOutput({label} #{self.index}{alias})"


class GtLane:
    """One Gigabit Transceiver lane on an FPGA."""

    __slots__ = ("fpga", "index")

    def __init__(self, fpga: Device, index: int) -> None:
        self.fpga = fpga
        self.index = index


class Pin:
    """A single-ended GPIO/reset/sync pin on a device (placeholder)."""

    __slots__ = ("device", "name")

    def __init__(self, device: Device, name: str) -> None:
        self.device = device
        self.name = name
