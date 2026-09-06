"""Declarative composition of the fixed AD9371/ZC706 reference wiring."""

from copy import deepcopy

from .devices.converters.base import Jesd204Settings
from .xsa.build.builders.adrv937x import ADRV937xBuilder, _topology_instance_names
from .xsa.config.profiles import ProfileManager


def compose_adrv937x(system, boards, fpga):
    """Use the same complete clock/JESD wiring as the validated XSA builder."""
    if len(boards) != 1 or fpga.PLATFORM != "zc706" or len(system.components) != 2:
        raise ValueError("ADRV937x System composition supports one FMC on ZC706")
    board = boards[0]
    if board.clock.label != "clk0_ad9528" or board.converter.label != "trx0_ad9371":
        raise ValueError(
            "ADRV937x reference wiring requires its canonical device labels"
        )
    clock_bus, clock_cs = system._spi_location(board.clock)
    trx_bus, trx_cs = system._spi_location(board.converter)
    if len(system._spi) != 2:
        raise ValueError("ADRV937x requires exactly two SPI connections")
    if any(connection.primary.device is not fpga for connection in system._spi):
        raise ValueError("ADRV937x SPI connections must originate on this FPGA")
    if clock_bus != trx_bus:
        raise ValueError("ADRV937x clock and converter must share the FMC SPI bus")
    links = {}
    for link in system._links:
        converter, direction, is_rx = system._direction_of(link)
        if converter is not board.converter or direction in links:
            raise ValueError("ADRV937x requires one RX link and one TX link")
        endpoint = link.sink if is_rx else link.source
        if not any(endpoint is lane for lane in fpga.gt):
            raise ValueError("ADRV937x links must terminate on this FPGA")
        ref = link.sink_reference_clock if is_rx else link.source_reference_clock
        core = link.sink_core_clock if is_rx else link.source_core_clock
        for actual, index in ((ref, 1), (core, 13)):
            if (
                actual is None
                or actual.device is not board.clock
                or actual.index != index
            ):
                raise ValueError(
                    "ADRV937x requires FMC reference channel 1 and device channel 13"
                )
        other_ref = link.source_reference_clock if is_rx else link.sink_reference_clock
        other_core = link.source_core_clock if is_rx else link.sink_core_clock
        if other_ref is not None or other_core is not None:
            raise ValueError(
                "ADRV937x reference profile does not accept converter-side clock overrides"
            )
        for sysref in (link.sink_sysref, link.source_sysref):
            if sysref is not None and (
                sysref.device is not board.clock or sysref.index != (12 if is_rx else 3)
            ):
                raise ValueError(
                    "ADRV937x SYSREF connection does not match the reference board"
                )
        links[direction] = link
    if set(links) != {"rx", "tx"}:
        raise ValueError("ADRV937x requires one RX link and one TX link")
    # Existing API records one transceiver setting for both directions; the
    # reference design has different RX/TX framing. Unspecified settings use
    # the board profile. Reject ambiguous overrides instead of discarding them.
    params = board.converter.jesd204_settings
    if params != Jesd204Settings():
        raise ValueError("ADRV937x asymmetric framing requires an XSA/profile pipeline")
    if board.clock.vcxo_hz != 122_880_000:
        raise ValueError("ADRV937x reference profile requires a 122.88 MHz VCXO")
    cfg = deepcopy(ProfileManager().load("adrv937x_zc706")["defaults"])
    cfg["adrv9009_board"].update(
        spi_bus=clock_bus,
        clk_cs=clock_cs,
        trx_cs=trx_cs,
        ad9528_vcxo_freq=board.clock.vcxo_hz,
    )
    if system._xsa_topology is not None:
        if system._xsa_topology.inferred_platform() != "zc706":
            raise ValueError("ADRV937x topology must target ZC706")
        names = _topology_instance_names(system._xsa_topology)
    else:
        # Reference HDL names for declarative rendering without an XSA.
        names = {
            f"axi_ad9371_{side}_{suffix}"
            for side in ("rx", "rx_os", "tx")
            for suffix in (
                "dma",
                "clkgen",
                "xcvr",
                f"jesd_{'tx' if side == 'tx' else 'rx'}_axi",
            )
        }
        names.update(
            {
                "rx_ad9371_tpl_core_adc_tpl_core",
                "rx_os_ad9371_tpl_core_adc_tpl_core",
                "tx_ad9371_tpl_core_dac_tpl_core",
            }
        )
    model = ADRV937xBuilder()._build_from_names(
        names,
        fpga.PLATFORM,
        cfg,
        fpga.PS_CLK_LABEL,
        fpga.PS_CLK_INDEX,
        fpga.GPIO_LABEL,
        clock_device=board.clock,
        transceiver_device=board.converter,
    )
    if model is None or len(model.jesd_links) != 3:
        raise ValueError(
            "ADRV937x reference topology requires RX, observation, and TX links"
        )
    model.extra_nodes.extend(model.metadata.pop("extra_nodes_before", []))
    model.extra_nodes.extend(model.metadata.pop("extra_nodes_after", []))
    model.name = system.name
    model.metadata["config_source"] = "adidt.system"
    return model
