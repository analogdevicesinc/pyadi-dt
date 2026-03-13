"""ADRV9009 + ZCU102: full XSA -> DTS generation example.

This example mirrors ``examples/xsa/ad9081_zcu102_xsa_parse.py`` but targets
the ADRV9009 ZCU102 design and runs the full pipeline:

1. Get an ADRV9009 XSA (local path or optional Kuiper download).
2. Parse the topology from the XSA.
3. Run SDTGen + NodeBuilder + merge to produce a full DTS.
4. Optionally compile the generated DTS into a DTB.

Generated output summary
------------------------
The script writes the following artifacts into ``--output-dir``:

- ``base/``: SDTGen output (for example ``system-top.dts``, ``pl.dtsi``,
  ``pcw.dtsi`` and related include/init files).
- ``<name>.dtso``: ADI overlay snippet produced from parsed topology + config.
- ``<name>.dts``: full merged DTS (base SDT + ADI overlay content).
- ``<name>_report.html``: topology + clock-reference visualization report.
- ``<name>.dtb`` and optionally ``<name>.pp.dts``: best-effort merge compile
  check performed by the merger when tools are present.
- ``system.dtb``: optional explicit output generated when ``--compile-dtb`` is
  requested.

When ``--download-kuiper`` is used:
- ``kuiper_cache/<release>_latest_boot_partition.tar.gz``
- ``xsa/system_top.xsa``

Usage
-----
Local XSA:

    python examples/xsa/adrv9009_zcu102.py \
        --xsa /path/to/system_top.xsa

Kuiper download via adi-labgrid-plugins:

    python examples/xsa/adrv9009_zcu102.py --download-kuiper
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import tarfile
from pathlib import Path

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.topology import XsaParser

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output"
DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-adrv9009"


def _config() -> dict:
    # Matches the working HW-test defaults for ADRV9009 on ZCU102.
    return {
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 4, "L": 4, "Np": 16, "S": 1},
            "tx": {"F": 4, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1},
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
        },
    }


def _download_kuiper_xsa(
    release: str, project: str, cache_dir: Path, out_dir: Path
) -> Path:
    try:
        from adi_lg_plugins.drivers.kuiperdldriver import Downloader, KuiperDLDriver
    except ImportError as ex:
        raise RuntimeError(
            "adi-labgrid-plugins is required for --download-kuiper"
        ) from ex

    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    tarball = cache_dir / f"{release}_latest_boot_partition.tar.gz"
    if not tarball.exists():
        url = KuiperDLDriver.sw_downloads_template.format(release=release)
        response = Downloader().retry_session().get(url, stream=True, timeout=120)
        if not response.ok:
            raise RuntimeError(
                f"failed to download Kuiper boot partition: release={release} "
                f"status={response.status_code}"
            )
        with tarball.open("wb") as fout:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fout.write(chunk)

    nested_member_name = f"{project}/bootgen_sysfiles.tgz"
    with tarfile.open(tarball, "r:gz") as outer_tar:
        nested_member = outer_tar.getmember(nested_member_name)
        nested_f = outer_tar.extractfile(nested_member)
        if nested_f is None:
            raise RuntimeError(f"missing member data: {nested_member_name}")
        nested_bytes = nested_f.read()

    with tarfile.open(fileobj=io.BytesIO(nested_bytes), mode="r:gz") as inner_tar:
        xsa_members = [m for m in inner_tar.getmembers() if m.name.endswith(".xsa")]
        if not xsa_members:
            raise RuntimeError(f"no .xsa found in nested archive for project {project}")
        selected = next(
            (m for m in xsa_members if m.name.endswith("/system_top.xsa")),
            xsa_members[0],
        )
        src = inner_tar.extractfile(selected)
        if src is None:
            raise RuntimeError(f"unable to read XSA member {selected.name}")
        out_path = out_dir / Path(selected.name).name
        out_path.write_bytes(src.read())
        return out_path


def _compile_dts_to_dtb(dts_path: Path, dtb_path: Path):
    compile_input = dts_path
    text = dts_path.read_text()

    if "#include" in text:
        if shutil.which("cpp") is None:
            raise RuntimeError(
                "cpp not found on PATH (required for #include preprocessing)"
            )
        preprocessed = dtb_path.parent / f"{dts_path.stem}.pp.dts"
        include_dirs = [dts_path.parent, dts_path.parent / "base"]
        cmd = ["cpp", "-P", "-nostdinc", "-undef", "-x", "assembler-with-cpp"]
        for inc in include_dirs:
            if inc.exists():
                cmd.extend(["-I", str(inc)])
        cmd.extend([str(dts_path), str(preprocessed)])
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"cpp failed:\n{res.stderr}")
        compile_input = preprocessed

    res = subprocess.run(
        ["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb_path), str(compile_input)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"dtc failed:\n{res.stderr}")


def _print_generated_details(result: dict[str, Path], explicit_dtb: Path | None = None):
    base_dir = result["base_dir"]
    overlay = result["overlay"]
    merged = result["merged"]
    report = result["report"]
    merged_dtb = merged.with_suffix(".dtb")
    preprocessed = merged.with_suffix(".pp.dts")

    print()
    print("Generated file details:")
    print(f"  [base/]      {base_dir}")
    print("    - SDTGen output directory (base DTS + include files).")
    if base_dir.exists():
        base_files = sorted(p.name for p in base_dir.glob("*") if p.is_file())
        if base_files:
            print(f"    - files: {', '.join(base_files)}")
    print(f"  [overlay]    {overlay}")
    print("    - ADI overlay (.dtso) generated from parsed topology.")
    print(f"  [merged]     {merged}")
    print("    - Full merged DTS (base SDT + ADI nodes).")
    print(f"  [report]     {report}")
    print("    - HTML topology/clock visualization report.")
    if merged_dtb.exists():
        print(f"  [auto-dtb]   {merged_dtb}")
        print("    - DTB compile output generated by merger (best effort).")
    if preprocessed.exists():
        print(f"  [pp-dts]     {preprocessed}")
        print("    - Preprocessed DTS used when #include handling is needed.")
    if explicit_dtb:
        print(f"  [system.dtb] {explicit_dtb}")
        print("    - Explicit DTB generated by --compile-dtb.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xsa", type=Path, help="Path to ADRV9009 system_top.xsa")
    parser.add_argument(
        "--download-kuiper",
        action="store_true",
        help="Download Kuiper boot-partition archive and extract project XSA",
    )
    parser.add_argument(
        "--kuiper-release",
        default=DEFAULT_KUIPER_RELEASE,
        help=f"Kuiper release name (default: {DEFAULT_KUIPER_RELEASE})",
    )
    parser.add_argument(
        "--kuiper-project",
        default=DEFAULT_KUIPER_PROJECT,
        help=f"Project directory inside Kuiper archive (default: {DEFAULT_KUIPER_PROJECT})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--compile-dtb",
        action="store_true",
        help="Compile generated DTS into DTB using dtc",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.xsa:
        xsa_path = args.xsa
    elif args.download_kuiper:
        xsa_path = _download_kuiper_xsa(
            release=args.kuiper_release,
            project=args.kuiper_project,
            cache_dir=out_dir / "kuiper_cache",
            out_dir=out_dir / "xsa",
        )
    else:
        raise SystemExit("provide --xsa or --download-kuiper")

    if not xsa_path.exists():
        raise SystemExit(f"XSA not found: {xsa_path}")

    print("=" * 60)
    print("ADRV9009 + ZCU102: XSA -> full DTS")
    print("=" * 60)
    print(f"XSA: {xsa_path}")

    topo = XsaParser().parse(xsa_path)
    print(f"FPGA part: {topo.fpga_part}")
    print(f"JESD RX instances: {len(topo.jesd204_rx)}")
    print(f"JESD TX instances: {len(topo.jesd204_tx)}")
    print(f"CLKGEN instances : {len(topo.clkgens)}")
    print(f"Converters       : {[c.ip_type for c in topo.converters]}")

    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=_config(),
        output_dir=out_dir,
        sdtgen_timeout=300,
    )

    explicit_dtb = None
    if args.compile_dtb:
        dtb = out_dir / "system.dtb"
        _compile_dts_to_dtb(result["merged"], dtb)
        explicit_dtb = dtb

    _print_generated_details(result, explicit_dtb)

    print("=" * 60)
    print("Done")
    print("=" * 60)


if __name__ == "__main__":
    main()
