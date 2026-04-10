"""Board registry for pyadi-dt."""

from adidt.boards.daq2 import daq2 as daq2
from adidt.boards.ad9081_fmc import ad9081_fmc as ad9081_fmc
from adidt.boards.ad9084_fmc import ad9084_fmc as ad9084_fmc
from adidt.boards.adrv9009_fmc import adrv9009_fmc as adrv9009_fmc
from adidt.boards.fmcomms_fmc import fmcomms_fmc as fmcomms_fmc
from adidt.boards.adrv9361_z7035 import adrv9361_z7035 as adrv9361_z7035
from adidt.boards.adrv9364_z7020 import adrv9364_z7020 as adrv9364_z7020
from adidt.boards.rpi import rpi as rpi

# Variant registry — boards that reuse a parent's logic with different PLATFORM_CONFIGS
_VARIANTS: dict[str, tuple[type, dict]] = {
    "ad9082_fmc": (ad9081_fmc, {"zcu102": {**ad9081_fmc.PLATFORM_CONFIGS["zcu102"]}}),
    "ad9083_fmc": (ad9081_fmc, {"zcu102": {**ad9081_fmc.PLATFORM_CONFIGS["zcu102"]}}),
    "adrv9008_fmc": (
        adrv9009_fmc,
        {
            "zcu102": {**adrv9009_fmc.PLATFORM_CONFIGS["zcu102"]},
            "zc706": {**adrv9009_fmc.PLATFORM_CONFIGS["zc706"]},
        },
    ),
    "adrv9025_fmc": (
        adrv9009_fmc,
        {"zcu102": {**adrv9009_fmc.PLATFORM_CONFIGS["zcu102"]}},
    ),
    "adrv937x_fmc": (
        adrv9009_fmc,
        {
            "zcu102": {**adrv9009_fmc.PLATFORM_CONFIGS["zcu102"]},
            "zc706": {**adrv9009_fmc.PLATFORM_CONFIGS["zc706"]},
        },
    ),
}

_BOARDS: dict[str, type] = {
    "daq2": daq2,
    "ad9081_fmc": ad9081_fmc,
    "ad9084_fmc": ad9084_fmc,
    "adrv9009_fmc": adrv9009_fmc,
    "fmcomms_fmc": fmcomms_fmc,
    "adrv9361_z7035": adrv9361_z7035,
    "adrv9364_z7020": adrv9364_z7020,
    "rpi": rpi,
}

# Generate variant classes dynamically
for _name, (_parent, _configs) in _VARIANTS.items():
    _cls = type(_name, (_parent,), {"PLATFORM_CONFIGS": _configs})
    _BOARDS[_name] = _cls
    globals()[_name] = _cls


def get_board(name: str, **kwargs) -> object:
    """Create a board instance by name."""
    if name not in _BOARDS:
        raise KeyError(
            f"Board '{name}' not found. Available: {', '.join(sorted(_BOARDS))}"
        )
    return _BOARDS[name](**kwargs)


def list_boards() -> list[str]:
    """Return sorted list of all registered board names."""
    return sorted(_BOARDS.keys())
