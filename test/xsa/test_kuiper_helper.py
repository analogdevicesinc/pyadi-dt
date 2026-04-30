from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

pytest.importorskip("requests", reason="requests not installed")

from adidt.xsa.parse.kuiper import download_kuiper_xsa


def _build_boot_partition_tar(
    tarball_path: Path, project: str, xsa_name: str = "system_top.xsa"
) -> None:
    nested_buf = io.BytesIO()
    with tarfile.open(fileobj=nested_buf, mode="w:gz") as inner:
        payload = b"FAKE_XSA"
        info = tarfile.TarInfo(name=xsa_name)
        info.size = len(payload)
        inner.addfile(info, io.BytesIO(payload))
    nested_bytes = nested_buf.getvalue()

    with tarfile.open(tarball_path, mode="w:gz") as outer:
        nested_info = tarfile.TarInfo(name=f"{project}/bootgen_sysfiles.tgz")
        nested_info.size = len(nested_bytes)
        outer.addfile(nested_info, io.BytesIO(nested_bytes))


def test_download_kuiper_xsa_uses_cached_tarball(tmp_path):
    cache_dir = tmp_path / "cache"
    out_dir = tmp_path / "out"
    cache_dir.mkdir()
    out_dir.mkdir()
    tarball = cache_dir / "2023_r2_latest_boot_partition.tar.gz"
    _build_boot_partition_tar(tarball, "zynq-zc706-adv7511-fmcdaq2")

    xsa = download_kuiper_xsa(
        release="2023_r2",
        project="zynq-zc706-adv7511-fmcdaq2",
        cache_dir=cache_dir,
        out_dir=out_dir,
    )

    assert xsa.exists()
    assert xsa.name == "system_top.xsa"
    assert xsa.read_bytes() == b"FAKE_XSA"


def test_download_kuiper_xsa_reports_available_projects_for_bad_project(tmp_path):
    cache_dir = tmp_path / "cache"
    out_dir = tmp_path / "out"
    cache_dir.mkdir()
    out_dir.mkdir()
    tarball = cache_dir / "2023_r2_latest_boot_partition.tar.gz"
    _build_boot_partition_tar(tarball, "zynqmp-zcu102-rev10-fmcdaq2")

    with pytest.raises(RuntimeError) as ex:
        download_kuiper_xsa(
            release="2023_r2",
            project="zynq-zc706-adv7511-fmcdaq2",
            cache_dir=cache_dir,
            out_dir=out_dir,
        )
    msg = str(ex.value)
    assert "project not found" in msg
    assert "zynqmp-zcu102-rev10-fmcdaq2" in msg
