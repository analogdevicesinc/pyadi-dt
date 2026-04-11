"""Clock chip context builders.

Provides context builders for HMC7044, AD9523-1, AD9528, ADF4382,
AD9545, LTC6952, LTC6953, ADF4371, ADF4377, ADF4350, and ADF4030
clock/PLL devices.
"""

from __future__ import annotations

from .fpga import fmt_gpi_gpo, fmt_hz


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


def build_ad9545_ctx(
    *,
    label: str = "clk0_ad9545",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    clk_names_str: str | None = None,
    ref_frequency_hz: int | None = None,
    freq_doubler: bool = False,
    ref_crystal: bool = False,
) -> dict:
    """Build context dict for ``ad9545.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "clk_names_str": clk_names_str,
        "ref_frequency_hz": ref_frequency_hz,
        "freq_doubler": freq_doubler,
        "ref_crystal": ref_crystal,
    }


def build_ltc6952_ctx(
    *,
    label: str = "clk0_ltc6952",
    compatible_id: str = "ltc6952",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    clock_output_names_str: str | None = None,
    vco_frequency_hz: int | None = None,
    ref_frequency_hz: int | None = None,
    channels: list[dict] | None = None,
) -> dict:
    """Build context dict for ``ltc6952.tmpl``."""
    if channels is None:
        channels = []
    return {
        "label": label,
        "compatible_id": compatible_id,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "clock_output_names_str": clock_output_names_str,
        "vco_frequency_hz": vco_frequency_hz,
        "ref_frequency_hz": ref_frequency_hz,
        "channels": channels,
    }


def build_ltc6953_ctx(
    *,
    label: str = "clk0_ltc6953",
    compatible_id: str = "ltc6953",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    clock_output_names_str: str | None = None,
    channels: list[dict] | None = None,
) -> dict:
    """Build context dict for ``ltc6953.tmpl``."""
    if channels is None:
        channels = []
    return {
        "label": label,
        "compatible_id": compatible_id,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "clock_output_names_str": clock_output_names_str,
        "channels": channels,
    }


def build_adf4371_ctx(
    *,
    label: str = "pll0_adf4371",
    compatible_id: str = "adf4371",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    spi_3wire: bool = False,
    muxout_select: int | None = None,
    charge_pump_microamp: int | None = None,
    mute_till_lock: bool = False,
) -> dict:
    """Build context dict for ``adf4371.tmpl``."""
    return {
        "label": label,
        "compatible_id": compatible_id,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "spi_3wire": spi_3wire,
        "muxout_select": muxout_select,
        "charge_pump_microamp": charge_pump_microamp,
        "mute_till_lock": mute_till_lock,
    }


def build_adf4377_ctx(
    *,
    label: str = "pll0_adf4377",
    compatible_id: str = "adf4377",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    muxout_select: str | None = None,
) -> dict:
    """Build context dict for ``adf4377.tmpl``."""
    return {
        "label": label,
        "compatible_id": compatible_id,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "muxout_select": muxout_select,
    }


def build_adf4350_ctx(
    *,
    label: str = "pll0_adf4350",
    compatible_id: str = "adf4350",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    channel_spacing: int | None = None,
    power_up_frequency: int | None = None,
    output_power: int | None = None,
    charge_pump_current: int | None = None,
    muxout_select: int | None = None,
) -> dict:
    """Build context dict for ``adf4350.tmpl``."""
    return {
        "label": label,
        "compatible_id": compatible_id,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "channel_spacing": channel_spacing,
        "power_up_frequency": power_up_frequency,
        "output_power": output_power,
        "charge_pump_current": charge_pump_current,
        "muxout_select": muxout_select,
    }


def build_adf4030_ctx(
    *,
    label: str = "clk0_adf4030",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    clock_output_names_str: str | None = None,
    vco_frequency_hz: int | None = None,
    bsync_frequency_hz: int | None = None,
    channels: list[dict] | None = None,
) -> dict:
    """Build context dict for ``adf4030.tmpl``."""
    if channels is None:
        channels = []
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "clock_output_names_str": clock_output_names_str,
        "vco_frequency_hz": vco_frequency_hz,
        "bsync_frequency_hz": bsync_frequency_hz,
        "channels": channels,
    }
