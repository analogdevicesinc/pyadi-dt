"""Typed MDD-style contract loader for SDT Tcl drivers."""

from __future__ import annotations

import base64
import shutil
# The only child process is an absolute, shutil-resolved tclsh executable with
# an argv list and shell=False.
import subprocess  # nosec B404
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ALLOWED_PROPERTY_TYPES = {
    "aliasref",
    "boolean",
    "hexint",
    "hexlist",
    "int",
    "intlist",
    "noformating",
    "phandle-array",
    "reference",
    "reg",
    "string",
    "stringlist",
}
_REQUIRED_KEYS = {
    "schema_version",
    "name",
    "supported_ip_names",
    "supported_vlnv_globs",
    "generator_proc",
    "output_files",
    "architectures",
    "required_hsi_properties",
    "required_interfaces",
    "compatibles",
    "binding",
    "binding_format",
    "emitted_properties",
}


class SdtDriverDefinition(BaseModel):
    """Machine-readable contract exposed by one SDT Tcl driver."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(ge=1, le=1)
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    supported_ip_names: tuple[str, ...]
    supported_vlnv_globs: tuple[str, ...]
    generator_proc: str
    output_files: tuple[str, ...]
    architectures: tuple[str, ...]
    required_hsi_properties: tuple[str, ...]
    required_interfaces: tuple[str, ...]
    compatibles: tuple[str, ...]
    binding: str
    binding_format: str
    emitted_properties: dict[str, str]

    @field_validator(
        "supported_ip_names",
        "supported_vlnv_globs",
        "output_files",
        "architectures",
        "compatibles",
    )
    @classmethod
    def _must_not_be_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("binding_format")
    @classmethod
    def _valid_binding_format(cls, value: str) -> str:
        if value not in {"yaml", "legacy-text"}:
            raise ValueError("binding_format must be 'yaml' or 'legacy-text'")
        return value

    @field_validator("emitted_properties")
    @classmethod
    def _valid_property_types(cls, value: dict[str, str]) -> dict[str, str]:
        invalid = sorted(set(value.values()) - _ALLOWED_PROPERTY_TYPES)
        if invalid:
            raise ValueError(f"unsupported SDT property types: {invalid}")
        return value


_HARNESS = r"""
set driver_file [lindex $argv 0]
set definition_proc [lindex $argv 1]
source $driver_file
if {[llength [info procs $definition_proc]] != 1} {
    error "definition proc not found: $definition_proc"
}
set definition [$definition_proc]
set list_keys {
    supported_ip_names supported_vlnv_globs output_files architectures
    required_hsi_properties required_interfaces compatibles
}
foreach key [lsort [dict keys $definition]] {
    set value [dict get $definition $key]
    if {$key in $list_keys || $key eq "emitted_properties"} {
        set value [join $value \u001f]
    }
    set encoded [binary encode base64 -maxlen 0 $value]
    puts "$key\t$encoded"
}
set generator [dict get $definition generator_proc]
if {[llength [info procs $generator]] != 1} {
    error "generator proc not found: $generator"
}
"""


def load_tcl_definition(
    path: str | Path, definition_proc: str | None = None
) -> SdtDriverDefinition:
    """Load and validate an SDT definition through stock ``tclsh``."""
    driver_path = Path(path).resolve()
    if not driver_path.is_file():
        raise FileNotFoundError(driver_path)
    tclsh = shutil.which("tclsh")
    if tclsh is None:
        raise RuntimeError("tclsh is required to inspect SDT driver definitions")
    proc = definition_proc or f"::adidt::sdt::{driver_path.stem}::definition"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".tcl", encoding="utf-8"
    ) as harness:
        harness.write(_HARNESS)
        harness.flush()
        result = subprocess.run(  # nosec B603
            [tclsh, harness.name, str(driver_path), proc],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"failed to load SDT Tcl definition {driver_path}: {detail}")

    raw: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, encoded = line.partition("\t")
        if not separator:
            raise ValueError(f"malformed definition output: {line!r}")
        raw[key] = base64.b64decode(encoded).decode()
    missing = sorted(_REQUIRED_KEYS - raw.keys())
    if missing:
        raise ValueError(f"definition is missing required keys: {missing}")

    list_keys = {
        "supported_ip_names",
        "supported_vlnv_globs",
        "output_files",
        "architectures",
        "required_hsi_properties",
        "required_interfaces",
        "compatibles",
    }
    data: dict[str, object] = dict(raw)
    data["schema_version"] = int(raw["schema_version"])
    for key in list_keys:
        data[key] = tuple(raw[key].split("\x1f")) if raw[key] else ()
    prop_items = tuple(raw["emitted_properties"].split("\x1f"))
    if len(prop_items) % 2:
        raise ValueError("emitted_properties must be a Tcl dict")
    data["emitted_properties"] = dict(zip(prop_items[::2], prop_items[1::2]))
    return SdtDriverDefinition.model_validate(data)
