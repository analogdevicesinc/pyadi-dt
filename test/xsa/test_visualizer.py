# test/xsa/test_visualizer.py
import pytest
from adidt.xsa.parse.topology import (
    XsaTopology,
    Jesd204Instance,
    ClkgenInstance,
    ConverterInstance,
)
from adidt.xsa.viz.visualizer import HtmlVisualizer


@pytest.fixture
def topo():
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_jesd204_rx_0",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=54,
                link_clk="jesd_rx_device_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_jesd204_tx_0",
                base_addr=0x44B90000,
                num_lanes=4,
                irq=55,
                link_clk="jesd_tx_device_clk",
                direction="tx",
            )
        ],
        clkgens=[
            ClkgenInstance(
                name="axi_clkgen_0",
                base_addr=0x43C00000,
                output_clks=["jesd_rx_device_clk"],
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9081_0",
                ip_type="axi_ad9081",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
        fpga_part="xczu9eg-ffvb1156-2",
    )


@pytest.fixture
def cfg():
    return {
        "clock": {"hmc7044_rx_channel": 10, "hmc7044_tx_channel": 6},
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 8, "L": 4, "Np": 16},
            "tx": {"F": 4, "K": 32, "M": 8, "L": 4, "Np": 16},
        },
    }


@pytest.fixture
def merged_dts():
    return (
        "/dts-v1/;\n/ {\n\tamba: axi {\n"
        "\t\taxi_jesd204_rx_0: axi-jesd204-rx@44a90000 "
        '{ compatible = "adi,axi-jesd204-rx-1.0"; };\n'
        "\t};\n};\n"
    )


def test_generate_returns_html_string(topo, cfg, merged_dts, tmp_path):
    html = HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "test")
    assert isinstance(html, str)
    assert "<html" in html


def test_html_is_self_contained_no_external_urls(topo, cfg, merged_dts, tmp_path):
    html = HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "test")
    assert "cdn.jsdelivr.net" not in html
    assert "unpkg.com" not in html


def test_html_contains_node_names(topo, cfg, merged_dts, tmp_path):
    html = HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "test")
    assert "axi_jesd204_rx_0" in html
    assert "axi_ad9081_0" in html


def test_html_file_written(topo, cfg, merged_dts, tmp_path):
    HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "myboard")
    assert (tmp_path / "myboard_report.html").exists()


def test_missing_d3_bundle_raises(topo, cfg, merged_dts, tmp_path, monkeypatch):
    import adidt.xsa.viz.visualizer as vis_mod

    monkeypatch.setattr(vis_mod, "_D3_BUNDLE", "")
    with pytest.raises(RuntimeError, match="D3 bundle missing"):
        HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "fail")


def test_title_with_html_chars_is_escaped(topo, cfg, merged_dts, tmp_path):
    html_output = HtmlVisualizer().generate(
        topo, cfg, merged_dts, tmp_path, "</title><script>alert(1)</script>"
    )
    assert "<script>alert(1)</script>" not in html_output
    assert "&lt;/title&gt;" in html_output or "&lt;" in html_output


def test_node_name_closing_script_tag_is_safe(topo, cfg, tmp_path):
    # Build a topology where a converter name contains </script>
    from adidt.xsa.parse.topology import ConverterInstance, XsaTopology

    topo_injected = XsaTopology(
        converters=[
            ConverterInstance(
                name="</script><script>alert(1)</script>",
                ip_type="axi_ad9081",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            )
        ]
    )
    cfg_simple = {"clock": {}, "jesd": {}}
    merged_dts_simple = "/dts-v1/;\n/ {};\n"
    html_output = HtmlVisualizer().generate(
        topo_injected, cfg_simple, merged_dts_simple, tmp_path, "safe"
    )
    # The </script> sequence should be escaped in the JSON data
    assert "<script>alert(1)</script>" not in html_output


def test_html_contains_xsa_match_coverage_summary(topo, cfg, merged_dts, tmp_path):
    html = HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "test")
    assert "XSA Match Coverage" in html
    assert "coverage-summary" in html
    assert "jesd204_tx_0" in html


def test_html_contains_expandable_detail_sections(topo, cfg, merged_dts, tmp_path):
    html = HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "test")
    assert '<details id="detail-coverage"' in html
    assert '<details id="detail-topology"' in html
    assert '<details id="detail-clocks"' in html
    assert '<details id="detail-jesd"' in html
    assert "Parsed Topology" in html
    assert "Clock References" in html
    assert "JESD Paths" in html


def test_html_contains_wiring_panel(topo, cfg, merged_dts, tmp_path):
    html = HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "test")
    assert "Control-Plane Wiring" in html
    assert '<svg id="wiring-svg">' in html
    # Five kind-toggle checkboxes.
    for kind in ("spi", "jesd", "gpio", "irq", "i2c"):
        assert f'data-kind="{kind}"' in html


def test_html_contains_wiring_data_object(topo, cfg, merged_dts, tmp_path):
    html = HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "test")
    assert "const wiringData=" in html
    # The fixture has JESD instances with IRQ values, so the wiring graph
    # should contain at least IRQ edges.
    assert '"kind": "irq"' in html or '"kind":"irq"' in html
    assert '"kind": "jesd"' in html or '"kind":"jesd"' in html
