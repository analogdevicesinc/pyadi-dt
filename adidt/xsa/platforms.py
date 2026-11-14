"""Carrier platforms the XSA pipeline recognises, and how to detect them.

One table answers the per-platform questions the pipeline keeps asking:
which carrier an XSA was built for, how many address cells its bus uses,
and which processor-side clock and GPIO controller labels the base device
tree provides.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class XsaPlatform:
    """Processor-side constants of a carrier platform."""

    name: str
    arch: str  # "arm", "arm64" or "microblaze"
    addr_cells: int
    ps_clk_label: str
    ps_clk_index: int | None
    gpio_label: str


def _zynq(name: str) -> XsaPlatform:
    return XsaPlatform(name, "arm", 1, "clkc", 15, "gpio0")


def _zynqmp(name: str) -> XsaPlatform:
    return XsaPlatform(name, "arm64", 2, "zynqmp_clk", 71, "gpio")


def _versal(name: str) -> XsaPlatform:
    return XsaPlatform(name, "arm64", 2, "versal_clk", 65, "gpio")


def _microblaze(name: str) -> XsaPlatform:
    # ADI MicroBlaze designs clock the AXI bus from a fixed-clock with
    # #clock-cells = <0>, so there is no clock index.
    return XsaPlatform(name, "microblaze", 1, "clk_bus_0", None, "axi_gpio")


PLATFORMS: dict[str, XsaPlatform] = {
    p.name: p
    for p in (
        _zynq("zed"),
        _zynq("zc702"),
        _zynq("zc706"),
        _zynq("coraz7s"),
        _zynq("adrv9361z7035"),
        _zynq("adrv9364z7020"),
        _zynqmp("zcu102"),
        _zynqmp("zcu104"),
        _zynqmp("zu11eg"),
        _zynqmp("kv260"),
        _versal("vck190"),
        _versal("vmk180"),
        _versal("vpk180"),
        _microblaze("ac701"),
        _microblaze("kc705"),
        _microblaze("kcu105"),
        _microblaze("vc707"),
        _microblaze("vc709"),
        _microblaze("vcu118"),
        _microblaze("vcu128"),
    )
}

# Used for platforms the table does not know, matching the pipeline's
# long-standing ZynqMP default.
_FALLBACK = _zynqmp("unknown")

# Vivado board-file names (second field of the HWH ``BOARD`` attribute, e.g.
# ``xilinx.com:zc702:part0:1.4``) -> platform.  Matched by prefix so board
# revisions such as ``kv260_som`` resolve too.
_BOARD_TO_PLATFORM: tuple[tuple[str, str], ...] = (
    ("zc702", "zc702"),
    ("zc706", "zc706"),
    ("zed", "zed"),
    ("zcu102", "zcu102"),
    ("zcu104", "zcu104"),
    ("kv260", "kv260"),
    ("vck190", "vck190"),
    ("vmk180", "vmk180"),
    ("vpk180", "vpk180"),
    ("ac701", "ac701"),
    ("kc705", "kc705"),
    ("kcu105", "kcu105"),
    ("vc707", "vc707"),
    ("vc709", "vc709"),
    ("vcu118", "vcu118"),
    ("vcu128", "vcu128"),
)

# (device substring, package substring or None, platform).  Order matters:
# package-specific rows come before the catch-all for the same device.  The
# ADI ZedBoard project does not use a board file, so a bare 7z020 in the
# clg484 package is the ZedBoard; ZC702 designs carry ``BOARD`` and are
# resolved from it first.
_PART_TO_PLATFORM: tuple[tuple[str, str | None, str], ...] = (
    ("7z045", None, "zc706"),
    ("7z035", None, "adrv9361z7035"),
    ("7z020", "clg400", "adrv9364z7020"),
    ("7z020", None, "zed"),
    ("7z007s", None, "coraz7s"),
    ("zu9eg", None, "zcu102"),
    ("zu11eg", None, "zu11eg"),
    ("zu3eg", None, "zcu104"),
    ("xck26", None, "kv260"),
    ("vp1202", None, "vpk180"),
    ("vc1902", None, "vck190"),
    ("vm1802", None, "vmk180"),
    ("vu9p", None, "vcu118"),
    ("vu37p", None, "vcu128"),
    ("ku040", None, "kcu105"),
    ("7k325t", None, "kc705"),
    ("7vx485t", None, "vc707"),
    ("7vx690t", None, "vc709"),
    ("7a200t", None, "ac701"),
)


def detect_platform(fpga_part: str, board: str = "") -> str:
    """Return the platform name for an FPGA part string and optional board file.

    Args:
        fpga_part: Part string in any of the spellings Vivado exports
            (``xczu9eg-ffvb1156-2``, ``7z045-ffg900-2``, ``xilinx,xcvp1202,revA``).
        board: The HWH ``BOARD`` attribute (``vendor:name:part:version``) or
            just its name field.  Empty when the design uses no board file.

    Returns:
        A key of :data:`PLATFORMS`, or ``"unknown"``.
    """
    board_name = board.lower()
    if ":" in board_name:
        board_name = board_name.split(":")[1]
    if board_name:
        for prefix, platform in _BOARD_TO_PLATFORM:
            if board_name.startswith(prefix):
                return platform

    part = fpga_part.lower()
    for device, package, platform in _PART_TO_PLATFORM:
        if device in part and (package is None or package in part):
            return platform
    return "unknown"


def platform_info(name: str) -> XsaPlatform:
    """Return the constants for platform *name* (ZynqMP defaults if unknown)."""
    return PLATFORMS.get(name, _FALLBACK)
