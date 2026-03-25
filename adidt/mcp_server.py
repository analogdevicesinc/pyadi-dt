"""MCP server exposing pyadi-dt devicetree generation and profile tools."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.profiles import ProfileManager

mcp = FastMCP("pyadi-dt")


@mcp.tool
def generate_devicetree(
    xsa_path: str,
    output_dir: str,
    config_json: str = "{}",
    profile: Optional[str] = None,
    emit_report: bool = True,
    emit_clock_graphs: bool = True,
    sdtgen_timeout: int = 300,
    reference_dts: Optional[str] = None,
    strict_parity: bool = False,
) -> Dict[str, Any]:
    """Generate a devicetree from a Vivado XSA archive.

    Runs the full XsaPipeline: sdtgen -> topology parse -> node build -> merge -> visualize.

    Args:
        xsa_path: Path to the Vivado .xsa archive.
        output_dir: Directory where output files are written.
        config_json: JSON string with configuration (clock, JESD, datapath settings).
            For AD9084-EBZ on VCU118, prefer `profile="ad9084_vcu118"` so the
            MCP path applies the board-specific HMC7044 + AD9084 + ADF4382 defaults.
            Low-level AD9084 overrides can still be passed via `ad9084_board`.
            JESD framing parameters (F/K/M/L/Np/S) are not in the profile and must
            be supplied here (typically from pyadi-jif solve_system output).
        profile: Optional built-in profile name (e.g. "ad9081_zcu102",
            "ad9084_vcu118").
        emit_report: When True, generate an HTML topology report. Defaults to True.
        emit_clock_graphs: When True, generate DOT/D2 clock-tree diagrams.
            Defaults to True.
        sdtgen_timeout: Maximum seconds to wait for sdtgen to finish generating
            the base DTS. Default 300 s — adequate for AD9084+VCU118 XSA processing.
        reference_dts: Optional path to a reference DTS for parity checking. When
            provided, "map" and "coverage" keys are added to the result.
        strict_parity: When True and reference_dts is provided, raise an error if
            the merged DTS is missing required roles, links, or properties.

    Returns:
        Dict with paths to generated artifacts (overlay, merged, report, clock_dot, etc.)
        or an error dict if the operation fails.
    """
    xsa = Path(xsa_path)
    if not xsa.exists():
        return {"error": f"XSA file not found: {xsa_path}"}

    try:
        cfg = json.loads(config_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid config_json: {e}"}

    out = Path(output_dir)
    ref = Path(reference_dts) if reference_dts else None

    try:
        pipeline = XsaPipeline()
        result = pipeline.run(
            xsa_path=xsa,
            cfg=cfg,
            output_dir=out,
            profile=profile,
            emit_report=emit_report,
            emit_clock_graphs=emit_clock_graphs,
            sdtgen_timeout=sdtgen_timeout,
            reference_dts=ref,
            strict_parity=strict_parity,
        )
        serialized = {k: str(v) for k, v in result.items()}

        merged_path = result.get("merged")
        if merged_path is not None:
            serialized["dts_path"] = str(merged_path)

        base_dir = result.get("base_dir")
        if base_dir is not None:
            pl_dtsi = Path(base_dir) / "pl.dtsi"
            if pl_dtsi.exists():
                serialized["pl_dtsi_path"] = str(pl_dtsi)

        return serialized
    except Exception as e:
        return {"error": f"Pipeline failed: {e}"}


@mcp.tool
def list_xsa_profiles() -> list[str]:
    """List all available built-in XSA board profiles.

    Returns:
        Sorted list of profile names (e.g. ["ad9081_zcu102", "adrv9009_zc706", ...]).
    """
    return ProfileManager().list_profiles()


@mcp.tool
def show_xsa_profile(name: str) -> Dict[str, Any]:
    """Show the full configuration for a named XSA board profile.

    Args:
        name: Profile name (e.g. "ad9081_zcu102"). Use list_xsa_profiles to see available names.

    Returns:
        Profile dict with 'defaults' key containing board configuration,
        or an error dict if the profile is not found.
    """
    try:
        return ProfileManager().load(name)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def read_dt_property(
    node_name: str,
    property_name: Optional[str] = None,
    filepath: Optional[str] = None,
) -> Dict[str, Any]:
    """Read a devicetree property from a DTS/DTB file or the running system.

    Args:
        node_name: Name (or compatible string) of the devicetree node to look up.
        property_name: Specific property to read. If omitted, all properties are returned.
        filepath: Path to a .dts or .dtb file. If omitted, reads from the running system (local_sysfs).

    Returns:
        Dict with property values, or an error dict if the node/property is not found.
    """
    try:
        from adidt.dt import dt

        if filepath:
            d = dt(dt_source="local_file", local_dt_filepath=filepath)
        else:
            d = dt(dt_source="local_sysfs")

        # Use fdt-based lookup: find node by name in the parsed tree
        node = None
        if hasattr(d, "fdt") and d.fdt is not None:
            for path, nodes, props in d.fdt.walk():
                if path.endswith("/" + node_name) or path == "/" + node_name:
                    node = d.fdt.get_node(path)
                    break
            # Also try compatible string match
            if node is None:
                node = d.get_node_by_compatible(node_name)

        if node is None:
            return {"error": f"Node not found: {node_name}"}

        # Extract properties from the fdt node
        all_props = {}
        for prop in node.props:
            all_props[prop.name] = str(prop)

        if property_name:
            if property_name in all_props:
                return {"node": node_name, "property": property_name, "value": all_props[property_name]}
            else:
                return {"error": f"Property '{property_name}' not found on node '{node_name}'"}

        return {"node": node_name, "properties": all_props}
    except ImportError:
        return {"error": "adidt.dt module not available. Install adidt with device tree support."}
    except Exception as e:
        return {"error": f"Failed to read property: {e}"}


def main():
    """Entry point for the adidt-mcp console script."""
    mcp.run()


if __name__ == "__main__":
    main()
