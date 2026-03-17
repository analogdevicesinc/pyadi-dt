# test/xsa/test_clock_graph.py
"""Tests for the ClockGraphGenerator / DTS clock-tree diagram module."""


import pytest

from adidt.xsa.clock_graph import ClockGraphGenerator, _DotRenderer, _DtsParser

# ---------------------------------------------------------------------------
# Sample DTS fragments used across tests
# ---------------------------------------------------------------------------

_SIMPLE_DTS = """\
/dts-v1/;
/ {
\tamba: axi {
\t\taxi_clkgen_0: axi-clkgen@44a10000 {
\t\t\tcompatible = "adi,axi-clkgen-2.00.a";
\t\t\t#clock-cells = <1>;
\t\t\tclock-output-names = "axi_clkgen_0_0", "axi_clkgen_0_1";
\t\t};
\t\taxi_jesd_rx: axi-jesd204-rx@44a50000 {
\t\t\tcompatible = "adi,axi-jesd204-rx-1.0";
\t\t\tclocks = <&zynqmp_clk 71>, <&axi_clkgen_0 0>, <&axi_adxcvr 0>;
\t\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";
\t\t\t#clock-cells = <0>;
\t\t};
\t};
};
"""

_HMC7044_DTS = """\
/dts-v1/;
/ {
\thmc7044_fmc: hmc7044@0 {
\t\tcompatible = "adi,hmc7044";
\t\t#clock-cells = <1>;
\t\tclock-output-names = "hmc7044_out0", "hmc7044_out1";
\t};
\taxi_xcvr_rx: axi-adxcvr-rx@85a40000 {
\t\tcompatible = "adi,axi-adxcvr-1.0";
\t\tclocks = <&hmc7044_fmc 5>, <&hmc7044_fmc 9>;
\t\tclock-names = "conv", "div40";
\t\t#clock-cells = <1>;
\t\tclock-output-names = "rx_gt_clk", "rx_out_clk";
\t};
\taxi_jesd_rx: axi-jesd204-rx@85a50000 {
\t\tcompatible = "adi,axi-jesd204-rx-1.0";
\t\tclocks = <&zynqmp_clk 71>, <&hmc7044_fmc 9>, <&axi_xcvr_rx 0>;
\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";
\t\t#clock-cells = <0>;
\t};
};
"""


# ---------------------------------------------------------------------------
# _DtsParser tests
# ---------------------------------------------------------------------------


def test_parser_finds_clkgen_output_names():
    nodes = _DtsParser().parse(_SIMPLE_DTS)
    clkgen = next(n for n in nodes if n.label == "axi_clkgen_0")
    assert clkgen.clock_output_names == ["axi_clkgen_0_0", "axi_clkgen_0_1"]


def test_parser_finds_consumer_clocks():
    nodes = _DtsParser().parse(_SIMPLE_DTS)
    jesd = next(n for n in nodes if n.label == "axi_jesd_rx")
    assert ("zynqmp_clk", 71) in jesd.clocks
    assert ("axi_clkgen_0", 0) in jesd.clocks
    assert ("axi_adxcvr", 0) in jesd.clocks


def test_parser_finds_clock_names():
    nodes = _DtsParser().parse(_SIMPLE_DTS)
    jesd = next(n for n in nodes if n.label == "axi_jesd_rx")
    assert jesd.clock_names == ["s_axi_aclk", "device_clk", "lane_clk"]


def test_parser_only_returns_clock_related_nodes():
    dts = """\
/dts-v1/;
/ {
\tsome_node: node@1000 {
\t\tcompatible = "irrelevant";
\t\tstatus = "okay";
\t};
\tclock_node: axi-clkgen@2000 {
\t\tclock-output-names = "out0";
\t};
};
"""
    nodes = _DtsParser().parse(dts)
    labels = {n.label for n in nodes}
    assert "clock_node" in labels
    assert "some_node" not in labels


def test_parser_handles_multi_provider_xcvr():
    nodes = _DtsParser().parse(_HMC7044_DTS)
    xcvr = next(n for n in nodes if n.label == "axi_xcvr_rx")
    assert ("hmc7044_fmc", 5) in xcvr.clocks
    assert ("hmc7044_fmc", 9) in xcvr.clocks
    assert xcvr.clock_names == ["conv", "div40"]
    assert xcvr.clock_output_names == ["rx_gt_clk", "rx_out_clk"]


# ---------------------------------------------------------------------------
# _DotRenderer tests
# ---------------------------------------------------------------------------


def test_dot_renderer_produces_digraph():
    nodes = _DtsParser().parse(_SIMPLE_DTS)
    dot = _DotRenderer().render(nodes, "test")
    assert dot.startswith("digraph clock_topology")
    assert "}" in dot


def test_dot_renderer_declares_all_provider_nodes():
    nodes = _DtsParser().parse(_SIMPLE_DTS)
    dot = _DotRenderer().render(nodes, "test")
    # zynqmp_clk is external (not defined in DTS) but referenced
    assert "zynqmp_clk" in dot
    assert "axi_clkgen_0" in dot
    assert "axi_jesd_rx" in dot


def test_dot_renderer_emits_clock_edges():
    nodes = _DtsParser().parse(_SIMPLE_DTS)
    dot = _DotRenderer().render(nodes, "test")
    assert "zynqmp_clk -> axi_jesd_rx" in dot
    assert "axi_clkgen_0 -> axi_jesd_rx" in dot


def test_dot_renderer_labels_edges_with_clock_name():
    nodes = _DtsParser().parse(_SIMPLE_DTS)
    dot = _DotRenderer().render(nodes, "test")
    assert "device_clk" in dot
    assert "lane_clk" in dot
    assert "s_axi_aclk" in dot


def test_dot_renderer_uses_dashed_style_for_s_axi_aclk():
    nodes = _DtsParser().parse(_SIMPLE_DTS)
    dot = _DotRenderer().render(nodes, "test")
    # The s_axi_aclk edge should use dashed style
    assert "style=dashed" in dot


# ---------------------------------------------------------------------------
# ClockGraphGenerator integration tests
# ---------------------------------------------------------------------------


def test_generator_writes_dot_file(tmp_path):
    result = ClockGraphGenerator().generate(_SIMPLE_DTS, tmp_path, "testboard")
    assert "clock_dot" in result
    assert result["clock_dot"].exists()
    assert result["clock_dot"].suffix == ".dot"


def test_generator_dot_file_has_correct_name(tmp_path):
    result = ClockGraphGenerator().generate(_SIMPLE_DTS, tmp_path, "my_board")
    assert result["clock_dot"].name == "my_board_clocks.dot"


def test_generator_dot_content_is_valid(tmp_path):
    result = ClockGraphGenerator().generate(_HMC7044_DTS, tmp_path, "hmc_test")
    dot_text = result["clock_dot"].read_text()
    assert "digraph clock_topology" in dot_text
    assert "hmc7044_fmc" in dot_text
    assert "axi_xcvr_rx" in dot_text
    assert "axi_jesd_rx" in dot_text


def test_generator_sanitises_name_with_special_chars(tmp_path):
    result = ClockGraphGenerator().generate(_SIMPLE_DTS, tmp_path, "board/v1.2")
    # safe_name replaces /. with _
    assert result["clock_dot"].exists()
    assert "/" not in result["clock_dot"].name


def test_generator_returns_svg_path_when_dot_available(tmp_path):
    import shutil

    if shutil.which("dot") is None:
        pytest.skip("Graphviz 'dot' not available")
    result = ClockGraphGenerator().generate(_HMC7044_DTS, tmp_path, "svg_test")
    assert "clock_svg" in result
    assert result["clock_svg"].exists()
    assert result["clock_svg"].suffix == ".svg"


def test_generator_no_svg_key_when_dot_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr("adidt.xsa.clock_graph.shutil.which", lambda _: None)
    result = ClockGraphGenerator().generate(_SIMPLE_DTS, tmp_path, "nodot")
    assert "clock_svg" not in result
    assert "clock_dot" in result
