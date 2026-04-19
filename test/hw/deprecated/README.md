# Deprecated hardware tests

Every test in this directory has been superseded by the declarative
`adidt.System` hardware-test pattern.

## Canonical replacement

- `test/hw/test_ad9081_zcu102_system_hw.py` — end-to-end reference
  flow using `adidt.eval.ad9081_fmc` + `adidt.fpga.zcu102` +
  `adidt.System`, with XSA parsing, base DTS generation via
  `SdtgenRunner`, overlay rendering, merge, DTB compile, and labgrid
  boot + IIO + JESD204 verification. Verified green on
  `/jenkins/lg_ad9081_zcu102.yaml`.

## Mapping from deprecated → recommended follow-up

| Deprecated test | Recommended path |
|---|---|
| `test_ad9081_board_model_hw.py` | `test/hw/test_ad9081_zcu102_system_hw.py` |
| `test_adrv9009_board_model_hw.py` | add a sibling `test_adrv9009_zcu102_system_hw.py` |
| `test_fmcdaq2_board_model_hw.py` | add a sibling `test_fmcdaq2_zcu102_system_hw.py` |
| `xsa/test_ad9081_xsa_hw_clean.py` | `test/hw/test_ad9081_zcu102_system_hw.py` |
| `xsa/test_ad9081_xsa_hw_m4_l8.py` | same, with M4/L8 JESD mode |
| `xsa/test_ad9084_vcu118_xsa_hw.py` | add a sibling `test_ad9084_vcu118_system_hw.py` |
| `xsa/test_ad9172_zcu102_xsa_hw_clean.py` | add a sibling `test_ad9172_zcu102_system_hw.py` |
| `xsa/test_adrv9009_xsa_hw*.py` | add a sibling `test_adrv9009_*_system_hw.py` |
| `xsa/test_fmcdaq2_*_xsa_hw_clean.py` | add siblings for fmcdaq2 |
| `xsa/test_fmcdaq3_*_xsa_hw_clean.py` | add siblings for fmcdaq3 |
| `xsa/test_fmcomms8_zcu102_xsa_hw_clean.py` | add a sibling for fmcomms8 dual-chip |
| `xsa/test_kuiper_boards.py` | XSA-pipeline meta test; may stay as-is under deprecated until `System` gains a board-inventory API |
| `xsa/test_petalinux_build_hw.py` | XSA-pipeline PetaLinux test; may stay as-is until `System` gains equivalent coverage |

## Running a deprecated test

```
RUN_DEPRECATED_HW=1 pytest test/hw/deprecated/test_ad9081_board_model_hw.py -v
```

Without the environment variable the directory is silently excluded
from pytest collection via `conftest.py:collect_ignore_glob`.
