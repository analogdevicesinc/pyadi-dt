# adidt/xsa/pipeline.py
import re
from pathlib import Path
from typing import Any

from .sdtgen import SdtgenRunner
from .topology import XsaParser, XsaTopology
from .node_builder import NodeBuilder
from .merger import DtsMerger
from .visualizer import HtmlVisualizer
from .profiles import ProfileManager, merge_profile_defaults
from .reference import ReferenceManifestExtractor
from .parity import check_manifest_against_dts, write_parity_reports
from .exceptions import ParityError

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
        profile: str | None = None,
        reference_dts: Path | None = None,
        strict_parity: bool = False,
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
        safe_name = re.sub(r"[^\w\-.]", "_", name)  # Same logic as visualizer
        cfg_merged = cfg
        selected_profile = profile or self._auto_profile_name(topology)
        if selected_profile:
            profile_data = ProfileManager().load(selected_profile)
            cfg_merged = merge_profile_defaults(cfg, profile_data)
        nodes = NodeBuilder().build(topology, cfg_merged)
        _, merged_content = DtsMerger().merge(base_dts, nodes, output_dir, name)
        HtmlVisualizer().generate(topology, cfg_merged, merged_content, output_dir, name)

        result = {
            "base_dir": base_dir,
            "overlay": output_dir / f"{name}.dtso",
            "merged": output_dir / f"{name}.dts",
            "report": output_dir / f"{safe_name}_report.html",
        }
        if reference_dts is not None:
            manifest = ReferenceManifestExtractor().extract(reference_dts)
            parity = check_manifest_against_dts(manifest, merged_content)
            map_path, coverage_path = write_parity_reports(parity, output_dir, name)
            result["map"] = map_path
            result["coverage"] = coverage_path
            if strict_parity:
                issues: list[str] = []
                if parity.missing_roles:
                    issues.append(
                        f"missing required roles: {', '.join(parity.missing_roles)}"
                    )
                if parity.missing_links:
                    issues.append(
                        f"missing required links: {', '.join(parity.missing_links)}"
                    )
                if parity.missing_properties:
                    issues.append(
                        f"missing required properties: {', '.join(parity.missing_properties)}"
                    )
                if parity.mismatched_properties:
                    issues.append(
                        "mismatched required properties: "
                        f"{', '.join(parity.mismatched_properties)}"
                    )
                if issues:
                    raise ParityError("; ".join(issues))

        return result

    def _derive_name(self, topology: XsaTopology) -> str:
        conv_type = "unknown"
        if topology.converters:
            conv_type = re.sub(r"^axi_", "", topology.converters[0].ip_type)
        platform = "unknown"
        for prefix, plat_name in _PART_TO_PLATFORM.items():
            if topology.fpga_part.lower().startswith(prefix):
                platform = plat_name
                break
        return f"{conv_type}_{platform}"

    def _auto_profile_name(self, topology: XsaTopology) -> str | None:
        candidate = self._derive_name(topology)
        if candidate in ProfileManager().list_profiles():
            return candidate
        return None
