"""Shared template-context builders for FMCDAQ2 components.

Each function takes a board config dataclass (e.g. ``_FMCDAQ2Cfg``) and
returns a plain dict ready to pass to a Jinja2 template.  These are used
by both the XSA pipeline (via ``FMCDAQ2Builder``) and the manual board
class workflow (via ``daq2.to_board_model()``).
"""

from __future__ import annotations

from typing import Any


def fmt_hz(hz: int) -> str:
    """Format *hz* as a human-readable frequency string (e.g. '245.76 MHz')."""
    if hz >= 1_000_000_000:
        s = f"{hz / 1_000_000_000:.6f}".rstrip("0").rstrip(".")
        return f"{s} GHz"
    if hz >= 1_000_000:
        s = f"{hz / 1_000_000:.6f}".rstrip("0").rstrip(".")
        return f"{s} MHz"
    if hz >= 1_000:
        s = f"{hz / 1_000:.3f}".rstrip("0").rstrip(".")
        return f"{s} kHz"
    return f"{hz} Hz"


def coerce_board_int(value: Any, key_path: str) -> int:
    """Convert *value* to int; raise ValueError with *key_path* context on failure."""
    if isinstance(value, bool):
        raise ValueError(f"{key_path} must be an integer, got {value!r}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key_path} must be an integer, got {value!r}") from exc


# ---------------------------------------------------------------------------
# FMCDAQ2 context builders
# ---------------------------------------------------------------------------


def build_ad9523_1_ctx(
    *,
    label: str = "clk0_ad9523",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    vcxo_hz: int = 125_000_000,
    gpio_controller: str = "gpio0",
    sync_gpio: int | None = None,
    status0_gpio: int | None = None,
    status1_gpio: int | None = None,
    channels: list[dict] | None = None,
) -> dict:
    """Build context dict for ``ad9523_1.tmpl``.

    Args:
        label: DT node label.
        cs: SPI chip select.
        spi_max_hz: SPI max frequency.
        vcxo_hz: VCXO frequency.
        gpio_controller: GPIO controller label.
        sync_gpio: GPIO index for sync pin, or None to omit.
        status0_gpio: GPIO index for status0 pin, or None to omit.
        status1_gpio: GPIO index for status1 pin, or None to omit.
        channels: List of channel dicts with keys ``id``, ``name``,
            ``divider``, ``freq_str``.  If None, uses FMCDAQ2 defaults.
    """
    _m1 = 1_000_000_000  # adi,pll2-m1-freq distribution frequency
    if channels is None:
        channels = [
            {"id": 1, "name": "DAC_CLK", "divider": 1, "freq_str": fmt_hz(_m1 // 1)},
            {
                "id": 4,
                "name": "ADC_CLK_FMC",
                "divider": 2,
                "freq_str": fmt_hz(_m1 // 2),
            },
            {
                "id": 5,
                "name": "ADC_SYSREF",
                "divider": 128,
                "freq_str": fmt_hz(_m1 // 128),
            },
            {
                "id": 6,
                "name": "CLKD_ADC_SYSREF",
                "divider": 128,
                "freq_str": fmt_hz(_m1 // 128),
            },
            {
                "id": 7,
                "name": "CLKD_DAC_SYSREF",
                "divider": 128,
                "freq_str": fmt_hz(_m1 // 128),
            },
            {
                "id": 8,
                "name": "DAC_SYSREF",
                "divider": 128,
                "freq_str": fmt_hz(_m1 // 128),
            },
            {
                "id": 9,
                "name": "FMC_DAC_REF_CLK",
                "divider": 2,
                "freq_str": fmt_hz(_m1 // 2),
            },
            {"id": 13, "name": "ADC_CLK", "divider": 1, "freq_str": fmt_hz(_m1 // 1)},
        ]

    gpio_lines = []
    for prop, val in [
        ("sync-gpios", sync_gpio),
        ("status0-gpios", status0_gpio),
        ("status1-gpios", status1_gpio),
    ]:
        if val is not None:
            gpio_lines.append(
                {"prop": prop, "controller": gpio_controller, "index": int(val)}
            )

    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "vcxo_hz": vcxo_hz,
        "gpio_lines": gpio_lines,
        "channels": channels,
    }


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
    clk_ref: str,
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


def build_adxcvr_ctx(
    *,
    label: str,
    sys_clk_select: int,
    out_clk_select: int,
    clk_ref: str,
    use_div40: bool = True,
    div40_clk_ref: str | None = None,
    clock_output_names_str: str,
    use_lpm_enable: bool = True,
    jesd_l: int,
    jesd_m: int,
    jesd_s: int,
    jesd204_inputs: str | None = None,
    is_rx: bool = True,
) -> dict:
    """Build context dict for ``adxcvr.tmpl``."""
    return {
        "label": label,
        "sys_clk_select": sys_clk_select,
        "out_clk_select": out_clk_select,
        "clk_ref": clk_ref,
        "use_div40": use_div40,
        "div40_clk_ref": div40_clk_ref or clk_ref,
        "clock_output_names_str": clock_output_names_str,
        "use_lpm_enable": use_lpm_enable,
        "jesd_l": jesd_l,
        "jesd_m": jesd_m,
        "jesd_s": jesd_s,
        "jesd204_inputs": jesd204_inputs,
        "is_rx": is_rx,
    }


def build_jesd204_overlay_ctx(
    *,
    label: str,
    direction: str,
    clocks_str: str,
    clock_names_str: str,
    clock_output_name: str,
    f: int,
    k: int,
    jesd204_inputs: str,
    converter_resolution: int | None = None,
    converters_per_device: int | None = None,
    bits_per_sample: int | None = None,
    control_bits_per_sample: int | None = None,
) -> dict:
    """Build context dict for ``jesd204_overlay.tmpl``."""
    return {
        "label": label,
        "direction": direction,
        "clocks_str": clocks_str,
        "clock_names_str": clock_names_str,
        "clock_output_name": clock_output_name,
        "f": f,
        "k": k,
        "jesd204_inputs": jesd204_inputs,
        "converter_resolution": converter_resolution,
        "converters_per_device": converters_per_device,
        "bits_per_sample": bits_per_sample,
        "control_bits_per_sample": control_bits_per_sample,
    }


def build_tpl_core_ctx(
    *,
    label: str,
    compatible: str,
    direction: str,
    dma_label: str,
    spibus_label: str,
    jesd_label: str,
    jesd_link_offset: int,
    link_id: int,
    pl_fifo_enable: bool = False,
    sampl_clk_ref: str | None = None,
    sampl_clk_name: str | None = None,
) -> dict:
    """Build context dict for ``tpl_core.tmpl``."""
    return {
        "label": label,
        "compatible": compatible,
        "direction": direction,
        "dma_label": dma_label,
        "spibus_label": spibus_label,
        "jesd_label": jesd_label,
        "jesd_link_offset": jesd_link_offset,
        "link_id": link_id,
        "pl_fifo_enable": pl_fifo_enable,
        "sampl_clk_ref": sampl_clk_ref,
        "sampl_clk_name": sampl_clk_name,
    }
