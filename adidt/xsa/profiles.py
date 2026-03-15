import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .exceptions import ProfileError


_AD9081_BOARD_ALLOWED_KEYS = {
    "clock_spi",
    "clock_cs",
    "adc_spi",
    "adc_cs",
    "reset_gpio",
    "sysref_req_gpio",
    "rx1_enable_gpio",
    "rx2_enable_gpio",
    "tx1_enable_gpio",
    "tx2_enable_gpio",
    "hmc7044_channel_blocks",
}
_ADRV9009_BOARD_ALLOWED_KEYS = {
    "misc_clk_hz",
    "spi_bus",
    "clk_cs",
    "trx_cs",
    "trx_reset_gpio",
    "trx_sysref_req_gpio",
    "trx_spi_max_frequency",
    "ad9528_vcxo_freq",
    "rx_link_id",
    "rx_os_link_id",
    "tx_link_id",
    "tx_octets_per_frame",
    "rx_os_octets_per_frame",
    "trx_profile_props",
    "ad9528_channel_blocks",
}
_FMCDAQ2_BOARD_ALLOWED_KEYS = {
    "spi_bus",
    "clock_cs",
    "adc_cs",
    "dac_cs",
    "clock_vcxo_hz",
    "clock_spi_max_frequency",
    "adc_spi_max_frequency",
    "dac_spi_max_frequency",
    "adc_core_label",
    "dac_core_label",
    "adc_dma_label",
    "dac_dma_label",
    "adc_xcvr_label",
    "dac_xcvr_label",
    "adc_jesd_label",
    "dac_jesd_label",
    "adc_jesd_link_id",
    "dac_jesd_link_id",
    "adc_device_clk_idx",
    "adc_sysref_clk_idx",
    "adc_xcvr_ref_clk_idx",
    "adc_sampling_frequency_hz",
    "dac_device_clk_idx",
    "dac_xcvr_ref_clk_idx",
    "gpio_controller",
    "clk_sync_gpio",
    "clk_status0_gpio",
    "clk_status1_gpio",
    "dac_txen_gpio",
    "dac_reset_gpio",
    "dac_irq_gpio",
    "adc_powerdown_gpio",
    "adc_fastdetect_a_gpio",
    "adc_fastdetect_b_gpio",
}
_LIST_ONLY_KEYS = {
    "hmc7044_channel_blocks",
    "trx_profile_props",
    "ad9528_channel_blocks",
}

_AD9081_BOARD_INT_KEYS = {
    "clock_cs",
    "adc_cs",
    "reset_gpio",
    "sysref_req_gpio",
    "rx1_enable_gpio",
    "rx2_enable_gpio",
    "tx1_enable_gpio",
    "tx2_enable_gpio",
}
_AD9081_BOARD_STR_KEYS = {"clock_spi", "adc_spi"}
_ADRV9009_BOARD_INT_KEYS = {
    "misc_clk_hz",
    "clk_cs",
    "trx_cs",
    "trx_reset_gpio",
    "trx_sysref_req_gpio",
    "trx_spi_max_frequency",
    "ad9528_vcxo_freq",
    "rx_link_id",
    "rx_os_link_id",
    "tx_link_id",
    "tx_octets_per_frame",
    "rx_os_octets_per_frame",
}
_ADRV9009_BOARD_STR_KEYS = {"spi_bus"}
_FMCDAQ2_BOARD_INT_KEYS = {
    "clock_cs",
    "adc_cs",
    "dac_cs",
    "clock_vcxo_hz",
    "clock_spi_max_frequency",
    "adc_spi_max_frequency",
    "dac_spi_max_frequency",
    "adc_jesd_link_id",
    "dac_jesd_link_id",
    "adc_device_clk_idx",
    "adc_sysref_clk_idx",
    "adc_xcvr_ref_clk_idx",
    "adc_sampling_frequency_hz",
    "dac_device_clk_idx",
    "dac_xcvr_ref_clk_idx",
    "clk_sync_gpio",
    "clk_status0_gpio",
    "clk_status1_gpio",
    "dac_txen_gpio",
    "dac_reset_gpio",
    "dac_irq_gpio",
    "adc_powerdown_gpio",
    "adc_fastdetect_a_gpio",
    "adc_fastdetect_b_gpio",
}
_FMCDAQ2_BOARD_STR_KEYS = {
    "spi_bus",
    "adc_core_label",
    "dac_core_label",
    "adc_dma_label",
    "dac_dma_label",
    "adc_xcvr_label",
    "dac_xcvr_label",
    "adc_jesd_label",
    "dac_jesd_label",
    "gpio_controller",
}


def _is_valid_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_typed_keys(
    board_name: str,
    values: dict[str, Any],
    int_keys: set[str],
    str_keys: set[str],
) -> None:
    for key in int_keys.intersection(values):
        value = values[key]
        if not _is_valid_int(value):
            raise ProfileError(
                f"invalid profile defaults.{board_name}.{key}: expected integer"
            )
        if value < 0:
            raise ProfileError(
                f"invalid profile defaults.{board_name}.{key}: must be >= 0"
            )
    for key in str_keys.intersection(values):
        value = values[key]
        if not isinstance(value, str) or not value.strip():
            raise ProfileError(
                f"invalid profile defaults.{board_name}.{key}: expected non-empty string"
            )


def _validate_board_defaults(
    board_name: str, values: dict[str, Any], allowed: set[str]
) -> None:
    unknown_keys = sorted(set(values) - allowed)
    if unknown_keys:
        unknown = ", ".join(unknown_keys)
        raise ProfileError(
            f"invalid profile defaults.{board_name}: unknown key(s): {unknown}"
        )
    for key in _LIST_ONLY_KEYS.intersection(values):
        if not isinstance(values[key], list):
            raise ProfileError(
                f"invalid profile defaults.{board_name}.{key}: must be a list"
            )


def _validate_profile_defaults(defaults: dict[str, Any]) -> None:
    ad9081_board = defaults.get("ad9081_board")
    if ad9081_board is not None:
        if not isinstance(ad9081_board, dict):
            raise ProfileError("invalid profile defaults.ad9081_board: expected object")
        _validate_board_defaults(
            "ad9081_board", ad9081_board, _AD9081_BOARD_ALLOWED_KEYS
        )
        _validate_typed_keys(
            "ad9081_board",
            ad9081_board,
            _AD9081_BOARD_INT_KEYS,
            _AD9081_BOARD_STR_KEYS,
        )

    adrv9009_board = defaults.get("adrv9009_board")
    if adrv9009_board is not None:
        if not isinstance(adrv9009_board, dict):
            raise ProfileError(
                "invalid profile defaults.adrv9009_board: expected object"
            )
        _validate_board_defaults(
            "adrv9009_board", adrv9009_board, _ADRV9009_BOARD_ALLOWED_KEYS
        )
        _validate_typed_keys(
            "adrv9009_board",
            adrv9009_board,
            _ADRV9009_BOARD_INT_KEYS,
            _ADRV9009_BOARD_STR_KEYS,
        )

    fmcdaq2_board = defaults.get("fmcdaq2_board")
    if fmcdaq2_board is not None:
        if not isinstance(fmcdaq2_board, dict):
            raise ProfileError(
                "invalid profile defaults.fmcdaq2_board: expected object"
            )
        _validate_board_defaults(
            "fmcdaq2_board", fmcdaq2_board, _FMCDAQ2_BOARD_ALLOWED_KEYS
        )
        _validate_typed_keys(
            "fmcdaq2_board",
            fmcdaq2_board,
            _FMCDAQ2_BOARD_INT_KEYS,
            _FMCDAQ2_BOARD_STR_KEYS,
        )


class ProfileManager:
    """Loads built-in XSA board profiles."""

    def __init__(self, profile_dir: Path | None = None):
        self.profile_dir = profile_dir or (Path(__file__).parent / "profiles")

    def list_profiles(self) -> list[str]:
        if not self.profile_dir.exists():
            return []
        return sorted(p.stem for p in self.profile_dir.glob("*.json"))

    def load(self, name: str) -> dict[str, Any]:
        path = self.profile_dir / f"{name}.json"
        if not path.exists():
            raise ProfileError(f"profile not found: {name}")
        try:
            profile = json.loads(path.read_text())
        except json.JSONDecodeError as ex:
            raise ProfileError(f"invalid profile JSON for {name}: {ex}") from ex

        if not isinstance(profile, dict):
            raise ProfileError(f"invalid profile format for {name}: expected object")
        defaults = profile.get("defaults")
        if defaults is None or not isinstance(defaults, dict):
            raise ProfileError(f"invalid profile format for {name}: missing defaults")
        _validate_profile_defaults(defaults)
        return profile


def merge_profile_defaults(
    cfg: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    """Merge profile defaults into cfg, preserving explicit cfg values."""

    def _merge(defaults: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = deepcopy(current)
        for key, val in defaults.items():
            if key not in merged:
                merged[key] = deepcopy(val)
            elif isinstance(val, dict) and isinstance(merged[key], dict):
                merged[key] = _merge(val, merged[key])
        return merged

    defaults = profile.get("defaults", {})
    return _merge(defaults, cfg)
