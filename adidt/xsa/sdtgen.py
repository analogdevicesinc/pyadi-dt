import subprocess
from pathlib import Path

from .exceptions import SdtgenError, SdtgenNotFoundError


class SdtgenRunner:
    """Invokes sdtgen as a subprocess to generate a base SDT/DTS from an XSA file."""

    def __init__(self, binary: str = "sdtgen"):
        self.binary = binary
        # Instance-level cache avoids cross-test interference
        self._checked: bool = False

    def _check_binary(self) -> None:
        """Confirm the sdtgen binary exists and is reachable.

        Runs ``sdtgen --help`` to verify the binary is on PATH.  Raises
        SdtgenNotFoundError if the binary cannot be found, or SdtgenError if
        the probe call times out.  Does nothing if the binary was already
        confirmed during this runner's lifetime.
        """
        if self._checked:
            return
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
            raise SdtgenError("sdtgen --help timed out after 10s")
        self._checked = True

    def run(self, xsa_path: Path, output_dir: Path, timeout: int = 120) -> Path:
        """Run sdtgen and return the path to the generated base DTS file.

        Raises:
            SdtgenNotFoundError: If sdtgen is not on PATH.
            SdtgenError: If sdtgen fails, times out, or produces no output.
        """
        self._check_binary()
        src_flag, out_flag = "-s", "-d"
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
