"""Pre-configured component factories for common ADI devices.

Each factory returns a :class:`~adidt.model.board_model.ComponentModel`
(or a typed subclass) with the correct role, part name, and template
already set.  Pass device-specific parameters as keyword arguments --
they are forwarded to the matching context builder.

Usage::

    from adidt.model.components import adis16495, ad9680, hmc7044

    model = BoardModel(
        name="my_board",
        platform="rpi5",
        components=[
            adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
        ],
    )
"""

from __future__ import annotations

# Base mixin
from .base import JesdDeviceMixin, JESD_PARAM_NAMES, JESD_SUBCLASS_MAP

# Typed component classes
from .clocks import ClockComponent
from .converters import AdcComponent, DacComponent
from .transceivers import TransceiverComponent
from .sensors import SensorComponent
from .rf_frontends import RfFrontendComponent

# ---------------------------------------------------------------------------
# Backward-compatible standalone function aliases
# ---------------------------------------------------------------------------

# Clocks
hmc7044 = ClockComponent.hmc7044
ad9523_1 = ClockComponent.ad9523_1
ad9528 = ClockComponent.ad9528
adf4382 = ClockComponent.adf4382

# ADCs
ad9680 = AdcComponent.ad9680

# DACs
ad9144 = DacComponent.ad9144
ad9152 = DacComponent.ad9152
ad9172 = DacComponent.ad9172

# Transceivers
ad9081 = TransceiverComponent.ad9081
ad9084 = TransceiverComponent.ad9084
adrv9009 = TransceiverComponent.adrv9009

# Sensors
adis16495 = SensorComponent.adis16495
adxl345 = SensorComponent.adxl345
ad7124 = SensorComponent.ad7124

__all__ = [
    # Base
    "JesdDeviceMixin",
    "JESD_PARAM_NAMES",
    "JESD_SUBCLASS_MAP",
    # Typed classes
    "ClockComponent",
    "AdcComponent",
    "DacComponent",
    "TransceiverComponent",
    "SensorComponent",
    "RfFrontendComponent",
    # Backward-compat function aliases
    "hmc7044",
    "ad9523_1",
    "ad9528",
    "adf4382",
    "ad9680",
    "ad9144",
    "ad9152",
    "ad9172",
    "ad9081",
    "ad9084",
    "adrv9009",
    "adis16495",
    "adxl345",
    "ad7124",
]
