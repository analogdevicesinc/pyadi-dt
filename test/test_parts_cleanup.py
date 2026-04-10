"""Tests verifying parts cleanup: deduplication and dead code removal."""


class TestAd9545Dedup:
    def test_methods_exist(self):
        from adidt.parts.ad9545 import ad9545_dt

        assert hasattr(ad9545_dt, "pll_set_rate")
        assert hasattr(ad9545_dt, "output_set_rate")
        assert hasattr(ad9545_dt, "_set_assigned_clock_rate")


class TestHmc7044Cleanup:
    def test_no_pulse_gen_modes(self):
        from adidt.parts.hmc7044 import hmc7044_dt

        assert not hasattr(hmc7044_dt, "pulse_gen_modes")


class TestAdrv9009Cleanup:
    def test_no_stub_methods(self):
        from adidt.parts.adrv9009 import adrv9009_dt

        assert not hasattr(adrv9009_dt, "_add_tx_profile_fields")
        assert not hasattr(adrv9009_dt, "_add_obs_profile_fields")
