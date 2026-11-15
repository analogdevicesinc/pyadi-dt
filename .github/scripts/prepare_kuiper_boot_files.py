#!/usr/bin/env python3
"""Stage one rig's boot files from a Kuiper boot-partition release.

Prints shell ``export`` lines for the hardware test step.  Zynq-7000 rigs get
the release bitstream and PS init script for the JTAG bootstrap; ZynqMP rigs
get the release ``BOOT.BIN`` for the SD card.  The rig's own U-Boot is kept
because the lab TFTP flow needs one built for its non-default port.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shlex
import sys
import tarfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from test.xsa.kuiper_release import download_boot_partition_release  # noqa: E402

# (daughter-board, carrier) -> (platform, project directory in the release)
RIGS = {
    ("adrv9009", "zc706"): ("zynq", "zynq-zc706-adv7511-adrv9009"),
    ("adrv9371", "zc706"): ("zynq", "zynq-zc706-adv7511-adrv937x"),
    ("ad9081", "zcu102"): ("zynqmp", "zynqmp-zcu102-rev10-ad9081/m8_l4"),
}


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    path.chmod(0o644)
    digest = hashlib.sha256(data).hexdigest()
    print(f"{path.name} sha256={digest} bytes={len(data)}", file=sys.stderr)
    return path


def stage(tarball: Path, project: str, platform: str, output: Path) -> dict[str, Path]:
    """Extract the files *platform* boots from; return variable name -> path."""
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o755)
    wanted = {f"{project}/BOOT.BIN", f"{project}/bootgen_sysfiles.tgz"}
    found: dict[str, bytes] = {}
    with tarfile.open(tarball, "r:gz") as outer:
        for member in outer:
            if member.name in wanted:
                found[Path(member.name).name] = outer.extractfile(member).read()
            if len(found) == len(wanted):
                break
    missing = {Path(name).name for name in wanted} - set(found)
    if missing:
        raise SystemExit(f"{project}: release archive lacks {sorted(missing)}")
    if platform == "zynqmp":
        out = {"ADIDT_BOOT_BIN": _write(output / "BOOT.BIN", found["BOOT.BIN"])}
        with tarfile.open(tarball, "r:gz") as outer:  # TEMPORARY
            dtb = outer.extractfile(f"{project}/m8_l4_vcxo122p88/system.dtb").read()
        out["ADIDT_FORCE_DTB"] = _write(output / "release.dtb", dtb)
        return out
    with tarfile.open(fileobj=io.BytesIO(found["bootgen_sysfiles.tgz"])) as inner:
        files = {
            Path(m.name).name: inner.extractfile(m).read() for m in inner if m.isfile()
        }
    with zipfile.ZipFile(io.BytesIO(files["system_top.xsa"])) as xsa:
        ps7_init = xsa.read("ps7_init.tcl")
    return {
        "ADIDT_ZYNQ_BITSTREAM": _write(
            output / "system_top.bit", files["system_top.bit"]
        ),
        "ADIDT_ZYNQ_PS7_INIT": _write(output / "ps7_init.tcl", ps7_init),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--board", required=True)
    parser.add_argument("--carrier", required=True)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        platform, project = RIGS[(args.board, args.carrier)]
    except KeyError:
        raise SystemExit(
            f"no {args.release} boot files are mapped for {args.board}/{args.carrier}"
        ) from None
    tarball = download_boot_partition_release(args.release, args.cache)
    exports = stage(tarball, project, platform, args.output)
    exports["ADIDT_KUIPER_CACHE"] = args.cache
    for name, path in exports.items():
        print(f"export {name}={shlex.quote(str(path))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
