"""Base class for converter devices (ADCs, DACs, MxFE transceivers).

Converters own :class:`Jesd204Settings` that :meth:`System.add_link`
consumes when the caller does not explicitly override them.  Subclasses
with separate RX/TX halves (MxFE parts like AD9081/AD9084) keep per-side
settings on their ``.adc`` / ``.dac`` sub-models.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, PrivateAttr

from ..base import Device, SpiPort


class Jesd204Settings(BaseModel):
    """JESD204 framing parameters for one direction of a link.

    Attributes:
        jesd_class: ``"jesd204b"`` or ``"jesd204c"``.
        jesd_mode: Vendor mode number (e.g. AD9081 mode 9 / 10).
        link_id: JESD204 framework link id.
        M, L, F, K, Np, S: Standard JESD204 framing parameters.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    jesd_class: str = "jesd204b"
    jesd_mode: int | None = None
    link_id: int = 0
    M: int = 0
    L: int = 0
    F: int = 0
    K: int = 32
    Np: int = 16
    S: int = 1


class ConverterSide(BaseModel):
    """Base class for one side (ADC or DAC) of a converter device.

    Sub-classes add digital-datapath attributes (decimations /
    interpolations) and fine-grained analog properties.  The JESD settings
    held here are consumed by :meth:`System.add_link`.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    sample_rate: int = 0
    jesd204_settings: Jesd204Settings = Jesd204Settings()

    def set_jesd204_mode(self, mode: int, jesd_class: str) -> None:
        """Record the requested mode + class.

        If the concrete converter side declares a :attr:`MODE_TABLE`
        (``{(mode, jesd_class): {"M":..., "L":..., ...}}``), the
        framing parameters M/L/F/K/Np/S are filled in from it.  Callers
        can still override any individual field afterwards.
        """
        self.jesd204_settings.jesd_mode = int(mode)
        self.jesd204_settings.jesd_class = jesd_class
        table = getattr(self, "MODE_TABLE", None)
        if not table:
            return
        framing = table.get((int(mode), jesd_class)) or table.get(int(mode))
        if not framing:
            return
        for key in ("M", "L", "F", "K", "Np", "S"):
            if key in framing:
                setattr(self.jesd204_settings, key, int(framing[key]))


class ConverterDevice(Device):
    """Base class for converter / MxFE transceiver chips.

    Exposes an :class:`SpiPort` and (in subclasses) ``.adc`` / ``.dac``
    sub-models that hold the per-direction JESD204 and datapath state.
    """

    role: ClassVar[str] = "converter"

    _spi: SpiPort = PrivateAttr()

    def model_post_init(self, context: object) -> None:  # noqa: D401
        """Initialize runtime-only attributes after pydantic build."""
        self._spi = SpiPort(self)

    @property
    def spi(self) -> SpiPort:
        """SPI slave port used to configure this converter."""
        return self._spi
