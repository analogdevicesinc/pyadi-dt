"""Regression coverage for the reusable feature-driven MxFE core."""

from __future__ import annotations

from adidt.devices.converters import (
    AD9081,
    AD9081Adc,
    AD9081Dac,
    AD9084,
    MxFEAdc,
    MxFEDac,
    MxFEDevice,
)


def test_existing_mxfe_parts_use_the_feature_driven_core() -> None:
    """Part adapters retain only their chip-specific data and rendering."""
    assert issubclass(AD9081, MxFEDevice)
    assert issubclass(AD9084, MxFEDevice)
    assert issubclass(AD9081Adc, MxFEAdc)
    assert issubclass(AD9081Dac, MxFEDac)


def test_generic_mxfe_sides_derive_converter_clock() -> None:
    """Cascaded rate conversion is reusable independently of AD9081."""
    adc = MxFEAdc(sample_rate=250_000_000, cddc_decimation=4, fddc_decimation=4)
    dac = MxFEDac(sample_rate=250_000_000, cduc_interpolation=12, fduc_interpolation=4)
    assert adc.converter_clock_hz() == 4_000_000_000
    assert dac.converter_clock_hz() == 12_000_000_000


def test_ad9081_feature_descriptor_drives_common_contract() -> None:
    """The compatibility adapter declares capabilities rather than core wiring."""
    part = AD9081()
    part.adc.jesd204_settings.link_id = 2
    part.dac.jesd204_settings.link_id = 0
    part.gpio_values = {"reset-gpios": 133, "not-supported-gpios": 1}
    lines = part.common_extra_dt_lines(
        {"gpio_label": "gpio", "dev_clk_ref": "hmc7044 2", "rx_core_label": "rx", "tx_core_label": "tx"}
    )
    assert "reset-gpios = <&gpio 133 0>;" in lines
    assert not any("not-supported" in line for line in lines)
    assert "clocks = <&hmc7044 2>;" in lines
    assert "jesd204-link-ids = <2 0>;" in lines
