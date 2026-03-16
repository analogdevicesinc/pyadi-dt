from __future__ import annotations

import sys
from types import SimpleNamespace


def test_resolve_fmcdaq3_config_falls_back_when_ad9152_model_missing(monkeypatch):
    from adidt.xsa.adijif_fmcdaq3 import resolve_fmcdaq3_config

    class _FakeSystem:
        pass

    def _raise_missing_model(*_args, **_kwargs):
        raise AttributeError("module 'adijif' has no attribute 'ad9152'")

    fake_adijif = SimpleNamespace(system=_raise_missing_model)
    monkeypatch.setitem(sys.modules, "adijif", fake_adijif)

    cfg, summary = resolve_fmcdaq3_config(
        vcxo_hz=125e6,
        sample_rate_hz=500e6,
        dev_kit_name="zcu102",
        solve=True,
    )

    assert cfg["jesd"]["rx"]["L"] == 4
    assert cfg["jesd"]["tx"]["F"] == 1
    assert summary["solver_succeeded"] is False
    assert summary["fallback_used"] is True
    assert "ad9152" in summary["fallback_reason"]
