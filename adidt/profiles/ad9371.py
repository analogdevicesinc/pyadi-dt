"""Parse AD9371 profile-wizard files and render Linux DT properties."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HEADER_RE = re.compile(
    r"<profile\s+(?P<device>\S+)\s+version=(?P<version>\S+)\s+name=(?P<name>.*?)>",
    re.IGNORECASE,
)
_SECTION_RE = re.compile(
    r"<(?P<name>clocks|rx|obs|tx)\b[^>]*>(?P<body>.*?)</(?P=name)>",
    re.DOTALL | re.IGNORECASE,
)
_SCALAR_RE = re.compile(r"^<([A-Za-z0-9_]+)\s*=\s*([^>]+)>$")
_ATTR_RE = re.compile(r"([A-Za-z0-9_-]+)=([^\s>]+)")

_CLOCK_KEYS = {
    "clkPllVcoFreq_kHz": "adi,clocks-clk-pll-vco-freq_khz",
    "deviceClock_kHz": "adi,clocks-device-clock_khz",
    "clkPllHsDiv": "adi,clocks-clk-pll-hs-div",
    "clkPllVcoDiv": "adi,clocks-clk-pll-vco-div",
}
_RX_KEYS = {
    "adcDiv": "adc-div",
    "enHighRejDec5": "en-high-rej-dec5",
    "iqRate_kHz": "iq-rate_khz",
    "rfBandwidth_Hz": "rf-bandwidth_hz",
    "rhb1Decimation": "rhb1-decimation",
    "rxBbf3dBCorner_kHz": "rx-bbf-3db-corner_khz",
    "rxDec5Decimation": "rx-dec5-decimation",
    "rxFirDecimation": "rx-fir-decimation",
}
_TX_KEYS = {
    "dacDiv": "dac-div",
    "iqRate_kHz": "iq-rate_khz",
    "primarySigBandwidth_Hz": "primary-sig-bandwidth_hz",
    "rfBandwidth_Hz": "rf-bandwidth_hz",
    "thb1Interpolation": "thb1-interpolation",
    "thb2Interpolation": "thb2-interpolation",
    "txBbf3dBCorner_kHz": "tx-bbf-3db-corner_khz",
    "txDac3dBCorner_kHz": "tx-dac-3db-corner_khz",
    "txFirInterpolation": "tx-fir-interpolation",
    "txInputHbInterpolation": "tx-input-hb-interpolation",
}
_SNIFFER_DEFAULTS = {
    "adc-div": 1,
    "en-high-rej-dec5": 0,
    "iq-rate_khz": 30_720,
    "rf-bandwidth_hz": 20_000_000,
    "rhb1-decimation": 2,
    "rx-bbf-3db-corner_khz": 100_000,
    "rx-dec5-decimation": 5,
    "rx-fir-decimation": 4,
}


def _number(value: str) -> int | float | str:
    value = value.strip()
    try:
        number = float(value) if "." in value else int(value)
    except ValueError:
        return value
    return int(number) if isinstance(number, float) and number.is_integer() else number


def _scalars(body: str) -> dict[str, int | float | str]:
    result: dict[str, int | float | str] = {}
    for line in body.splitlines():
        match = _SCALAR_RE.match(line.strip())
        if match:
            result[match.group(1)] = _number(match.group(2))
    return result


def _arrays(body: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    patterns = {
        "filter": re.compile(
            r"<filter\s+FIR\s+(?P<attrs>[^>]*)>(?P<body>.*?)</filter>",
            re.DOTALL | re.IGNORECASE,
        ),
        "adc-profile": re.compile(
            r"<adc-profile\s+(?P<attrs>[^>]*)>(?P<body>.*?)</adc-profile>",
            re.DOTALL | re.IGNORECASE,
        ),
        "lpbk-adc-profile": re.compile(
            r"<lpbk-adc-profile\s+(?P<attrs>[^>]*)>"
            r"(?P<body>.*?)</lpbk-adc-profile>",
            re.DOTALL | re.IGNORECASE,
        ),
    }
    for key, pattern in patterns.items():
        match = pattern.search(body)
        if match is None:
            continue
        attrs = {
            name: _number(value)
            for name, value in _ATTR_RE.findall(match.group("attrs"))
        }
        values = [
            int(line.strip())
            for line in match.group("body").splitlines()
            if line.strip()
        ]
        declared = attrs.get("num")
        if declared is not None and declared != len(values):
            raise ValueError(
                f"AD9371 {key} declares {declared} values but contains {len(values)}"
            )
        result[key] = {"attrs": attrs, "values": values}
    return result


def _cell(value: int) -> str:
    return f"0x{value & 0xFFFFFFFF:02x}"


def _statement(name: str, value: int) -> str:
    return f"{name} = <{_cell(value)}>;"


def _integer(value: int | float, field: str) -> int:
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"AD9371 profile field {field} must be an integer")
    return int(value)


def _packed_cells(values: list[int]) -> str:
    for value in values:
        if not -0x8000 <= value <= 0x7FFF:
            raise ValueError(
                f"AD9371 profile coefficient {value} is outside signed 16-bit range"
            )
    padded = values + ([0] if len(values) % 2 else [])
    cells = [
        ((padded[index] & 0xFFFF) << 16) | (padded[index + 1] & 0xFFFF)
        for index in range(0, len(padded), 2)
    ]
    return " ".join(_cell(value) for value in cells)


@dataclass(frozen=True)
class AD9371Profile:
    """Parsed AD9371 profile with DT rendering support."""

    name: str
    version: int | float | str
    sections: dict[str, dict[str, Any]]

    def _section_props(self, section: str) -> list[str]:
        data = self.sections[section]
        prefix = f"adi,{section}-profile"
        key_map = _RX_KEYS if section in ("rx", "obs") else _TX_KEYS
        props: list[str] = []
        for source, target in key_map.items():
            if source not in data["scalars"]:
                raise ValueError(f"AD9371 {section} section is missing {source}")
            value = data["scalars"][source]
            if source == "dacDiv":
                if value != 2.5:
                    raise ValueError(f"Unsupported AD9371 dacDiv value: {value}")
                value = 1  # Linux mykonos driver enum for DAC divider 2.5.
            props.append(_statement(f"{prefix}-{target}", _integer(value, source)))

        filt = data["arrays"].get("filter")
        if filt is None:
            raise ValueError(f"AD9371 {section} section is missing FIR filter data")
        stem = "tx-fir" if section == "tx" else "rx-fir"
        props.extend(
            [
                _statement(
                    f"{prefix}-{stem}-gain_db",
                    _integer(filt["attrs"].get("gain", 0), f"{section} FIR gain"),
                ),
                _statement(f"{prefix}-{stem}-num-fir-coefs", len(filt["values"])),
                f"{prefix}-{stem}-coefs = <{_packed_cells(filt['values'])}>;",
            ]
        )

        if section in ("rx", "obs"):
            adc = data["arrays"].get("adc-profile")
            if adc is None:
                raise ValueError(f"AD9371 {section} section is missing adc-profile")
            props.append(
                f"{prefix}-custom-adc-profile = <{_packed_cells(adc['values'])}>;"
            )
        if section == "obs":
            loopback = data["arrays"].get("lpbk-adc-profile")
            if loopback is None:
                raise ValueError("AD9371 obs section is missing lpbk-adc-profile")
            props.append(
                "adi,obs-settings-custom-loopback-adc-profile = "
                f"<{_packed_cells(loopback['values'])}>;"
            )
        return props

    def to_dt_properties(self, *, include_sniffer_defaults: bool = True) -> list[str]:
        """Render the profile as AD9371 Linux devicetree statements."""
        clocks = self.sections["clocks"]["scalars"]
        props = [
            _statement(target, _integer(clocks[source], source))
            for source, target in _CLOCK_KEYS.items()
            if source in clocks
        ]
        if len(props) != len(_CLOCK_KEYS):
            missing = sorted(set(_CLOCK_KEYS) - set(clocks))
            raise ValueError(f"AD9371 clocks section is missing: {', '.join(missing)}")
        props.append(_statement("adi,jesd204-obs-framer-over-sample", 0))
        props.extend(self._section_props("rx"))
        props.extend(self._section_props("obs"))
        props.extend(self._section_props("tx"))
        if include_sniffer_defaults:
            props.extend(
                _statement(f"adi,sniffer-profile-{name}", value)
                for name, value in _SNIFFER_DEFAULTS.items()
            )
        return props


def parse_ad9371_profile(path: str | Path) -> AD9371Profile:
    """Parse one canonical AD9371 text profile."""
    profile_path = Path(path)
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile file not found: {profile_path}")
    text = profile_path.read_text(encoding="utf-8")
    header = _HEADER_RE.search(text)
    if not header or header.group("device").upper() != "AD9371":
        raise ValueError(f"Not an AD9371 profile: {profile_path}")
    version = _number(header.group("version"))
    if version != 0:
        raise ValueError(f"Unsupported AD9371 profile version: {version}")

    sections: dict[str, dict[str, Any]] = {}
    for match in _SECTION_RE.finditer(text):
        name = match.group("name").lower()
        if name in sections:
            raise ValueError(f"AD9371 profile has duplicate {name} section")
        body = match.group("body")
        sections[name] = {
            "scalars": _scalars(body),
            "arrays": _arrays(body),
        }
    missing = [name for name in ("clocks", "rx", "obs", "tx") if name not in sections]
    if missing:
        raise ValueError(f"AD9371 profile is missing: {', '.join(missing)}")
    return AD9371Profile(
        name=header.group("name").strip(),
        version=version,
        sections=sections,
    )
