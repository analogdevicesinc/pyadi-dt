"""Wrapper for invoking the sdtgen tool to generate a base SDT/DTS from an XSA."""

import subprocess
from pathlib import Path
import re
import stat

from .exceptions import SdtgenError, SdtgenNotFoundError


class SdtgenRunner:
    """Invokes sdtgen as a subprocess to generate a base SDT/DTS from an XSA file."""

    _CPU_CLUSTER_RE = re.compile(r"(\bcpus_a53\s*:\s*)cpus-a53@0(\s*\{)")
    _CPU_CLUSTER_MB_RE = re.compile(
        r"(\bcpus_microblaze_\d+\s*:\s*)cpus_microblaze@\d+(\s*\{)"
    )
    _IPI_STATUS_RE = re.compile(
        r"(&ipi([3-6])\s*\{.*?\bstatus\s*=\s*\")okay(\";)", re.DOTALL
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

    def __init__(self, binary: str = "sdtgen"):
        """Initialize the runner with the sdtgen *binary* name or path."""
        self.binary = binary
        # Instance-level cache avoids cross-test interference
        self._checked: bool = False
        self._use_eval_mode: bool = False

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
                result = subprocess.run(
                    [self.binary, help_opt],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except FileNotFoundError:
                raise SdtgenNotFoundError()
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
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
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
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
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
        if not use_eval:
            return [self.binary, "-s", str(xsa_path), "-d", str(output_dir)]
        eval_script = (
            f"sdtgen set_dt_param -xsa {{{xsa_path}}} -dir {{{output_dir}}}; "
            "sdtgen generate_sdt"
        )
        return [self.binary, "-eval", eval_script]

    def _postprocess_generated_tree(self, output_dir: Path) -> None:
        """Apply all normalization patches to every DTS/DTSI file in *output_dir*."""
        for path in sorted(output_dir.glob("*.dts")) + sorted(
            output_dir.glob("*.dtsi")
        ):
            text = path.read_text()
            updated = self._normalize_cpu_and_interrupt_nodes(text)
            if updated != text:
                self._write_text_allow_readonly(path, updated)

    _CHOSEN_RE = re.compile(r"(chosen\s*\{)(.*?)(\n\s*\};)", re.DOTALL)

    def _normalize_cpu_and_interrupt_nodes(self, text: str) -> str:
        """Apply CPU cluster rename, IPI disable, SDHCI1/GEM3 fixups, and memory-node cleanup."""
        normalized = self._CPU_CLUSTER_RE.sub(r"\1cpus\2", text)
        normalized = self._CPU_CLUSTER_MB_RE.sub(r"\1cpus\2", normalized)
        normalized = normalized.replace("<&imux>", "<&gic_a53>")
        normalized = self._IPI_STATUS_RE.sub(r"\1disabled\3", normalized)
        normalized = self._SDHCI1_RE.sub(self._ensure_sdhci1_props, normalized)
        normalized = self._SDHCI1_REF_RE.sub(self._ensure_sdhci1_props, normalized)
        normalized = self._SDHCI1_ADDR_RE.sub(self._ensure_sdhci1_props, normalized)
        normalized = self._GEM3_RE.sub(self._ensure_gem3_props, normalized)
        normalized = self._GEM3_REF_RE.sub(self._ensure_gem3_props, normalized)
        normalized = self._GEM3_ADDR_RE.sub(self._ensure_gem3_props, normalized)
        normalized = self._MEMORY_NODE_RE.sub(self._filter_memory_node, normalized)
        normalized = self._CHOSEN_RE.sub(self._ensure_earlycon, normalized)
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

    _DDR_COMPAT_RE = re.compile(r"xlnx,(?:psu-ddr-1\.0|ddr4-[\d.]+)")
    _MEM_REG_4CELL_RE = re.compile(
        r"^(\s*reg\s*=\s*<)0x0\s+(0x[0-9a-fA-F]+)\s+0x0\s+(0x[0-9a-fA-F]+)(>.*)$",
        re.MULTILINE,
    )

    def _filter_memory_node(self, match: re.Match[str]) -> str:
        """Fix DDR memory nodes and strip ``device_type`` from non-DDR nodes.

        For DDR nodes (``xlnx,psu-ddr-*`` and ``xlnx,ddr4-*``):
        - Ensure ``device_type = "memory"`` is present (Linux requires it).
        - Collapse 4-cell ``reg`` to 2-cell when the high 32 bits are zero
          (sdtgen sometimes emits 64-bit addresses for 32-bit platforms).

        For all other memory nodes (LMB BRAM, OCM, etc.):
        - Strip ``device_type = "memory"`` to avoid confusing Linux's memory
          detection.
        """
        node = match.group(1)
        if self._DDR_COMPAT_RE.search(node):
            # Ensure device_type = "memory" is present
            if 'device_type = "memory"' not in node:
                node = re.sub(
                    r"(compatible\s*=\s*\"[^\"]+\";)",
                    r'\1\n\t\tdevice_type = "memory";',
                    node,
                    count=1,
                )
            # Collapse 4-cell reg to 2-cell (strip leading zero cells)
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
