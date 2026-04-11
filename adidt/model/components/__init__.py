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
ad9545 = ClockComponent.ad9545
ltc6952 = ClockComponent.ltc6952
ltc6953 = ClockComponent.ltc6953
adf4371 = ClockComponent.adf4371
adf4377 = ClockComponent.adf4377
adf4350 = ClockComponent.adf4350
adf4030 = ClockComponent.adf4030

# ADCs
ad9680 = AdcComponent.ad9680
ad9088 = AdcComponent.ad9088
ad9467 = AdcComponent.ad9467
ad7768 = AdcComponent.ad7768
adaq8092 = AdcComponent.adaq8092

# DACs
ad9144 = DacComponent.ad9144
ad9152 = DacComponent.ad9152
ad9172 = DacComponent.ad9172
ad9739a = DacComponent.ad9739a
ad916x = DacComponent.ad916x

# Transceivers
ad9081 = TransceiverComponent.ad9081
ad9082 = TransceiverComponent.ad9082
ad9083 = TransceiverComponent.ad9083
ad9084 = TransceiverComponent.ad9084
adrv9009 = TransceiverComponent.adrv9009

# Sensors
adis16495 = SensorComponent.adis16495
adxl345 = SensorComponent.adxl345
ad7124 = SensorComponent.ad7124

# RF front-ends
admv1013 = RfFrontendComponent.admv1013
admv1014 = RfFrontendComponent.admv1014
adrf6780 = RfFrontendComponent.adrf6780
adar1000 = RfFrontendComponent.adar1000

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
    "ad9545",
    "ltc6952",
    "ltc6953",
    "adf4371",
    "adf4377",
    "adf4350",
    "adf4030",
    "ad9680",
    "ad9088",
    "ad9467",
    "ad7768",
    "adaq8092",
    "ad9144",
    "ad9152",
    "ad9172",
    "ad9739a",
    "ad916x",
    "ad9081",
    "ad9082",
    "ad9083",
    "ad9084",
    "adrv9009",
    "adis16495",
    "adxl345",
    "ad7124",
    "admv1013",
    "admv1014",
    "adrf6780",
    "adar1000",
]
