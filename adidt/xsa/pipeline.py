# adidt/xsa/pipeline.py
"""Orchestrate the full XSA-to-DeviceTree pipeline from archive to merged DTS."""

import re
from pathlib import Path
from typing import Any

from .pipeline_config import PipelineConfig
from .sdtgen import SdtgenRunner
from .topology import XsaParser, XsaTopology
from .node_builder import NodeBuilder
from .merger import DtsMerger
from .visualizer import HtmlVisualizer
from .clock_graph import ClockGraphGenerator
from .profiles import ProfileManager, merge_profile_defaults
from .reference import ReferenceManifestExtractor
from .parity import check_manifest_against_dts, write_parity_reports
from .dts_lint import DtsLinter
from .exceptions import DtsLintError, ParityError
from .board_fixups import apply_board_fixups


class XsaPipeline:
    """Orchestrates the five-stage XSA-to-DeviceTree pipeline."""

    def run(
        self,
        xsa_path: Path,
        cfg: PipelineConfig | dict[str, Any],
        output_dir: Path,
        sdtgen_timeout: int = 120,
        profile: str | None = None,
        reference_dts: Path | None = None,
        strict_parity: bool = False,
        emit_report: bool = False,
        emit_clock_graphs: bool = False,
        lint: bool = False,
        strict_lint: bool = False,
    ) -> dict[str, Path]:
        """Run the full pipeline.

        Args:
            xsa_path: Path to the Vivado ``.xsa`` archive.
            cfg: User-supplied configuration dictionary passed to
                :class:`~adidt.xsa.node_builder.NodeBuilder`.
            output_dir: Directory where all output files are written.
                Created automatically if it does not exist.
            sdtgen_timeout: Maximum seconds to wait for ``sdtgen`` to finish
                generating the base DTS.  Defaults to ``120``.
            profile: Name of a built-in profile to load (e.g.
                ``"adrv9009_zcu102"``).  When ``None`` the pipeline attempts
                to auto-detect a matching profile from the XSA topology.
            reference_dts: Optional path to a reference DTS used for parity
                checking.  When provided, ``"map"`` and ``"coverage"`` keys
                are added to the result.
            strict_parity: When ``True`` and *reference_dts* is provided,
                raise :class:`~adidt.xsa.exceptions.ParityError` if the
                merged DTS is missing required roles, links, or properties.
            emit_report: When ``True`` (default) the HTML topology report is
                generated and ``"report"`` is included in the result dict.
                Pass ``False`` to skip report generation.
            emit_clock_graphs: When ``True`` (default) DOT and D2 clock-tree
                diagrams are generated and their paths included in the result
                dict.  Pass ``False`` to skip clock-graph generation.
            lint: When ``True``, run the structural DTS linter on the merged
                DTS and write a diagnostics JSON file.  Defaults to ``False``.
            strict_lint: When ``True``, raise
                :class:`~adidt.xsa.exceptions.DtsLintError` if the linter
                finds any errors.  Implies ``lint=True``.

        Returns:
            Dict always containing ``"base_dir"``, ``"overlay"``, and
            ``"merged"``.  ``"report"`` is present when *emit_report* is
            ``True``.  ``"clock_dot"`` and ``"clock_d2"`` (plus optionally
            ``"clock_dot_svg"`` / ``"clock_d2_svg"``) are present when
            *emit_clock_graphs* is ``True``.  ``"map"`` and ``"coverage"``
            are present when *reference_dts* is provided.  ``"diagnostics"``
            is present when *lint* or *strict_lint* is ``True``.

        Raises:
            ParityError: When *strict_parity* is ``True`` and the merged DTS
                fails the parity check against *reference_dts*.
            DtsLintError: When *strict_lint* is ``True`` and the linter finds
                errors in the generated DTS.
        """
        if strict_lint:
            lint = True
        output_dir.mkdir(parents=True, exist_ok=True)
        base_dir = output_dir / "base"
        base_dir.mkdir(exist_ok=True)

        base_dts_path = SdtgenRunner().run(xsa_path, base_dir, timeout=sdtgen_timeout)

        topology = XsaParser().parse(xsa_path)
        inferred_name = self._derive_name(topology)
        name = profile or inferred_name
        safe_name = re.sub(r"[^\w\-.]", "_", name)  # Same logic as visualizer
        cfg_merged = cfg
        selected_profile = profile or self._auto_profile_name(topology)
        if selected_profile:
            profile_data = ProfileManager().load(selected_profile)
            cfg_merged = merge_profile_defaults(cfg, profile_data)
            cfg_merged = self._apply_profile_jesd_defaults(
                cfg, cfg_merged, selected_profile
            )

        # Apply board-level fixups to the sdtgen base DTS before merging.
        # These correct board-specific issues (PHY config, node naming) that
        # sdtgen cannot derive from the XSA alone.
        apply_board_fixups(selected_profile, base_dir)

        base_dts = base_dts_path.read_text()
        nodes = NodeBuilder().build(topology, cfg_merged)
        _, merged_content = DtsMerger().merge(base_dts, nodes, output_dir, name)

        result: dict[str, Path] = {
            "base_dir": base_dir,
            "overlay": output_dir / f"{name}.dtso",
            "merged": output_dir / f"{name}.dts",
        }

        if emit_report:
            HtmlVisualizer().generate(
                topology, cfg_merged, merged_content, output_dir, name
            )
            result["report"] = output_dir / f"{safe_name}_report.html"

        if emit_clock_graphs:
            result.update(
                ClockGraphGenerator().generate(merged_content, output_dir, name)
            )

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

        if lint:
            diagnostics = DtsLinter().lint(merged_content, topology)
            import json as _json

            diag_path = output_dir / f"{safe_name}_diagnostics.json"
            diag_data = {
                "diagnostics": [
                    {
                        "severity": d.severity,
                        "rule": d.rule,
                        "node": d.node,
                        "message": d.message,
                    }
                    for d in diagnostics
                ],
                "summary": {
                    "errors": sum(1 for d in diagnostics if d.severity == "error"),
                    "warnings": sum(1 for d in diagnostics if d.severity == "warning"),
                    "info": sum(1 for d in diagnostics if d.severity == "info"),
                    "total": len(diagnostics),
                },
            }
            diag_path.write_text(_json.dumps(diag_data, indent=2) + "\n")
            result["diagnostics"] = diag_path

            if strict_lint:
                errors = [d for d in diagnostics if d.severity == "error"]
                if errors:
                    raise DtsLintError(
                        f"{len(errors)} lint error(s) in generated DTS",
                        errors,
                    )

        return result

    def _derive_name(self, topology: XsaTopology) -> str:
        """Return a ``"<converter_family>_<platform>"`` name string inferred from the topology.

        Args:
            topology: Parsed XSA topology object.

        Returns:
            A snake-case string such as ``"adrv9009_zcu102"``.
        """
        conv_type = topology.inferred_converter_family()
        platform = topology.inferred_platform()
        return f"{conv_type}_{platform}"

    @staticmethod
    def _apply_profile_jesd_defaults(
        cfg_in: dict[str, Any], cfg_out: dict[str, Any], profile_name: str
    ) -> dict[str, Any]:
        """Inject well-known JESD lane-count defaults for profiles that require them.

        Only fills in ``jesd.<direction>.L`` when the caller did not supply it
        and the active profile (e.g. ``ad9172_zcu102``, ``fmcdaq3_*``) has a
        hard-coded default.  All other keys are left unchanged.

        Args:
            cfg_in: The original caller-supplied configuration dict, used to
                check which keys were explicitly set.
            cfg_out: The merged configuration dict (profile defaults already
                applied) that will be mutated and returned.
            profile_name: The active profile name used to select which
                defaults to inject.

        Returns:
            The (possibly mutated) *cfg_out* dict.
        """
        cfg_in_jesd = cfg_in.get("jesd", {})
        if profile_name == "ad9172_zcu102":
            profile_tx = cfg_out.setdefault("jesd", {}).setdefault("tx", {})
            if "L" not in cfg_in_jesd.get("tx", {}):
                profile_tx["L"] = 8
            return cfg_out

        if profile_name in {"fmcdaq3_zcu102", "fmcdaq3_zc706"}:
            profile_jesd = cfg_out.setdefault("jesd", {})
            for direction in ("rx", "tx"):
                profile_dir = profile_jesd.setdefault(direction, {})
                if "L" not in cfg_in_jesd.get(direction, {}):
                    profile_dir["L"] = 2
            return cfg_out

        return cfg_out

    def _auto_profile_name(self, topology: XsaTopology) -> str | None:
        """Return the inferred profile name if a matching built-in profile exists, else None.

        Args:
            topology: Parsed XSA topology object.

        Returns:
            The candidate profile name (e.g. ``"adrv9009_zcu102"``) when a
            matching built-in profile is available, otherwise ``None``.
        """
        candidate = self._derive_name(topology)
        if candidate in ProfileManager().list_profiles():
            return candidate
        return None
