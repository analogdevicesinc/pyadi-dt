import subprocess
from pathlib import Path

from .exceptions import SdtgenError, SdtgenNotFoundError


class SdtgenRunner:
    """Invokes sdtgen as a subprocess to generate a base SDT/DTS from an XSA file."""

    def __init__(self, binary: str = "sdtgen"):
        self.binary = binary
        # Instance-level cache avoids cross-test interference
        self._flags: tuple[str, str] | None = None

    def _detect_flags(self) -> tuple[str, str]:
        """Confirm binary exists and return (src_flag, out_flag)."""
        if self._flags is not None:
            return self._flags
        try:
            subprocess.run(
                [self.binary, "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except FileNotFoundError:
            raise SdtgenNotFoundError()
        except subprocess.TimeoutExpired:
            raise SdtgenError(f"sdtgen --help timed out after 10s")
        self._flags = ("-s", "-d")
        return self._flags

    def run(self, xsa_path: Path, output_dir: Path, timeout: int = 120) -> Path:
        """Run sdtgen and return the path to the generated base DTS file.

        Raises:
            SdtgenNotFoundError: If sdtgen is not on PATH.
            SdtgenError: If sdtgen fails, times out, or produces no output.
        """
        src_flag, out_flag = self._detect_flags()
        cmd = [self.binary, src_flag, str(xsa_path), out_flag, str(output_dir)]
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

        if result.returncode != 0:
            raise SdtgenError(
                f"sdtgen exited with code {result.returncode}",
                stderr=result.stderr,
            )

        expected = output_dir / "system-top.dts"
        if expected.exists():
            return expected

        dts_files = sorted(output_dir.glob("*.dts"))
        if dts_files:
            return dts_files[0]

        raise SdtgenError("sdtgen produced no .dts output")
