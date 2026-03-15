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
class SignalConnection:
    """Connectivity information for one HWH signal net."""

    signal: str
    producers: list[str] = field(default_factory=list)
    consumers: list[str] = field(default_factory=list)
    bidirectional: list[str] = field(default_factory=list)


@dataclass
class XsaTopology:
    jesd204_rx: list[Jesd204Instance] = field(default_factory=list)
    jesd204_tx: list[Jesd204Instance] = field(default_factory=list)
    clkgens: list[ClkgenInstance] = field(default_factory=list)
    converters: list[ConverterInstance] = field(default_factory=list)
    signal_connections: list[SignalConnection] = field(default_factory=list)
    fpga_part: str = ""

    def _jesd_name_blob(self) -> str:
        return " ".join(j.name.lower() for j in self.jesd204_rx + self.jesd204_tx)

    def has_converter_types(self, *ip_types: str) -> bool:
        converter_types = {c.ip_type for c in self.converters}
        return set(ip_types).issubset(converter_types)

    def is_fmcdaq2_design(self) -> bool:
        if self.has_converter_types("axi_ad9680", "axi_ad9144"):
            return True
        jesd_names = self._jesd_name_blob()
        return "ad9680" in jesd_names and "ad9144" in jesd_names

    def is_fmcdaq3_design(self) -> bool:
        if self.has_converter_types("axi_ad9680", "axi_ad9152"):
            return True
        jesd_names = self._jesd_name_blob()
        return "ad9680" in jesd_names and "ad9152" in jesd_names

    def inferred_converter_family(self) -> str:
        if self.is_fmcdaq2_design():
            return "fmcdaq2"
        if self.is_fmcdaq3_design():
            return "fmcdaq3"
        if self.converters:
            known_priority = (
                "ad9081",
                "ad9082",
                "ad9084",
                "adrv9025",
                "adrv9026",
                "adrv9009",
                "adrv9001",
                "ad9371",
                "ad9680",
                "ad9152",
                "ad9144",
            )
            converter_families = [
                c.ip_type.removeprefix("axi_").lower() for c in self.converters
            ]
            for family in known_priority:
                if family in converter_families:
                    if family == "adrv9026":
                        return "adrv9025"
                    if family == "adrv9001":
                        return "adrv9002"
                    if family == "ad9371":
                        return "adrv937x"
                    return family
            return converter_families[0]
        jesd_names = self._jesd_name_blob()
        if "adrv9026" in jesd_names or "adrv9025" in jesd_names:
            return "adrv9025"
        if "ad9084" in jesd_names:
            return "ad9084"
        if "mxfe" in jesd_names or "ad9081" in jesd_names:
            return "ad9081"
        if "adrv9009" in jesd_names:
            return "adrv9009"
        if "ad9371" in jesd_names or "adrv937" in jesd_names:
            return "adrv937x"
        return "unknown"

    def inferred_platform(self) -> str:
        part = self.fpga_part.lower()
        for prefix, platform in _PART_TO_PLATFORM.items():
            if part.startswith(prefix):
                return platform
        for prefix, platform in _PART_TO_PLATFORM.items():
            if prefix in part:
                return platform
        return "unknown"


_ADI_JESD_RX_TYPES = {"axi_jesd204_rx"}
_ADI_JESD_TX_TYPES = {"axi_jesd204_tx"}
_ADI_CLKGEN_TYPES = {"axi_clkgen"}
_ADI_AD9081_TPL_ADC_TYPES = {"ad_ip_jesd204_tpl_adc"}
_ADI_AD9081_TPL_DAC_TYPES = {"ad_ip_jesd204_tpl_dac"}
_ADI_CONVERTER_TYPES = {
    "axi_ad9680",
    "axi_ad9081",
    "axi_ad9082",
    "axi_ad9084",
    "axi_ad9162",
    "axi_ad9144",
    "axi_ad9152",
    "axi_adrv9001",
    "axi_adrv9009",
    "axi_adrv9025",
    "axi_adrv9026",
    "axi_ad9371",
}
_PART_TO_PLATFORM = {
    "xczu9eg": "zcu102",
    "xczu3eg": "zcu104",
    "xck26": "kv260",
    "xcvp1202": "vpk180",
    "xc7z045": "zc706",
    "xc7z020": "zc702",
    # Some exported HWHs omit the leading "xc" (e.g. "7z045-ffg900-2").
    "7z045": "zc706",
    "7z020": "zc702",
}


class XsaParser:
    """Parses a Vivado .xsa file and returns an XsaTopology."""

    def parse_hwh_map(self, hwh_content: str) -> dict:
        root = ET.fromstring(hwh_content)

        # Build map of IP instances
        ip_map = {}
        for mod in root.findall(".//MODULE"):
            mod_type = mod.get("MODTYPE", "").lower()
            if "slice" in mod_type:
                continue
            instance = mod.get("INSTANCE", mod_type)
            base_addr = self._parse_base_addr(mod)
            ip_map[instance] = {
                "type": mod_type,
                "base_addr": base_addr,
            }

        # connections between the ips
        connections = {}
        for port in root.findall(".//PORT"):
            DIR = port.get("DIR")
            if DIR == "I":
                direction = "input"
            elif DIR == "O":
                direction = "output"
            else:
                direction = "inout"
            sig_name = port.get("SIGNAME")
            cons = port.findall(".//CONNECTION")
            print(sig_name)
            print(cons)
            if len(cons) == 0:
                continue
            component = cons[0].get("INSTANCE")
            if "slice" in component:
                continue

            if sig_name in connections:
                partial = connections[sig_name]
                if direction == "input":
                    connections[sig_name] = {
                        "input": component,
                        "output": partial["output"],
                    }
                elif direction == "output":
                    connections[sig_name] = {
                        "input": partial["input"],
                        "output": component,
                    }
                elif direction == "inout":
                    connections[sig_name] = {"inout": component}
            else:
                if direction == "input":
                    connections[sig_name] = {"input": component, "output": None}
                elif direction == "output":
                    connections[sig_name] = {"input": None, "output": component}
                elif direction == "inout":
                    connections[sig_name] = {"inout": component}
        from pprint import pprint

        print("connections")
        pprint(connections)

        # Create dot diagram
        dot = "digraph G {\n"
        for sig_name, connection in connections.items():
            if connection["input"] and connection["output"]:
                dot += f'  "{connection["input"]}" -> "{connection["output"]}";\n'
            elif connection["input"]:
                dot += f'  "{connection["input"]}";\n'
            elif connection["output"]:
                dot += f'  "{connection["output"]}";\n'
            elif connection["inout"]:
                dot += f'  "{connection["inout"]}";\n'
        dot += "}\n"
        with open("connections.dot", "w") as f:
            f.write(dot)

        # Create d2 diagram
        d2 = "direction: right\n"
        for sig_name, connection in connections.items():
            if connection["input"] and connection["output"]:
                d2 += f'  "{connection["input"]}" -> "{connection["output"]}";\n'
            elif connection["input"]:
                d2 += f'  "{connection["input"]}";\n'
            elif connection["output"]:
                d2 += f'  "{connection["output"]}";\n'
            elif connection["inout"]:
                d2 += f'  "{connection["inout"]}";\n'
        with open("connections.d2", "w") as f:
            f.write(d2)

        import d2 as d2lib

        graph = d2lib.compile(d2)
        with open("connections.d2.svg", "w") as f:
            f.write(graph)

        return ip_map

    def parse(self, xsa_path: Path) -> XsaTopology:
        hwh_content = self._extract_hwh(xsa_path)
        # with open("hwh_content.xml", "w") as f:
        #     f.write(hwh_content)

        # ip_map = self.parse_hwh_map(hwh_content)
        # from pprint import pprint
        # pprint(ip_map)
        # with open("ip_map.txt", "w") as f:
        #     f.write(str(ip_map))

        root = ET.fromstring(hwh_content)
        # with open("root.txt", "w") as f:
        #     f.write(str(root))
        topology = XsaTopology()
        topology.fpga_part = self._parse_part(root)
        topology.signal_connections = self._parse_signal_connections(root)
        global_base_addrs = self._parse_global_base_addrs(root)

        found_adi = False
        ad9081_tpl_adc_base: Optional[int] = None
        ad9081_tpl_dac_seen = False
        ad9081_tpl_signature = False
        for mod in root.findall(".//MODULE"):
            mod_type = mod.get("MODTYPE", "").lower()
            instance = mod.get("INSTANCE", mod_type)
            base_addr = self._parse_base_addr(mod, instance, global_base_addrs)

            if mod_type in _ADI_JESD_RX_TYPES:
                found_adi = True
                topology.jesd204_rx.append(
                    self._parse_jesd(mod, instance, base_addr, "rx")
                )
            elif mod_type in _ADI_JESD_TX_TYPES:
                found_adi = True
                topology.jesd204_tx.append(
                    self._parse_jesd(mod, instance, base_addr, "tx")
                )
            elif mod_type in _ADI_CLKGEN_TYPES:
                found_adi = True
                topology.clkgens.append(self._parse_clkgen(mod, instance, base_addr))
            elif mod_type in _ADI_AD9081_TPL_ADC_TYPES:
                # AD9081 HDL designs can expose TPL blocks but no explicit
                # axi_ad9081 converter module in the HWH.
                found_adi = True
                if ad9081_tpl_adc_base is None:
                    ad9081_tpl_adc_base = base_addr
                if "mxfe" in instance.lower() or "ad9081" in instance.lower():
                    ad9081_tpl_signature = True
            elif mod_type in _ADI_AD9081_TPL_DAC_TYPES:
                found_adi = True
                ad9081_tpl_dac_seen = True
                if "mxfe" in instance.lower() or "ad9081" in instance.lower():
                    ad9081_tpl_signature = True
            elif mod_type in _ADI_CONVERTER_TYPES:
                found_adi = True
                topology.converters.append(
                    self._parse_converter(mod, instance, mod_type, base_addr)
                )

        if (
            not topology.converters
            and ad9081_tpl_adc_base is not None
            and ad9081_tpl_dac_seen
            and ad9081_tpl_signature
        ):
            topology.converters.append(
                ConverterInstance(
                    name="axi_ad9081_0",
                    ip_type="axi_ad9081",
                    base_addr=ad9081_tpl_adc_base,
                    spi_bus=None,
                    spi_cs=None,
                )
            )

        if not found_adi:
            warnings.warn(
                f"no recognized ADI IPs found in {xsa_path.name}; "
                "pipeline will produce base DTS only",
                UserWarning,
                stacklevel=2,
            )

        return topology

    def _parse_signal_connections(self, root: ET.Element) -> list[SignalConnection]:
        """Extract module-level connectivity using HWH SIGNAME + port directions."""
        by_signal: dict[str, SignalConnection] = {}

        for mod in root.findall(".//MODULE"):
            instance = mod.get("INSTANCE", "")
            if not instance:
                continue

            # Prefer direct module port lists; fallback for variant structures.
            ports = mod.findall("./PORTS/PORT")
            if not ports:
                ports = mod.findall(".//PORT")

            for port in ports:
                sig_name = (port.get("SIGNAME") or "").strip()
                if not sig_name:
                    continue
                direction = (port.get("DIR") or "").upper()
                conn = by_signal.setdefault(sig_name, SignalConnection(signal=sig_name))

                if direction == "O":
                    if instance not in conn.producers:
                        conn.producers.append(instance)
                elif direction == "I":
                    if instance not in conn.consumers:
                        conn.consumers.append(instance)
                else:
                    if instance not in conn.bidirectional:
                        conn.bidirectional.append(instance)

        return sorted(by_signal.values(), key=lambda c: c.signal)

    def _parse_global_base_addrs(self, root: ET.Element) -> dict[str, int]:
        """Parse top-level MEMORYMAP instance address assignments.

        Newer Vivado exports can place authoritative per-instance addresses in a
        global MEMORYMAP while module-local MEMRANGE entries remain 0x0.
        """
        addr_map: dict[str, int] = {}
        for mr in root.findall(".//MEMRANGE"):
            instance = mr.get("INSTANCE", "")
            raw = mr.get("BASEVALUE", "")
            if not instance or not raw:
                continue
            try:
                addr = int(raw, 16)
            except ValueError:
                continue
            # Prefer non-zero address assignments where available.
            if instance not in addr_map or (addr_map[instance] == 0 and addr != 0):
                addr_map[instance] = addr
        return addr_map

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
                    raise XsaParseError(f"cannot decode {hwh_names[0]} as UTF-8: {e}")
        except zipfile.BadZipFile as e:
            raise XsaParseError(f"cannot open {xsa_path.name} as a zip archive: {e}")

    def _parse_part(self, root: ET.Element) -> str:
        """Return dash-separated FPGA part string, e.g. 'xczu9eg-ffvb1156-2'."""
        device_el = root.find(".//DEVICE")
        if device_el is not None:
            part = device_el.get("Name", "")
            package = device_el.get("Package", "")
            speed = device_el.get("SpeedGrade", "")
        else:
            # Newer Vivado exports place part metadata in SYSTEMINFO attrs.
            sysinfo = root.find(".//SYSTEMINFO")
            if sysinfo is None:
                return ""
            part = sysinfo.get("DEVICE", "") or sysinfo.get("Name", "")
            package = sysinfo.get("PACKAGE", "") or sysinfo.get("Package", "")
            speed = sysinfo.get("SPEEDGRADE", "") or sysinfo.get("SpeedGrade", "")

        if speed.startswith("-"):
            speed = speed[1:]
        parts = [part, package, speed]
        return "-".join(p for p in parts if p)

    def _parse_base_addr(
        self, mod: ET.Element, instance: str, global_base_addrs: dict[str, int]
    ) -> int:
        mr = mod.find(".//MEMRANGE")
        module_addr = 0
        if mr is not None:
            raw = mr.get("BASEVALUE", "0x0")
            try:
                module_addr = int(raw, 16)
            except ValueError:
                raise XsaParseError(
                    f"invalid BASEVALUE '{raw}' for module '{instance}'"
                )

        global_addr = global_base_addrs.get(instance)
        if global_addr is not None and (module_addr == 0 or mr is None):
            return global_addr
        if module_addr == 0:
            c_baseaddr = self._get_param(mod, "C_BASEADDR", "")
            if c_baseaddr:
                try:
                    return int(c_baseaddr, 16)
                except ValueError:
                    raise XsaParseError(
                        f"invalid C_BASEADDR '{c_baseaddr}' for module '{instance}'"
                    )
        return module_addr

    def _parse_jesd(
        self, mod: ET.Element, name: str, base_addr: int, direction: str
    ) -> Jesd204Instance:
        num_lanes_str = self._get_param(mod, "C_NUM_LANES", "")
        if not num_lanes_str:
            num_lanes_str = self._get_param(mod, "NUM_LANES", "")
        if not num_lanes_str:
            warnings.warn(
                f"lane count param not found for {name}; defaulting to 1",
                UserWarning,
                stacklevel=3,
            )
            num_lanes_str = "1"
        link_clk = self._get_port_signame(mod, "device_clk")
        if not link_clk:
            link_clk = self._get_port_signame(mod, "core_clk")
        return Jesd204Instance(
            name=name,
            base_addr=base_addr,
            num_lanes=int(num_lanes_str),
            irq=self._parse_irq(mod),
            link_clk=link_clk,
            direction=direction,
        )

    def _parse_clkgen(
        self, mod: ET.Element, name: str, base_addr: int
    ) -> ClkgenInstance:
        output_clks = [
            port.get("SIGNAME", "")
            for port in mod.findall(".//PORT")
            if port.get("DIR") == "O"
            and port.get("SIGIS", "").lower() == "clk"
            and port.get("SIGNAME", "")
        ]
        return ClkgenInstance(name=name, base_addr=base_addr, output_clks=output_clks)

    def _parse_converter(
        self, mod: ET.Element, name: str, ip_type: str, base_addr: int
    ) -> ConverterInstance:
        return ConverterInstance(
            name=name,
            ip_type=ip_type,
            base_addr=base_addr,
            spi_bus=None,
            spi_cs=None,
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
            if port.get("NAME") in ("interrupt", "irq"):
                m = re.search(r"(\d+)$", port.get("SIGNAME", ""))
                if m:
                    return int(m.group(1))
        for param_name in ("C_IRQ", "IRQ"):
            irq_str = self._get_param(mod, param_name, "")
            if not irq_str:
                continue
            try:
                return int(irq_str, 0)
            except ValueError:
                continue
        return None
