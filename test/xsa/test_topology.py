# test/xsa/test_topology.py
import io
import warnings
import zipfile
import pytest
from pathlib import Path
from adidt.xsa.topology import (
    Jesd204Instance,
    ClkgenInstance,
    ConverterInstance,
    XsaTopology,
    XsaParser,
)
from adidt.xsa.exceptions import XsaParseError


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
    assert topo.signal_connections == []
    assert topo.fpga_part == ""


def test_xsa_topology_detects_fmcdaq2_from_converter_types():
    topo = XsaTopology(
        converters=[
            ConverterInstance(
                name="axi_ad9680_0",
                ip_type="axi_ad9680",
                base_addr=0x44A10000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_ad9144_0",
                ip_type="axi_ad9144",
                base_addr=0x44A20000,
                spi_bus=None,
                spi_cs=None,
            ),
        ]
    )
    assert topo.is_fmcdaq2_design()


def test_xsa_topology_detects_fmcdaq2_from_jesd_names_only():
    topo = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9680_jesd_rx_axi",
                base_addr=0x84AA0000,
                num_lanes=4,
                irq=None,
                link_clk="rx_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9144_jesd_tx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=None,
                link_clk="tx_clk",
                direction="tx",
            )
        ],
    )
    assert topo.is_fmcdaq2_design()


def test_xsa_topology_infers_converter_family_from_jesd_names():
    topo = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=None,
                link_clk="rx_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=4,
                irq=None,
                link_clk="tx_clk",
                direction="tx",
            )
        ],
    )
    assert topo.inferred_converter_family() == "ad9081"


def test_xsa_topology_infers_ad9084_family_from_jesd_names():
    topo = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9084_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=8,
                irq=None,
                link_clk="rx_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9084_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=8,
                irq=None,
                link_clk="tx_clk",
                direction="tx",
            )
        ],
    )
    assert topo.inferred_converter_family() == "ad9084"


def test_xsa_topology_prefers_known_converter_family_when_first_is_unknown():
    topo = XsaTopology(
        converters=[
            ConverterInstance(
                name="axi_unknown_0",
                ip_type="axi_unknown_chip",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_adrv9009_0",
                ip_type="axi_adrv9009",
                base_addr=0x44A10000,
                spi_bus=None,
                spi_cs=None,
            ),
        ]
    )
    assert topo.inferred_converter_family() == "adrv9009"


def test_xsa_topology_infers_adrv9025_family_from_adrv9026_jesd_names():
    topo = XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9026_rx_jesd_rx_axi",
                base_addr=0x84AA0000,
                num_lanes=4,
                irq=None,
                link_clk="rx_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9026_tx_jesd_tx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=None,
                link_clk="tx_clk",
                direction="tx",
            )
        ],
    )
    assert topo.inferred_converter_family() == "adrv9025"


def test_xsa_topology_infers_platform_from_part_prefix():
    topo = XsaTopology(fpga_part="xczu9eg_ffvb1156_-2")
    assert topo.inferred_platform() == "zcu102"


def test_xsa_topology_infers_platform_from_part_substring():
    topo = XsaTopology(fpga_part="xilinx,xcvp1202,revA")
    assert topo.inferred_platform() == "vpk180"


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


def test_parser_detects_ad9680_converter_type(tmp_path):
    xsa = tmp_path / "ad9680_only.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER><DEVICE Name="xc7z045" Package="ffg900" SpeedGrade="-2"/></HEADER>
  <MODULES>
    <MODULE MODTYPE="axi_ad9680" INSTANCE="axi_ad9680_0">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x44A10000" HIGHVALUE="0x44A1FFFF"/></MEMORYMAP>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    topo = XsaParser().parse(xsa)
    assert len(topo.converters) == 1
    assert topo.converters[0].ip_type == "axi_ad9680"


def test_parser_does_not_infer_ad9081_from_non_mxfe_tpl_blocks(tmp_path):
    xsa = tmp_path / "daq2_tpl_only.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER><DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/></HEADER>
  <MODULES>
    <MODULE MODTYPE="ad_ip_jesd204_tpl_adc" INSTANCE="ad9680_tpl_core_adc_tpl_core">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84A10000" HIGHVALUE="0x84A11FFF"/></MEMORYMAP>
    </MODULE>
    <MODULE MODTYPE="ad_ip_jesd204_tpl_dac" INSTANCE="ad9144_tpl_core_dac_tpl_core">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84A20000" HIGHVALUE="0x84A21FFF"/></MEMORYMAP>
    </MODULE>
    <MODULE MODTYPE="axi_jesd204_rx" INSTANCE="axi_ad9680_jesd_rx_axi">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84AA0000" HIGHVALUE="0x84AA3FFF"/></MEMORYMAP>
      <PARAMETERS><PARAMETER NAME="NUM_LANES" VALUE="4"/></PARAMETERS>
      <PORTS><PORT NAME="core_clk" SIGNAME="rx_clk"/></PORTS>
    </MODULE>
    <MODULE MODTYPE="axi_jesd204_tx" INSTANCE="axi_ad9144_jesd_tx_axi">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84A90000" HIGHVALUE="0x84A93FFF"/></MEMORYMAP>
      <PARAMETERS><PARAMETER NAME="NUM_LANES" VALUE="4"/></PARAMETERS>
      <PORTS><PORT NAME="core_clk" SIGNAME="tx_clk"/></PORTS>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    topo = XsaParser().parse(xsa)
    assert topo.converters == []
    assert len(topo.jesd204_rx) == 1
    assert len(topo.jesd204_tx) == 1


def test_parser_extracts_signal_connection_graph(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(_make_xsa_bytes(FIXTURE_HWH))
    topo = XsaParser().parse(xsa)

    by_signal = {c.signal: c for c in topo.signal_connections}
    assert "jesd_rx_device_clk" in by_signal
    assert "jesd_tx_device_clk" in by_signal

    rx_clk = by_signal["jesd_rx_device_clk"]
    assert "axi_clkgen_0" in rx_clk.producers
    assert "axi_jesd204_rx_0" in rx_clk.consumers

    tx_clk = by_signal["jesd_tx_device_clk"]
    assert "axi_clkgen_0" in tx_clk.producers
    assert "axi_jesd204_tx_0" in tx_clk.consumers


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


def test_parser_uses_global_memrange_when_module_memrange_is_zero(tmp_path):
    xsa = tmp_path / "global_memmap.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER>
    <DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/>
  </HEADER>
  <MODULES>
    <MODULE MODTYPE="axi_jesd204_rx" INSTANCE="axi_adrv9009_rx_jesd_rx_axi">
      <MEMORYMAP>
        <MEMRANGE BASEVALUE="0x00000000" HIGHVALUE="0x00003FFF"/>
      </MEMORYMAP>
      <PORTS>
        <PORT NAME="device_clk" SIGNAME="rx_clk"/>
      </PORTS>
      <PARAMETERS>
        <PARAMETER NAME="C_NUM_LANES" VALUE="4"/>
      </PARAMETERS>
    </MODULE>
  </MODULES>
  <MEMORYMAP>
    <MEMRANGE INSTANCE="axi_adrv9009_rx_jesd_rx_axi" BASEVALUE="0x84AA0000" HIGHVALUE="0x84AA3FFF"/>
  </MEMORYMAP>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    topo = XsaParser().parse(xsa)
    assert len(topo.jesd204_rx) == 1
    assert topo.jesd204_rx[0].base_addr == 0x84AA0000


def test_parser_uses_num_lanes_and_core_clk_fallback(tmp_path):
    xsa = tmp_path / "num_lanes_core_clk.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER>
    <DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/>
  </HEADER>
  <MODULES>
    <MODULE MODTYPE="axi_clkgen" INSTANCE="axi_clkgen_0">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x43C00000" HIGHVALUE="0x43C0FFFF"/></MEMORYMAP>
      <PORTS>
        <PORT DIR="O" NAME="clk_0" SIGIS="clk" SIGNAME="rx_clk_net"/>
      </PORTS>
    </MODULE>
    <MODULE MODTYPE="axi_jesd204_rx" INSTANCE="axi_rx_0">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84AA0000" HIGHVALUE="0x84AA3FFF"/></MEMORYMAP>
      <PARAMETERS>
        <PARAMETER NAME="NUM_LANES" VALUE="2"/>
      </PARAMETERS>
      <PORTS>
        <PORT NAME="core_clk" SIGNAME="rx_clk_net"/>
      </PORTS>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    topo = XsaParser().parse(xsa)
    assert len(topo.clkgens) == 1
    assert topo.clkgens[0].output_clks == ["rx_clk_net"]
    assert len(topo.jesd204_rx) == 1
    assert topo.jesd204_rx[0].num_lanes == 2
    assert topo.jesd204_rx[0].link_clk == "rx_clk_net"


def test_parser_reads_part_from_systeminfo_attributes(tmp_path):
    xsa = tmp_path / "systeminfo_part.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKSYSTEM>
  <SYSTEMINFO DEVICE="xczu9eg" PACKAGE="ffvb1156" SPEEDGRADE="-2"/>
  <MODULES>
    <MODULE MODTYPE="axi_jesd204_rx" INSTANCE="axi_rx_0">
      <PARAMETERS>
        <PARAMETER NAME="C_BASEADDR" VALUE="0x84AA0000"/>
        <PARAMETER NAME="NUM_LANES" VALUE="4"/>
      </PARAMETERS>
      <PORTS>
        <PORT NAME="device_clk" SIGNAME="rx_clk"/>
      </PORTS>
    </MODULE>
  </MODULES>
</EDKSYSTEM>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    topo = XsaParser().parse(xsa)
    assert topo.fpga_part == "xczu9eg-ffvb1156-2"


def test_parser_uses_c_baseaddr_when_memrange_missing(tmp_path):
    xsa = tmp_path / "c_baseaddr_only.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER>
    <DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/>
  </HEADER>
  <MODULES>
    <MODULE MODTYPE="axi_jesd204_tx" INSTANCE="axi_tx_0">
      <PARAMETERS>
        <PARAMETER NAME="C_BASEADDR" VALUE="0x84B90000"/>
        <PARAMETER NAME="NUM_LANES" VALUE="4"/>
      </PARAMETERS>
      <PORTS>
        <PORT NAME="device_clk" SIGNAME="tx_clk"/>
      </PORTS>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    topo = XsaParser().parse(xsa)
    assert len(topo.jesd204_tx) == 1
    assert topo.jesd204_tx[0].base_addr == 0x84B90000


def test_parser_infers_ad9081_converter_from_tpl_blocks(tmp_path):
    xsa = tmp_path / "infer_ad9081.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER>
    <DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/>
  </HEADER>
  <MODULES>
    <MODULE MODTYPE="ad_ip_jesd204_tpl_adc" INSTANCE="rx_mxfe_tpl_core_adc_tpl_core">
      <PARAMETERS>
        <PARAMETER NAME="C_BASEADDR" VALUE="0x84A10000"/>
      </PARAMETERS>
    </MODULE>
    <MODULE MODTYPE="ad_ip_jesd204_tpl_dac" INSTANCE="tx_mxfe_tpl_core_dac_tpl_core">
      <PARAMETERS>
        <PARAMETER NAME="C_BASEADDR" VALUE="0x84B10000"/>
      </PARAMETERS>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    topo = XsaParser().parse(xsa)
    assert len(topo.converters) == 1
    assert topo.converters[0].ip_type == "axi_ad9081"
    assert topo.converters[0].base_addr == 0x84A10000
