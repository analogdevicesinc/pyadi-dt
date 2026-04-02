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
    jesd_l: int | None = None,
    jesd_m: int | None = None,
    jesd_s: int | None = None,
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
    dma_label: str | None,
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


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def fmt_gpi_gpo(controls: list) -> str:
    """Format a list of int/hex values as a space-separated hex string for DTS."""
    return " ".join(f"0x{int(v):02x}" for v in controls)


# ---------------------------------------------------------------------------
# HMC7044 clock chip (used by AD9081, AD9084, AD9172)
# ---------------------------------------------------------------------------


def build_hmc7044_channel_ctx(pll2_hz: int, channels_spec: list) -> list:
    """Pre-compute freq_str for each HMC7044 channel."""
    result = []
    for ch in channels_spec:
        d = dict(ch)
        if "freq_str" not in d:
            d["freq_str"] = fmt_hz(pll2_hz / d["divider"])
        d.setdefault("coarse_digital_delay", None)
        d.setdefault("startup_mode_dynamic", False)
        d.setdefault("high_perf_mode_disable", False)
        d.setdefault("is_sysref", False)
        result.append(d)
    return result


def build_hmc7044_ctx(
    *,
    label: str,
    cs: int,
    spi_max_hz: int,
    pll1_clkin_frequencies: list,
    vcxo_hz: int,
    pll2_output_hz: int,
    clock_output_names: list,
    channels: list[dict] | None,
    raw_channels: str | None = None,
    jesd204_sysref_provider: bool = True,
    jesd204_max_sysref_hz: int = 2_000_000,
    pll1_loop_bandwidth_hz=None,
    pll1_ref_prio_ctrl=None,
    pll1_ref_autorevert: bool = False,
    pll1_charge_pump_ua=None,
    pfd1_max_freq_hz=None,
    sysref_timer_divider=None,
    pulse_generator_mode=None,
    clkin0_buffer_mode=None,
    clkin1_buffer_mode=None,
    clkin2_buffer_mode: str | None = None,
    clkin3_buffer_mode: str | None = None,
    oscin_buffer_mode=None,
    gpi_controls=None,
    gpo_controls=None,
    sync_pin_mode=None,
    high_perf_mode_dist_enable: bool = False,
    clkin0_ref: str | None = None,
) -> dict:
    """Build context dict for ``hmc7044.tmpl``."""
    clock_output_names_str = ", ".join(f'"{n}"' for n in clock_output_names)
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clkin0_ref": clkin0_ref,
        "pll1_clkin_frequencies": pll1_clkin_frequencies,
        "vcxo_hz": vcxo_hz,
        "pll2_output_hz": pll2_output_hz,
        "clock_output_names_str": clock_output_names_str,
        "jesd204_sysref_provider": jesd204_sysref_provider,
        "jesd204_max_sysref_hz": jesd204_max_sysref_hz,
        "pll1_loop_bandwidth_hz": pll1_loop_bandwidth_hz,
        "pll1_ref_prio_ctrl": pll1_ref_prio_ctrl,
        "pll1_ref_autorevert": pll1_ref_autorevert,
        "pll1_charge_pump_ua": pll1_charge_pump_ua,
        "pfd1_max_freq_hz": pfd1_max_freq_hz,
        "sysref_timer_divider": sysref_timer_divider,
        "pulse_generator_mode": pulse_generator_mode,
        "clkin0_buffer_mode": clkin0_buffer_mode,
        "clkin1_buffer_mode": clkin1_buffer_mode,
        "clkin2_buffer_mode": clkin2_buffer_mode,
        "clkin3_buffer_mode": clkin3_buffer_mode,
        "oscin_buffer_mode": oscin_buffer_mode,
        "gpi_controls_str": fmt_gpi_gpo(gpi_controls) if gpi_controls else "",
        "gpo_controls_str": fmt_gpi_gpo(gpo_controls) if gpo_controls else "",
        "sync_pin_mode": sync_pin_mode,
        "high_perf_mode_dist_enable": high_perf_mode_dist_enable,
        "channels": channels,
        "raw_channels": raw_channels,
    }


# ---------------------------------------------------------------------------
# AD9528 clock chip (used by FMCDAQ3, ADRV9009)
# ---------------------------------------------------------------------------


def build_ad9528_ctx(
    *,
    label: str = "clk0_ad9528",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    vcxo_hz: int = 122_880_000,
    gpio_lines: list[dict] | None = None,
    channels: list[dict] | None = None,
) -> dict:
    """Build context dict for ``ad9528.tmpl``.

    If *channels* is None, uses FMCDAQ3 default channels.
    """
    _m1 = 1_233_333_333  # adi,pll2-m1-frequency
    if channels is None:
        channels = [
            {
                "id": 2,
                "name": "DAC_CLK",
                "divider": 1,
                "freq_str": fmt_hz(_m1 // 1),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 4,
                "name": "DAC_CLK_FMC",
                "divider": 2,
                "freq_str": fmt_hz(_m1 // 2),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 5,
                "name": "DAC_SYSREF",
                "divider": 1,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": True,
            },
            {
                "id": 6,
                "name": "CLKD_DAC_SYSREF",
                "divider": 2,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": True,
            },
            {
                "id": 7,
                "name": "CLKD_ADC_SYSREF",
                "divider": 2,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": True,
            },
            {
                "id": 8,
                "name": "ADC_SYSREF",
                "divider": 1,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": True,
            },
            {
                "id": 9,
                "name": "ADC_CLK_FMC",
                "divider": 2,
                "freq_str": fmt_hz(_m1 // 2),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 13,
                "name": "ADC_CLK",
                "divider": 1,
                "freq_str": fmt_hz(_m1 // 1),
                "signal_source": 0,
                "is_sysref": False,
            },
        ]
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "vcxo_hz": vcxo_hz,
        "gpio_lines": gpio_lines or [],
        "channels": channels,
    }


def build_ad9528_1_ctx(
    *,
    label: str = "clk0_ad9528",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    vcxo_hz: int = 122_880_000,
    gpio_lines: list[dict] | None = None,
    channels: list[dict] | None = None,
) -> dict:
    """Build context dict for ``ad9528_1.tmpl`` (ADRV9009 variant).

    If *channels* is None, uses standard ADRV9009 default channels.
    """
    if channels is None:
        ch_freq = vcxo_hz * 10 // 5
        channels = [
            {
                "id": 13,
                "name": "DEV_CLK",
                "divider": 5,
                "freq_str": fmt_hz(ch_freq),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 1,
                "name": "FMC_CLK",
                "divider": 5,
                "freq_str": fmt_hz(ch_freq),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 12,
                "name": "DEV_SYSREF",
                "divider": 5,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": False,
            },
            {
                "id": 3,
                "name": "FMC_SYSREF",
                "divider": 5,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": False,
            },
        ]
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "vcxo_hz": vcxo_hz,
        "gpio_lines": gpio_lines or [],
        "channels": channels,
    }


# ---------------------------------------------------------------------------
# AD9152 DAC (used by FMCDAQ3)
# ---------------------------------------------------------------------------


def build_ad9152_ctx(
    *,
    label: str = "dac0_ad9152",
    cs: int = 1,
    spi_max_hz: int = 1_000_000,
    clk_ref: str,
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


# ---------------------------------------------------------------------------
# AD9172 DAC (used by AD9172Builder)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# AD9081 MxFE transceiver (used by AD9081Builder)
# ---------------------------------------------------------------------------


def build_ad9081_mxfe_ctx(
    *,
    label: str,
    cs: int,
    gpio_label: str,
    reset_gpio: int,
    sysref_req_gpio: int,
    rx2_enable_gpio: int,
    rx1_enable_gpio: int,
    tx2_enable_gpio: int,
    tx1_enable_gpio: int,
    dev_clk_ref: str,
    rx_core_label: str,
    tx_core_label: str,
    rx_link_id: int,
    tx_link_id: int,
    dac_frequency_hz: int,
    tx_cduc_interpolation: int,
    tx_fduc_interpolation: int,
    tx_converter_select: str,
    tx_lane_map: str,
    tx_link_mode: int,
    tx_m: int,
    tx_f: int,
    tx_k: int,
    tx_l: int,
    tx_s: int,
    adc_frequency_hz: int,
    rx_cddc_decimation: int,
    rx_fddc_decimation: int,
    rx_converter_select: str,
    rx_lane_map: str,
    rx_link_mode: int,
    rx_m: int,
    rx_f: int,
    rx_k: int,
    rx_l: int,
    rx_s: int,
    spi_max_hz: int = 5_000_000,
) -> dict:
    """Build context dict for ``ad9081_mxfe.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "gpio_label": gpio_label,
        "reset_gpio": reset_gpio,
        "sysref_req_gpio": sysref_req_gpio,
        "rx2_enable_gpio": rx2_enable_gpio,
        "rx1_enable_gpio": rx1_enable_gpio,
        "tx2_enable_gpio": tx2_enable_gpio,
        "tx1_enable_gpio": tx1_enable_gpio,
        "dev_clk_ref": dev_clk_ref,
        "rx_core_label": rx_core_label,
        "tx_core_label": tx_core_label,
        "rx_link_id": rx_link_id,
        "tx_link_id": tx_link_id,
        "dac_frequency_hz": dac_frequency_hz,
        "tx_cduc_interpolation": tx_cduc_interpolation,
        "tx_fduc_interpolation": tx_fduc_interpolation,
        "tx_converter_select": tx_converter_select,
        "tx_lane_map": tx_lane_map,
        "tx_link_mode": tx_link_mode,
        "tx_m": tx_m,
        "tx_f": tx_f,
        "tx_k": tx_k,
        "tx_l": tx_l,
        "tx_s": tx_s,
        "adc_frequency_hz": adc_frequency_hz,
        "rx_cddc_decimation": rx_cddc_decimation,
        "rx_fddc_decimation": rx_fddc_decimation,
        "rx_converter_select": rx_converter_select,
        "rx_lane_map": rx_lane_map,
        "rx_link_mode": rx_link_mode,
        "rx_m": rx_m,
        "rx_f": rx_f,
        "rx_k": rx_k,
        "rx_l": rx_l,
        "rx_s": rx_s,
    }


# ---------------------------------------------------------------------------
# ADRV9009/9025 transceiver (used by ADRV9009Builder)
# ---------------------------------------------------------------------------


def build_adrv9009_device_ctx(
    *,
    phy_family: str,
    phy_compatible: str,
    trx_cs: int,
    spi_max_hz: int = 25_000_000,
    gpio_label: str,
    trx_reset_gpio: int,
    trx_sysref_req_gpio: int,
    trx_clocks_value: str,
    trx_clock_names_value: str,
    trx_link_ids_value: str,
    trx_inputs_value: str,
    trx_profile_props_block: str,
    is_fmcomms8: bool,
    trx2_cs: int | None = None,
    trx2_reset_gpio: int | None = None,
    trx1_clocks_value: str | None = None,
) -> dict:
    """Build context dict for ``adrv9009.tmpl``."""
    return {
        "phy_label": f"trx0_{phy_family}",
        "phy_node_name": f"{phy_family}-phy",
        "phy_compatible": phy_compatible,
        "trx_cs": trx_cs,
        "spi_max_hz": spi_max_hz,
        "gpio_label": gpio_label,
        "trx_reset_gpio": trx_reset_gpio,
        "trx_sysref_req_gpio": trx_sysref_req_gpio,
        "trx_clocks_value": trx_clocks_value,
        "trx_clock_names_value": trx_clock_names_value,
        "trx_link_ids_value": trx_link_ids_value,
        "trx_inputs_value": trx_inputs_value,
        "trx_profile_props_block": trx_profile_props_block,
        "is_fmcomms8": is_fmcomms8,
        "trx1_phy_label": f"trx1_{phy_family}" if is_fmcomms8 else None,
        "trx1_phy_compatible": phy_family,
        "trx2_cs": trx2_cs,
        "trx2_reset_gpio": trx2_reset_gpio,
        "trx1_clocks_value": trx1_clocks_value,
    }


# ---------------------------------------------------------------------------
# ADF4382 PLL (used by AD9084Builder)
# ---------------------------------------------------------------------------


def build_adf4382_ctx(
    *,
    label: str = "adf4382",
    cs: int,
    spi_max_hz: int = 1_000_000,
    clks_str: str | None = None,
    clock_output_names_str: str | None = None,
    power_up_frequency: int | None = None,
    spi_3wire: bool = True,
    charge_pump_microamp: int | None = None,
    output_power: int | None = None,
) -> dict:
    """Build context dict for ``adf4382.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "clock_output_names_str": clock_output_names_str,
        "power_up_frequency": power_up_frequency,
        "spi_3wire": spi_3wire,
        "charge_pump_microamp": charge_pump_microamp,
        "output_power": output_power,
    }


# ---------------------------------------------------------------------------
# AD9084 transceiver + inline PLLs (used by AD9084Builder)
# ---------------------------------------------------------------------------


def build_ad9084_ctx(
    *,
    label: str,
    cs: int,
    spi_max_hz: int = 5_000_000,
    gpio_label: str,
    reset_gpio: int,
    dev_clk_ref: str,
    dev_clk_scales: str | None = None,
    firmware_name: str | None = None,
    subclass: int = 1,
    side_b_separate_tpl: bool = False,
    jrx0_physical_lane_mapping: str | None = None,
    jtx0_logical_lane_mapping: str | None = None,
    jrx1_physical_lane_mapping: str | None = None,
    jtx1_logical_lane_mapping: str | None = None,
    hsci_label: str | None = None,
    hsci_auto_linkup: bool = False,
    link_ids: str = "",
    jesd204_inputs: str = "",
) -> dict:
    """Build context dict for ``ad9084.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "gpio_label": gpio_label,
        "reset_gpio": reset_gpio,
        "dev_clk_ref": dev_clk_ref,
        "dev_clk_scales": dev_clk_scales,
        "firmware_name": firmware_name,
        "subclass": subclass,
        "side_b_separate_tpl": side_b_separate_tpl,
        "jrx0_physical_lane_mapping": jrx0_physical_lane_mapping,
        "jtx0_logical_lane_mapping": jtx0_logical_lane_mapping,
        "jrx1_physical_lane_mapping": jrx1_physical_lane_mapping,
        "jtx1_logical_lane_mapping": jtx1_logical_lane_mapping,
        "hsci_label": hsci_label,
        "hsci_auto_linkup": hsci_auto_linkup,
        "link_ids": link_ids,
        "jesd204_inputs": jesd204_inputs,
    }
