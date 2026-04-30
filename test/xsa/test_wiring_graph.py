"""Tests for WiringGraph extractors + DOT/D2 renderers + generator."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from adidt.xsa.parse.topology import (
    ConverterInstance,
    Jesd204Instance,
    XsaTopology,
)
from adidt.xsa.viz.wiring_graph import (
    WiringEdge,
    WiringGraph,
    WiringGraphGenerator,
    WiringNode,
    _extract_gpio_from_dts,
    _extract_gpio_from_system,
    _extract_i2c_from_dts,
    _extract_irq_from_topology,
    _extract_jesd_from_system,
    _extract_jesd_from_topology,
    _extract_spi_from_system,
    _extract_spi_from_topology,
    _WiringD2Renderer,
    _WiringDotRenderer,
)


# ---------------------------------------------------------------------------
# Fixtures: XsaTopology + DTS strings
# ---------------------------------------------------------------------------


@pytest.fixture
def topo_ad9081() -> XsaTopology:
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=89,
                link_clk="device_clk_net",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd",
                base_addr=0x44B90000,
                num_lanes=4,
                irq=90,
                link_clk="device_clk_net",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9081_rx",
                ip_type="axi_ad9081",
                base_addr=0x44A04000,
                spi_bus=1,
                spi_cs=0,
            ),
            ConverterInstance(
                name="axi_ad9081_tx",
                ip_type="axi_ad9081",
                base_addr=0x44B04000,
                spi_bus=1,
                spi_cs=0,
            ),
        ],
    )


_GPIO_DTS = """\
/dts-v1/;
/ {
\ttrx0_ad9081: ad9081@0 {
\t\tcompatible = "adi,ad9081";
\t\treset-gpios = <&gpio 133 0>;
\t\tsysref-req-gpios = <&gpio 121 0>;
\t};
};
"""

_I2C_DTS = """\
/dts-v1/;
/ {
\t&i2c0 {
\t\teeprom: at24@50 {
\t\t\tcompatible = "atmel,24c02";
\t\t\treg = <0x50>;
\t\t};
\t\ttmp: tmp101@4b {
\t\t\tcompatible = "ti,tmp101";
\t\t\treg = <0x4b>;
\t\t};
\t};
};
"""


# ---------------------------------------------------------------------------
# Stand-in System object so we don't depend on Device construction
# ---------------------------------------------------------------------------


@dataclass
class _StubLabelable:
    label: str


@dataclass
class _StubDevice:
    label: str
    reset_gpio: int | None = None
    sysref_req_gpio: int | None = None


@dataclass
class _StubSpiPort:
    device: _StubLabelable
    label: str | None = None  # mimic optional .label for SPI master


@dataclass
class _StubSpiConn:
    bus_index: int
    primary: _StubSpiPort
    secondary: _StubSpiPort
    cs: int


@dataclass
class _StubLink:
    source: _StubLabelable
    sink: _StubLabelable


@dataclass
class _StubSystem:
    _spi: list[_StubSpiConn] = field(default_factory=list)
    _links: list[_StubLink] = field(default_factory=list)
    _devs: list[_StubDevice] = field(default_factory=list)
    components: list = field(default_factory=list)

    def _all_devices(self):
        return iter(self._devs)


@pytest.fixture
def system_ad9081() -> _StubSystem:
    fpga = _StubLabelable("zcu102_fpga")
    spi0 = _StubSpiPort(device=fpga, label="spi0")
    spi1 = _StubSpiPort(device=fpga, label="spi1")
    hmc = _StubLabelable("hmc7044")
    ad9081 = _StubLabelable("trx0_ad9081")
    sys = _StubSystem(
        _spi=[
            _StubSpiConn(bus_index=0, primary=spi0, secondary=_StubSpiPort(device=hmc), cs=0),
            _StubSpiConn(bus_index=1, primary=spi1, secondary=_StubSpiPort(device=ad9081), cs=0),
        ],
        _links=[
            _StubLink(source=_StubLabelable("axi_mxfe_rx_xcvr"), sink=_StubLabelable("trx0_ad9081_adc")),
            _StubLink(source=_StubLabelable("trx0_ad9081_dac"), sink=_StubLabelable("axi_mxfe_tx_xcvr")),
        ],
        _devs=[
            _StubDevice(label="trx0_ad9081", reset_gpio=133, sysref_req_gpio=121),
        ],
    )
    return sys


# ---------------------------------------------------------------------------
# Per-extractor unit tests — XSA topology path
# ---------------------------------------------------------------------------


def test_spi_from_topology_emits_one_edge_per_converter(topo_ad9081):
    g = WiringGraph()
    edges = _extract_spi_from_topology(topo_ad9081, g)
    assert len(edges) == 2
    assert {e.kind for e in edges} == {"spi"}
    assert {e.src for e in edges} == {"spi1"}
    assert {e.dst for e in edges} == {"axi_ad9081_rx", "axi_ad9081_tx"}
    assert all(e.label == "cs=0" for e in edges)


def test_spi_from_topology_skips_converters_without_spi(topo_ad9081):
    topo_ad9081.converters[0].spi_bus = None
    g = WiringGraph()
    edges = _extract_spi_from_topology(topo_ad9081, g)
    assert len(edges) == 1
    assert edges[0].dst == "axi_ad9081_tx"


def test_jesd_from_topology_pairs_rx_tx(topo_ad9081):
    g = WiringGraph()
    edges = _extract_jesd_from_topology(topo_ad9081, g)
    rx = [e for e in edges if e.dst == "axi_mxfe_rx_jesd"]
    tx = [e for e in edges if e.src == "axi_mxfe_tx_jesd"]
    assert len(rx) == 1 and rx[0].label == "L4"
    assert len(tx) == 1 and tx[0].label == "L4"


def test_irq_from_topology_emits_one_edge_per_jesd(topo_ad9081):
    g = WiringGraph()
    edges = _extract_irq_from_topology(topo_ad9081, g)
    assert {e.label for e in edges} == {"IRQ 89", "IRQ 90"}
    assert all(e.dst == "interrupt_controller" for e in edges)


def test_irq_skipped_when_irq_is_none():
    topo = XsaTopology(
        jesd204_rx=[Jesd204Instance("a", 0, 1, None, "clk", "rx")],
        jesd204_tx=[],
    )
    g = WiringGraph()
    assert _extract_irq_from_topology(topo, g) == []


# ---------------------------------------------------------------------------
# Per-extractor unit tests — DTS regex path
# ---------------------------------------------------------------------------


def test_gpio_from_dts_extracts_reset_and_sysref():
    g = WiringGraph()
    edges = _extract_gpio_from_dts(_GPIO_DTS, g)
    labels = {e.label for e in edges}
    assert "reset=133" in labels
    assert "sysref-req=121" in labels
    assert all(e.src == "gpio" and e.dst == "trx0_ad9081" for e in edges)


def test_i2c_from_dts_emits_edge_per_child():
    g = WiringGraph()
    edges = _extract_i2c_from_dts(_I2C_DTS, g)
    dsts = {e.dst for e in edges}
    assert {"eeprom", "tmp"}.issubset(dsts)
    assert all(e.src == "i2c0" and e.kind == "i2c" for e in edges)


# ---------------------------------------------------------------------------
# Per-extractor unit tests — System path
# ---------------------------------------------------------------------------


def test_spi_from_system_emits_master_and_slave_edges(system_ad9081):
    g = WiringGraph()
    edges = _extract_spi_from_system(system_ad9081, g)
    assert {(e.src, e.dst) for e in edges} == {
        ("spi0", "hmc7044"),
        ("spi1", "trx0_ad9081"),
    }


def test_jesd_from_system_emits_one_edge_per_link(system_ad9081):
    g = WiringGraph()
    edges = _extract_jesd_from_system(system_ad9081, g)
    assert len(edges) == 2
    assert all(e.kind == "jesd" for e in edges)


def test_gpio_from_system_walks_known_fields(system_ad9081):
    g = WiringGraph()
    edges = _extract_gpio_from_system(system_ad9081, g)
    labels = {e.label for e in edges}
    assert "reset=133" in labels
    assert "sysref-req=121" in labels


# ---------------------------------------------------------------------------
# WiringGraph adapter tests
# ---------------------------------------------------------------------------


def test_from_topology_combines_all_kinds(topo_ad9081):
    g = WiringGraph.from_topology(topo_ad9081, merged_dts=_GPIO_DTS)
    kinds = {e.kind for e in g.edges}
    assert kinds == {"spi", "jesd", "irq", "gpio"}


def test_from_topology_without_merged_dts_skips_gpio_i2c(topo_ad9081):
    g = WiringGraph.from_topology(topo_ad9081)
    kinds = {e.kind for e in g.edges}
    assert "gpio" not in kinds
    assert "i2c" not in kinds


def test_from_system_combines_spi_jesd_gpio(system_ad9081):
    g = WiringGraph.from_system(system_ad9081)
    kinds = {e.kind for e in g.edges}
    assert kinds == {"spi", "jesd", "gpio"}


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------


def test_dot_renderer_emits_digraph_and_color_keyed_edges():
    g = WiringGraph()
    g.add_node("spi0", kind="spi_master")
    g.add_node("ad9081")
    g.add_edge(WiringEdge(src="spi0", dst="ad9081", kind="spi", label="cs=0"))
    out = _WiringDotRenderer().render(g, "test")
    assert out.startswith('digraph "test_wiring"')
    assert "spi0 -> ad9081" in out
    assert "#4ac4d8" in out  # SPI color
    assert "cs=0" in out


def test_dot_renderer_uses_distinct_colors_per_kind():
    g = WiringGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_edge(WiringEdge(src="a", dst="b", kind="spi"))
    g.add_edge(WiringEdge(src="a", dst="b", kind="jesd"))
    g.add_edge(WiringEdge(src="a", dst="b", kind="gpio"))
    g.add_edge(WiringEdge(src="a", dst="b", kind="irq"))
    g.add_edge(WiringEdge(src="a", dst="b", kind="i2c"))
    out = _WiringDotRenderer().render(g, "x")
    # All five kinds should pick up unique colors.
    assert "#4ac4d8" in out  # spi
    assert "#44cc44" in out  # jesd
    assert "#cc9944" in out  # gpio
    assert "#cc4444" in out  # irq
    assert "#a04ac4" in out  # i2c


def test_d2_renderer_produces_arrows_with_stroke_colors():
    g = WiringGraph()
    g.add_node("spi0", kind="spi_master")
    g.add_node("ad9081")
    g.add_edge(WiringEdge(src="spi0", dst="ad9081", kind="spi", label="cs=0"))
    out = _WiringD2Renderer().render(g, "test")
    assert "spi0 -> ad9081" in out
    assert "#4ac4d8" in out


# ---------------------------------------------------------------------------
# WiringGraphGenerator integration tests
# ---------------------------------------------------------------------------


def _basic_graph() -> WiringGraph:
    g = WiringGraph()
    g.add_node("spi0", kind="spi_master")
    g.add_node("ad9081")
    g.add_edge(WiringEdge(src="spi0", dst="ad9081", kind="spi"))
    return g


def test_generator_writes_dot_and_d2_files(tmp_path):
    result = WiringGraphGenerator().generate(_basic_graph(), tmp_path, "test")
    assert "wiring_dot" in result and result["wiring_dot"].exists()
    assert "wiring_d2" in result and result["wiring_d2"].exists()
    assert result["wiring_dot"].suffix == ".dot"
    assert result["wiring_d2"].suffix == ".d2"


def test_generator_kinds_filter_excludes_other_edge_kinds(tmp_path):
    g = _basic_graph()
    g.add_edge(WiringEdge(src="gpio", dst="ad9081", kind="gpio"))
    result = WiringGraphGenerator().generate(g, tmp_path, "filt", kinds={"spi"})
    text = result["wiring_dot"].read_text()
    assert "spi0 -> ad9081" in text
    assert "gpio -> ad9081" not in text


def test_generator_no_svg_keys_when_tools_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr("adidt.xsa.viz._common.shutil.which", lambda _: None)
    result = WiringGraphGenerator().generate(_basic_graph(), tmp_path, "notools")
    assert "wiring_dot_svg" not in result
    assert "wiring_d2_svg" not in result


def test_generator_emits_dot_svg_when_dot_on_path(tmp_path):
    if shutil.which("dot") is None:
        pytest.skip("graphviz dot not on PATH")
    result = WiringGraphGenerator().generate(_basic_graph(), tmp_path, "svg")
    assert "wiring_dot_svg" in result
    assert result["wiring_dot_svg"].exists()
    assert result["wiring_dot_svg"].read_text().startswith("<?xml")
