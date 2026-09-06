"""Rev.B ZU11EG/ADRV2CRR clock wiring from the ADI reference board design.

Reference: ADI Linux 2e8908932dfd, zynqmp-adrv9009-zu11eg-revb-
adrv2crr-fmc-revb-jesd204-fsm.dts. The SoM and FMComms8 route outputs 6–9
differently and must not share a clock-channel table.
"""

from typing import Annotated, ClassVar

from ....devices.clocks import HMC7044
from ....devices._fields import DtSkip
from ....devices.transceivers import ADRV9009


class SecondaryPhy(ADRV9009):
    """Second die participates in the primary die's JESD topology."""

    dt_header: ClassVar[dict] = {
        key: value
        for key, value in ADRV9009.dt_header.items()
        if key != "jesd204-top-device"
    }


class _TreeClock(HMC7044):
    dt_flags: ClassVar[tuple[str, ...]] = (
        "jesd204-device",
        "adi,hmc-two-level-tree-sync-en",
    )
    parent_links: Annotated[tuple[int, ...], DtSkip()] = ()

    def extra_dt_lines(self, context=None):
        lines = super().extra_dt_lines(context)
        if self.parent_links:
            lines += [
                "clocks = <&hmc7044_car 2>;",
                'clock-names = "clkin1";',
                "jesd204-inputs = "
                + ", ".join(f"<&hmc7044_car 0 {link}>" for link in self.parent_links)
                + ";",
            ]
        return lines


def _channels(entries, *, som=True):
    lines = []
    for index, divider, mode, sysref, delay in entries:
        props = [
            f"reg = <{index}>;",
            f"adi,divider = <{divider}>;",
            f"adi,driver-mode = <{mode}>;",
        ]
        if sysref:
            props += [
                "adi,startup-mode-dynamic-enable;",
                "adi,high-performance-mode-disable;",
            ]
        if sysref and som:
            props.append("adi,force-mute-enable;")
        if sysref and (index in (1, 3) or not som):
            props.append(f"adi,driver-impedance-mode = <{1 if som else 3}>;")
        if delay:
            props += [f"adi,coarse-digital-delay = <{delay}>;"]
        lines.append(f"channel@{index} {{ " + " ".join(props) + " };")
    return "\n".join(lines)


def clock_components(spi_bus, clk_cs, pll2, link_ids):
    """Return SoM and carrier clock components with their physical output modes."""
    common = dict(
        spi_max_hz=10_000_000,
        vcxo_hz=122_880_000,
        pll2_output_hz=pll2,
        pll1_loop_bandwidth_hz=200,
        pfd1_max_freq_hz=30_720_000,
        pll1_charge_pump_ua=1920,
        sysref_timer_divider=3840,
        pulse_generator_mode=5,
        oscin_buffer_mode=0x15,
        gpi_controls=[0, 0, 0, 0x11],
        gpo_controls=[0x1F, 0x2B, 0, 0],
    )
    som = _TreeClock(
        label="hmc7044_fmc",
        parent_links=tuple(link_ids),
        pll1_clkin_frequencies=[30_720_000, 30_720_000, 0, 0],
        pll1_ref_prio_ctrl=0xE5,
        clkin0_buffer_mode=0x09,
        clkin1_buffer_mode=0x0B,
        sync_pin_mode=1,
        jesd204_sysref_provider=False,
        high_perf_mode_dist_enable=True,
        raw_channels=_channels(
            [
                (0, 12, 2, False, 15),
                (1, 3840, 1, True, 0),
                (2, 12, 2, False, 15),
                (3, 3840, 1, True, 0),
                (4, 12, 2, False, 0),
                (5, 12, 2, False, 0),
                (6, 24, 0, False, 0),
                (7, 12, 0, False, 0),
                (8, 3840, 1, True, 0),
                (9, 3840, 1, True, 0),
            ]
        ),
        **common,
    )
    carrier = _TreeClock(
        label="hmc7044_car",
        clock_output_names=[f"hmc7044_car_out{i}" for i in range(14)],
        pll1_clkin_frequencies=[122_880_000, 30_720_000, 0, 38_400_000],
        pll1_ref_prio_ctrl=0xB1,
        pll1_ref_autorevert=True,
        clkin0_buffer_mode=0x07,
        clkin1_buffer_mode=0x07,
        clkin3_buffer_mode=0x11,
        sync_pin_mode=0,
        raw_channels=_channels(
            [
                (0, 96, 2, False, 0),
                (2, 96, 1, False, 0),
                (5, 3840, 3, True, 0),
                (6, 3840, 3, True, 0),
                (8, 96, 2, False, 0),
                (9, 96, 1, False, 0),
                (10, 96, 1, False, 0),
                (11, 24, 1, False, 0),
            ],
            som=False,
        ),
        **common,
    )
    return [
        som.to_component_model(spi_bus=spi_bus, spi_cs=clk_cs),
        carrier.to_component_model(spi_bus=spi_bus, spi_cs=3),
    ]
