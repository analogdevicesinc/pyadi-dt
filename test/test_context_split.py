"""Verify context split preserves all import paths."""

from __future__ import annotations


class TestNewImportPaths:
    """Verify functions importable from their new submodule locations."""

    def test_fpga_submodule(self):
        from adidt.model.contexts.fpga import (
            build_adxcvr_ctx,
            build_jesd204_overlay_ctx,
            build_tpl_core_ctx,
            coerce_board_int,
            fmt_gpi_gpo,
            fmt_hz,
        )

        assert callable(fmt_hz)
        assert callable(coerce_board_int)
        assert callable(fmt_gpi_gpo)
        assert callable(build_adxcvr_ctx)
        assert callable(build_jesd204_overlay_ctx)
        assert callable(build_tpl_core_ctx)

    def test_clocks_submodule(self):
        from adidt.model.contexts.clocks import (
            build_ad9523_1_ctx,
            build_ad9528_1_ctx,
            build_ad9528_ctx,
            build_adf4382_ctx,
            build_hmc7044_channel_ctx,
            build_hmc7044_ctx,
        )

        assert callable(build_hmc7044_ctx)
        assert callable(build_hmc7044_channel_ctx)
        assert callable(build_ad9523_1_ctx)
        assert callable(build_ad9528_ctx)
        assert callable(build_ad9528_1_ctx)
        assert callable(build_adf4382_ctx)

    def test_converters_submodule(self):
        from adidt.model.contexts.converters import (
            build_ad9144_ctx,
            build_ad9152_ctx,
            build_ad9172_device_ctx,
            build_ad9680_ctx,
        )

        assert callable(build_ad9680_ctx)
        assert callable(build_ad9144_ctx)
        assert callable(build_ad9152_ctx)
        assert callable(build_ad9172_device_ctx)

    def test_transceivers_submodule(self):
        from adidt.model.contexts.transceivers import (
            build_ad9081_mxfe_ctx,
            build_ad9084_ctx,
            build_adrv9009_device_ctx,
        )

        assert callable(build_ad9081_mxfe_ctx)
        assert callable(build_ad9084_ctx)
        assert callable(build_adrv9009_device_ctx)

    def test_sensors_submodule(self):
        from adidt.model.contexts.sensors import (
            build_ad7124_ctx,
            build_adis16495_ctx,
            build_adxl345_ctx,
        )

        assert callable(build_adis16495_ctx)
        assert callable(build_adxl345_ctx)
        assert callable(build_ad7124_ctx)


class TestBackwardCompatImports:
    """Verify all old import paths still work via __init__.py."""

    def test_direct_imports(self):
        from adidt.model.contexts import (
            build_ad7124_ctx,
            build_ad9081_mxfe_ctx,
            build_ad9084_ctx,
            build_ad9144_ctx,
            build_ad9152_ctx,
            build_ad9172_device_ctx,
            build_ad9523_1_ctx,
            build_ad9528_1_ctx,
            build_ad9528_ctx,
            build_ad9680_ctx,
            build_adf4382_ctx,
            build_adis16495_ctx,
            build_adrv9009_device_ctx,
            build_adxcvr_ctx,
            build_adxl345_ctx,
            build_hmc7044_channel_ctx,
            build_hmc7044_ctx,
            build_jesd204_overlay_ctx,
            build_tpl_core_ctx,
            coerce_board_int,
            fmt_gpi_gpo,
            fmt_hz,
        )

        for fn in [
            fmt_hz,
            coerce_board_int,
            fmt_gpi_gpo,
            build_adxcvr_ctx,
            build_jesd204_overlay_ctx,
            build_tpl_core_ctx,
            build_hmc7044_channel_ctx,
            build_hmc7044_ctx,
            build_ad9523_1_ctx,
            build_ad9528_ctx,
            build_ad9528_1_ctx,
            build_adf4382_ctx,
            build_ad9680_ctx,
            build_ad9144_ctx,
            build_ad9152_ctx,
            build_ad9172_device_ctx,
            build_ad9081_mxfe_ctx,
            build_ad9084_ctx,
            build_adrv9009_device_ctx,
            build_adis16495_ctx,
            build_adxl345_ctx,
            build_ad7124_ctx,
        ]:
            assert callable(fn)

    def test_module_attribute_access(self):
        from adidt.model import contexts

        funcs = [
            "fmt_hz",
            "coerce_board_int",
            "fmt_gpi_gpo",
            "build_adxcvr_ctx",
            "build_jesd204_overlay_ctx",
            "build_tpl_core_ctx",
            "build_hmc7044_channel_ctx",
            "build_hmc7044_ctx",
            "build_ad9523_1_ctx",
            "build_ad9528_ctx",
            "build_ad9528_1_ctx",
            "build_adf4382_ctx",
            "build_ad9680_ctx",
            "build_ad9144_ctx",
            "build_ad9152_ctx",
            "build_ad9172_device_ctx",
            "build_ad9081_mxfe_ctx",
            "build_ad9084_ctx",
            "build_adrv9009_device_ctx",
            "build_adis16495_ctx",
            "build_adxl345_ctx",
            "build_ad7124_ctx",
        ]
        for name in funcs:
            assert hasattr(contexts, name), f"contexts.{name} not found"
            assert callable(getattr(contexts, name))

    def test_fmt_hz_returns_correct_values(self):
        from adidt.model.contexts import fmt_hz

        assert fmt_hz(1_000_000_000) == "1 GHz"
        assert fmt_hz(245_760_000) == "245.76 MHz"
        assert fmt_hz(1_000) == "1 kHz"
        assert fmt_hz(500) == "500 Hz"
