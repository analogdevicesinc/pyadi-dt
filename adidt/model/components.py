"""Pre-configured component factories for common ADI devices.

Each factory returns a :class:`~adidt.model.board_model.ComponentModel`
with the correct role, part name, and template already set.  Pass
device-specific parameters as keyword arguments — they are forwarded to
the matching context builder.

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

from .board_model import ComponentModel
from . import contexts


# ---------------------------------------------------------------------------
# IMU / simple SPI devices
# ---------------------------------------------------------------------------


def adis16495(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """ADIS16495 6-DOF IMU.

    Common kwargs: ``label``, ``spi_max_hz``, ``compatible``,
    ``gpio_label``, ``interrupt_gpio``, ``spi_cpol``, ``spi_cpha``.
    """
    config = contexts.build_adis16495_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="imu",
        part="adis16495",
        template="adis16495.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


def adxl345(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """ADXL345 3-axis accelerometer.

    Common kwargs: ``label``, ``spi_max_hz``, ``compatible``,
    ``gpio_label``, ``interrupt_gpio``.
    """
    config = contexts.build_adxl345_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="accelerometer",
        part="adxl345",
        template="adxl345.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


def ad7124(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """AD7124 24-bit precision ADC.

    Common kwargs: ``label``, ``spi_max_hz``, ``compatible``,
    ``gpio_label``, ``interrupt_gpio``, ``channels``.
    """
    config = contexts.build_ad7124_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="adc",
        part="ad7124",
        template="ad7124.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


# ---------------------------------------------------------------------------
# Clock chips
# ---------------------------------------------------------------------------


def hmc7044(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """HMC7044 14-channel clock distributor.

    Common kwargs: ``label``, ``spi_max_hz``, ``pll1_clkin_frequencies``,
    ``vcxo_hz``, ``pll2_output_hz``, ``clock_output_names``, ``channels``.
    """
    config = contexts.build_hmc7044_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="clock",
        part="hmc7044",
        template="hmc7044.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


def ad9523_1(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """AD9523-1 clock generator.

    Common kwargs: ``label``, ``spi_max_hz``, ``vcxo_hz``,
    ``gpio_controller``, ``sync_gpio``, ``channels``.
    """
    config = contexts.build_ad9523_1_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="clock",
        part="ad9523_1",
        template="ad9523_1.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


def ad9528(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """AD9528 clock generator.

    Common kwargs: ``label``, ``spi_max_hz``, ``vcxo_hz``, ``channels``.
    """
    config = contexts.build_ad9528_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="clock",
        part="ad9528",
        template="ad9528.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


# ---------------------------------------------------------------------------
# ADCs
# ---------------------------------------------------------------------------


def ad9680(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """AD9680 dual-channel ADC.

    Common kwargs: ``label``, ``spi_max_hz``, ``clks_str``,
    ``clk_names_str``, ``sampling_frequency_hz``, ``rx_m``, ``rx_l``,
    ``rx_f``, ``rx_k``, ``rx_np``.
    """
    config = contexts.build_ad9680_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="adc",
        part="ad9680",
        template="ad9680.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


# ---------------------------------------------------------------------------
# DACs
# ---------------------------------------------------------------------------


def ad9144(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """AD9144 quad-channel DAC.

    Common kwargs: ``label``, ``spi_max_hz``, ``clk_ref``,
    ``jesd204_top_device``, ``jesd204_link_ids``, ``jesd204_inputs``.
    """
    config = contexts.build_ad9144_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="dac",
        part="ad9144",
        template="ad9144.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


def ad9152(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """AD9152 dual-channel DAC.

    Common kwargs: ``label``, ``spi_max_hz``, ``clk_ref``,
    ``jesd_link_mode``.
    """
    config = contexts.build_ad9152_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="dac",
        part="ad9152",
        template="ad9152.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


def ad9172(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """AD9172 RF DAC.

    Common kwargs: ``label``, ``spi_max_hz``, ``clk_ref``,
    ``dac_rate_khz``, ``jesd_link_mode``, ``dac_interpolation``,
    ``channel_interpolation``, ``clock_output_divider``.
    """
    config = contexts.build_ad9172_device_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="dac",
        part="ad9172",
        template="ad9172.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


# ---------------------------------------------------------------------------
# Transceivers
# ---------------------------------------------------------------------------


def ad9081(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """AD9081 MxFE transceiver (combined ADC + DAC).

    Common kwargs: ``label``, ``gpio_label``, ``reset_gpio``,
    ``dev_clk_ref``, ``rx_core_label``, ``tx_core_label``,
    ``dac_frequency_hz``, ``adc_frequency_hz``, and JESD params.
    """
    config = contexts.build_ad9081_mxfe_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="transceiver",
        part="ad9081",
        template="ad9081_mxfe.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )


def ad9084(
    spi_bus: str = "spi0",
    cs: int = 0,
    **kwargs,
) -> ComponentModel:
    """AD9084 RX transceiver.

    Common kwargs: ``label``, ``gpio_label``, ``reset_gpio``,
    ``dev_clk_ref``, ``firmware_name``, ``subclass``.
    """
    config = contexts.build_ad9084_ctx(cs=cs, **kwargs)
    return ComponentModel(
        role="transceiver",
        part="ad9084",
        template="ad9084.tmpl",
        spi_bus=spi_bus,
        spi_cs=cs,
        config=config,
    )
