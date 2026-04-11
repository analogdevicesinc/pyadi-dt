"""ADC/DAC converter context builders.

Provides context builders for AD9680, AD9144, AD9152, AD9172, AD9088,
AD9467, AD7768, ADAQ8092, AD9739a, and AD916x converters.
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


def build_ad9088_ctx(
    *,
    label: str = "adc0_ad9088",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    clk_names_str: str | None = None,
    firmware_name: str | None = None,
    subclass: int | None = None,
    spi_3wire: bool = False,
    jesd204_top_device: int = 0,
    link_ids: str = "0",
    jesd204_inputs: str = "",
) -> dict:
    """Build context dict for ``ad9088.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "clk_names_str": clk_names_str,
        "firmware_name": firmware_name,
        "subclass": subclass,
        "spi_3wire": spi_3wire,
        "jesd204_top_device": jesd204_top_device,
        "link_ids": link_ids,
        "jesd204_inputs": jesd204_inputs,
    }


def build_ad9467_ctx(
    *,
    label: str = "adc0_ad9467",
    compatible_id: str = "ad9467",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    gpio_label: str = "gpio",
    reset_gpio: int | None = None,
) -> dict:
    """Build context dict for ``ad9467.tmpl``."""
    return {
        "label": label,
        "compatible_id": compatible_id,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "gpio_label": gpio_label,
        "reset_gpio": reset_gpio,
    }


def build_ad7768_ctx(
    *,
    label: str = "adc0_ad7768",
    compatible_id: str = "ad7768",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    dma_label: str | None = None,
    data_lines: int | None = None,
    gpio_label: str = "gpio",
    reset_gpio: int | None = None,
) -> dict:
    """Build context dict for ``ad7768.tmpl``."""
    return {
        "label": label,
        "compatible_id": compatible_id,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "dma_label": dma_label,
        "data_lines": data_lines,
        "gpio_label": gpio_label,
        "reset_gpio": reset_gpio,
    }


def build_adaq8092_ctx(
    *,
    label: str = "adc0_adaq8092",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
) -> dict:
    """Build context dict for ``adaq8092.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
    }


def build_ad9739a_ctx(
    *,
    label: str = "dac0_ad9739a",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    full_scale_microamp: int | None = None,
    gpio_label: str = "gpio",
    reset_gpio: int | None = None,
) -> dict:
    """Build context dict for ``ad9739a.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "full_scale_microamp": full_scale_microamp,
        "gpio_label": gpio_label,
        "reset_gpio": reset_gpio,
    }


def build_ad916x_ctx(
    *,
    label: str = "dac0_ad916x",
    compatible_id: str = "ad9162",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    clk_names_str: str | None = None,
    interpolation: int | None = None,
    jesd204_top_device: int = 0,
    jesd204_link_ids: list[int] | None = None,
    jesd204_inputs: str = "",
    octets_per_frame: int | None = None,
    frames_per_multiframe: int | None = None,
    converters_per_device: int | None = None,
    lanes_per_device: int | None = None,
    subclass: int | None = None,
) -> dict:
    """Build context dict for ``ad916x.tmpl``."""
    if jesd204_link_ids is None:
        jesd204_link_ids = [0]
    return {
        "label": label,
        "compatible_id": compatible_id,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "clk_names_str": clk_names_str,
        "interpolation": interpolation,
        "jesd204_top_device": jesd204_top_device,
        "jesd204_link_ids": jesd204_link_ids,
        "jesd204_inputs": jesd204_inputs,
        "octets_per_frame": octets_per_frame,
        "frames_per_multiframe": frames_per_multiframe,
        "converters_per_device": converters_per_device,
        "lanes_per_device": lanes_per_device,
        "subclass": subclass,
    }
