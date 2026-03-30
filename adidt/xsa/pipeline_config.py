"""Top-level pipeline configuration wrapping JESD, clock, and board configs.

``PipelineConfig`` is the typed entry point for all pipeline configuration.
It can be constructed from a raw dict (backward compatible) or directly
with typed sub-configs::

    # From a raw dict (JSON profile, MCP server, existing tests)
    cfg = PipelineConfig.from_dict(raw_dict)

    # Directly with typed configs
    cfg = PipelineConfig(
        jesd=JesdConfig(rx=JesdLinkParams(F=4, K=32)),
        clock=ClockConfig(rx_device_clk_label="hmc7044"),
        fmcdaq2_board=FMCDAQ2BoardConfig(spi_bus="spi0"),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .board_configs import (
    AD9081BoardConfig,
    AD9084BoardConfig,
    AD9172BoardConfig,
    ADRV9009BoardConfig,
    ClockConfig,
    FMCDAQ2BoardConfig,
    FMCDAQ3BoardConfig,
    JesdConfig,
    JesdLinkParams,
)

# Maps dict key -> (attribute name, config class)
_BOARD_KEY_MAP: dict[str, tuple[str, type]] = {
    "fmcdaq2_board": ("fmcdaq2_board", FMCDAQ2BoardConfig),
    "fmcdaq3_board": ("fmcdaq3_board", FMCDAQ3BoardConfig),
    "ad9172_board": ("ad9172_board", AD9172BoardConfig),
    "ad9084_board": ("ad9084_board", AD9084BoardConfig),
    "ad9081_board": ("ad9081_board", AD9081BoardConfig),
    "adrv9009_board": ("adrv9009_board", ADRV9009BoardConfig),
}


@dataclass
class PipelineConfig:
    """Top-level configuration for the XSA-to-DeviceTree pipeline.

    Wraps :class:`JesdConfig`, :class:`ClockConfig`, and an optional
    board-family config.  At most one board config should be set.

    The raw dict form (``cfg["jesd"]["rx"]["F"]``) is still accepted
    everywhere via :meth:`from_dict`, which auto-detects the board family
    from key presence.
    """

    jesd: JesdConfig = field(default_factory=JesdConfig)
    clock: ClockConfig = field(default_factory=ClockConfig)
    fmcdaq2_board: Optional[FMCDAQ2BoardConfig] = None
    fmcdaq3_board: Optional[FMCDAQ3BoardConfig] = None
    ad9172_board: Optional[AD9172BoardConfig] = None
    ad9084_board: Optional[AD9084BoardConfig] = None
    ad9081_board: Optional[AD9081BoardConfig] = None
    adrv9009_board: Optional[ADRV9009BoardConfig] = None
    # Pass-through for fpga_adc / fpga_dac solver output (used by FMCDAQ2/3)
    fpga_adc: dict[str, Any] = field(default_factory=dict)
    fpga_dac: dict[str, Any] = field(default_factory=dict)
    # Extra keys are preserved for forward compatibility
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PipelineConfig":
        """Construct from a raw config dict, auto-detecting board family.

        This is the backward-compatibility bridge for JSON profiles,
        MCP server requests, and existing test dicts.
        """
        jesd = JesdConfig.from_dict(d.get("jesd", {}))
        clock = ClockConfig.from_dict(d.get("clock", {}))

        kwargs: dict[str, Any] = {
            "jesd": jesd,
            "clock": clock,
            "fpga_adc": d.get("fpga_adc", {}),
            "fpga_dac": d.get("fpga_dac", {}),
        }

        extra: dict[str, Any] = {}
        consumed = {"jesd", "clock", "fpga_adc", "fpga_dac"}

        for dict_key, (attr_name, config_cls) in _BOARD_KEY_MAP.items():
            if dict_key in d:
                consumed.add(dict_key)
                kwargs[attr_name] = config_cls.from_dict(d[dict_key])

        # Preserve unrecognized top-level keys
        for k, v in d.items():
            if k not in consumed:
                extra[k] = v
        kwargs["_extra"] = extra

        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Convert back to a raw dict (for serialization or backward compat)."""
        import dataclasses

        result: dict[str, Any] = {}
        result["jesd"] = {
            "rx": dataclasses.asdict(self.jesd.rx),
            "tx": dataclasses.asdict(self.jesd.tx),
        }
        result["clock"] = dataclasses.asdict(self.clock)
        if self.fpga_adc:
            result["fpga_adc"] = self.fpga_adc
        if self.fpga_dac:
            result["fpga_dac"] = self.fpga_dac

        for dict_key, (attr_name, _) in _BOARD_KEY_MAP.items():
            board = getattr(self, attr_name)
            if board is not None:
                result[dict_key] = dataclasses.asdict(board)

        result.update(self._extra)
        return result
