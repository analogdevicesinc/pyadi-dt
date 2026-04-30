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
import shutil
import subprocess
from pathlib import Path
from typing import Any

from adidt.xsa.parse.kuiper import download_kuiper_xsa
from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.parse.topology import XsaParser

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output"
DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-adrv9009"
DEFAULT_VCXO_HZ = 122.88e6
DEFAULT_SAMPLE_RATE_HZ = 245.76e6


def _resolve_config_from_adijif(
    vcxo_hz: float, sample_rate_hz: float, solve: bool = False
) -> tuple[dict, dict]:
    """Build XSA pipeline config using pyadi-jif settings from adrv9009_pcbz example.

    Reference:
    https://raw.githubusercontent.com/analogdevicesinc/pyadi-jif/refs/heads/main/examples/adrv9009_pcbz_example.py
    """
    import adijif

    sys = adijif.system("adrv9009", "ad9528", "xilinx", vcxo=vcxo_hz)

    # Match adrv9009_pcbz_example.py clocking constraints.
    # sys.clock.m1 = 3
    # sys.clock.use_vcxo_doubler = True
    sys.fpga.setup_by_dev_kit_name("zcu102")
    # sys.fpga.force_qpll = True

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc,
        M=4,
        L=2,
        S=1,
        Np=16,
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac,
        M=4,
        L=4,
        S=1,
        Np=16,
    )
    if not mode_rx or not mode_tx:
        raise RuntimeError("No matching ADRV9009 JESD modes found via adijif")

    sys.converter.adc.set_quick_configuration_mode(
        mode_rx[0]["mode"], mode_rx[0]["jesd_class"]
    )
    sys.converter.dac.set_quick_configuration_mode(
        mode_tx[0]["mode"], mode_tx[0]["jesd_class"]
    )

    sys.converter.adc.decimation = 8
    sys.converter.adc.sample_clock = sample_rate_hz
    sys.converter.dac.interpolation = 8
    sys.converter.dac.sample_clock = sample_rate_hz

    rx_settings = mode_rx[0]["settings"]
    tx_settings = mode_tx[0]["settings"]

    # Keep clock labels aligned with current ADRV9009 NodeBuilder path.
    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {
                "F": int(rx_settings["F"]),
                "K": int(rx_settings["K"]),
                "M": int(rx_settings["M"]),
                "L": int(rx_settings["L"]),
                "Np": int(rx_settings["Np"]),
                "S": int(rx_settings["S"]),
            },
            "tx": {
                "F": int(tx_settings["F"]),
                "K": int(tx_settings["K"]),
                "M": int(tx_settings["M"]),
                "L": int(tx_settings["L"]),
                "Np": int(tx_settings["Np"]),
                "S": int(tx_settings["S"]),
            },
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
        },
    }

    summary: dict[str, Any] = {
        "vcxo_hz": vcxo_hz,
        "sample_rate_hz": sample_rate_hz,
        "clock_m1": 3,
        "clock_use_vcxo_doubler": True,
        "rx_mode": mode_rx[0]["mode"],
        "tx_mode": mode_tx[0]["mode"],
        "rx_jesd_class": mode_rx[0]["jesd_class"],
        "tx_jesd_class": mode_tx[0]["jesd_class"],
        "solver_used": None,
        "solver_succeeded": False,
        "solver_attempted": solve,
        "clock_output_clocks": None,
        "solve_error": None,
    }

    if solve:
        # Optional full solve for clock outputs; not required for DTS generation.
        try:
            conf = sys.solve()
            summary["solver_used"] = "default"
            summary["solver_succeeded"] = True
            summary["clock_output_clocks"] = conf.get("clock", {}).get("output_clocks")
            rx_conf = conf.get("jesd_ADRV9009_RX", {})
            tx_conf = conf.get("jesd_ADRV9009_TX", {})
            for key in ("F", "K", "M", "L", "Np", "S"):
                if key in rx_conf:
                    cfg["jesd"]["rx"][key] = int(rx_conf[key])
                if key in tx_conf:
                    cfg["jesd"]["tx"][key] = int(tx_conf[key])
        except Exception as ex:
            summary["solve_error"] = str(ex)

    return cfg, summary


def _print_adijif_details(cfg: dict, summary: dict):
    print()
    print("adijif-derived configuration:")
    print(f"  VCXO (Hz)           : {summary['vcxo_hz']}")
    print(f"  Sample rate (Hz)    : {summary['sample_rate_hz']}")
    print(f"  AD9528 m1           : {summary['clock_m1']}")
    print(f"  VCXO doubler        : {summary['clock_use_vcxo_doubler']}")
    print(
        f"  RX JESD             : mode={summary['rx_mode']} class={summary['rx_jesd_class']} "
        f"F={cfg['jesd']['rx']['F']} K={cfg['jesd']['rx']['K']} "
        f"L={cfg['jesd']['rx']['L']} M={cfg['jesd']['rx']['M']}"
    )
    print(
        f"  TX JESD             : mode={summary['tx_mode']} class={summary['tx_jesd_class']} "
        f"F={cfg['jesd']['tx']['F']} K={cfg['jesd']['tx']['K']} "
        f"L={cfg['jesd']['tx']['L']} M={cfg['jesd']['tx']['M']}"
    )
    if summary["solver_succeeded"]:
        print("  Solver              : succeeded")
        if summary["clock_output_clocks"] is not None:
            print(f"  Clock outputs       : {summary['clock_output_clocks']}")
    elif not summary["solver_attempted"]:
        print(
            "  Solver              : skipped (use --solve-adijif to attempt full solve)"
        )
    else:
        print(
            "  Solver              : unavailable/failed, using quick-mode JESD config"
        )
        if summary["solve_error"]:
            print(f"  Solver error        : {summary['solve_error']}")


def _default_config() -> dict:
    """Fallback config when adijif is unavailable."""
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
    return download_kuiper_xsa(
        release=release,
        project=project,
        cache_dir=cache_dir,
        out_dir=out_dir,
    )


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
    parser.add_argument(
        "--vcxo-hz",
        type=float,
        default=DEFAULT_VCXO_HZ,
        help=f"VCXO frequency for adijif setup (default: {DEFAULT_VCXO_HZ})",
    )
    parser.add_argument(
        "--sample-rate-hz",
        type=float,
        default=DEFAULT_SAMPLE_RATE_HZ,
        help=f"ADC/DAC sample rate for adijif setup (default: {DEFAULT_SAMPLE_RATE_HZ})",
    )
    parser.add_argument(
        "--solve-adijif",
        action="store_true",
        help="Attempt full adijif solve to extract solved clock outputs",
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

    try:
        cfg, summary = _resolve_config_from_adijif(
            args.vcxo_hz, args.sample_rate_hz, solve=args.solve_adijif
        )
        _print_adijif_details(cfg, summary)
    except Exception as ex:
        print()
        print("adijif configuration failed; using fallback static config.")
        print(f"  reason: {ex}")
        cfg = _default_config()

    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
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
