# adidt/xsa/merger.py
import logging
import re
import subprocess
import warnings
from pathlib import Path

_LABEL_RE = re.compile(r"^\s*([a-zA-Z_]\w*)\s*:\s*\w", re.MULTILINE)
_NODE_ADDR_RE = re.compile(r"@([0-9a-fA-F]+)\s*\{")
_NODE_LABEL_IN_SNIPPET_RE = re.compile(r"^\s*([a-zA-Z_]\w*)\s*:")
_INTERRUPTS_PROP_RE = re.compile(r"^\s*interrupts\s*=\s*<[^;]+>;\s*$", re.MULTILINE)
_INTERRUPT_PARENT_PROP_RE = re.compile(
    r"^\s*interrupt-parent\s*=\s*<[^;]+>;\s*$", re.MULTILINE
)
_log = logging.getLogger(__name__)

_BUS_LABELS = {"amba", "amba_pl", "axi", "ahb", "soc", "bus"}


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
            nodes.get("clkgens", [])
            + nodes.get("jesd204_rx", [])
            + nodes.get("jesd204_tx", [])
            + nodes.get("converters", [])
        )
        overlay = self._build_overlay(base_dts, all_nodes)
        merged = self._build_merged(
            base_dts, all_nodes, [output_dir, output_dir / "base"]
        )

        (output_dir / f"{name}.dtso").write_text(overlay)
        merged_path = output_dir / f"{name}.dts"
        merged_path.write_text(merged)
        self._try_compile_dtb(merged_path)

        return overlay, merged

    def _scan_labels(self, dts: str) -> set[str]:
        return set(_LABEL_RE.findall(dts))

    def _bus_label(self, labels: set[str]) -> str | None:
        # Prefer "amba" (standard Xilinx/ARM bus label)
        if "amba" in labels:
            return "amba"
        # Fall back to other recognized bus labels in sorted order
        for label in sorted(labels & _BUS_LABELS):
            return label
        return None

    def _build_overlay(self, base_dts: str, all_nodes: list[str]) -> str:
        bus_nodes = [n for n in all_nodes if not n.lstrip().startswith("&")]
        top_nodes = [n for n in all_nodes if n.lstrip().startswith("&")]
        bus = self._bus_label(self._scan_labels(base_dts))
        lines = ["/dts-v1/;", "/plugin/;", ""]
        if bus and bus_nodes:
            lines += [f"&{bus} {{"] + bus_nodes + ["};"]
        elif bus_nodes:
            lines += bus_nodes
        lines += top_nodes
        return "\n".join(lines) + "\n"

    def _build_merged(
        self, base_dts: str, all_nodes: list[str], include_dirs: list[Path]
    ) -> str:
        merged = base_dts
        include_labels = self._scan_include_labels(base_dts, include_dirs)
        include_nodes = self._scan_include_nodes(base_dts, include_dirs)
        all_nodes = [
            self._augment_node_from_include(node, include_nodes) for node in all_nodes
        ]
        delete_directives = self._include_conflict_delete_directives(
            all_nodes, include_labels
        )
        if delete_directives:
            merged = self._insert_delete_directives(merged, delete_directives)

        # Replace conflicting address stubs
        for node in all_nodes:
            if node.lstrip().startswith("&"):
                continue
            label_match = _NODE_LABEL_IN_SNIPPET_RE.search(node)
            if label_match:
                label = label_match.group(1)
                label_conflict_re = re.compile(
                    r"[ \t]*"
                    + re.escape(label)
                    + r"\s*:\s*\w[\w-]*@[0-9a-fA-Fx]+\s*\{(?:[^{}]|\{[^}]*\})*\};",
                    re.DOTALL,
                )
                if label_conflict_re.search(merged):
                    warnings.warn(
                        f"Replaced existing base node with duplicate label '{label}'",
                        UserWarning,
                        stacklevel=2,
                    )
                    merged = label_conflict_re.sub("", merged)

            m = _NODE_ADDR_RE.search(node)
            if m:
                addr = m.group(1).lower()
                # Address 0x0 is common for unrelated CPU/memory stubs in base
                # trees; global replacement by unit-address can corrupt DTS.
                # Label-based replacement above already handles true duplicates.
                if int(addr, 16) == 0:
                    continue
                conflict_re = re.compile(
                    r"[ \t]+\w[\w-]*@"
                    + re.escape(addr)
                    + r"\s*\{(?:[^{}]|\{[^}]*\})*\};",
                    re.DOTALL,
                )
                if conflict_re.search(merged):
                    warnings.warn(
                        f"Replaced existing base node at address 0x{addr} with ADI node",
                        UserWarning,
                        stacklevel=2,
                    )
                    merged = conflict_re.sub("", merged)

        bus_nodes = [n for n in all_nodes if not n.lstrip().startswith("&")]
        top_nodes = [n for n in all_nodes if n.lstrip().startswith("&")]
        nodes_block = "\n".join(bus_nodes) + ("\n" if bus_nodes else "")
        top_nodes_block = "\n".join(top_nodes) + ("\n" if top_nodes else "")
        if not bus_nodes:
            return self._append_top_nodes(merged, top_nodes_block)
        merged_labels = self._scan_labels(merged)
        bus = self._bus_label(merged_labels)
        include_bus = self._bus_label(include_labels)

        if bus and f"{bus}:" in merged and bus_nodes:
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
                return self._append_top_nodes(new_merged, top_nodes_block)
            warnings.warn(
                f"Could not insert into bus node '{bus}'; appending at root level",
                UserWarning,
                stacklevel=2,
            )
        elif include_bus and bus_nodes:
            block = f"&{include_bus} {{\n{nodes_block}}};\n"
            return self._append_top_nodes(
                merged.rstrip() + "\n\n" + block, top_nodes_block
            )
        else:
            warnings.warn(
                "No amba/axi bus label found; inserting ADI nodes under root node",
                UserWarning,
                stacklevel=2,
            )

        root_close = re.search(r"\n\};\s*$", merged)
        if root_close:
            insert_at = root_close.start()
            merged_with_bus = (
                merged[:insert_at] + "\n" + nodes_block + merged[insert_at:]
            )
            return self._append_top_nodes(merged_with_bus, top_nodes_block)

        warnings.warn(
            "Root node close not found; appending ADI nodes at file end",
            UserWarning,
            stacklevel=2,
        )
        return self._append_top_nodes(
            merged.rstrip() + "\n\n" + nodes_block, top_nodes_block
        )

    def _append_top_nodes(self, merged: str, top_nodes_block: str) -> str:
        if not top_nodes_block.strip():
            return merged
        return merged.rstrip() + "\n\n" + top_nodes_block

    def _include_conflict_delete_directives(
        self, nodes: list[str], include_labels: set[str]
    ) -> list[str]:
        if not include_labels:
            return []
        directives: list[str] = []
        for node in nodes:
            label_match = _NODE_LABEL_IN_SNIPPET_RE.search(node)
            if label_match and label_match.group(1) in include_labels:
                label = label_match.group(1)
                warnings.warn(
                    f"Replaced included node with duplicate label '{label}'",
                    UserWarning,
                    stacklevel=3,
                )
                directives.append(f"/delete-node/ &{label};")
        return directives

    def _insert_delete_directives(self, merged: str, directives: list[str]) -> str:
        if not directives:
            return merged
        block = "\n".join(directives) + "\n"
        return self._insert_after_includes(merged, block)

    def _insert_after_includes(self, merged: str, block: str) -> str:
        include_line_re = re.compile(r'^\s*#include\s+"[^"]+"\s*$', re.MULTILINE)
        matches = list(include_line_re.finditer(merged))
        if matches:
            insert_at = matches[-1].end()
            return merged[:insert_at] + "\n" + block + merged[insert_at:]
        dts_header_idx = merged.find("/dts-v1/;")
        if dts_header_idx != -1:
            line_end = merged.find("\n", dts_header_idx)
            if line_end != -1:
                return merged[: line_end + 1] + block + merged[line_end + 1 :]
        return block + merged

    def _scan_include_labels(self, base_dts: str, include_dirs: list[Path]) -> set[str]:
        include_re = re.compile(r'^\s*#include\s+"([^"]+)"', re.MULTILINE)
        seen: set[str] = set()
        labels: set[str] = set()

        def walk(text: str) -> None:
            for match in include_re.findall(text):
                if match in seen:
                    continue
                seen.add(match)
                include_text = self._read_include_file(match, include_dirs)
                if include_text is not None:
                    labels.update(self._scan_labels(include_text))
                    walk(include_text)

        walk(base_dts)
        return labels

    def _scan_include_nodes(
        self, base_dts: str, include_dirs: list[Path]
    ) -> dict[str, str]:
        include_re = re.compile(r'^\s*#include\s+"([^"]+)"', re.MULTILINE)
        seen: set[str] = set()
        nodes: dict[str, str] = {}
        label_node_re = re.compile(
            r"^\s*([a-zA-Z_]\w*)\s*:\s*\w[\w-]*@[0-9a-fA-Fx]+\s*\{(?:[^{}]|\{[^}]*\})*\};",
            re.MULTILINE | re.DOTALL,
        )

        def walk(text: str) -> None:
            for match in include_re.findall(text):
                if match in seen:
                    continue
                seen.add(match)
                include_text = self._read_include_file(match, include_dirs)
                if include_text is None:
                    continue
                for node_match in label_node_re.finditer(include_text):
                    label = node_match.group(1)
                    nodes[label] = node_match.group(0)
                walk(include_text)

        walk(base_dts)
        return nodes

    def _augment_node_from_include(
        self, node: str, include_nodes: dict[str, str]
    ) -> str:
        label_match = _NODE_LABEL_IN_SNIPPET_RE.search(node)
        if not label_match:
            return node
        include_node = include_nodes.get(label_match.group(1))
        if include_node is None:
            return node

        additions: list[str] = []
        if "interrupts" not in node:
            prop = _INTERRUPTS_PROP_RE.search(include_node)
            if prop:
                additions.append(prop.group(0).strip())
        if "interrupt-parent" not in node:
            prop = _INTERRUPT_PARENT_PROP_RE.search(include_node)
            if prop:
                additions.append(prop.group(0).strip())
        if not additions:
            return node

        insertion = "".join(f"\n\t\t{line}" for line in additions)
        return re.sub(r"\n\s*\};\s*$", f"{insertion}\n\t}};", node)

    def _read_include_file(
        self, include_name: str, include_dirs: list[Path]
    ) -> str | None:
        for base in include_dirs:
            path = base / include_name
            if path.exists():
                return path.read_text()
        return None

    def _try_compile_dtb(self, dts_path: Path) -> None:
        dtb_path = dts_path.with_suffix(".dtb")
        try:
            compile_input = dts_path
            text = dts_path.read_text()
            if "#include" in text:
                cpp = self._find_tool("cpp")
                if cpp is None:
                    _log.info(
                        "cpp not found on PATH; skipping include-aware DTB compilation check"
                    )
                    return
                preprocessed = dts_path.with_suffix(".pp.dts")
                cpp_cmd = [
                    cpp,
                    "-P",
                    "-nostdinc",
                    "-undef",
                    "-x",
                    "assembler-with-cpp",
                    "-I",
                    str(dts_path.parent),
                    "-I",
                    str(dts_path.parent / "base"),
                    str(dts_path),
                    str(preprocessed),
                ]
                cpp_result = subprocess.run(
                    cpp_cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if cpp_result.returncode != 0:
                    _log.warning("cpp preprocessing failed: %s", cpp_result.stderr)
                    return
                compile_input = preprocessed
            result = subprocess.run(
                [
                    "dtc",
                    "-I",
                    "dts",
                    "-O",
                    "dtb",
                    "-o",
                    str(dtb_path),
                    str(compile_input),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                _log.warning("dtc compilation failed: %s", result.stderr)
        except FileNotFoundError:
            _log.info("dtc not found on PATH; skipping DTB compilation")

    def _find_tool(self, name: str) -> str | None:
        from shutil import which

        return which(name)
