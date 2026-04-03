import io
import json
import os
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.topology import XsaParser
from test.xsa.kuiper_release import (
    extract_project_xsa,
    download_project_xsa,
    KuiperXsaError,
)


FIXTURE_CFG = Path(__file__).parent / "fixtures" / "ad9081_config.json"


def _fake_sdtgen_run(xsa_path, output_dir, timeout=120):
    dts = output_dir / "system-top.dts"
    dts.write_text(
        "/dts-v1/;\n/ {\n\tamba: axi {\n\t\t#address-cells = <2>;\n\t};\n};\n"
    )
    return dts


def _build_outer_tar_with_nested_xsa(
    tarball_path: Path, project: str, xsa_bytes: bytes
):
    nested_buf = io.BytesIO()
    with tarfile.open(fileobj=nested_buf, mode="w:gz") as inner:
        info = tarfile.TarInfo(name="system_top.xsa")
        info.size = len(xsa_bytes)
        inner.addfile(info, io.BytesIO(xsa_bytes))
    nested_bytes = nested_buf.getvalue()

    with tarfile.open(tarball_path, mode="w:gz") as outer:
        nested_info = tarfile.TarInfo(name=f"{project}/bootgen_sysfiles.tgz")
        nested_info.size = len(nested_bytes)
        outer.addfile(nested_info, io.BytesIO(nested_bytes))


def test_extract_project_xsa_from_nested_bootgen_archive(tmp_path):
    project = "zynqmp-zcu102-rev10-adrv9009"
    tarball = tmp_path / "boot_partition.tar.gz"
    expected = b"FAKE_XSA"
    _build_outer_tar_with_nested_xsa(tarball, project, expected)

    out = extract_project_xsa(
        tarball_path=tarball,
        project_dir=project,
        output_dir=tmp_path / "out",
    )

    assert out.name == "system_top.xsa"
    assert out.read_bytes() == expected


def test_extract_project_xsa_raises_useful_error_for_unknown_project(tmp_path):
    tarball = tmp_path / "boot_partition.tar.gz"
    _build_outer_tar_with_nested_xsa(
        tarball, "zynqmp-zcu102-rev10-fmcdaq2", b"FAKE_XSA"
    )

    with pytest.raises(KuiperXsaError) as ex:
        extract_project_xsa(
            tarball_path=tarball,
            project_dir="zynq-zc706-adv7511-fmcdaq2",
            output_dir=tmp_path / "out",
        )

    msg = str(ex.value)
    assert "project not found" in msg
    assert "zynqmp-zcu102-rev10-fmcdaq2" in msg


def test_xsa_parser_detects_axi_adrv9009_converter(tmp_path):
    hwh = """<?xml version="1.0" encoding="UTF-8"?>
<HWH>
  <SYSTEM>
    <MODULE INSTANCE="axi_adrv9009_0" MODTYPE="axi_adrv9009">
      <MEMRANGE BASEVALUE="0x84a00000" />
    </MODULE>
  </SYSTEM>
</HWH>
"""
    xsa = tmp_path / "adrv9009.xsa"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("system.hwh", hwh)
    xsa.write_bytes(buf.getvalue())

    topo = XsaParser().parse(xsa)
    assert any(conv.ip_type == "axi_adrv9009" for conv in topo.converters)


@pytest.mark.network
def test_adrv9009_zcu102_kuiper_xsa_parse_and_generate(tmp_path):
    if os.getenv("ADI_XSA_KUIPER_ONLINE") != "1":
        pytest.skip("set ADI_XSA_KUIPER_ONLINE=1 to run Kuiper online XSA test")
    pytest.importorskip("adi_lg_plugins")

    release = os.getenv("ADI_KUIPER_BOOT_RELEASE", "2023_r2")
    project = os.getenv(
        "ADI_KUIPER_XSA_PROJECT",
        "zynqmp-zcu102-rev10-adrv9009",
    )

    xsa_path = download_project_xsa(
        release=release,
        project_dir=project,
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "xsa",
    )
    assert xsa_path.exists()

    topology = XsaParser().parse(xsa_path)
    assert topology.jesd204_rx
    assert topology.jesd204_tx

    cfg = json.loads(FIXTURE_CFG.read_text())
    outdir = tmp_path / "pipeline_out"
    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        result = XsaPipeline().run(xsa_path, cfg, outdir)

    assert result["overlay"].exists()
    assert result["merged"].exists()
    merged = result["merged"].read_text()
    assert "adi,axi-jesd204-rx-1.0" in merged
