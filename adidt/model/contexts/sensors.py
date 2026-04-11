"""Simple SPI sensor context builders.

Provides context builders for ADIS16495 IMU, ADXL345 accelerometer,
and AD7124 precision ADC devices.
"""

from __future__ import annotations


def build_adis16495_ctx(
    *,
    label: str = "imu0",
    device: str = "adis16495",
    compatible: str = "adi,adis16495-1",
    cs: int = 0,
    spi_max_hz: int = 2_000_000,
    spi_cpol: bool = True,
    spi_cpha: bool = True,
    gpio_label: str = "gpio",
    interrupt_gpio: int | None = None,
    irq_type: str = "IRQ_TYPE_EDGE_FALLING",
) -> dict:
    """Build context dict for ``adis16495.tmpl``.

    The ADIS16495 is a 6-DOF IMU connected via SPI.  This context builder
    produces a minimal device tree node with SPI mode, interrupt, and
    compatible string.
    """
    return {
        "label": label,
        "device": device,
        "compatible": compatible,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "spi_cpol": spi_cpol,
        "spi_cpha": spi_cpha,
        "gpio_label": gpio_label,
        "interrupt_gpio": interrupt_gpio,
        "irq_type": irq_type,
    }


def build_adxl345_ctx(
    *,
    label: str = "accel0",
    device: str = "adxl345",
    compatible: str = "adi,adxl345",
    cs: int = 0,
    spi_max_hz: int = 5_000_000,
    spi_cpol: bool = True,
    spi_cpha: bool = True,
    gpio_label: str = "gpio",
    interrupt_gpio: int | None = None,
    irq_type: str = "IRQ_TYPE_LEVEL_HIGH",
) -> dict:
    """Build context dict for ``adxl345.tmpl``."""
    return {
        "label": label,
        "device": device,
        "compatible": compatible,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "spi_cpol": spi_cpol,
        "spi_cpha": spi_cpha,
        "gpio_label": gpio_label,
        "interrupt_gpio": interrupt_gpio,
        "irq_type": irq_type,
    }


def build_ad7124_ctx(
    *,
    label: str = "adc0",
    device: str = "ad7124",
    compatible: str = "adi,ad7124-8",
    cs: int = 0,
    spi_max_hz: int = 5_000_000,
    gpio_label: str = "gpio",
    interrupt_gpio: int | None = None,
    irq_type: str = "IRQ_TYPE_EDGE_FALLING",
    channels: list[dict] | None = None,
) -> dict:
    """Build context dict for ``ad7124.tmpl``.

    Args:
        channels: List of channel dicts with keys ``id`` and optional ``name``.
            If None, creates 8 default channels.
    """
    if channels is None:
        channels = [{"id": i} for i in range(8)]
    return {
        "label": label,
        "device": device,
        "compatible": compatible,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "gpio_label": gpio_label,
        "interrupt_gpio": interrupt_gpio,
        "irq_type": irq_type,
        "channels": channels,
    }
