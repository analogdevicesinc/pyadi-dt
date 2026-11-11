#!/usr/bin/env python3
"""Reject PyPI-incompatible wheel metadata and optionally smoke-test [xsa]."""

import argparse
from email.parser import BytesParser
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
from zipfile import ZipFile

from packaging.requirements import Requirement


def main():
    """Validate the wheel and test the installed optional XSA dependency set."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--smoke-xsa", action="store_true")
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with ZipFile(wheel) as archive:
        metadata_files = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_files) != 1:
            parser.error("wheel must contain exactly one METADATA file")
        metadata = BytesParser().parsebytes(archive.read(metadata_files[0]))
    for raw in metadata.get_all("Requires-Dist", []):
        if Requirement(raw).url is not None:
            parser.error(
                f"PyPI does not allow direct URL dependencies, including extras: {raw}"
            )
    if args.smoke_xsa:
        with tempfile.TemporaryDirectory(prefix="adidt-wheel-smoke-") as directory:
            root = Path(directory)
            venv.EnvBuilder(with_pip=True).create(root / "venv")
            python = (
                root
                / "venv"
                / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            )
            subprocess.run(
                [str(python), "-m", "pip", "install", f"{wheel}[xsa]"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    str(python),
                    "-c",
                    "import adidt, importlib.metadata as m; "
                    "from adidt.xsa.parse.kuiper import download_kuiper_xsa; "
                    "from adidt.xsa.config.profiles import ProfileManager; "
                    'assert adidt.__version__ == m.version("pyadi-dt"); '
                    'assert {"adrv9040_zcu102", "adrv9040_zcu102_nls"}.issubset(ProfileManager().list_profiles())',
                ],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [str(python), "-c", 'from adidt.cli.main import cli; cli(["--help"])'],
                cwd=root,
                check=True,
            )
    print(
        f"Validated PyPI wheel metadata{' and clean [xsa] installation' if args.smoke_xsa else ''}: {wheel.name}"
    )


if __name__ == "__main__":
    main()
