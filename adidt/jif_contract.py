"""Versioned interface contract between pyadi-jif and pyadi-dt.

The contract carries solved electrical intent.  Physical device-tree placement
(clock channel numbers, labels, SPI chip-selects, and GPIOs) remains owned by
pyadi-dt and is joined through :class:`JifDtBindings`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

CONTRACT_NAME = "adi.jif-dt"
CONTRACT_VERSION = "1.0"


class ContractError(ValueError):
    """Raised when a JIF/DT handoff is incompatible or cannot be bound."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Producer(_StrictModel):
    """Identity of the program that generated the handoff."""

    name: Literal["pyadi-jif"] = "pyadi-jif"
    version: str = Field(min_length=1)


class JesdParameters(_StrictModel):
    """JESD transport parameters shared by converter and FPGA endpoints."""

    F: int = Field(gt=0, strict=True)
    K: int = Field(gt=0, strict=True)
    L: int = Field(gt=0, strict=True)
    M: int = Field(gt=0, strict=True)
    N: int = Field(gt=0, strict=True)
    Np: int = Field(gt=0, strict=True)
    S: int = Field(gt=0, strict=True)
    HD: int = Field(ge=0, le=1, strict=True)
    CS: int = Field(default=0, ge=0, strict=True)
    CF: int = Field(default=0, ge=0, strict=True)

    @model_validator(mode="after")
    def validate_transport_identity(self) -> "JesdParameters":
        # JESD204 transport identity: F = M * S * Np / (8 * L).
        numerator = self.M * self.S * self.Np
        denominator = 8 * self.L
        if numerator != self.F * denominator:
            raise ValueError(
                "inconsistent JESD transport parameters: "
                "M*S*Np must equal 8*L*F"
            )
        return self


class JesdLink(_StrictModel):
    """One solved unidirectional JESD link."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    direction: Literal["adc-to-fpga", "fpga-to-dac"]
    converter: str = Field(min_length=1)
    fpga: str = Field(min_length=1)
    standard: Literal["jesd204b", "jesd204c"]
    sample_rate_hz: int = Field(gt=0, strict=True)
    lane_rate_hz: int = Field(gt=0, strict=True)
    parameters: JesdParameters
    fpga_config: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_lane_rate(self) -> "JesdLink":
        p = self.parameters
        encoding_ratio = (10, 8) if self.standard == "jesd204b" else (66, 64)
        expected_num = self.sample_rate_hz * p.M * p.Np * encoding_ratio[0]
        expected_den = p.L * encoding_ratio[1]
        # Integer-Hz interchange allows one hertz of rounding at the boundary.
        if abs(self.lane_rate_hz * expected_den - expected_num) > expected_den:
            raise ValueError("lane_rate_hz is inconsistent with JESD parameters")
        return self


class ClockRequirement(_StrictModel):
    """A semantic solved clock requirement, not a physical output channel."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    role: Literal[
        "converter-device",
        "converter-sysref",
        "fpga-ref",
        "fpga-link",
        "pll-ref",
        "other",
    ]
    sink: str = Field(min_length=1)
    rate_hz: int = Field(gt=0, strict=True)
    divider: int | None = Field(default=None, gt=0, strict=True)
    source: str = Field(min_length=1)


class JifDtContract(_StrictModel):
    """Portable, versioned result produced by JIF and consumed by DT."""

    schema_name: Literal["adi.jif-dt"] = Field(CONTRACT_NAME, alias="schema")
    version: Literal["1.0"] = CONTRACT_VERSION
    producer: Producer
    jesd_links: tuple[JesdLink, ...]
    clock_requirements: tuple[ClockRequirement, ...]
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "JifDtContract":
        for kind, entries in (
            ("JESD link", self.jesd_links),
            ("clock requirement", self.clock_requirements),
        ):
            ids = [entry.id for entry in entries]
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            if duplicates:
                raise ValueError(f"duplicate {kind} ids: {duplicates}")
        return self

    @classmethod
    def from_json_file(cls, path: str | Path) -> "JifDtContract":
        """Load and validate a contract without mutating any DT state."""
        try:
            payload = json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"cannot read JIF/DT contract: {exc}") from exc
        try:
            return cls.model_validate(payload)
        except ValueError as exc:
            raise ContractError(f"invalid JIF/DT contract: {exc}") from exc

    def to_json_file(self, path: str | Path) -> None:
        """Write deterministic JSON suitable for fixtures and interchange."""
        Path(path).write_text(self.model_dump_json(indent=2, by_alias=True) + "\n")


class ClockBinding(_StrictModel):
    """pyadi-dt-owned placement of one semantic clock onto a DT endpoint."""

    requirement_id: str
    dt_label: str = Field(min_length=1)
    output_index: int = Field(ge=0, strict=True)


class JesdBinding(_StrictModel):
    """pyadi-dt-owned placement of one semantic JESD link onto DT nodes."""

    link_id: str
    converter_label: str = Field(min_length=1)
    jesd_label: str = Field(min_length=1)
    xcvr_label: str = Field(min_length=1)


class JifDtBindings(_StrictModel):
    """Physical pyadi-dt profile bindings for a JIF handoff."""

    clocks: tuple[ClockBinding, ...]
    jesd_links: tuple[JesdBinding, ...]

    def check(self, contract: JifDtContract) -> None:
        """Require complete, unique bindings before any DT is rendered or edited."""
        self._check_set(
            "clock requirement",
            {item.id for item in contract.clock_requirements},
            [item.requirement_id for item in self.clocks],
        )
        self._check_set(
            "JESD link",
            {item.id for item in contract.jesd_links},
            [item.link_id for item in self.jesd_links],
        )
        endpoints = [(item.dt_label, item.output_index) for item in self.clocks]
        duplicates = sorted({item for item in endpoints if endpoints.count(item) > 1})
        if duplicates:
            raise ContractError(f"multiple clocks bound to DT endpoints: {duplicates}")

    @staticmethod
    def _check_set(kind: str, required: set[str], supplied: list[str]) -> None:
        duplicate = sorted({item for item in supplied if supplied.count(item) > 1})
        missing = sorted(required - set(supplied))
        unknown = sorted(set(supplied) - required)
        problems = []
        if missing:
            problems.append(f"missing={missing}")
        if unknown:
            problems.append(f"unknown={unknown}")
        if duplicate:
            problems.append(f"duplicate={duplicate}")
        if problems:
            raise ContractError(f"invalid {kind} bindings: " + ", ".join(problems))
