# test/xsa/test_node_builder_templates.py
from types import SimpleNamespace

from adidt.xsa.node_builder import NodeBuilder


def test_render_existing_template_returns_string():
    """_render loads an existing template and returns a non-empty string."""
    nb = NodeBuilder()
    # clkgen.tmpl needs instance.name, instance.base_addr, ps_clk_label, ps_clk_index
    ctx = {
        "instance": SimpleNamespace(name="test_clkgen", base_addr=0x43C00000),
        "ps_clk_label": "zynqmp_clk",
        "ps_clk_index": 71,
    }
    result = nb._render("clkgen.tmpl", ctx)
    assert isinstance(result, str)
    assert "test_clkgen" in result


def test_wrap_spi_bus_produces_overlay():
    nb = NodeBuilder()
    result = nb._wrap_spi_bus("spi0", "\t\tchild_node;\n")
    assert "\t&spi0 {" in result
    assert 'status = "okay";' in result
    assert "\t\tchild_node;" in result
    assert "\t};" in result
