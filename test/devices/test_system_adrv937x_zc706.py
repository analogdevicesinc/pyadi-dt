"""End-to-end smoke test for ADRV937x + ZC706 via the System API."""

from __future__ import annotations

import adidt


def _build_system() -> adidt.System:
    fmc = adidt.eval.adrv937x_fmc(reference_frequency=122_880_000)
    fpga = adidt.fpga.zc706()

    system = adidt.System(name="adrv937x_zc706", components=[fmc, fpga])
    system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0)
    system.connect_spi(
        bus_index=0, primary=fpga.spi[0], secondary=fmc.converter.spi, cs=1
    )

    # RX: converter -> FPGA GT
    system.add_link(
        source=fmc.converter,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.xcvr_refclk,
        sink_core_clock=fmc.dev_clk,
        sink_sysref=fmc.sysref_dev,
    )
    # TX: FPGA GT -> converter
    system.add_link(
        source=fpga.gt[1],
        sink=fmc.converter,
        source_reference_clock=fmc.xcvr_refclk,
        source_core_clock=fmc.dev_clk,
        sink_sysref=fmc.sysref_fmc,
    )
    return system


def test_generate_dts_emits_expected_nodes() -> None:
    dts = _build_system().generate_dts()
    assert "/dts-v1/;" in dts
    assert "/plugin/;" in dts
    assert "&spi0" in dts
    assert "clk0_ad9528:" in dts
    assert "trx0_ad9371:" in dts
    assert 'compatible = "adi,ad9371"' in dts


def test_board_model_has_expected_components() -> None:
    model = _build_system().to_board_model()
    parts = sorted(c.part for c in model.components)
    # Both clock and transceiver/converter should be present.
    assert "adrv9009" in parts
    assert any("9528" in p for p in parts)


def test_zc706_platform_constants() -> None:
    fpga = adidt.fpga.zc706()
    assert fpga.ADDR_CELLS == 1
    assert fpga.PS_CLK_LABEL == "clkc"
    assert len(fpga.spi) == 2
    assert len(fpga.gt) == 8


def test_connect_spi_determines_component_bus() -> None:
    system = _build_system()
    model = system.to_board_model()
    clock_comp = next((c for c in model.components if "9528" in c.part), None)
    conv_comp = next((c for c in model.components if c.part == "adrv9009"), None)
    assert clock_comp is not None
    assert conv_comp is not None
    assert clock_comp.spi_bus == "spi0"
    assert clock_comp.spi_cs == 0
    assert conv_comp.spi_bus == "spi0"
    assert conv_comp.spi_cs == 1


def test_reference_wiring_includes_clock_generators_and_observation():
    model = _build_system().to_board_model()
    assert len(model.jesd_links) == 3
    rendered = adidt.BoardModelRenderer().render(model)
    dts = "\n".join(node for group in rendered.values() for node in group)
    for side in ("rx", "rx_os", "tx"):
        assert f"&axi_ad9371_{side}_clkgen" in dts
        assert f"&axi_ad9371_{side}_xcvr" in dts
    assert "jesd204-sysref-provider" in dts
    assert "<&tx_ad9371_tpl_core_dac_tpl_core 0 0>" in dts
    assert "adi,clocks-device-clock_khz" in dts


def test_component_changes_are_preserved():
    system = _build_system()
    board = system.components[0]
    board.converter.spi_max_hz = 12_000_000
    board.clock.spi_max_hz = 8_000_000
    model = system.to_board_model()
    assert "spi-max-frequency = <12000000>" in model.components[1].rendered
    assert "spi-max-frequency = <8000000>" in model.components[0].rendered


def test_missing_tx_link_fails_instead_of_synthesizing_a_connection():
    import pytest

    system = _build_system()
    system._links.pop()
    with pytest.raises(ValueError, match="one RX link and one TX link"):
        system.generate_dts()


def test_ambiguous_transceiver_framing_is_not_silently_discarded():
    import pytest

    system = _build_system()
    system.components[0].converter.jesd204_settings.K = 64
    with pytest.raises(ValueError, match="asymmetric framing"):
        system.generate_dts()


def test_xsa_names_drive_all_reference_overlays():
    from pathlib import Path
    from adidt.xsa.parse.topology import XsaParser
    from adidt.xsa.build.builders.adrv937x import _topology_instance_names
    import re

    system = _build_system()
    xsa = Path(__file__).parents[1] / "hw/xsa/system_top_adrv9371_zc706.xsa"
    topology = XsaParser().parse(xsa)
    system.apply_xsa_topology(topology)
    dts = system.generate_dts()
    external = set(re.findall(r"^\s*&([a-zA-Z0-9_]+)\s*\{", dts, re.M))
    assert external - {"spi0", "misc_clk_0"} <= _topology_instance_names(topology)
    assert "axi_adrv9009" not in dts


def test_unused_clock_override_is_rejected():
    import pytest

    system = _build_system()
    system._links[0].source_reference_clock = system.components[0].sysref_fmc
    with pytest.raises(ValueError, match="converter-side clock overrides"):
        system.generate_dts()
