# adidt/xsa/merger.py
import logging
import re
import subprocess
import warnings
from pathlib import Path
from typing import Any

_LABEL_RE = re.compile(r"^\s*([a-zA-Z_]\w*)\s*:\s*\w", re.MULTILINE)
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
                    r"[ \t]+\w[\w-]*@" + re.escape(addr) + r"\s*\{(?:[^{}]|\{[^}]*\})*\};",
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
