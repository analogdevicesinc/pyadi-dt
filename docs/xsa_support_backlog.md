# XSA Support Backlog (Kuiper-Derived)

Last updated: 2026-03-15

## Scope

This backlog is derived from Kuiper release boot-partition project directories
that include `bootgen_sysfiles.tgz` with extractable XSA payloads. It is used
to prioritize adding XSA parser/profile/example/test coverage in `pyadi-dt`.

Release/source used for enumeration:

- Kuiper releases API: `https://api.github.com/repos/analogdevicesinc/kuiper/releases`
- Boot partition archive: `https://swdownloads.analog.com/cse/boot_partition_files/2023_r2/latest_boot_partition.tar.gz`

Enumeration snapshot (2023_r2):

- Projects with `bootgen_sysfiles.tgz`: **72**
- Projects with `.xsa` (and `system_top.xsa`): **67**
- Projects without `.xsa` in nested archive: **5** (all Versal; listed below)

## Already Supported

These projects already have XSA parsing/profile flow in this branch:

- `zynqmp-zcu102-rev10-adrv9009`
- `zynqmp-zcu102-rev10-fmcdaq2`

## Prioritized Backlog

Status legend:

- `Todo`: not started
- `WIP`: in progress
- `Done`: implemented and validated
- `N/A`: not applicable

Hardware verification legend:

- `No`: hardware test not yet verified on DUT
- `Yes`: hardware test verified on DUT
- `Partial`: some hardware variants verified, others pending

| Priority | Kuiper Project | Family | Profile | Example | Unit Tests | HW Test | HW Verified | pyadi-build | Notes | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `zynqmp-zcu102-rev10-adrv9025` | ADRV9025 | WIP | WIP | WIP | Todo | No | Todo | Closest to existing ADRV9009 flow | WIP |
| 2 | `zynqmp-zcu102-rev10-adrv9008-1-2` | ADRV9008 | WIP | WIP | WIP | Todo | No | Todo | Explicit `adrv9008_zcu102` profile path (XSA labels are often ADRV9009-style, so auto-detect is ambiguous) | WIP |
| 3 | `zynqmp-zcu102-rev10-adrv937x` | ADRV937x | WIP | WIP | WIP | Todo | No | Todo | Added `adrv937x_zcu102` profile + example + converter-family inference from AD9371 JESD labels; hardware verification pending | WIP |
| 4 | `zynqmp-zcu102-rev10-ad9082-m4-l8` | AD9082 | WIP | WIP | WIP | Todo | No | Todo | Added `ad9082_zcu102` explicit profile + example; AD9081/AD9082 `mxfe` naming ambiguity requires explicit selection | WIP |
| 5 | `zynqmp-zcu102-rev10-ad9083-fmc-ebz` | AD9083 | WIP | WIP | WIP | Todo | No | Todo | Added `ad9083_zcu102` explicit profile + example; explicit selection required due shared AD908x `mxfe` naming | WIP |
| 6 | `zynqmp-zcu102-rev10-ad9172-fmc-ebz-mode4` | AD9172 | WIP | WIP | WIP | Todo | No | Todo | Added explicit `ad9172_zcu102` profile + example for JESD/clock transport mapping; SPI board nodes still require dedicated board overlay support | WIP |
| 7 | `zynqmp-zcu102-rev10-fmcdaq3` | FMCDAQ3 | WIP | WIP | WIP | Todo | No | Todo | Added `fmcdaq3_zcu102` explicit profile + example; JESD/clock transport defaults in place, board SPI overlay extension pending | WIP |
| 8 | `zynq-zc706-adv7511-adrv9009` | ADRV9009 (ZC706) | WIP | WIP | WIP | Todo | No | Todo | Added `adrv9009_zc706` explicit profile + example; generic JESD label variant still needs dedicated node mapping for clean DT compile | WIP |
| 9 | `zynq-zc706-adv7511-adrv9008-1-2` | ADRV9008 (ZC706) | WIP | WIP | WIP | Todo | No | Todo | Added `adrv9008_zc706` explicit profile + example; generic JESD label variant still needs dedicated node mapping for clean DT compile | WIP |
| 10 | `zynq-zc706-adv7511-adrv937x` | ADRV937x (ZC706) | WIP | WIP | WIP | Todo | No | Todo | Added `adrv937x_zc706` explicit profile + example; generic JESD label variant still needs dedicated node mapping for clean DT compile | WIP |
| 11 | `zynq-zc706-adv7511-adrv9002` | ADRV9002 | WIP | WIP | WIP | Todo | No | Todo | Added `adrv9002_zc706` converter-family alias (`axi_adrv9001`) + explicit profile/example scaffold; board-specific node generation pending | WIP |
| 12 | `zynq-zc706-adv7511-ad9081` | AD9081 (ZC706) | WIP | WIP | WIP | Todo | No | Todo | Added `ad9081_zc706` explicit profile + example; platform-specific node tuning still needed for clean DT compile | WIP |
| 13 | `zynq-zc706-adv7511-ad9082` | AD9082 (ZC706) | Todo | Todo | Todo | Todo | No | Todo | ZC706 variant | Todo |
| 14 | `zynq-zc706-adv7511-fmcdaq3-revC` | FMCDAQ3 (ZC706) | WIP | WIP | WIP | Todo | No | Todo | Added `fmcdaq3_zc706` explicit profile + example; JESD/clock transport defaults in place, board SPI overlay extension pending | WIP |
| 15 | `zynq-zc706-adv7511-fmcomms11` | FMCOMMS11 | Todo | Todo | Todo | Todo | No | Todo | Distinct mixed-signal topology | Todo |
| 16 | `zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb` | ADRV9009 + ZU11EG | Todo | Todo | Todo | Todo | No | Todo | Alternate carrier/clocking | Todo |
| 17 | `zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb-fmcbridge` | ADRV9009 + bridge | Todo | Todo | Todo | Todo | No | Todo | Variant topology | Todo |
| 18 | `zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb-sync-fmcomms8` | ADRV9009 sync | Todo | Todo | Todo | Todo | No | Todo | Multi-device sync path | Todo |
| 19 | `zynqmp-adrv9009-zu11eg-revb-adrv2crr-fmc-revb-xmicrowave` | ADRV9009 + xmicrowave | Todo | Todo | Todo | Todo | No | Todo | External RF front-end integration | Todo |
| 20 | `zynqmp-zcu102-rev10-stingray` | Stingray | Todo | Todo | Todo | Todo | No | Todo | Custom project-specific mapping | Todo |

## Deferred (No XSA Found in 2023_r2 Nested Tar)

These projects were present but had no `.xsa` in `bootgen_sysfiles.tgz` at the
time of enumeration:

- `versal-vck190-reva-ad9081`
- `versal-vck190-reva-ad9082`
- `versal-vck190-reva-ad9209`
- `versal-vpk180-reva-ad9081`
- `versal-vpk180-reva-ad9082`

## Suggested Execution Order

1. Finish ZCU102 transceiver family (`adrv9025`, `adrv9008`, `adrv937x`).
2. Add AD908x variants (`ad9082`, `ad9083`) reusing AD9081 framework.
3. Add FMCDAQ3 class support (`zcu102` then `zc706`).
4. Extend existing families to ZC706 variants.
5. Add ZU11EG ADRV9009 variant cluster.

## Per-Project Acceptance Checklist

For each project, complete:

- Add/extend parser mapping and profile JSON
- Add example script in `examples/xsa/`
- Add `test/xsa` unit coverage for parser + node builder + pipeline name/profile
- Add `test/hw` hardware clean test (when LG env is available)
- Add optional pyadi-build integration for kernel+dtb deployment path
- Add docs update (`README` + `doc/source/xsa.rst`) with usage notes
