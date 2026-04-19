"""Base classes for FPGA board models."""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, PrivateAttr

from ..devices.base import Device, GtLane, SpiPort


class SpiMaster(SpiPort):
    """An SPI master interface on an FPGA.

    Attributes:
        label: DT label that the peripheral's overlay references,
            e.g. ``"spi0"``, ``"spi1"``.  Peripheral nodes are wrapped in
            ``&<label> { ... };`` by the renderer.
    """

    __slots__ = ("label",)

    def __init__(self, device: Device, label: str) -> None:
        super().__init__(device)
        self.label = label


class FpgaBoard(Device):
    """Base class for FPGA boards (ZCU102, VPK180, ZC706, VCU118, ...).

    Subclasses override class-level constants (``PLATFORM``,
    ``ADDR_CELLS``, ``PS_CLK_LABEL``, ``PS_CLK_INDEX``, ``GPIO_LABEL``,
    ``SPI_LABELS``, ``NUM_GT_LANES``).
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True, populate_by_name=True, extra="forbid"
    )

    role: ClassVar[str] = "fpga"

    PLATFORM: ClassVar[str] = ""
    ADDR_CELLS: ClassVar[int] = 2
    PS_CLK_LABEL: ClassVar[str] = ""
    PS_CLK_INDEX: ClassVar[int | None] = None
    GPIO_LABEL: ClassVar[str] = "gpio"
    SPI_LABELS: ClassVar[tuple[str, ...]] = ()
    NUM_GT_LANES: ClassVar[int] = 16

    label: str = "fpga"

    _spi: list[SpiMaster] = PrivateAttr(default_factory=list)
    _gt: list[GtLane] = PrivateAttr(default_factory=list)

    def model_post_init(self, context: object) -> None:  # noqa: D401
        """Build SPI master and GT lane handles from class-level constants."""
        self._spi = [SpiMaster(self, lbl) for lbl in self.SPI_LABELS]
        self._gt = [GtLane(self, i) for i in range(self.NUM_GT_LANES)]

    @property
    def spi(self) -> list[SpiMaster]:
        """SPI masters exposed by this FPGA platform."""
        return self._spi

    @property
    def gt(self) -> list[GtLane]:
        """GT (gigabit transceiver) lanes available for JESD204 links."""
        return self._gt

    @property
    def platform(self) -> str:
        """Platform string (e.g. ``"zcu102"``)."""
        return self.PLATFORM
