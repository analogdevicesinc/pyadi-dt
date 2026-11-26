"""Wrapper for invoking the sdtgen tool to generate a base SDT/DTS from an XSA."""

import os
import re
import shlex
import stat
import subprocess
from pathlib import Path

from ..exceptions import SdtgenError, SdtgenNotFoundError


class SdtgenRunner:
    """Invokes sdtgen as a subprocess to generate a base SDT/DTS from an XSA file."""

    _CPU_CLUSTER_RE = re.compile(r"(\bcpus_a(?:53|72)\s*:\s*)cpus-a(?:53|72)@0(\s*\{)")
    # Versal trees name the APU interrupt controller after its Cortex-A72.
    _VERSAL_GIC_RE = re.compile(r"\bgic_a72\s*:")
    _CPU_CLUSTER_MB_RE = re.compile(
        r"(\bcpus_microblaze_\d+\s*:\s*)cpus_microblaze@\d+(\s*\{)"
    )
    _IPI_STATUS_RE = re.compile(
        r"(&ipi([3-6])\s*\{.*?\bstatus\s*=\s*\")okay(\";)", re.DOTALL
    )
    # sdtgen turns the SMMU on; the kernel trees leave it off.  With it on,
    # PL masters such as the ADI DMA cores have no stream ID, their writes are
    # blocked, and captures read back as zeros.
    _SMMU_STATUS_RE = re.compile(
        r"(&smmu\s*\{[^}]*?\bstatus\s*=\s*\")okay(\";)", re.DOTALL
    )
    _SDHCI1_RE = re.compile(
        r"(sdhci1\s*:\s*mmc@ff170000\s*\{)(.*?)(\n\s*\};)", re.DOTALL
    )
    _SDHCI1_REF_RE = re.compile(r"(&sdhci1\s*\{)(.*?)(\n\s*\};)", re.DOTALL)
    _SDHCI1_ADDR_RE = re.compile(r"(mmc@ff170000\s*\{)(.*?)(\n\s*\};)", re.DOTALL)
    _GEM3_RE = re.compile(
        r"(gem3\s*:\s*ethernet@ff0e0000\s*\{)(.*?)(\n\s*\};)", re.DOTALL
    )
    _GEM3_REF_RE = re.compile(r"(&gem3\s*\{)(.*?)(\n\s*\};)", re.DOTALL)
    _GEM3_ADDR_RE = re.compile(r"(ethernet@ff0e0000\s*\{)(.*?)(\n\s*\};)", re.DOTALL)
    _MEMORY_NODE_RE = re.compile(
        r"(^\s*(?:[a-zA-Z_]\w*\s*:\s*)?memory@[0-9A-Fa-fx]+\s*\{.*?^\s*\};\n?)",
        re.MULTILINE | re.DOTALL,
    )

    _VITIS_RELEASES = ("2025.1", "2023.2", "2022.2")
    _VITIS_DEFAULT_BASE_DIRS = (
        "/opt/Xilinx",
        "/tools/Xilinx",
        "/usr/local/Xilinx",
        "~/Xilinx",
    )
    _VITIS_INSTALL_HINTS = (
        "VITIS_ROOT",
        "XILINX_VITIS",
        "XILINX_VIVADO",
        "XILINX_PATH",
    )
    _VITIS_TOOL_DIRS = ("Vivado", "Vitis", "Vitis_HLS")

    def __init__(self, binary: str = "sdtgen"):
        """Initialize the runner with the sdtgen *binary* name or path."""
        self.binary = binary
        # Instance-level cache avoids cross-test interference
        self._checked: bool = False
        self._use_eval_mode: bool = False
        self._sourced_vitis_settings: Path | None = None

    def _command_shell(self, command: list[str]) -> str:
        quoted = " ".join(shlex.quote(part) for part in command)
        if self._sourced_vitis_settings is None:
            return quoted
        return (
            f"source {shlex.quote(str(self._sourced_vitis_settings))} >/dev/null 2>&1; "
            f"{quoted}"
        )

    def _run(self, command: list[str], timeout: int = 10, check: bool = False):
        """Run *command* directly or through a shell after sourcing Vitis."""
        if self._sourced_vitis_settings is None:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )
        return subprocess.run(
            ["bash", "-lc", self._command_shell(command)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )

    def _find_vitis_settings_script(self) -> Path | None:
        """Find a Vitis/Vivado settings script to source when sdtgen is missing."""
        candidate_dirs: list[Path] = []
        for key in self._VITIS_INSTALL_HINTS:
            value = os.environ.get(key)
            if not value:
                continue
            for entry in value.split(os.pathsep):
                if entry:
                    candidate_dirs.append(Path(entry).expanduser())
        candidate_dirs.extend(
            Path(x).expanduser() for x in self._VITIS_DEFAULT_BASE_DIRS
        )

        unique_dirs: list[Path] = []
        for release in self._VITIS_RELEASES:
            for tool_dir in self._VITIS_TOOL_DIRS:
                candidate_dirs.append(Path(f"/opt/Xilinx/{release}"))
                candidate_dirs.append(Path(f"/tools/Xilinx/{release}"))
                candidate_dirs.append(Path(f"/usr/local/Xilinx/{release}"))
                candidate_dirs.append(Path(f"~/Xilinx/{release}").expanduser())
                candidate_dirs.append(Path(f"/opt/Xilinx/Vits/{release}"))
                candidate_dirs.append(Path(f"/tools/Xilinx/Vitis/{release}"))
                candidate_dirs.append(Path(f"/usr/local/Xilinx/Vitis/{release}"))
                candidate_dirs.append(Path(f"~/Xilinx/{release}").expanduser())
        for directory in candidate_dirs:
            try:
                resolved = directory.resolve()
            except OSError:
                continue
            if resolved not in unique_dirs:
                unique_dirs.append(resolved)

        candidates: set[Path] = set()
        for base in unique_dirs:
            if not base.is_dir():
                continue
            direct = base / "settings64.sh"
            if direct.is_file():
                candidates.add(direct)

            for tool_dir in self._VITIS_TOOL_DIRS:
                parent = base / tool_dir
                if not parent.is_dir():
                    continue
                for version_dir in sorted(parent.iterdir(), reverse=True):
                    if not version_dir.is_dir():
                        continue
                    script = version_dir / "settings64.sh"
                    if script.is_file():
                        candidates.add(script)

            legacy = base / "settings.sh"
            if legacy.is_file():
                candidates.add(legacy)

        if not candidates:
            return None
        return sorted(
            (path for path in candidates if path.is_file()),
            key=lambda path: (path.stat().st_mtime, path.as_posix()),
            reverse=True,
        )[0]

    def _check_binary(self) -> None:
        """Confirm the sdtgen binary exists and is reachable.

        Runs ``sdtgen --help`` to verify the binary is on PATH.  Raises
        SdtgenNotFoundError if the binary cannot be found, or SdtgenError if
        the probe call times out.  Does nothing if the binary was already
        confirmed during this runner's lifetime.
        """
        if self._checked:
            return
        result = None
        for help_opt in ("--help", "-help"):
            try:
                result = self._run([self.binary, help_opt], timeout=10, check=False)
            except FileNotFoundError:
                if self._sourced_vitis_settings is None:
                    self._sourced_vitis_settings = self._find_vitis_settings_script()
                    if self._sourced_vitis_settings is None:
                        raise SdtgenNotFoundError()
                    try:
                        result = self._run(
                            [self.binary, help_opt], timeout=10, check=False
                        )
                    except FileNotFoundError:
                        raise SdtgenNotFoundError()
                else:
                    raise
            except subprocess.TimeoutExpired:
                raise SdtgenError(f"sdtgen {help_opt} timed out after 10s")
            # Prefer the first successful probe but allow fallback to -help for
            # Vivado wrappers that reject the GNU-style --help option.
            if result.returncode == 0:
                break

        if result is None:
            raise SdtgenError("failed to probe sdtgen help output")

        help_text = f"{result.stdout}\n{result.stderr}"
        self._use_eval_mode = self._detect_eval_mode(help_text)
        self._checked = True

    def run(self, xsa_path: Path, output_dir: Path, timeout: int = 120) -> Path:
        """Run sdtgen and return the path to the generated base DTS file.

        Raises:
            SdtgenNotFoundError: If sdtgen is not on PATH.
            SdtgenError: If sdtgen fails, times out, or produces no output.
        """
        self._check_binary()
        cmd = self._build_cmd(xsa_path, output_dir, use_eval=self._use_eval_mode)
        try:
            result = self._run(cmd, timeout=timeout, check=False)
        except FileNotFoundError:
            raise SdtgenNotFoundError()
        except subprocess.TimeoutExpired:
            raise SdtgenError(f"sdtgen timed out after {timeout}s")

        # Older scripts use -s/-d; newer (2025.1+) expose set_dt_param/generate_sdt via -eval.
        if (
            result.returncode != 0
            and not self._use_eval_mode
            and "illegal option '-s'" in f"{result.stderr}\n{result.stdout}".lower()
        ):
            self._use_eval_mode = True
            cmd = self._build_cmd(xsa_path, output_dir, use_eval=True)
            try:
                result = self._run(cmd, timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                raise SdtgenError(f"sdtgen timed out after {timeout}s")

        if result.returncode != 0:
            raise SdtgenError(
                f"sdtgen exited with code {result.returncode}",
                stderr=result.stderr,
            )

        expected = output_dir / "system-top.dts"
        if expected.exists():
            self._postprocess_generated_tree(output_dir)
            return expected

        dts_files = sorted(output_dir.glob("*.dts"))
        if dts_files:
            self._postprocess_generated_tree(output_dir)
            return dts_files[0]

        raise SdtgenError("sdtgen produced no .dts output")

    def _detect_eval_mode(self, help_text: str) -> bool:
        """Return True if the sdtgen binary uses ``-eval`` mode rather than ``-s/-d`` flags."""
        text = help_text.lower()
        return "-eval" in text and "-s <xsa>" not in text

    def _build_cmd(self, xsa_path: Path, output_dir: Path, use_eval: bool) -> list[str]:
        """Return the sdtgen command list for either legacy ``-s/-d`` or modern ``-eval`` mode."""
        xsa_abs = xsa_path.resolve()
        out_abs = output_dir.resolve()
        if not use_eval:
            return [self.binary, "-s", str(xsa_abs), "-d", str(out_abs)]
        eval_script = (
            f"sdtgen set_dt_param -xsa {{{xsa_abs}}} -dir {{{out_abs}}}; "
            "sdtgen generate_sdt"
        )
        return [self.binary, "-eval", eval_script]

    def _postprocess_generated_tree(self, output_dir: Path) -> None:
        """Apply all normalization patches to every DTS/DTSI file in *output_dir*."""
        paths = sorted(output_dir.glob("*.dts")) + sorted(output_dir.glob("*.dtsi"))
        versal = any(self._VERSAL_GIC_RE.search(path.read_text()) for path in paths)
        gic_label = "gic_a72" if versal else "gic_a53"
        for path in paths:
            text = path.read_text()
            updated = self._normalize_cpu_and_interrupt_nodes(text, gic_label)
            if path.name == "system-top.dts":
                updated = self._ensure_board_ethernet_phy(updated)
                if versal:
                    updated = self._disable_versal_foreign_nodes(
                        updated, [other.read_text() for other in paths]
                    )
            if updated != text:
                self._write_text_allow_readonly(path, updated)

    _BOARD_RE = re.compile(r'^\s*board\s*=\s*"([^"]+)"\s*;', re.MULTILINE)
    # sdtgen describes the MAC but not the board's PHY.  Without a PHY node the
    # kernel scans the MDIO bus and takes the first responder, which on newer
    # kernels can be a phantom Clause 45 device instead of the real PHY.
    _BOARD_ETHERNET_PHY = {"zc706": ("gem0", 7)}

    def _ensure_board_ethernet_phy(self, text: str) -> str:
        """Append the board's Ethernet PHY when the generated tree names none."""
        board = self._BOARD_RE.search(text)
        phy = self._BOARD_ETHERNET_PHY.get(board.group(1)) if board else None
        if phy is None or "ethernet-phy@" in text:
            return text
        mac, address = phy
        return (
            text.rstrip("\n")
            + f"\n&{mac} {{\n\tphy-handle = <&ethernet_phy>;\n"
            + f"\tethernet_phy: ethernet-phy@{address} {{\n"
            + f"\t\treg = <{address}>;\n\t}};\n}};\n"
        )

    # A labelled node and its body up to (not including) the first child node
    # or the closing brace: enough to read the node's own ``compatible``.
    _LABELLED_NODE_RE = re.compile(
        r"^[ \t]*([A-Za-z_]\w*)\s*:\s*[\w,.+-]+(?:@[0-9A-Fa-f]+)?\s*\{(?=([^{}]*))",
        re.MULTILINE,
    )
    # Drivers Linux would bind although the hardware is not the APU's to
    # touch.  Each of these stopped a VPK180 from booting:
    #   - the IPI mailboxes include the PMC's and PSM's own channels, and the
    #     TMR cores sit in the PMC and PSM; touching either raises an
    #     exception in the secure monitor;
    #   - the kernel reference trees describe no mailbox at all.
    _VERSAL_FOREIGN_COMPATIBLES = (
        "xlnx,zynqmp-ipi-mailbox",
        "xlnx,tmr-manager-1.0",
        "xlnx,tmr-inject-1.0",
    )
    # The RPU's GIC shares the APU GIC's address and breaks it when probed;
    # the ITS has no backing here and times out.  Both are off in the kernel
    # trees.
    _VERSAL_FOREIGN_LABELS = ("gic_r5", "gic_its")
    _VERSAL_FOREIGN_MARKER = "/* pyadi-dt: not usable from the APU running Linux */"

    def _disable_versal_foreign_nodes(self, top: str, sources: list[str]) -> str:
        """Append overrides that turn off nodes Linux must not drive on Versal.

        sdtgen describes the whole device for every processor in it.  Linux
        only runs on the APU, so *top* (``system-top.dts``, which includes the
        other *sources*) gets ``status = "disabled"`` for the nodes that
        belong to the platform firmware or to the RPU.
        """
        if self._VERSAL_FOREIGN_MARKER in top:
            return top
        labels: list[str] = []
        for text in sources:
            for label, body in self._LABELLED_NODE_RE.findall(text):
                foreign = label in self._VERSAL_FOREIGN_LABELS or any(
                    f'"{compatible}"' in body
                    for compatible in self._VERSAL_FOREIGN_COMPATIBLES
                )
                if foreign and label not in labels:
                    labels.append(label)
        if not labels:
            return top
        overrides = "".join(
            f'&{label} {{\n\tstatus = "disabled";\n}};\n' for label in sorted(labels)
        )
        return f"{top.rstrip()}\n\n{self._VERSAL_FOREIGN_MARKER}\n{overrides}"

    _CHOSEN_RE = re.compile(r"(chosen\s*\{)(.*?)(\n\s*\};)", re.DOTALL)

    _ZYNQ_ROOT_COMPAT_RE = re.compile(
        r'^(\s*compatible\s*=\s*)"xlnx,zc7\d+"\s*;',
        re.MULTILINE,
    )

    def _normalize_cpu_and_interrupt_nodes(
        self, text: str, gic_label: str = "gic_a53"
    ) -> str:
        """Apply CPU cluster rename, IPI disable, SDHCI1/GEM3 fixups, and memory-node cleanup.

        The interrupt multiplexer sdtgen emits is replaced by *gic_label*, the
        APU interrupt controller of the tree (``gic_a72`` on Versal).
        """
        normalized = self._CPU_CLUSTER_RE.sub(r"\1cpus\2", text)
        normalized = self._CPU_CLUSTER_MB_RE.sub(r"\1cpus\2", normalized)
        normalized = normalized.replace("<&imux>", f"<&{gic_label}>")
        normalized = self._IPI_STATUS_RE.sub(r"\1disabled\3", normalized)
        normalized = self._SMMU_STATUS_RE.sub(r"\1disabled\2", normalized)
        normalized = self._SDHCI1_RE.sub(self._ensure_sdhci1_props, normalized)
        normalized = self._SDHCI1_REF_RE.sub(self._ensure_sdhci1_props, normalized)
        normalized = self._SDHCI1_ADDR_RE.sub(self._ensure_sdhci1_props, normalized)
        normalized = self._GEM3_RE.sub(self._ensure_gem3_props, normalized)
        normalized = self._GEM3_REF_RE.sub(self._ensure_gem3_props, normalized)
        normalized = self._GEM3_ADDR_RE.sub(self._ensure_gem3_props, normalized)
        normalized = self._MEMORY_NODE_RE.sub(self._filter_memory_node, normalized)
        normalized = self._CHOSEN_RE.sub(self._ensure_earlycon, normalized)
        # Zynq-7000: sdtgen emits board-specific compatible (e.g. "xlnx,zc706")
        # but the kernel machine descriptor requires "xlnx,zynq-7000".
        normalized = self._ZYNQ_ROOT_COMPAT_RE.sub(r'\1"xlnx,zynq-7000";', normalized)
        return normalized

    def _ensure_sdhci1_props(self, match: re.Match[str]) -> str:
        """Regex substitution callback that injects missing iommus and no-1-8-v into sdhci1."""
        head, body, tail = match.groups()
        updated = body
        if "iommus =" not in updated:
            updated += "\n\t\tiommus = <&smmu 0x871>;"
        if "no-1-8-v;" not in updated:
            updated += "\n\t\tno-1-8-v;"
        return f"{head}{updated}{tail}"

    def _ensure_gem3_props(self, match: re.Match[str]) -> str:
        """Regex substitution callback that injects a missing iommus property into gem3."""
        head, body, tail = match.groups()
        updated = body
        if "iommus =" not in updated:
            updated += "\n\t\tiommus = <&smmu 0x877>;"
        return f"{head}{updated}{tail}"

    _DDR_COMPAT_RE = re.compile(
        r"xlnx,(?:ps7-ddr-[\d.]+[a-z]?|psu-ddr-1\.0|ddr4-[\d.]+|axi-noc-[\d.]+)"
    )
    _MEM_REG_4CELL_RE = re.compile(
        r"^(\s*reg\s*=\s*<)0x0\s+(0x[0-9a-fA-F]+)\s+0x0\s+(0x[0-9a-fA-F]+)(>.*)$",
        re.MULTILINE,
    )

    def _filter_memory_node(self, match: re.Match[str]) -> str:
        """Fix DDR memory nodes and strip ``device_type`` from non-DDR nodes.

        For DDR nodes (``xlnx,psu-ddr-*``, ``xlnx,ddr4-*`` and the Versal
        ``xlnx,axi-noc-*``):
        - Ensure ``device_type = "memory"`` is present (Linux requires it).
        - Preserve ZynqMP DDR address/size cells; collapse the redundant high
          cells only for the 32-bit fabric DDR case.

        For all other memory nodes (R5 mappings, LMB BRAM, OCM, etc.):
        - Strip ``device_type = "memory"`` to avoid confusing Linux's memory
          detection.
        """
        node = match.group(1)
        if self._DDR_COMPAT_RE.search(node) and "psu_r5_ddr" not in node:
            # Ensure device_type = "memory" is present
            if 'device_type = "memory"' not in node:
                node = re.sub(
                    r"(compatible\s*=\s*\"[^\"]+\";)",
                    r'\1\n\t\tdevice_type = "memory";',
                    node,
                    count=1,
                )
            # Collapse 4-cell reg to 2-cell (strip leading zero cells)
            # ZynqMP and Versal (NoC) buses have two address cells: keep them.
            if "xlnx,psu-ddr" not in node and "xlnx,axi-noc" not in node:
                node = self._MEM_REG_4CELL_RE.sub(r"\1\2 \3\4", node)
            return node
        return re.sub(
            r"^\s*device_type\s*=\s*\"memory\";\n?", "", node, flags=re.MULTILINE
        )

    def _ensure_earlycon(self, match: re.Match[str]) -> str:
        """Inject ``bootargs = "earlycon"`` into the chosen node if missing."""
        head, body, tail = match.groups()
        if "bootargs" not in body:
            body += '\n\t\tbootargs = "earlycon";'
        return f"{head}{body}{tail}"

    def _write_text_allow_readonly(self, path: Path, content: str) -> None:
        """Write *content* to *path*, temporarily lifting read-only permissions if needed."""
        try:
            path.write_text(content)
            return
        except PermissionError:
            mode = path.stat().st_mode
            path.chmod(mode | stat.S_IWUSR)
            path.write_text(content)
