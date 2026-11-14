"""Tests for carrier-platform detection and the shared platform table."""

import io
import zipfile

import pytest

from adidt.xsa.build.node_builder import NodeBuilder
from adidt.xsa.parse.topology import XsaParser, XsaTopology
from adidt.xsa.platforms import PLATFORMS, detect_platform, platform_info


@pytest.mark.parametrize(
    "part, board, expected",
    [
        ("xczu9eg-ffvb1156-2", "xilinx.com:zcu102:part0:3.4", "zcu102"),
        ("xczu9eg_ffvb1156_-2", "", "zcu102"),
        ("xczu11eg-ffvf1517-2", "", "zu11eg"),
        ("xilinx,xcvp1202,revA", "", "vpk180"),
        ("7z045-ffg900-2", "xilinx.com:zc706:part0:1.4", "zc706"),
        ("7z045-ffg900-2", "", "zc706"),
        # ZedBoard and ZC702 share the xc7z020clg484 part; only the board
        # file tells them apart, and the ADI ZedBoard design has none.
        ("7z020-clg484-1", "", "zed"),
        ("7z020-clg484-1", "xilinx.com:zc702:part0:1.4", "zc702"),
        ("7z020-clg400-1", "", "adrv9364z7020"),
        ("7z035i-fbg676-2L", "", "adrv9361z7035"),
        ("7z007s-clg400-1", "", "coraz7s"),
        ("xcvc1902-vsva2197-2MP-e-S", "", "vck190"),
        ("xcvu9p-flga2104-2L-e", "", "vcu118"),
        ("xcku040-ffva1156-2-e", "", "kcu105"),
        ("xck26-sfvc784-2LV-c", "xilinx.com:kv260_som:part0:1.4", "kv260"),
        ("xc7s50", "", "unknown"),
    ],
)
def test_detect_platform(part, board, expected):
    assert detect_platform(part, board) == expected


def test_every_detectable_platform_has_constants():
    from adidt.xsa import platforms

    names = {p for _, p in platforms._BOARD_TO_PLATFORM}
    names |= {p for _, _, p in platforms._PART_TO_PLATFORM}
    assert names <= set(PLATFORMS)


@pytest.mark.parametrize(
    "name, addr_cells, clk, index, gpio",
    [
        ("zc706", 1, "clkc", 15, "gpio0"),
        ("zed", 1, "clkc", 15, "gpio0"),
        ("zcu102", 2, "zynqmp_clk", 71, "gpio"),
        ("zu11eg", 2, "zynqmp_clk", 71, "gpio"),
        ("vpk180", 2, "versal_clk", 65, "gpio"),
        ("vcu118", 1, "clk_bus_0", None, "axi_gpio"),
        ("kcu105", 1, "clk_bus_0", None, "axi_gpio"),
        # Unknown platforms keep the pipeline's ZynqMP defaults.
        ("unknown", 2, "zynqmp_clk", 71, "gpio"),
    ],
)
def test_platform_constants(name, addr_cells, clk, index, gpio):
    info = platform_info(name)
    assert (info.addr_cells, info.ps_clk_label, info.ps_clk_index, info.gpio_label) == (
        addr_cells,
        clk,
        index,
        gpio,
    )


def test_node_builder_ps_labels_come_from_the_platform_table():
    topology = XsaTopology(fpga_part="7z020-clg484-1")
    assert NodeBuilder._platform_ps_labels(topology) == ("clkc", 15, "gpio0")


def _xsa_with_sysinfo(tmp_path, attrs: str):
    hwh = f"""<?xml version="1.0" encoding="UTF-8"?>
<EDKSYSTEM>
  <SYSTEMINFO {attrs} NAME="system"/>
  <MODULES>
    <MODULE INSTANCE="axi_ad9680_core" MODTYPE="axi_ad9680">
      <MEMRANGE BASEVALUE="0x44A10000" />
    </MODULE>
  </MODULES>
</EDKSYSTEM>
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("system.hwh", hwh)
    xsa = tmp_path / "system_top.xsa"
    xsa.write_bytes(buf.getvalue())
    return xsa


def test_parser_uses_board_file_to_tell_zc702_from_zedboard(tmp_path):
    part = 'ARCH="zynq" DEVICE="7z020" PACKAGE="clg484" SPEEDGRADE="-1"'

    zed = XsaParser().parse(_xsa_with_sysinfo(tmp_path, part))
    assert zed.board == ""
    assert zed.inferred_platform() == "zed"

    zc702 = XsaParser().parse(
        _xsa_with_sysinfo(tmp_path, f'{part} BOARD="xilinx.com:zc702:part0:1.4"')
    )
    assert zc702.board == "xilinx.com:zc702:part0:1.4"
    assert zc702.inferred_platform() == "zc702"
