# XSA-to-DeviceTree Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `adidtc xsa2dt` command that invokes sdtgen against a Vivado XSA file, detects ADI AXI IPs from the `.hwh` hardware handoff, generates JESD204 FSM-framework-compatible DTS nodes, and produces a DTS overlay, merged DTS, and interactive HTML visualization report.

**Architecture:** Five-stage pipeline in a new `adidt/xsa/` subpackage: (1) sdtgen subprocess wrapper, (2) XSA `.hwh` topology parser, (3) ADI node builder via Jinja2 templates, (4) DTS overlay/merge writer, (5) self-contained HTML visualizer. A `XsaPipeline` orchestrator wires the stages. Existing `gen-dts` flow is untouched.

**Tech Stack:** Python 3.10+, Jinja2 (existing), Click (existing), `subprocess`, `zipfile`, `xml.etree.ElementTree`, `re`, D3.js v7 (embedded at dev time), pytest, `unittest.mock`

---

## Chunk 1: Foundation — Exceptions and sdtgen Wrapper

### Task 1: Create xsa subpackage skeleton and custom exceptions

**Files:**
- Create: `adidt/xsa/__init__.py`
- Create: `adidt/xsa/exceptions.py`
- Create: `test/xsa/__init__.py`
- Create: `test/xsa/test_exceptions.py`

- [ ] **Step 1: Write the failing test**

```python
# test/xsa/test_exceptions.py
from adidt.xsa.exceptions import SdtgenNotFoundError, SdtgenError, XsaParseError, ConfigError


def test_sdtgen_not_found_error_is_exception():
    err = SdtgenNotFoundError("sdtgen not found")
    assert isinstance(err, Exception)
    assert "sdtgen not found" in str(err)


def test_sdtgen_error_carries_stderr():
    err = SdtgenError("failed", stderr="error output")
    assert err.stderr == "error output"


def test_xsa_parse_error_is_exception():
    err = XsaParseError("no hwh found")
    assert isinstance(err, Exception)


def test_config_error_names_missing_field():
    err = ConfigError("sample_clock")
    assert "sample_clock" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/tcollins/dev/pyadi-dt-xsa-powers
pytest test/xsa/test_exceptions.py -v
```

Expected: `ImportError` — module does not exist yet.

- [ ] **Step 3: Create the files**

```python
# adidt/xsa/__init__.py
# (empty)
```

```python
# adidt/xsa/exceptions.py
class SdtgenNotFoundError(Exception):
    """Raised when sdtgen/lopper binary is not found on PATH."""
    INSTALL_URL = "https://github.com/devicetree-org/lopper"

    def __init__(self, message: str = "sdtgen not found on PATH"):
        super().__init__(
            f"{message}\nInstall lopper/sdtgen from: {self.INSTALL_URL}"
        )


class SdtgenError(Exception):
    """Raised when sdtgen exits with a non-zero status or produces no output."""

    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


class XsaParseError(Exception):
    """Raised when the XSA file cannot be parsed."""
    pass


class ConfigError(Exception):
    """Raised when the pyadi-jif JSON config is missing required fields."""

    def __init__(self, missing_field: str):
        super().__init__(f"Missing required config field: '{missing_field}'")
        self.missing_field = missing_field
```

```python
# test/xsa/__init__.py
# (empty)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest test/xsa/test_exceptions.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/__init__.py adidt/xsa/exceptions.py test/xsa/__init__.py test/xsa/test_exceptions.py
git commit -m "feat(xsa): add xsa subpackage skeleton and custom exceptions"
```

---

### Task 2: sdtgen subprocess wrapper

**Files:**
- Create: `adidt/xsa/sdtgen.py`
- Create: `test/xsa/test_sdtgen.py`

- [ ] **Step 1: Write the failing tests**

```python
# test/xsa/test_sdtgen.py
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest

from adidt.xsa.sdtgen import SdtgenRunner
from adidt.xsa.exceptions import SdtgenNotFoundError, SdtgenError


def _help_result():
    r = MagicMock()
    r.returncode = 0
    r.stdout = "sdtgen -s <xsa> -d <outdir>"
    r.stderr = ""
    return r


def _ok_result():
    r = MagicMock()
    r.returncode = 0
    r.stdout = ""
    r.stderr = ""
    return r


def test_run_invokes_sdtgen_with_correct_args(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;")

    # New runner per test avoids module-level cache interference
    runner = SdtgenRunner()
    with patch("subprocess.run", side_effect=[_help_result(), _ok_result()]) as mock_run:
        result = runner.run(xsa, out_dir)

    # The second call is the actual sdtgen invocation
    sdtgen_call = mock_run.call_args_list[1]
    cmd = sdtgen_call[0][0]
    assert cmd[0] == "sdtgen"
    assert str(xsa) in cmd
    assert str(out_dir) in cmd
    assert result == out_dir / "system-top.dts"


def test_run_raises_not_found_when_binary_missing(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SdtgenNotFoundError):
            runner.run(xsa, out_dir)


def test_run_raises_error_on_nonzero_exit(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    fail_result = MagicMock()
    fail_result.returncode = 1
    fail_result.stderr = "fatal: bad xsa"
    fail_result.stdout = ""

    runner = SdtgenRunner()
    with patch("subprocess.run", side_effect=[_help_result(), fail_result]):
        with pytest.raises(SdtgenError) as exc_info:
            runner.run(xsa, out_dir)
    assert "fatal: bad xsa" in exc_info.value.stderr


def test_run_raises_error_on_timeout(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch("subprocess.run", side_effect=[_help_result(), subprocess.TimeoutExpired("sdtgen", 5)]):
        with pytest.raises(SdtgenError, match="timed out"):
            runner.run(xsa, out_dir, timeout=5)


def test_run_scans_for_dts_when_system_top_absent(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "other_name.dts").write_text("/dts-v1/;")

    runner = SdtgenRunner()
    with patch("subprocess.run", side_effect=[_help_result(), _ok_result()]):
        result = runner.run(xsa, out_dir)
    assert result == out_dir / "other_name.dts"


def test_run_raises_error_when_no_dts_produced(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch("subprocess.run", side_effect=[_help_result(), _ok_result()]):
        with pytest.raises(SdtgenError, match=r"no \.dts output"):
            runner.run(xsa, out_dir)


def test_help_timeout_raises_sdtgen_error(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sdtgen", 10)):
        with pytest.raises(SdtgenError, match="timed out"):
            runner.run(xsa, out_dir)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/tcollins/dev/pyadi-dt-xsa-powers
pytest test/xsa/test_sdtgen.py -v
```

Expected: `ImportError` — module does not exist yet.

- [ ] **Step 3: Implement SdtgenRunner**

```python
# adidt/xsa/sdtgen.py
import subprocess
from pathlib import Path

from .exceptions import SdtgenError, SdtgenNotFoundError


class SdtgenRunner:
    """Invokes sdtgen as a subprocess to generate a base SDT/DTS from an XSA file."""

    def __init__(self, binary: str = "sdtgen"):
        self.binary = binary
        # Instance-level cache avoids cross-test interference
        self._flags: tuple[str, str] | None = None

    def _detect_flags(self) -> tuple[str, str]:
        """Confirm binary exists and return (src_flag, out_flag)."""
        if self._flags is not None:
            return self._flags
        try:
            subprocess.run(
                [self.binary, "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except FileNotFoundError:
            raise SdtgenNotFoundError()
        except subprocess.TimeoutExpired:
            raise SdtgenError(f"sdtgen --help timed out after 10s")
        self._flags = ("-s", "-d")
        return self._flags

    def run(self, xsa_path: Path, output_dir: Path, timeout: int = 120) -> Path:
        """Run sdtgen and return the path to the generated base DTS file.

        Raises:
            SdtgenNotFoundError: If sdtgen is not on PATH.
            SdtgenError: If sdtgen fails, times out, or produces no output.
        """
        src_flag, out_flag = self._detect_flags()
        cmd = [self.binary, src_flag, str(xsa_path), out_flag, str(output_dir)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            raise SdtgenNotFoundError()
        except subprocess.TimeoutExpired:
            raise SdtgenError(f"sdtgen timed out after {timeout}s")

        if result.returncode != 0:
            raise SdtgenError(
                f"sdtgen exited with code {result.returncode}",
                stderr=result.stderr,
            )

        expected = output_dir / "system-top.dts"
        if expected.exists():
            return expected

        dts_files = sorted(output_dir.glob("*.dts"))
        if dts_files:
            return dts_files[0]

        raise SdtgenError("sdtgen produced no .dts output")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest test/xsa/test_sdtgen.py -v
```

Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/sdtgen.py test/xsa/test_sdtgen.py
git commit -m "feat(xsa): add SdtgenRunner subprocess wrapper with full error handling"
```

---

## Chunk 2: XSA Topology Parser

### Task 3: XsaTopology data classes

**Files:**
- Create: `adidt/xsa/topology.py`
- Create: `test/xsa/test_topology.py` (data class section)

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/tcollins/dev/pyadi-dt-xsa-powers
pytest test/xsa/test_topology.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create `adidt/xsa/topology.py` with dataclasses**

```python
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
                return zf.read(hwh_names[0]).decode("utf-8")
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
        return int(mr.get("BASEVALUE", "0x0"), 16)

    def _parse_jesd(
        self, mod: ET.Element, name: str, base_addr: int, direction: str
    ) -> Jesd204Instance:
        return Jesd204Instance(
            name=name,
            base_addr=base_addr,
            num_lanes=int(self._get_param(mod, "C_NUM_LANES", "1")),
            irq=self._parse_irq(mod),
            link_clk=self._get_port_signame(mod, "device_clk"),
            direction=direction,
        )

    def _parse_clkgen(self, mod: ET.Element, name: str, base_addr: int) -> ClkgenInstance:
        output_clks = [
            port.get("SIGNAME", "")
            for port in mod.findall(".//PORT")
            if port.get("DIR") == "O"
            and port.get("SIGIS", "") != "RST"
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest test/xsa/test_topology.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/topology.py test/xsa/test_topology.py
git commit -m "feat(xsa): add XsaTopology data classes"
```

---

### Task 4: XSA .hwh parser — fixture and XsaParser tests

**Files:**
- Create: `test/xsa/fixtures/ad9081_zcu102.hwh`
- Modify: `test/xsa/test_topology.py` (append parser tests)

- [ ] **Step 1: Create the .hwh fixture**

Create file `test/xsa/fixtures/ad9081_zcu102.hwh`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<EDKPROJECT>
  <HEADER>
    <DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/>
  </HEADER>
  <MODULES>
    <MODULE MODTYPE="axi_jesd204_rx" INSTANCE="axi_jesd204_rx_0">
      <PARAMETERS>
        <PARAMETER NAME="C_NUM_LANES" VALUE="4"/>
      </PARAMETERS>
      <MEMRANGES>
        <MEMRANGE INSTANCE="axi_jesd204_rx_0" BASEVALUE="0x44A90000" HIGHVALUE="0x44A9FFFF"/>
      </MEMRANGES>
      <PORTS>
        <PORT DIR="I" NAME="s_axi_aclk" SIGIS="CLK" SIGNAME="sys_100mhz"/>
        <PORT DIR="I" NAME="device_clk" SIGIS="CLK" SIGNAME="jesd_rx_device_clk"/>
        <PORT DIR="O" NAME="interrupt" SIGNAME="irq_54"/>
      </PORTS>
    </MODULE>
    <MODULE MODTYPE="axi_jesd204_tx" INSTANCE="axi_jesd204_tx_0">
      <PARAMETERS>
        <PARAMETER NAME="C_NUM_LANES" VALUE="4"/>
      </PARAMETERS>
      <MEMRANGES>
        <MEMRANGE INSTANCE="axi_jesd204_tx_0" BASEVALUE="0x44B90000" HIGHVALUE="0x44B9FFFF"/>
      </MEMRANGES>
      <PORTS>
        <PORT DIR="I" NAME="s_axi_aclk" SIGIS="CLK" SIGNAME="sys_100mhz"/>
        <PORT DIR="I" NAME="device_clk" SIGIS="CLK" SIGNAME="jesd_tx_device_clk"/>
        <PORT DIR="O" NAME="interrupt" SIGNAME="irq_55"/>
      </PORTS>
    </MODULE>
    <MODULE MODTYPE="axi_clkgen" INSTANCE="axi_clkgen_0">
      <MEMRANGES>
        <MEMRANGE INSTANCE="axi_clkgen_0" BASEVALUE="0x43C00000" HIGHVALUE="0x43C0FFFF"/>
      </MEMRANGES>
      <PORTS>
        <PORT DIR="O" NAME="clk_0" SIGNAME="jesd_rx_device_clk"/>
        <PORT DIR="O" NAME="clk_1" SIGNAME="jesd_tx_device_clk"/>
      </PORTS>
    </MODULE>
    <MODULE MODTYPE="axi_ad9081" INSTANCE="axi_ad9081_0">
      <MEMRANGES>
        <MEMRANGE INSTANCE="axi_ad9081_0" BASEVALUE="0x44A00000" HIGHVALUE="0x44A0FFFF"/>
      </MEMRANGES>
      <PORTS>
        <PORT DIR="O" NAME="spi_csn" SIGNAME="spi0_cs_0"/>
      </PORTS>
    </MODULE>
  </MODULES>
</EDKPROJECT>
```

- [ ] **Step 2: Append parser tests to `test/xsa/test_topology.py`**

```python
# Append to test/xsa/test_topology.py
import io
import pytest
import warnings
import zipfile
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest test/xsa/test_topology.py -v -k "parser"
```

Expected: `NameError` or `ImportError` — XsaParser not yet in a separate import but it is already defined in topology.py from Task 3. Tests will fail because `FIXTURE_HWH` path does not exist yet.

- [ ] **Step 4: Run all topology tests to verify they pass**

```bash
pytest test/xsa/test_topology.py -v
```

Expected: all PASSED (XsaParser is already in `topology.py` from Task 3 Step 3)

- [ ] **Step 5: Commit**

```bash
git add test/xsa/test_topology.py test/xsa/fixtures/ad9081_zcu102.hwh
git commit -m "feat(xsa): add .hwh fixture and comprehensive XsaParser tests"
```

---

## Chunk 3: ADI Node Builder

### Task 5: Jinja2 templates for JESD204 FSM and converters

**Files:**
- Create: `adidt/templates/xsa/jesd204_fsm.tmpl`
- Create: `adidt/templates/xsa/axi_ad9081.tmpl`
- Modify: `pyproject.toml` (package-data)

No tests here — templates are exercised by Task 6.

- [ ] **Step 1: Create `adidt/templates/xsa/jesd204_fsm.tmpl`**

```jinja2
{# Context vars: instance (Jesd204Instance), jesd (dict), clkgen_label, hmc_channel #}
	{{ instance.name | replace("-", "_") }}: axi-jesd204-{{ instance.direction }}@{{ "%08x" | format(instance.base_addr) }} {
		compatible = "adi,axi-jesd204-{{ instance.direction }}-1.0";
		reg = <0x0 0x{{ "%08X" | format(instance.base_addr) }} 0x0 0x1000>;
{%- if instance.irq is not none %}
		interrupts = <0 {{ instance.irq }} IRQ_TYPE_LEVEL_HIGH>;
{%- endif %}
		clocks = <&{{ clkgen_label }} 0>, <&hmc7044 {{ hmc_channel }}>, <&{{ clkgen_label }} 1>;
		clock-names = "s_axi_aclk", "device_clk", "lane_clk";

		adi,octets-per-frame = <{{ jesd.F }}>;
		adi,frames-per-multiframe = <{{ jesd.K }}>;

		#sound-dai-cells = <0>;
	};
```

- [ ] **Step 2: Create `adidt/templates/xsa/axi_ad9081.tmpl`**

```jinja2
{# Context vars: instance (ConverterInstance), rx_jesd_label, tx_jesd_label, spi_label, spi_cs #}
	{{ instance.name }}: ad9081@{{ spi_cs }} {
		compatible = "adi,ad9081";
		reg = <{{ spi_cs }}>;
		spi-max-frequency = <1000000>;

		jesd204-device;
		#jesd204-cells = <2>;
		jesd204-top-device = <0>;
		jesd204-link-ids = <JESD204_LINK_IDS_TX_RX>;

		jesd204-inputs = <&{{ rx_jesd_label }} 0 JESD204_SUBDEV_RX>;
	};
```

- [ ] **Step 3: Update `pyproject.toml` package-data**

Change:
```toml
[tool.setuptools.package-data]
adidt = ["templates/*.tmpl"]
```
To:
```toml
[tool.setuptools.package-data]
adidt = ["templates/*.tmpl", "templates/xsa/*.tmpl", "xsa/d3_bundle.js"]
```

- [ ] **Step 4: Commit**

```bash
git add adidt/templates/xsa/jesd204_fsm.tmpl adidt/templates/xsa/axi_ad9081.tmpl pyproject.toml
git commit -m "feat(xsa): add Jinja2 templates for JESD204 FSM and AD9081 DTS nodes"
```

---

### Task 6: ADI node builder

**Files:**
- Create: `adidt/xsa/node_builder.py`
- Create: `test/xsa/test_node_builder.py`
- Create: `test/xsa/fixtures/ad9081_config.json`

- [ ] **Step 1: Create the JSON config fixture**

Create `test/xsa/fixtures/ad9081_config.json`:

```json
{
  "clock": {
    "part": "hmc7044",
    "hmc7044_out_freq": {
      "rx_device_clk": 250000000,
      "tx_device_clk": 250000000
    },
    "hmc7044_rx_channel": 10,
    "hmc7044_tx_channel": 6
  },
  "jesd": {
    "rx": {"F": 4, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1},
    "tx": {"F": 4, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1}
  }
}
```

- [ ] **Step 2: Write failing tests**

```python
# test/xsa/test_node_builder.py
import json
import warnings
from pathlib import Path
import pytest

from adidt.xsa.topology import (
    ClkgenInstance, ConverterInstance, Jesd204Instance, XsaTopology,
)
from adidt.xsa.node_builder import NodeBuilder

FIXTURE_CFG = Path(__file__).parent / "fixtures" / "ad9081_config.json"


@pytest.fixture
def topo():
    return XsaTopology(
        jesd204_rx=[Jesd204Instance(
            name="axi_jesd204_rx_0", base_addr=0x44A90000, num_lanes=4,
            irq=54, link_clk="jesd_rx_device_clk", direction="rx",
        )],
        jesd204_tx=[Jesd204Instance(
            name="axi_jesd204_tx_0", base_addr=0x44B90000, num_lanes=4,
            irq=55, link_clk="jesd_tx_device_clk", direction="tx",
        )],
        clkgens=[ClkgenInstance(
            name="axi_clkgen_0", base_addr=0x43C00000,
            output_clks=["jesd_rx_device_clk", "jesd_tx_device_clk"],
        )],
        converters=[ConverterInstance(
            name="axi_ad9081_0", ip_type="axi_ad9081",
            base_addr=0x44A00000, spi_bus=None, spi_cs=None,
        )],
    )


@pytest.fixture
def cfg():
    return json.loads(FIXTURE_CFG.read_text())


def test_build_rx_jesd_node_contains_compatible(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    assert "adi,axi-jesd204-rx-1.0" in nodes["jesd204_rx"][0]


def test_build_rx_jesd_node_contains_base_addr(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    assert "44A90000" in nodes["jesd204_rx"][0].upper()


def test_build_rx_jesd_node_contains_irq(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    assert "54" in nodes["jesd204_rx"][0]


def test_build_rx_jesd_node_contains_jesd_params(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    rx = nodes["jesd204_rx"][0]
    assert "adi,octets-per-frame = <4>" in rx
    assert "adi,frames-per-multiframe = <32>" in rx


def test_build_tx_jesd_node(topo, cfg):
    nodes = NodeBuilder().build(topo, cfg)
    tx = nodes["jesd204_tx"][0]
    assert "adi,axi-jesd204-tx-1.0" in tx
    assert "44B90000" in tx.upper()


def test_build_warns_on_unresolvable_clock(cfg):
    topo_no_clkgen = XsaTopology(
        jesd204_rx=[Jesd204Instance(
            name="axi_jesd204_rx_0", base_addr=0x44A90000, num_lanes=4,
            irq=None, link_clk="unknown_clk_net", direction="rx",
        )],
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        NodeBuilder().build(topo_no_clkgen, cfg)
    assert any("unresolved clock" in str(warning.message) for warning in w)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest test/xsa/test_node_builder.py -v
```

Expected: `ImportError`

- [ ] **Step 4: Implement NodeBuilder**

```python
# adidt/xsa/node_builder.py
import os
import warnings
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .topology import XsaTopology, Jesd204Instance, ClkgenInstance


class NodeBuilder:
    """Builds ADI DTS node strings from XsaTopology + pyadi-jif JSON config."""

    def build(self, topology: XsaTopology, cfg: dict[str, Any]) -> dict[str, list[str]]:
        """Render ADI DTS nodes.

        Returns:
            Dict with keys "jesd204_rx", "jesd204_tx", "converters".
        """
        env = self._make_jinja_env()
        clock_map = self._build_clock_map(topology)
        result: dict[str, list[str]] = {"jesd204_rx": [], "jesd204_tx": [], "converters": []}

        for inst in topology.jesd204_rx:
            clkgen_label, hmc_ch = self._resolve_clock(inst, clock_map, cfg, "rx")
            result["jesd204_rx"].append(
                self._render_jesd(env, inst, cfg.get("jesd", {}).get("rx", {}), clkgen_label, hmc_ch)
            )

        for inst in topology.jesd204_tx:
            clkgen_label, hmc_ch = self._resolve_clock(inst, clock_map, cfg, "tx")
            result["jesd204_tx"].append(
                self._render_jesd(env, inst, cfg.get("jesd", {}).get("tx", {}), clkgen_label, hmc_ch)
            )

        for conv in topology.converters:
            result["converters"].append(self._render_converter(env, conv, result))

        return result

    def _make_jinja_env(self) -> Environment:
        loc = os.path.join(os.path.dirname(__file__), "..", "templates", "xsa")
        return Environment(loader=FileSystemLoader(loc))

    def _build_clock_map(self, topology: XsaTopology) -> dict[str, ClkgenInstance]:
        return {net: cg for cg in topology.clkgens for net in cg.output_clks}

    def _resolve_clock(
        self,
        inst: Jesd204Instance,
        clock_map: dict[str, ClkgenInstance],
        cfg: dict[str, Any],
        direction: str,
    ) -> tuple[str, int]:
        clkgen = clock_map.get(inst.link_clk)
        if clkgen is None:
            warnings.warn(
                f"unresolved clock net '{inst.link_clk}' for {inst.name}; "
                "using literal net name as clock label",
                UserWarning,
                stacklevel=3,
            )
            return inst.link_clk, 0
        return (
            clkgen.name.replace("-", "_"),
            cfg.get("clock", {}).get(f"hmc7044_{direction}_channel", 0),
        )

    def _render_jesd(
        self,
        env: Environment,
        inst: Jesd204Instance,
        jesd_params: dict[str, Any],
        clkgen_label: str,
        hmc_channel: int,
    ) -> str:
        return env.get_template("jesd204_fsm.tmpl").render(
            instance=inst, jesd=jesd_params,
            clkgen_label=clkgen_label, hmc_channel=hmc_channel,
        )

    def _render_converter(self, env: Environment, conv, nodes: dict[str, list[str]]) -> str:
        try:
            tmpl = env.get_template(f"{conv.ip_type}.tmpl")
        except Exception:
            return f"\t/* {conv.name}: no template for {conv.ip_type} */"
        rx_label = nodes["jesd204_rx"][0].split(":")[0].strip() if nodes["jesd204_rx"] else "jesd_rx"
        tx_label = nodes["jesd204_tx"][0].split(":")[0].strip() if nodes["jesd204_tx"] else "jesd_tx"
        return tmpl.render(
            instance=conv, rx_jesd_label=rx_label, tx_jesd_label=tx_label,
            spi_label="spi0", spi_cs=conv.spi_cs if conv.spi_cs is not None else 0,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest test/xsa/test_node_builder.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add adidt/xsa/node_builder.py test/xsa/test_node_builder.py test/xsa/fixtures/ad9081_config.json
git commit -m "feat(xsa): add NodeBuilder for rendering ADI DTS nodes from topology and config"
```

---

## Chunk 4: DTS Merger

### Task 7: DTS merger — overlay and merged output

**Files:**
- Create: `adidt/xsa/merger.py`
- Create: `test/xsa/test_merger.py`

- [ ] **Step 1: Write failing tests**

```python
# test/xsa/test_merger.py
import warnings
from pathlib import Path
import pytest
from adidt.xsa.merger import DtsMerger

BASE_DTS = """\
/dts-v1/;
/ {
\tmodel = "Zynq UltraScale+ ZCU102 Rev1.0";
\t#address-cells = <2>;
\t#size-cells = <2>;
\tamba: axi {
\t\t#address-cells = <2>;
\t\t#size-cells = <2>;
\t\tcompatible = "simple-bus";
\t\tranges;
\t};
};"""

ADI_NODES = {
    "jesd204_rx": ['\taxi_jesd204_rx_0: axi-jesd204-rx@44a90000 {\n\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n\t};'],
    "jesd204_tx": ['\taxi_jesd204_tx_0: axi-jesd204-tx@44b90000 {\n\t\tcompatible = "adi,axi-jesd204-tx-1.0";\n\t};'],
    "converters": [],
}


def test_overlay_references_amba_label(tmp_path):
    overlay, _ = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "&amba" in overlay


def test_overlay_contains_adi_nodes(tmp_path):
    overlay, _ = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "adi,axi-jesd204-rx-1.0" in overlay
    assert "adi,axi-jesd204-tx-1.0" in overlay


def test_overlay_has_dts_v1_and_plugin_header(tmp_path):
    overlay, _ = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "/dts-v1/;" in overlay
    assert "/plugin/;" in overlay


def test_merged_contains_adi_nodes(tmp_path):
    _, merged = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "adi,axi-jesd204-rx-1.0" in merged
    assert "adi,axi-jesd204-tx-1.0" in merged


def test_merged_retains_base_content(tmp_path):
    _, merged = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "Zynq UltraScale+" in merged


def test_overlay_file_written(tmp_path):
    DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "myboard")
    assert (tmp_path / "myboard.dtso").exists()


def test_merged_file_written(tmp_path):
    DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "myboard")
    assert (tmp_path / "myboard.dts").exists()


def test_conflict_replaces_existing_node_and_warns(tmp_path):
    base_with_conflict = BASE_DTS.replace(
        "\t\tranges;\n\t};",
        "\t\tranges;\n\n\t\taxi-jesd204-rx@44a90000 {\n\t\t\tcompatible = \"stub\";\n\t\t};\n\t};",
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _, merged = DtsMerger().merge(base_with_conflict, ADI_NODES, tmp_path, "conflict")
    assert any("replaced" in str(warning.message).lower() for warning in w)
    assert '"stub"' not in merged
    assert "adi,axi-jesd204-rx-1.0" in merged


def test_fallback_to_root_when_no_amba_label(tmp_path):
    no_amba = "/dts-v1/;\n/ {\n\t#address-cells = <1>;\n};\n"
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        _, merged = DtsMerger().merge(no_amba, ADI_NODES, tmp_path, "noamba")
    assert "adi,axi-jesd204-rx-1.0" in merged
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest test/xsa/test_merger.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement DtsMerger**

```python
# adidt/xsa/merger.py
import logging
import re
import subprocess
import warnings
from pathlib import Path
from typing import Any

_LABEL_RE = re.compile(r"^\s*(\w+)\s*:\s*\w+", re.MULTILINE)
_NODE_ADDR_RE = re.compile(r"@([0-9a-fA-F]+)\s*\{")
_log = logging.getLogger(__name__)


class DtsMerger:
    """Merges ADI DTS node strings into a base DTS, producing overlay and merged outputs."""

    def merge(
        self,
        base_dts: str,
        nodes: dict[str, list[str]],
        output_dir: Path,
        name: str,
    ) -> tuple[str, str]:
        """Produce overlay (.dtso) and merged (.dts) and write files.

        Returns:
            (overlay_content, merged_content)
        """
        all_nodes = (
            nodes.get("jesd204_rx", [])
            + nodes.get("jesd204_tx", [])
            + nodes.get("converters", [])
        )
        overlay = self._build_overlay(base_dts, all_nodes)
        merged = self._build_merged(base_dts, all_nodes)

        (output_dir / f"{name}.dtso").write_text(overlay)
        merged_path = output_dir / f"{name}.dts"
        merged_path.write_text(merged)
        self._try_compile_dtb(merged_path)

        return overlay, merged

    def _scan_labels(self, dts: str) -> set[str]:
        return set(_LABEL_RE.findall(dts))

    def _bus_label(self, labels: set[str]) -> str | None:
        if "amba" in labels:
            return "amba"
        for label in sorted(labels):
            if label not in {"root"}:
                return label
        return None

    def _build_overlay(self, base_dts: str, all_nodes: list[str]) -> str:
        bus = self._bus_label(self._scan_labels(base_dts))
        lines = ["/dts-v1/;", "/plugin/;", ""]
        if bus:
            lines += [f"&{bus} {{"] + all_nodes + ["};"]
        else:
            lines += all_nodes
        return "\n".join(lines) + "\n"

    def _build_merged(self, base_dts: str, all_nodes: list[str]) -> str:
        merged = base_dts

        # Replace conflicting address stubs
        for node in all_nodes:
            m = _NODE_ADDR_RE.search(node)
            if m:
                addr = m.group(1).lower()
                conflict_re = re.compile(
                    r"[ \t]+\w[\w-]*@" + re.escape(addr) + r"\s*\{[^}]*\};",
                    re.DOTALL,
                )
                if conflict_re.search(merged):
                    warnings.warn(
                        f"Replaced existing base node at address 0x{addr} with ADI node",
                        UserWarning,
                        stacklevel=2,
                    )
                    merged = conflict_re.sub("", merged)

        nodes_block = "\n".join(all_nodes) + "\n"
        bus = self._bus_label(self._scan_labels(merged))

        if bus and f"{bus}:" in merged:
            pattern = re.compile(
                r"(\s*" + re.escape(bus) + r"\s*:.*?\{)(.*?)(\n\s*\};)",
                re.DOTALL,
            )
            new_merged = pattern.sub(
                lambda m: m.group(1) + m.group(2) + "\n" + nodes_block + m.group(3),
                merged,
                count=1,
            )
            if new_merged != merged:
                return new_merged
            warnings.warn(
                f"Could not insert into bus node '{bus}'; appending at root level",
                UserWarning,
                stacklevel=2,
            )
        else:
            warnings.warn(
                "No amba/axi bus label found; appending ADI nodes at root level",
                UserWarning,
                stacklevel=2,
            )

        return merged.rstrip() + "\n\n" + nodes_block

    def _try_compile_dtb(self, dts_path: Path) -> None:
        dtb_path = dts_path.with_suffix(".dtb")
        try:
            result = subprocess.run(
                ["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb_path), str(dts_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                _log.warning("dtc compilation failed: %s", result.stderr)
        except FileNotFoundError:
            _log.info("dtc not found on PATH; skipping DTB compilation")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest test/xsa/test_merger.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/merger.py test/xsa/test_merger.py
git commit -m "feat(xsa): add DtsMerger producing overlay and merged DTS output"
```

---

## Chunk 5: HTML Visualizer and D3 Embedding

### Task 8: D3 embedding script and bundle

**Files:**
- Create: `scripts/embed_d3.py`
- Create: `adidt/xsa/d3_bundle.js` (populated by script)

- [ ] **Step 1: Create `scripts/embed_d3.py`**

```python
#!/usr/bin/env python3
# scripts/embed_d3.py
"""Download and inline D3.js v7.9.0 into adidt/xsa/d3_bundle.js.

Run once (or to update the pinned version):
    python scripts/embed_d3.py
"""
import urllib.request
from pathlib import Path

D3_URL = "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"
OUTPUT = Path(__file__).parent.parent / "adidt" / "xsa" / "d3_bundle.js"


def main():
    print(f"Downloading D3.js from {D3_URL}...")
    with urllib.request.urlopen(D3_URL) as resp:
        content = resp.read().decode("utf-8")
    OUTPUT.write_text(content)
    print(f"Written {len(content)} bytes to {OUTPUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script to populate the bundle**

```bash
cd /home/tcollins/dev/pyadi-dt-xsa-powers
python scripts/embed_d3.py
```

Expected: "Written N bytes to .../adidt/xsa/d3_bundle.js"

- [ ] **Step 3: Commit**

```bash
git add scripts/embed_d3.py adidt/xsa/d3_bundle.js
git commit -m "feat(xsa): add D3.js v7.9.0 bundle and embed script for HTML visualizer"
```

---

### Task 9: HTML visualizer

**Files:**
- Create: `adidt/xsa/visualizer.py`
- Create: `test/xsa/test_visualizer.py`

- [ ] **Step 1: Write failing smoke tests**

```python
# test/xsa/test_visualizer.py
from pathlib import Path
import pytest
from adidt.xsa.topology import XsaTopology, Jesd204Instance, ClkgenInstance, ConverterInstance
from adidt.xsa.visualizer import HtmlVisualizer


@pytest.fixture
def topo():
    return XsaTopology(
        jesd204_rx=[Jesd204Instance(
            name="axi_jesd204_rx_0", base_addr=0x44A90000,
            num_lanes=4, irq=54, link_clk="jesd_rx_device_clk", direction="rx",
        )],
        jesd204_tx=[Jesd204Instance(
            name="axi_jesd204_tx_0", base_addr=0x44B90000,
            num_lanes=4, irq=55, link_clk="jesd_tx_device_clk", direction="tx",
        )],
        clkgens=[ClkgenInstance(
            name="axi_clkgen_0", base_addr=0x43C00000,
            output_clks=["jesd_rx_device_clk"],
        )],
        converters=[ConverterInstance(
            name="axi_ad9081_0", ip_type="axi_ad9081",
            base_addr=0x44A00000, spi_bus=None, spi_cs=None,
        )],
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
    import adidt.xsa.visualizer as vis_mod
    monkeypatch.setattr(vis_mod, "_D3_BUNDLE", "")
    with pytest.raises(RuntimeError, match="D3 bundle missing"):
        HtmlVisualizer().generate(topo, cfg, merged_dts, tmp_path, "fail")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest test/xsa/test_visualizer.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement HtmlVisualizer**

```python
# adidt/xsa/visualizer.py
import json
import re
from pathlib import Path
from typing import Any

from .topology import XsaTopology

_D3_BUNDLE_PATH = Path(__file__).parent / "d3_bundle.js"
_D3_BUNDLE = _D3_BUNDLE_PATH.read_text() if _D3_BUNDLE_PATH.exists() else ""


class HtmlVisualizer:
    """Generates a self-contained interactive HTML report."""

    def generate(
        self,
        topology: XsaTopology,
        cfg: dict[str, Any],
        merged_dts: str,
        output_dir: Path,
        name: str,
    ) -> str:
        if not _D3_BUNDLE:
            raise RuntimeError(
                "D3 bundle missing — run scripts/embed_d3.py to generate "
                "adidt/xsa/d3_bundle.js"
            )
        tree_data = self._dts_to_tree(merged_dts)
        clock_data = self._build_clock_data(topology, cfg)
        jesd_data = self._build_jesd_data(topology)
        html = self._render_html(tree_data, clock_data, jesd_data, name)
        (output_dir / f"{name}_report.html").write_text(html)
        return html

    def _dts_to_tree(self, dts: str) -> list[dict]:
        return [
            {"name": f"{m.group(1)}@{m.group(2)}", "addr": m.group(2)}
            for m in re.finditer(r"(\w[\w-]*)@([0-9a-fA-F]+)\s*\{", dts)
        ]

    def _build_clock_data(self, topology: XsaTopology, cfg: dict) -> dict:
        clock_cfg = cfg.get("clock", {})
        return {
            "clkgens": [{"name": cg.name, "outputs": cg.output_clks} for cg in topology.clkgens],
            "hmc_rx_ch": clock_cfg.get("hmc7044_rx_channel", "?"),
            "hmc_tx_ch": clock_cfg.get("hmc7044_tx_channel", "?"),
        }

    def _build_jesd_data(self, topology: XsaTopology) -> dict:
        return {
            "rx": [{"name": i.name, "addr": hex(i.base_addr), "lanes": i.num_lanes} for i in topology.jesd204_rx],
            "tx": [{"name": i.name, "addr": hex(i.base_addr), "lanes": i.num_lanes} for i in topology.jesd204_tx],
            "converters": [{"name": c.name, "type": c.ip_type} for c in topology.converters],
        }

    def _render_html(self, tree_data, clock_data, jesd_data, title: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>ADI DTS Report: {title}</title>
<style>
body{{font-family:monospace;background:#1e1e1e;color:#d4d4d4;margin:0}}
.panel{{padding:1em;border-bottom:1px solid #444}}
h2{{color:#569cd6}}
.adi-node{{color:#dcdcaa;font-weight:bold}}
.node-list li{{cursor:pointer;list-style:none;padding:2px 4px}}
.node-list li:hover{{background:#2d2d2d}}
#clock-svg,#jesd-svg{{width:100%;height:300px}}
.search{{background:#252526;color:#d4d4d4;border:1px solid #555;padding:4px;width:300px}}
</style></head>
<body>
<div class="panel"><h2>DTS Node Tree — {title}</h2>
<input class="search" type="text" id="search" placeholder="Search nodes..." oninput="filterNodes()">
<ul class="node-list" id="node-list"></ul></div>
<div class="panel"><h2>Clock Topology</h2><svg id="clock-svg"></svg></div>
<div class="panel"><h2>JESD204 Data Path</h2><svg id="jesd-svg"></svg></div>
<script>
{_D3_BUNDLE}
</script>
<script>
const treeData={json.dumps(tree_data)};
const clockData={json.dumps(clock_data)};
const jesdData={json.dumps(jesd_data)};
function renderTree(data){{
  const list=document.getElementById("node-list");
  list.innerHTML="";
  data.forEach(n=>{{
    const li=document.createElement("li");
    const isAdi=n.name.includes("jesd")||n.name.includes("ad9081")||n.name.includes("ad9084");
    li.className=isAdi?"adi-node":"";
    li.textContent=n.name;
    list.appendChild(li);
  }});
}}
function filterNodes(){{
  const q=document.getElementById("search").value.toLowerCase();
  renderTree(treeData.filter(n=>n.name.toLowerCase().includes(q)));
}}
renderTree(treeData);
(function(){{
  const svg=d3.select("#clock-svg");
  const bW=160,bH=40,gap=20;
  (clockData.clkgens||[]).forEach((cg,i)=>{{
    const x=gap+i*(bW+gap);
    svg.append("rect").attr("x",x).attr("y",10).attr("width",bW).attr("height",bH).attr("fill","#264f78").attr("stroke","#569cd6");
    svg.append("text").attr("x",x+bW/2).attr("y",35).attr("text-anchor","middle").attr("fill","#d4d4d4").attr("font-size","11px").text(cg.name);
    (cg.outputs||[]).forEach((out,j)=>{{
      svg.append("text").attr("x",x+bW/2).attr("y",75+j*18).attr("text-anchor","middle").attr("fill","#9cdcfe").attr("font-size","10px").text(out);
    }});
  }});
}})();
(function(){{
  const svg=d3.select("#jesd-svg");
  const bW=180,bH=50,gap=30,y=20;
  const boxes=[...jesdData.rx.map(r=>{{return{{...r,kind:"RX"}}}}),
               ...jesdData.converters.map(c=>{{return{{...c,kind:"CONV"}}}}),
               ...jesdData.tx.map(t=>{{return{{...t,kind:"TX"}}}})];
  boxes.forEach((b,i)=>{{
    const x=gap+i*(bW+gap);
    const color=b.kind==="RX"?"#1e4d78":b.kind==="TX"?"#4d1e78":"#264f1e";
    svg.append("rect").attr("x",x).attr("y",y).attr("width",bW).attr("height",bH).attr("fill",color).attr("stroke","#569cd6");
    svg.append("text").attr("x",x+bW/2).attr("y",y+20).attr("text-anchor","middle").attr("fill","#d4d4d4").attr("font-size","11px").text(b.name||b.type);
    svg.append("text").attr("x",x+bW/2).attr("y",y+38).attr("text-anchor","middle").attr("fill","#9cdcfe").attr("font-size","10px").text(b.lanes?b.lanes+" lanes":b.kind);
    if(i>0)svg.append("line").attr("x1",x-gap).attr("y1",y+bH/2).attr("x2",x).attr("y2",y+bH/2).attr("stroke","#569cd6");
  }});
}})();
</script></body></html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest test/xsa/test_visualizer.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/visualizer.py test/xsa/test_visualizer.py
git commit -m "feat(xsa): add self-contained HTML visualizer with D3 tree/clock/JESD panels"
```

---

## Chunk 6: Pipeline Orchestrator and CLI

### Task 10: Pipeline orchestrator

**Files:**
- Create: `adidt/xsa/pipeline.py`
- Create: `test/xsa/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# test/xsa/test_pipeline.py
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
import pytest

from adidt.xsa.pipeline import XsaPipeline

FIXTURE_HWH = Path(__file__).parent / "fixtures" / "ad9081_zcu102.hwh"
FIXTURE_CFG = Path(__file__).parent / "fixtures" / "ad9081_config.json"


@pytest.fixture
def xsa_path(tmp_path):
    xsa = tmp_path / "design.xsa"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.write(FIXTURE_HWH, "design.hwh")
    xsa.write_bytes(buf.getvalue())
    return xsa


@pytest.fixture
def cfg():
    return json.loads(FIXTURE_CFG.read_text())


def _fake_sdtgen_run(xsa_path, output_dir, timeout=120):
    dts = output_dir / "system-top.dts"
    dts.write_text("/dts-v1/;\n/ {\n\tamba: axi {\n\t\t#address-cells = <2>;\n\t};\n};\n")
    return dts


def test_pipeline_produces_overlay_and_merged(xsa_path, cfg, tmp_path):
    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        result = XsaPipeline().run(xsa_path, cfg, tmp_path)
    assert result["overlay"].exists()
    assert result["merged"].exists()
    assert result["report"].exists()


def test_pipeline_output_names_derived_from_converter(xsa_path, cfg, tmp_path):
    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        result = XsaPipeline().run(xsa_path, cfg, tmp_path)
    assert "ad9081" in result["overlay"].name
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest test/xsa/test_pipeline.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement XsaPipeline**

```python
# adidt/xsa/pipeline.py
import re
from pathlib import Path
from typing import Any

from .sdtgen import SdtgenRunner
from .topology import XsaParser
from .node_builder import NodeBuilder
from .merger import DtsMerger
from .visualizer import HtmlVisualizer

_PART_TO_PLATFORM = {
    "xczu9eg": "zcu102",
    "xczu3eg": "zcu104",
    "xck26": "kv260",
    "xcvp1202": "vpk180",
    "xc7z045": "zc706",
    "xc7z020": "zc702",
}


class XsaPipeline:
    """Orchestrates the five-stage XSA-to-DeviceTree pipeline."""

    def run(
        self,
        xsa_path: Path,
        cfg: dict[str, Any],
        output_dir: Path,
        sdtgen_timeout: int = 120,
    ) -> dict[str, Path]:
        """Run the full pipeline.

        Returns:
            Dict with keys: "base_dir", "overlay", "merged", "report"
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        base_dir = output_dir / "base"
        base_dir.mkdir(exist_ok=True)

        base_dts_path = SdtgenRunner().run(xsa_path, base_dir, timeout=sdtgen_timeout)
        base_dts = base_dts_path.read_text()

        topology = XsaParser().parse(xsa_path)
        name = self._derive_name(topology)
        nodes = NodeBuilder().build(topology, cfg)
        _, merged_content = DtsMerger().merge(base_dts, nodes, output_dir, name)
        HtmlVisualizer().generate(topology, cfg, merged_content, output_dir, name)

        return {
            "base_dir": base_dir,
            "overlay": output_dir / f"{name}.dtso",
            "merged": output_dir / f"{name}.dts",
            "report": output_dir / f"{name}_report.html",
        }

    def _derive_name(self, topology) -> str:
        conv_type = "unknown"
        if topology.converters:
            conv_type = re.sub(r"^axi_", "", topology.converters[0].ip_type)
        platform = "unknown"
        for prefix, plat_name in _PART_TO_PLATFORM.items():
            if topology.fpga_part.lower().startswith(prefix):
                platform = plat_name
                break
        return f"{conv_type}_{platform}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest test/xsa/test_pipeline.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/pipeline.py test/xsa/test_pipeline.py
git commit -m "feat(xsa): add XsaPipeline orchestrator wiring all five stages"
```

---

### Task 11: CLI command and pyproject.toml updates

**Files:**
- Modify: `adidt/cli/main.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `xsa2dt` command** — append to `adidt/cli/main.py` before the final line

Note: `json` and `Path` are already imported at the top of `main.py`. Do not re-import them.

```python
@cli.command("xsa2dt")
@click.option("--xsa", "-x", required=True, type=click.Path(exists=True),
              help="Path to Vivado .xsa file")
@click.option("--config", "-c", required=True, type=click.Path(exists=True),
              help="Path to pyadi-jif JSON configuration file")
@click.option("--output", "-o", default="./generated", type=click.Path(), show_default=True,
              help="Output directory")
@click.option("--timeout", "-t", default=120, type=int, show_default=True,
              help="sdtgen subprocess timeout in seconds")
@click.pass_context
def xsa2dt(ctx, xsa, config, output, timeout):
    """Generate ADI device tree from Vivado XSA file

    \b
    Invokes sdtgen against the XSA, detects ADI IPs, generates JESD204
    FSM-compatible nodes, and produces overlay (.dtso), merged (.dts), and
    interactive HTML visualization report.

    \b
    Requires sdtgen (lopper) on PATH.
    Install from: https://github.com/devicetree-org/lopper

    \b
    Examples:
      adidtc xsa2dt -x design_1.xsa -c ad9081_cfg.json
      adidtc xsa2dt -x design_1.xsa -c cfg.json -o ./out --timeout 180
    """
    try:
        from adidt.xsa.pipeline import XsaPipeline
        from adidt.xsa.exceptions import SdtgenNotFoundError, SdtgenError, XsaParseError, ConfigError
    except ImportError:
        click.echo(click.style(
            "Error: xsa support not installed. Run: pip install adidt[xsa]", fg="red"
        ))
        return

    try:
        with open(config, "r") as f:
            cfg = json.load(f)

        result = XsaPipeline().run(Path(xsa), cfg, Path(output), sdtgen_timeout=timeout)

        click.echo(click.style("Done!", fg="green", bold=True))
        click.echo(f"  Overlay:  {result['overlay']}")
        click.echo(f"  Merged:   {result['merged']}")
        click.echo(f"  Report:   {result['report']}")

    except Exception as e:
        from adidt.xsa.exceptions import SdtgenNotFoundError, SdtgenError, XsaParseError, ConfigError
        if isinstance(e, SdtgenNotFoundError):
            click.echo(click.style(str(e), fg="red"))
        elif isinstance(e, SdtgenError):
            click.echo(click.style(f"sdtgen failed: {e}", fg="red"))
            if e.stderr:
                click.echo(e.stderr)
        elif isinstance(e, (XsaParseError, ConfigError)):
            click.echo(click.style(str(e), fg="red"))
        else:
            click.echo(click.style(f"Unexpected error: {e}", fg="red"))
            import traceback
            traceback.print_exc()
```

- [ ] **Step 2: Add `[xsa]` optional deps** to `pyproject.toml`

In `pyproject.toml` under `[project.optional-dependencies]`, after the `dev` block, add:

```toml
xsa = ["lopper"]
```

- [ ] **Step 3: Run full test suite to verify no regressions**

```bash
cd /home/tcollins/dev/pyadi-dt-xsa-powers
pytest test/ -v --ignore=test/hw
```

Expected: all PASSED — no failures in existing tests, all new xsa/ tests pass.

- [ ] **Step 4: Verify CLI command is discoverable**

```bash
pip install -e . && adidtc xsa2dt --help
```

Expected: help text showing `--xsa`, `--config`, `--output`, `--timeout` options.

- [ ] **Step 5: Commit**

```bash
git add adidt/cli/main.py pyproject.toml
git commit -m "feat(xsa): add adidtc xsa2dt CLI command and [xsa] optional dependency group"
```

---

## File Summary

| File | Action | Purpose |
|------|--------|---------|
| `adidt/xsa/__init__.py` | Create | Package marker |
| `adidt/xsa/exceptions.py` | Create | Custom exceptions |
| `adidt/xsa/sdtgen.py` | Create | Stage 1: sdtgen subprocess wrapper |
| `adidt/xsa/topology.py` | Create | Stage 2: dataclasses + `XsaParser` (all in one file) |
| `adidt/xsa/node_builder.py` | Create | Stage 3: `NodeBuilder` |
| `adidt/xsa/merger.py` | Create | Stage 4: `DtsMerger` |
| `adidt/xsa/visualizer.py` | Create | Stage 5: `HtmlVisualizer` |
| `adidt/xsa/d3_bundle.js` | Create (script) | Embedded D3.js v7.9.0 |
| `adidt/xsa/pipeline.py` | Create | `XsaPipeline` orchestrator |
| `adidt/templates/xsa/jesd204_fsm.tmpl` | Create | JESD204 FSM node template |
| `adidt/templates/xsa/axi_ad9081.tmpl` | Create | AD9081 converter node template |
| `adidt/cli/main.py` | Modify | Add `xsa2dt` subcommand |
| `pyproject.toml` | Modify | Package-data for xsa templates + `[xsa]` deps |
| `scripts/embed_d3.py` | Create | D3.js download/embed utility |
| `test/xsa/__init__.py` | Create | Test package marker |
| `test/xsa/fixtures/ad9081_zcu102.hwh` | Create | `.hwh` fixture for topology tests |
| `test/xsa/fixtures/ad9081_config.json` | Create | pyadi-jif JSON fixture |
| `test/xsa/test_exceptions.py` | Create | Exception tests |
| `test/xsa/test_sdtgen.py` | Create | sdtgen wrapper tests (7 tests) |
| `test/xsa/test_topology.py` | Create | Dataclass + parser tests (11 tests) |
| `test/xsa/test_node_builder.py` | Create | Node builder tests |
| `test/xsa/test_merger.py` | Create | Merger tests |
| `test/xsa/test_visualizer.py` | Create | Visualizer smoke tests |
| `test/xsa/test_pipeline.py` | Create | Pipeline orchestrator tests |
