# adidt/xsa/topology.py
import re
import warnings
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .exceptions import XsaParseError


@dataclass
class Jesd204Instance:
    name: str
    base_addr: int
    num_lanes: int
    irq: Optional[int]
    link_clk: str
    direction: str  # "rx" or "tx"


@dataclass
class ClkgenInstance:
    name: str
    base_addr: int
    output_clks: list[str] = field(default_factory=list)


@dataclass
class ConverterInstance:
    name: str
    ip_type: str
    base_addr: int
    spi_bus: Optional[int]
    spi_cs: Optional[int]


@dataclass
class XsaTopology:
    jesd204_rx: list[Jesd204Instance] = field(default_factory=list)
    jesd204_tx: list[Jesd204Instance] = field(default_factory=list)
    clkgens: list[ClkgenInstance] = field(default_factory=list)
    converters: list[ConverterInstance] = field(default_factory=list)
    fpga_part: str = ""


_ADI_JESD_RX_TYPES = {"axi_jesd204_rx"}
_ADI_JESD_TX_TYPES = {"axi_jesd204_tx"}
_ADI_CLKGEN_TYPES = {"axi_clkgen"}
_ADI_CONVERTER_TYPES = {"axi_ad9081", "axi_ad9084", "axi_ad9162", "axi_ad9144"}


class XsaParser:
    """Parses a Vivado .xsa file and returns an XsaTopology."""

    def parse(self, xsa_path: Path) -> XsaTopology:
        hwh_content = self._extract_hwh(xsa_path)
        root = ET.fromstring(hwh_content)
        topology = XsaTopology()
        topology.fpga_part = self._parse_part(root)

        found_adi = False
        for mod in root.findall(".//MODULE"):
            mod_type = mod.get("MODTYPE", "").lower()
            instance = mod.get("INSTANCE", mod_type)
            base_addr = self._parse_base_addr(mod)

            if mod_type in _ADI_JESD_RX_TYPES:
                found_adi = True
                topology.jesd204_rx.append(self._parse_jesd(mod, instance, base_addr, "rx"))
            elif mod_type in _ADI_JESD_TX_TYPES:
                found_adi = True
                topology.jesd204_tx.append(self._parse_jesd(mod, instance, base_addr, "tx"))
            elif mod_type in _ADI_CLKGEN_TYPES:
                found_adi = True
                topology.clkgens.append(self._parse_clkgen(mod, instance, base_addr))
            elif mod_type in _ADI_CONVERTER_TYPES:
                found_adi = True
                topology.converters.append(
                    self._parse_converter(mod, instance, mod_type, base_addr)
                )

        if not found_adi:
            warnings.warn(
                f"no recognized ADI IPs found in {xsa_path.name}; "
                "pipeline will produce base DTS only",
                UserWarning,
                stacklevel=2,
            )

        return topology

    def _extract_hwh(self, xsa_path: Path) -> str:
        try:
            with zipfile.ZipFile(xsa_path) as zf:
                hwh_names = [n for n in zf.namelist() if n.endswith(".hwh")]
                if not hwh_names:
                    raise XsaParseError(
                        f"no hardware handoff (.hwh) file found in {xsa_path.name}"
                    )
                raw_bytes = zf.read(hwh_names[0])
                try:
                    return raw_bytes.decode("utf-8")
                except UnicodeDecodeError as e:
                    raise XsaParseError(
                        f"cannot decode {hwh_names[0]} as UTF-8: {e}"
                    )
        except zipfile.BadZipFile as e:
            raise XsaParseError(f"cannot open {xsa_path.name} as a zip archive: {e}")

    def _parse_part(self, root: ET.Element) -> str:
        """Return dash-separated FPGA part string, e.g. 'xczu9eg-ffvb1156-2'."""
        device_el = root.find(".//DEVICE")
        if device_el is None:
            return ""
        parts = [
            device_el.get("Name", ""),
            device_el.get("Package", ""),
            device_el.get("SpeedGrade", ""),
        ]
        return "-".join(p for p in parts if p)

    def _parse_base_addr(self, mod: ET.Element) -> int:
        mr = mod.find(".//MEMRANGE")
        if mr is None:
            return 0
        raw = mr.get("BASEVALUE", "0x0")
        try:
            return int(raw, 16)
        except ValueError:
            instance = mod.get("INSTANCE", "unknown")
            raise XsaParseError(
                f"invalid BASEVALUE '{raw}' for module '{instance}'"
            )

    def _parse_jesd(
        self, mod: ET.Element, name: str, base_addr: int, direction: str
    ) -> Jesd204Instance:
        num_lanes_str = self._get_param(mod, "C_NUM_LANES", "")
        if not num_lanes_str:
            warnings.warn(
                f"C_NUM_LANES not found for {name}; defaulting to 1",
                UserWarning,
                stacklevel=3,
            )
            num_lanes_str = "1"
        return Jesd204Instance(
            name=name,
            base_addr=base_addr,
            num_lanes=int(num_lanes_str),
            irq=self._parse_irq(mod),
            link_clk=self._get_port_signame(mod, "device_clk"),
            direction=direction,
        )

    def _parse_clkgen(self, mod: ET.Element, name: str, base_addr: int) -> ClkgenInstance:
        output_clks = [
            port.get("SIGNAME", "")
            for port in mod.findall(".//PORT")
            if port.get("DIR") == "O"
            and port.get("SIGIS", "") == "CLK"
            and port.get("SIGNAME", "")
        ]
        return ClkgenInstance(name=name, base_addr=base_addr, output_clks=output_clks)

    def _parse_converter(
        self, mod: ET.Element, name: str, ip_type: str, base_addr: int
    ) -> ConverterInstance:
        return ConverterInstance(
            name=name, ip_type=ip_type, base_addr=base_addr,
            spi_bus=None, spi_cs=None,
        )

    def _get_param(self, mod: ET.Element, name: str, default: str = "") -> str:
        for param in mod.findall(".//PARAMETER"):
            if param.get("NAME") == name:
                return param.get("VALUE", default)
        return default

    def _get_port_signame(self, mod: ET.Element, port_name: str) -> str:
        for port in mod.findall(".//PORT"):
            if port.get("NAME") == port_name:
                return port.get("SIGNAME", "")
        return ""

    def _parse_irq(self, mod: ET.Element) -> Optional[int]:
        for port in mod.findall(".//PORT"):
            if port.get("NAME") == "interrupt":
                m = re.search(r"(\d+)$", port.get("SIGNAME", ""))
                if m:
                    return int(m.group(1))
        return None
