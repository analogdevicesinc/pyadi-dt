from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


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
