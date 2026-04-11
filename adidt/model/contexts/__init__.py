"""Shared template-context builders for board components.

Each function returns a plain dict ready to pass to a Jinja2 template.
These are used by both the XSA pipeline (via board builders) and the
manual board-class workflow (via ``to_board_model()``).

This package re-exports every public function so that existing imports
of the form ``from adidt.model.contexts import build_hmc7044_ctx``
continue to work unchanged.
"""

from __future__ import annotations

# -- fpga: utilities and FPGA infrastructure builders -----------------------
from .fpga import build_adxcvr_ctx as build_adxcvr_ctx
from .fpga import build_jesd204_overlay_ctx as build_jesd204_overlay_ctx
from .fpga import build_tpl_core_ctx as build_tpl_core_ctx
from .fpga import coerce_board_int as coerce_board_int
from .fpga import fmt_gpi_gpo as fmt_gpi_gpo
from .fpga import fmt_hz as fmt_hz

# -- clocks: clock chip builders --------------------------------------------
from .clocks import build_ad9523_1_ctx as build_ad9523_1_ctx
from .clocks import build_ad9528_1_ctx as build_ad9528_1_ctx
from .clocks import build_ad9528_ctx as build_ad9528_ctx
from .clocks import build_ad9545_ctx as build_ad9545_ctx
from .clocks import build_adf4030_ctx as build_adf4030_ctx
from .clocks import build_adf4350_ctx as build_adf4350_ctx
from .clocks import build_adf4371_ctx as build_adf4371_ctx
from .clocks import build_adf4377_ctx as build_adf4377_ctx
from .clocks import build_adf4382_ctx as build_adf4382_ctx
from .clocks import build_hmc7044_channel_ctx as build_hmc7044_channel_ctx
from .clocks import build_hmc7044_ctx as build_hmc7044_ctx
from .clocks import build_ltc6952_ctx as build_ltc6952_ctx
from .clocks import build_ltc6953_ctx as build_ltc6953_ctx

# -- converters: ADC/DAC builders -------------------------------------------
from .converters import build_ad7768_ctx as build_ad7768_ctx
from .converters import build_ad9088_ctx as build_ad9088_ctx
from .converters import build_ad9144_ctx as build_ad9144_ctx
from .converters import build_ad9152_ctx as build_ad9152_ctx
from .converters import build_ad9172_device_ctx as build_ad9172_device_ctx
from .converters import build_ad916x_ctx as build_ad916x_ctx
from .converters import build_ad9467_ctx as build_ad9467_ctx
from .converters import build_ad9680_ctx as build_ad9680_ctx
from .converters import build_ad9739a_ctx as build_ad9739a_ctx
from .converters import build_adaq8092_ctx as build_adaq8092_ctx

# -- transceivers: transceiver builders -------------------------------------
from .transceivers import build_ad9081_mxfe_ctx as build_ad9081_mxfe_ctx
from .transceivers import build_ad9082_ctx as build_ad9082_ctx
from .transceivers import build_ad9083_ctx as build_ad9083_ctx
from .transceivers import build_ad9084_ctx as build_ad9084_ctx
from .transceivers import build_adrv9009_device_ctx as build_adrv9009_device_ctx

# -- rf_frontends: RF front-end builders ------------------------------------
from .rf_frontends import build_adar1000_ctx as build_adar1000_ctx
from .rf_frontends import build_admv1013_ctx as build_admv1013_ctx
from .rf_frontends import build_admv1014_ctx as build_admv1014_ctx
from .rf_frontends import build_adrf6780_ctx as build_adrf6780_ctx

# -- sensors: simple SPI sensor builders ------------------------------------
from .sensors import build_ad7124_ctx as build_ad7124_ctx
from .sensors import build_adis16495_ctx as build_adis16495_ctx
from .sensors import build_adxl345_ctx as build_adxl345_ctx

__all__ = [
    # fpga
    "fmt_hz",
    "coerce_board_int",
    "fmt_gpi_gpo",
    "build_adxcvr_ctx",
    "build_jesd204_overlay_ctx",
    "build_tpl_core_ctx",
    # clocks
    "build_hmc7044_channel_ctx",
    "build_hmc7044_ctx",
    "build_ad9523_1_ctx",
    "build_ad9528_ctx",
    "build_ad9528_1_ctx",
    "build_ad9545_ctx",
    "build_adf4382_ctx",
    "build_ltc6952_ctx",
    "build_ltc6953_ctx",
    "build_adf4371_ctx",
    "build_adf4377_ctx",
    "build_adf4350_ctx",
    "build_adf4030_ctx",
    # converters
    "build_ad9680_ctx",
    "build_ad9144_ctx",
    "build_ad9152_ctx",
    "build_ad9172_device_ctx",
    "build_ad9088_ctx",
    "build_ad9467_ctx",
    "build_ad7768_ctx",
    "build_adaq8092_ctx",
    "build_ad9739a_ctx",
    "build_ad916x_ctx",
    # transceivers
    "build_ad9081_mxfe_ctx",
    "build_ad9082_ctx",
    "build_ad9083_ctx",
    "build_ad9084_ctx",
    "build_adrv9009_device_ctx",
    # rf_frontends
    "build_admv1013_ctx",
    "build_admv1014_ctx",
    "build_adrf6780_ctx",
    "build_adar1000_ctx",
    # sensors
    "build_adis16495_ctx",
    "build_adxl345_ctx",
    "build_ad7124_ctx",
]
