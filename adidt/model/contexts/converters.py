"""ADC/DAC converter context builders.

Provides context builders for AD9680, AD9144, AD9152, and AD9172 converters.
"""

from __future__ import annotations


def build_ad9680_ctx(
    *,
    label: str = "adc0_ad9680",
    cs: int = 2,
    spi_max_hz: int = 1_000_000,
    use_spi_3wire: bool = False,
    clks_str: str,
    clk_names_str: str,
    sampling_frequency_hz: int = 1_000_000_000,
    rx_m: int = 2,
    rx_l: int = 4,
    rx_f: int = 1,
    rx_k: int = 32,
    rx_np: int = 16,
    jesd204_top_device: int = 0,
    jesd204_link_ids: list[int] | None = None,
    jesd204_inputs: str = "",
    gpio_controller: str = "gpio0",
    powerdown_gpio: int | None = None,
    fastdetect_a_gpio: int | None = None,
    fastdetect_b_gpio: int | None = None,
) -> dict:
    """Build context dict for ``ad9680.tmpl``."""
    gpio_lines = []
    for prop, val in [
        ("powerdown-gpios", powerdown_gpio),
        ("fastdetect-a-gpios", fastdetect_a_gpio),
        ("fastdetect-b-gpios", fastdetect_b_gpio),
    ]:
        if val is not None:
            gpio_lines.append(
                {"prop": prop, "controller": gpio_controller, "index": int(val)}
            )

    if jesd204_link_ids is None:
        jesd204_link_ids = [0]

    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "use_spi_3wire": use_spi_3wire,
        "clks_str": clks_str,
        "clk_names_str": clk_names_str,
        "sampling_frequency_hz": sampling_frequency_hz,
        "m": rx_m,
        "l": rx_l,
        "f": rx_f,
        "k": rx_k,
        "np": rx_np,
        "jesd204_top_device": jesd204_top_device,
        "jesd204_link_ids": jesd204_link_ids,
        "jesd204_inputs": jesd204_inputs,
        "gpio_lines": gpio_lines,
    }


def build_ad9144_ctx(
    *,
    label: str = "dac0_ad9144",
    cs: int = 1,
    spi_max_hz: int = 1_000_000,
    clk_ref: str | None = None,
    jesd204_top_device: int = 1,
    jesd204_link_ids: list[int] | None = None,
    jesd204_inputs: str = "",
    gpio_controller: str = "gpio0",
    txen_gpio: int | None = None,
    reset_gpio: int | None = None,
    irq_gpio: int | None = None,
) -> dict:
    """Build context dict for ``ad9144.tmpl``."""
    gpio_lines = []
    for prop, val in [
        ("txen-gpios", txen_gpio),
        ("reset-gpios", reset_gpio),
        ("irq-gpios", irq_gpio),
    ]:
        if val is not None:
            gpio_lines.append(
                {"prop": prop, "controller": gpio_controller, "index": int(val)}
            )

    if jesd204_link_ids is None:
        jesd204_link_ids = [0]

    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clk_ref": clk_ref,
        "jesd204_top_device": jesd204_top_device,
        "jesd204_link_ids": jesd204_link_ids,
        "jesd204_inputs": jesd204_inputs,
        "gpio_lines": gpio_lines,
    }


def build_ad9152_ctx(
    *,
    label: str = "dac0_ad9152",
    cs: int = 1,
    spi_max_hz: int = 1_000_000,
    clk_ref: str | None = None,
    jesd_link_mode: int = 4,
    jesd204_top_device: int = 1,
    jesd204_link_ids: list[int] | None = None,
    jesd204_inputs: str = "",
    gpio_controller: str = "gpio0",
    txen_gpio: int | None = None,
    irq_gpio: int | None = None,
) -> dict:
    """Build context dict for ``ad9152.tmpl``."""
    gpio_lines = []
    for prop, val in [
        ("txen-gpios", txen_gpio),
        ("irq-gpios", irq_gpio),
    ]:
        if val is not None:
            gpio_lines.append(
                {"prop": prop, "controller": gpio_controller, "index": int(val)}
            )
    if jesd204_link_ids is None:
        jesd204_link_ids = [0]
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clk_ref": clk_ref,
        "jesd_link_mode": jesd_link_mode,
        "jesd204_top_device": jesd204_top_device,
        "jesd204_link_ids": jesd204_link_ids,
        "jesd204_inputs": jesd204_inputs,
        "gpio_lines": gpio_lines,
    }


def build_ad9172_device_ctx(
    *,
    label: str = "dac0_ad9172",
    cs: int = 1,
    spi_max_hz: int = 1_000_000,
    clk_ref: str = "hmc7044 2",
    dac_rate_khz: int,
    jesd_link_mode: int,
    dac_interpolation: int,
    channel_interpolation: int,
    clock_output_divider: int,
    jesd_link_ids: list[int] | None = None,
    jesd204_inputs: str = "",
) -> dict:
    """Build context dict for ``ad9172.tmpl``."""
    if jesd_link_ids is None:
        jesd_link_ids = [0]
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clk_ref": clk_ref,
        "dac_rate_khz": dac_rate_khz,
        "jesd_link_mode": jesd_link_mode,
        "dac_interpolation": dac_interpolation,
        "channel_interpolation": channel_interpolation,
        "clock_output_divider": clock_output_divider,
        "jesd_link_ids": jesd_link_ids,
        "jesd204_inputs": jesd204_inputs,
    }
