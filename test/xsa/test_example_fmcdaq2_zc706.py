from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _load_example_module(file_name: str):
    module_path = Path(__file__).resolve().parents[2] / "examples" / "xsa" / file_name
    spec = importlib.util.spec_from_file_location("fmcdaq2_zc706_example", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_config_from_adijif_falls_back_when_solver_missing(monkeypatch):
    module = _load_example_module("fmcdaq2_zc706.py")

    class _FakeConverter:
        sample_clock = None

        def set_quick_configuration_mode(self, *_args, **_kwargs):
            return None

    class _FakeFpga:
        ref_clock_constraint = ""

        def setup_by_dev_kit_name(self, _name):
            return None

    class _FakeSystem:
        def __init__(self):
            self.fpga = _FakeFpga()
            self.converter = [_FakeConverter(), _FakeConverter()]

        def solve(self):
            raise RuntimeError("cpoptimizer not found")

    fake_adijif = SimpleNamespace(
        system=lambda *_args, **_kwargs: _FakeSystem(),
        utils=SimpleNamespace(
            get_jesd_mode_from_params=lambda *_args, **_kwargs: [
                {
                    "mode": "m",
                    "settings": {
                        "F": 1,
                        "K": 32,
                        "M": 2,
                        "L": 4,
                        "Np": 16,
                        "S": 1,
                    },
                }
            ]
        ),
    )
    monkeypatch.setitem(sys.modules, "adijif", fake_adijif)

    cfg, summary = module._resolve_config_from_adijif(125e6, 500e6)

    assert cfg["jesd"]["rx"]["L"] == 4
    assert cfg["jesd"]["tx"]["L"] == 4
    assert summary["solver_succeeded"] is False
    assert summary["clock_output_clocks"] is None


def test_resolve_config_from_adijif_falls_back_when_solver_missing_zcu102(monkeypatch):
    module = _load_example_module("fmcdaq2_zcu102.py")

    class _FakeConverter:
        sample_clock = None

        def set_quick_configuration_mode(self, *_args, **_kwargs):
            return None

    class _FakeFpga:
        ref_clock_constraint = ""

        def setup_by_dev_kit_name(self, _name):
            return None

    class _FakeSystem:
        def __init__(self):
            self.fpga = _FakeFpga()
            self.converter = [_FakeConverter(), _FakeConverter()]

        def solve(self):
            raise RuntimeError("cpoptimizer not found")

    fake_adijif = SimpleNamespace(
        system=lambda *_args, **_kwargs: _FakeSystem(),
        utils=SimpleNamespace(
            get_jesd_mode_from_params=lambda *_args, **_kwargs: [
                {
                    "mode": "m",
                    "settings": {
                        "F": 1,
                        "K": 32,
                        "M": 2,
                        "L": 4,
                        "Np": 16,
                        "S": 1,
                    },
                }
            ]
        ),
    )
    monkeypatch.setitem(sys.modules, "adijif", fake_adijif)

    cfg, summary = module._resolve_config_from_adijif(125e6, 500e6)

    assert cfg["jesd"]["rx"]["L"] == 4
    assert cfg["jesd"]["tx"]["L"] == 4
    assert summary["solver_succeeded"] is False
    assert summary["clock_output_clocks"] is None


def test_main_supports_download_kuiper_flow_zc706(monkeypatch, tmp_path):
    module = _load_example_module("fmcdaq2_zc706.py")

    fake_xsa = tmp_path / "downloaded_system_top.xsa"
    fake_xsa.write_text("xsa")

    monkeypatch.setattr(
        module,
        "_resolve_config_from_adijif",
        lambda *_args, **_kwargs: ({}, {"clock_output_clocks": None}),
    )
    monkeypatch.setattr(module, "_download_kuiper_xsa", lambda **_kwargs: fake_xsa)

    runner = MagicMock()
    runner.run.return_value = {
        "overlay": tmp_path / "o.dtso",
        "merged": tmp_path / "m.dts",
        "report": tmp_path / "r.html",
    }
    monkeypatch.setattr(module, "XsaPipeline", lambda: runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fmcdaq2_zc706.py",
            "--download-kuiper",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    module.main()
    assert runner.run.call_args.kwargs["xsa_path"] == fake_xsa


def test_main_supports_download_kuiper_flow_zcu102(monkeypatch, tmp_path):
    module = _load_example_module("fmcdaq2_zcu102.py")

    fake_xsa = tmp_path / "downloaded_system_top.xsa"
    fake_xsa.write_text("xsa")

    monkeypatch.setattr(
        module,
        "_resolve_config_from_adijif",
        lambda *_args, **_kwargs: ({}, {"clock_output_clocks": None}),
    )
    monkeypatch.setattr(module, "_download_kuiper_xsa", lambda **_kwargs: fake_xsa)

    runner = MagicMock()
    runner.run.return_value = {
        "overlay": tmp_path / "o.dtso",
        "merged": tmp_path / "m.dts",
        "report": tmp_path / "r.html",
    }
    monkeypatch.setattr(module, "XsaPipeline", lambda: runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fmcdaq2_zcu102.py",
            "--download-kuiper",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    module.main()
    assert runner.run.call_args.kwargs["xsa_path"] == fake_xsa


def test_download_kuiper_xsa_reports_available_projects(monkeypatch, tmp_path):
    module = _load_example_module("fmcdaq2_zc706.py")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)

    tarball = cache_dir / "2023_r2_latest_boot_partition.tar.gz"
    nested_buf = io.BytesIO()
    with tarfile.open(fileobj=nested_buf, mode="w:gz") as inner:
        info = tarfile.TarInfo(name="system_top.xsa")
        payload = b"FAKE_XSA"
        info.size = len(payload)
        inner.addfile(info, io.BytesIO(payload))
    nested_bytes = nested_buf.getvalue()
    with tarfile.open(tarball, mode="w:gz") as outer:
        member = tarfile.TarInfo(
            name="zynqmp-zcu102-rev10-fmcdaq2/bootgen_sysfiles.tgz"
        )
        member.size = len(nested_bytes)
        outer.addfile(member, io.BytesIO(nested_bytes))

    with pytest.raises(RuntimeError) as ex:
        module._download_kuiper_xsa(
            release="2023_r2",
            project="zynq-zc706-adv7511-fmcdaq2",
            cache_dir=cache_dir,
            out_dir=out_dir,
        )
    msg = str(ex.value)
    assert "project not found" in msg
    assert "zynqmp-zcu102-rev10-fmcdaq2" in msg
