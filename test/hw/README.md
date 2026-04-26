# Adding a new merged-DTB hardware test

You have a board + carrier combination running JESD204 + IIO + a Linux kernel, and you want to validate that the XSA pipeline produces a DTB that boots cleanly end-to-end (kernel probe + IIO discovery + JESD link DATA + RX capture).  This guide walks through writing a `test_<board>_<carrier>_hw.py` that uses the shared `BoardSystemProfile` flow.

For the runtime device-tree overlay test pattern (6 tests per board, configfs lifecycle), see `test/hw/xsa/README.md`.

## Prerequisites

- A labgrid place exposing the board with serial console, power control, and SD or TFTP staging.  The place's `features:` list must include the `lg_features` tuple you'll declare in the SPEC.
- An XSA from the HDL build, either committed under `test/hw/xsa/` or downloadable from a Kuiper boot-partition release.
- A profile JSON in `adidt/xsa/profiles/<profile>.json` if the board's SPI / clock / JESD topology is not already supported by an existing builder.
- A working `LG_COORDINATOR` (or `LG_ENV`) — see `.env.example`.

## Steps

### 1. Create the test file

Create `test/hw/test_<board>_<carrier>_hw.py` with this shape (replace every `<placeholder>`):

```python
from __future__ import annotations
from typing import Any
import pytest

from test.hw._system_base import (
    BoardSystemProfile,
    acquire_or_local_xsa,
    requires_lg,
    run_xsa_boot_and_verify,
)


def _board_cfg() -> dict[str, Any]:
    return {
        "<builder>_board": {...},
        "jesd": {"rx": {...}, "tx": {...}},
    }


def _topology_assert(topology) -> None:
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"


SPEC = BoardSystemProfile(
    lg_features=("<board>", "<carrier>"),
    cfg_builder=_board_cfg,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_<board>_<carrier>.xsa",
        "<kuiper_release>",
        "<kuiper_project_dir>",
    ),
    sdtgen_profile="<profile>",
    topology_assert=_topology_assert,
    boot_mode="tftp",                              # see step 2
    kernel_fixture_name="built_kernel_image_zynq",
    out_label="<board>_<carrier>",
    dmesg_grep_pattern="<board>|<chip>|jesd204|probe|failed|error",
    merged_dts_must_contain=('compatible = "adi,<chip>"',),
    probe_signature_any=("<chip>",),
    iio_required_all=("<chip>-phy",),
    iio_required_any_groups=(
        ("axi-<chip>-rx-hpc", "ad_ip_jesd204_tpl_adc"),
    ),
    rx_capture_target_names=("axi-<chip>-rx-hpc", "ad_ip_jesd204_tpl_adc"),
)


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_<board>_<carrier>_hw(board, tmp_path, request):
    """End-to-end pyadi-dt <board>+<carrier> via the XSA pipeline."""
    run_xsa_boot_and_verify(SPEC, board=board, request=request, tmp_path=tmp_path)
```

The test function takes `board, tmp_path, request` — the kernel-image fixture is pulled by name through `request.getfixturevalue(SPEC.kernel_fixture_name)` so the function signature stays the same across boards.

### 2. Pick a boot mode

| `boot_mode` | Use when | Required |
|---|---|---|
| `"tftp"` | Zynq-7000 boards using `BootFPGASoCTFTP` (DTB renamed to `devicetree.dtb`) | `kernel_fixture_name="built_kernel_image_zynq"` |
| `"sd"` | ZynqMP boards using `BootFPGASoC` + Kuiper SD card (DTB renamed to `system.dtb`) | `kernel_fixture_name="built_kernel_image_zynqmp"` |

Boards that boot from an embedded simpleImage with no DTB rebuild (FMCDAQ3 + VCU118) don't fit this pattern — write the test directly against `board` and `hw_helpers` like `test_fmcdaq3_vcu118_hw.py` does.

### 3. Add a board-specific diagnostic tail (optional)

`run_xsa_boot_and_verify` returns `(shell, ctx, dmesg_txt)`.  If your board needs extra forensics (sysfs register dumps, ILAS state, profile sweeps), append them after the helper call:

```python
@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_<board>_<carrier>_hw(board, tmp_path, request):
    shell, _ctx, dmesg_txt = run_xsa_boot_and_verify(
        SPEC, board=board, request=request, tmp_path=tmp_path
    )
    # board-specific diagnostics — print sysfs, parse ILAS, push profiles, ...
```

The standard verify covers: dmesg gating (no kernel faults, no probe errors), probe signature in dmesg, IIO device discovery, JESD links in DATA, optional RX capture.  Anything beyond that is per-board.  See `test_adrv9371_zc706_hw.py` for an extensive diagnostic tail (TPL descriptor regs, AXI DMAC state, AD9371 phy snapshot) and `test_adrv9009_zcu102_hw.py` for a Talise filter-profile sweep.

### 4. Verify

Run the test against the lab.  Hardware tests are excluded from the default pytest discovery via `--ignore-glob=*_hw.py`, so pass the file by exact path:

```sh
LG_COORDINATOR=10.0.0.41:20408 \
LG_ENV=test/hw/env/<place>.yaml \
uv run pytest test/hw/test_<board>_<carrier>_hw.py -v -s
```

Acquire the place first if it isn't already yours:

```sh
LG_COORDINATOR=10.0.0.41:20408 uv run labgrid-client -p <place> acquire
```

A clean run reports `1 passed`.  Common failure shapes:

- `AssertionError: IIO device 'X' not present` — the SPEC names don't match what the board exposes.  Compare the assert's `Devices: [...]` list against your `iio_required_all` / `iio_required_any_groups`.
- `AssertionError: <probe sig> not found in dmesg` — the kernel didn't probe the chip.  Check the merged DTS, GPIO numbers, SPI bus assignments.
- Pipeline-stage `pytest.skip` (XSA missing, pyadi-jif missing) — install the dependency or commit the XSA.

## Worked example: AD9081 + ZCU102

`test/hw/test_ad9081_zcu102_xsa_hw.py` is the reference.  It exercises every common SPEC field: a pyadi-jif `cfg_builder`, an `acquire_or_local_xsa` resolver, `boot_mode="sd"`, two `iio_required_any_groups` (RX + TX frontends), and reg-address-pinned JESD globs (`84a90000.axi[_-]jesd204[_-]rx`).  The test body is a single `run_xsa_boot_and_verify(...)` call.

For a board that adds a diagnostic tail, see `test_adrv9371_zc706_hw.py`.  For a board with a post-boot sweep, see `test_adrv9009_zcu102_hw.py`.

## `BoardSystemProfile` field reference

| Field | Default | Purpose |
|---|---|---|
| `lg_features` | — | labgrid place feature tuple, applied to the test via `@pytest.mark.lg_feature(...)`. |
| `cfg_builder` | — | Zero-arg callable returning the cfg dict for `XsaPipeline.run`. |
| `xsa_resolver` | — | `(tmp_path) -> Path` to the XSA file.  Skips on failure. |
| `boot_mode` | — | `"tftp"` or `"sd"`. |
| `kernel_fixture_name` | — | Name of a session-scoped kernel-image fixture (`"built_kernel_image_zynq"` or `"built_kernel_image_zynqmp"`). |
| `out_label` | — | Short string used in dmesg log filenames and assertion `context=` arguments. |
| `dmesg_grep_pattern` | — | Extended regex for the diagnostic `dmesg \| grep -Ei <pattern>` tail. |
| `sdtgen_profile` | `None` | Pipeline profile name; `None` means auto-detect from topology. |
| `sdtgen_timeout` | 300 | Pipeline `sdtgen` timeout in seconds. |
| `topology_assert` | no-op | `(XsaTopology) -> None`; raises or skips on unexpected topology. |
| `merged_dts_must_contain` | `()` | Substrings asserted to be present in the merged DTS (e.g. `'compatible = "adi,ad9081"'`). |
| `probe_signature_any` | `()` | Substrings of which at least one must appear in dmesg (case-insensitive); empty disables the check. |
| `probe_signature_message` | generic | Failure message when none of `probe_signature_any` matches. |
| `iio_required_all` | `()` | IIO device names that must all be present. |
| `iio_required_any_groups` | `()` | Tuple of groups; each inner tuple is "any of these names must be present".  Express multiple independent any-of asserts (e.g. RX frontend group + TX frontend group). |
| `jesd_rx_glob` | default | sysfs glob for the RX JESD platform device.  `None` uses a permissive default. |
| `jesd_tx_glob` | default | Same for TX. |
| `dmesg_filter` | identity | `(text) -> text` to strip benign noise before `assert_no_probe_errors`. |
| `rx_capture_target_names` | `()` | Tuple of IIO device names to try for the RX capture smoke test; empty skips the capture. |
