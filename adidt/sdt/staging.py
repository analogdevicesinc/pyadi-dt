"""Stage pyadi-dt Tcl drivers into an isolated SDT repository."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .definitions import load_tcl_definition

_SW_REGISTRY_ANCHOR = "\tdict set driverlist axi_dma driver axi_dma\n"
_COMMON_REGISTRY_ANCHOR = "\tdict set driverlist axi_dma driver axi_dma\n"
_SDT_REGISTRY_ANCHOR = '\tdict set ::sdtgen::namespacelist "axi_dma" "axi_dma"\n'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_sdt_repository(
    upstream: str | Path,
    output: str | Path,
    drivers_root: str | Path,
) -> Path:
    """Copy a complete SDT repository, install drivers, and patch dispatch."""
    source = Path(upstream).resolve()
    destination = Path(output).resolve()
    driver_source = Path(drivers_root).resolve()
    sw_registry_relative = Path("device_tree/data/xillib_sw.tcl")
    common_registry_relative = Path("device_tree/data/common_proc.tcl")
    sdt_registry_relative = Path("device_tree/data/device_tree.tcl")
    if not all(
        (source / path).is_file()
        for path in (
            sw_registry_relative,
            common_registry_relative,
            sdt_registry_relative,
        )
    ):
        raise ValueError(f"not a complete system-device-tree-xlnx checkout: {source}")
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git"))

    mappings: dict[str, str] = {}
    files: list[dict[str, str]] = []
    for tcl_path in sorted(driver_source.glob("*/data/*.tcl")):
        definition = load_tcl_definition(tcl_path)
        if tcl_path.stem != definition.name:
            raise ValueError(
                f"driver filename {tcl_path.stem!r} does not match {definition.name!r}"
            )
        for ip_name in definition.supported_ip_names:
            previous = mappings.setdefault(ip_name, definition.name)
            if previous != definition.name:
                raise ValueError(
                    f"IP {ip_name!r} maps to both {previous!r} and {definition.name!r}"
                )
        relative = Path(definition.name) / "data" / tcl_path.name
        installed = destination / relative
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tcl_path, installed)
        files.append({"path": relative.as_posix(), "sha256": _sha256(installed)})

    sw_registry = destination / sw_registry_relative
    sw_text = sw_registry.read_text()
    if _SW_REGISTRY_ANCHOR not in sw_text:
        raise ValueError("unsupported xillib_sw.tcl registry layout")
    sw_additions: list[str] = []
    for ip_name, driver in sorted(mappings.items()):
        line = f"\tdict set driverlist {ip_name} driver {driver}\n"
        if line not in sw_text:
            sw_additions.append(line)
    sw_text = sw_text.replace(
        _SW_REGISTRY_ANCHOR,
        _SW_REGISTRY_ANCHOR + "".join(sw_additions),
        1,
    )
    sw_registry.write_text(sw_text)

    common_registry = destination / common_registry_relative
    common_text = common_registry.read_text()
    if _COMMON_REGISTRY_ANCHOR not in common_text:
        raise ValueError("unsupported common_proc.tcl driver registry layout")
    common_additions: list[str] = []
    for ip_name, driver in sorted(mappings.items()):
        line = f"\tdict set driverlist {ip_name} driver {driver}\n"
        if line not in common_text:
            common_additions.append(line)
    common_text = common_text.replace(
        _COMMON_REGISTRY_ANCHOR,
        _COMMON_REGISTRY_ANCHOR + "".join(common_additions),
        1,
    )
    common_registry.write_text(common_text)

    sdt_registry = destination / sdt_registry_relative
    sdt_text = sdt_registry.read_text()
    if _SDT_REGISTRY_ANCHOR not in sdt_text:
        raise ValueError("unsupported device_tree.tcl namespace registry layout")
    sdt_additions: list[str] = []
    for ip_name, driver in sorted(mappings.items()):
        line = f'\tdict set ::sdtgen::namespacelist "{ip_name}" "{driver}"\n'
        if line not in sdt_text:
            sdt_additions.append(line)
    sdt_text = sdt_text.replace(
        _SDT_REGISTRY_ANCHOR,
        _SDT_REGISTRY_ANCHOR + "".join(sdt_additions),
        1,
    )
    sdt_registry.write_text(sdt_text)

    manifest = {
        "schema_version": 1,
        "upstream": str(source),
        "mappings": mappings,
        "files": files,
        "registries": {
            sw_registry_relative.as_posix(): _sha256(sw_registry),
            common_registry_relative.as_posix(): _sha256(common_registry),
            sdt_registry_relative.as_posix(): _sha256(sdt_registry),
        },
    }
    manifest_path = destination / "adidt-sdt-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path
