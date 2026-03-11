# test/xsa/test_topology.py
from adidt.xsa.topology import (
    Jesd204Instance,
    ClkgenInstance,
    ConverterInstance,
    XsaTopology,
)


def test_jesd204_instance_creation():
    inst = Jesd204Instance(
        name="axi_jesd204_rx_0",
        base_addr=0x44A90000,
        num_lanes=4,
        irq=54,
        link_clk="device_clk_net",
        direction="rx",
    )
    assert inst.name == "axi_jesd204_rx_0"
    assert inst.direction == "rx"
    assert inst.irq == 54


def test_clkgen_instance_has_output_clks():
    inst = ClkgenInstance(
        name="axi_clkgen_0",
        base_addr=0x43C00000,
        output_clks=["clk_out1", "clk_out2"],
    )
    assert len(inst.output_clks) == 2


def test_converter_instance_optional_spi():
    inst = ConverterInstance(
        name="axi_ad9081_0",
        ip_type="axi_ad9081",
        base_addr=0x44A00000,
        spi_bus=None,
        spi_cs=None,
    )
    assert inst.spi_bus is None


def test_xsa_topology_defaults_to_empty():
    topo = XsaTopology()
    assert topo.jesd204_rx == []
    assert topo.jesd204_tx == []
    assert topo.clkgens == []
    assert topo.converters == []
    assert topo.fpga_part == ""


import io
import warnings
import zipfile
import pytest
from pathlib import Path
from adidt.xsa.topology import XsaParser
from adidt.xsa.exceptions import XsaParseError

FIXTURE_HWH = Path(__file__).parent / "fixtures" / "ad9081_zcu102.hwh"


def _make_xsa_bytes(hwh_path: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.write(hwh_path, "design.hwh")
    return buf.getvalue()


def test_parser_detects_fpga_part(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(_make_xsa_bytes(FIXTURE_HWH))
    topo = XsaParser().parse(xsa)
    assert "xczu9eg" in topo.fpga_part
    assert "ffvb1156" in topo.fpga_part


def test_parser_detects_jesd204_rx(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(_make_xsa_bytes(FIXTURE_HWH))
    topo = XsaParser().parse(xsa)
    assert len(topo.jesd204_rx) == 1
    rx = topo.jesd204_rx[0]
    assert rx.name == "axi_jesd204_rx_0"
    assert rx.base_addr == 0x44A90000
    assert rx.num_lanes == 4
    assert rx.direction == "rx"
    assert rx.link_clk == "jesd_rx_device_clk"
    assert rx.irq == 54


def test_parser_detects_jesd204_tx(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(_make_xsa_bytes(FIXTURE_HWH))
    topo = XsaParser().parse(xsa)
    assert len(topo.jesd204_tx) == 1
    tx = topo.jesd204_tx[0]
    assert tx.direction == "tx"
    assert tx.base_addr == 0x44B90000
    assert tx.num_lanes == 4
    assert tx.link_clk == "jesd_tx_device_clk"
    assert tx.irq == 55


def test_parser_detects_clkgen_with_outputs(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(_make_xsa_bytes(FIXTURE_HWH))
    topo = XsaParser().parse(xsa)
    assert len(topo.clkgens) == 1
    cg = topo.clkgens[0]
    assert cg.base_addr == 0x43C00000
    assert "jesd_rx_device_clk" in cg.output_clks
    assert "jesd_tx_device_clk" in cg.output_clks


def test_parser_detects_converter(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(_make_xsa_bytes(FIXTURE_HWH))
    topo = XsaParser().parse(xsa)
    assert len(topo.converters) == 1
    conv = topo.converters[0]
    assert conv.ip_type == "axi_ad9081"
    assert conv.base_addr == 0x44A00000
    assert conv.spi_bus is None
    assert conv.spi_cs is None


def test_parser_raises_on_missing_hwh(tmp_path):
    xsa = tmp_path / "empty.xsa"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    xsa.write_bytes(buf.getvalue())
    with pytest.raises(XsaParseError, match="no hardware handoff"):
        XsaParser().parse(xsa)


def test_parser_warns_when_no_adi_ips(tmp_path):
    xsa = tmp_path / "no_adi.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER><DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/></HEADER>
  <MODULES>
    <MODULE MODTYPE="axi_gpio" INSTANCE="axi_gpio_0">
      <MEMRANGES><MEMRANGE BASEVALUE="0x41200000" HIGHVALUE="0x4120FFFF"/></MEMRANGES>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        topo = XsaParser().parse(xsa)
    assert topo.jesd204_rx == []
    assert any("no recognized ADI" in str(warning.message) for warning in w)
