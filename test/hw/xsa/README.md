# Adding a new overlay test

You have a board + carrier combination running JESD204 + IIO + a Linux kernel with `CONFIG_OF_OVERLAY`, and you want to validate the runtime device-tree overlay lifecycle on it. This guide walks through writing a `test_<board>_<carrier>_overlay.py` that plugs into the existing 6-test suite (unit, configfs, load, dma, unload, reload).

## Prerequisites

- A labgrid place exposing the board with serial console, power control, and (for SoC boots) SD or TFTP staging. The place's `features:` list must include the `lg_features` tuple you'll declare in the SPEC.
- An XSA from the HDL build, either committed under `test/hw/xsa/` or downloadable from a Kuiper boot-partition release.
- A profile JSON in `adidt/xsa/config/profiles/<profile>.json` if the board's SPI / clock / JESD topology is not already supported by an existing builder.
- A working `LG_COORDINATOR` (or `LG_ENV`) — see `.env.example`.

## Steps

### 1. Create the test file

Create `test/hw/xsa/test_<board>_<carrier>_overlay.py` with this shape (replace every `<placeholder>`):

```python
from __future__ import annotations
from typing import Any
import pytest

from test.hw.hw_helpers import check_jesd_framing_plausibility
from test.hw.xsa._overlay_base import (
    booted_board, overlay_dtbo, pipeline_result,
    test_overlay_generation_unit,
    test_configfs_overlay_support,
    test_load_overlay,
    test_dma_loopback,
    test_unload_overlay,
    test_reload_overlay,
)
from test.hw.xsa._overlay_spec import BoardOverlayProfile, acquire_or_local_xsa


def _board_cfg() -> dict[str, Any]:
    cfg = {
        "<builder>_board": {...},
        "jesd": {"rx": {...}, "tx": {...}},
    }
    framing_warnings = check_jesd_framing_plausibility(cfg["jesd"])
    assert not framing_warnings, "JESD cfg inconsistent: " + "\n  ".join(framing_warnings)
    return cfg


SPEC = BoardOverlayProfile(
    overlay_name="<board>_<carrier>_xsa",
    lg_features=("<board>", "<carrier>"),
    skip_reason_label="<board> <carrier>",
    cfg_builder=_board_cfg,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_<board>_<carrier>.xsa",
        "<kuiper_release>",
        "<kuiper_project_dir>",
    ),
    sdtgen_profile="<profile>",
    boot_mode="tftp",                            # see step 2
    kernel_fixture_name="built_kernel_image_zynq",
    iio_required_all=("<chip>",),
    iio_required_any=("<chip>-rx-hpc", "ad_ip_jesd204_tpl_adc"),
    iio_frontend_label="<chip> RX frontend",
    fft_mode="optional",                         # see step 3
)


@pytest.fixture(scope="module")
def overlay_spec() -> BoardOverlayProfile:
    return SPEC
```

Keep the `test_*` import block in the canonical sequence (`unit, configfs, load, dma, unload, reload`). Pytest collects tests in import order, and `test_dma_loopback` skips when the overlay isn't loaded — so it must follow `test_load_overlay`.

### 2. Pick a boot mode

| `boot_mode` | Use when | Required |
|---|---|---|
| `"tftp"` | Zynq-7000 boards using `BootFPGASoCTFTP` (DTB renamed to `devicetree.dtb`) | `kernel_fixture_name="built_kernel_image_zynq"` |
| `"sd"` | ZynqMP boards using `BootFPGASoC` + Kuiper SD card (DTB renamed to `system.dtb`) | `kernel_fixture_name="built_kernel_image_zynqmp"` |
| `"fabric_jtag"` | MicroBlaze / soft-CPU boards using `BootFabric` + JTAG simpleImage (no DTB rebuild) | `kernel_fixture_name=None` |

`fabric_jtag` skips lifecycle tests cleanly when the kernel lacks `CONFIG_OF_OVERLAY`. `test_configfs_overlay_support` always asserts strictly regardless of mode.

### 3. Pick an FFT mode

| `fft_mode` | Use when |
|---|---|
| `"required"` | Reference HDL has internal DAC→ADC loopback (e.g. AD9081 TPL cores). Asserts SNR > 10 dB. |
| `"optional"` | No internal loopback. Logs and passes on low SNR; passes outright on a coherent peak. |
| `"skip"` | Skip phase 2 entirely. Phase 1 (`assert_rx_capture_valid`) still runs. |

Phase 1 (mandatory bare RX capture) always runs and always asserts.

### 4. Add hooks if the board needs them

Wire pluggable callables into the SPEC for board-specific behavior:

| Field | Use when | Live example |
|---|---|---|
| `pre_capture_hook` | Board needs setup before RX capture (push a Talise profile, wake the radio) | `push_talise_profile` in `_overlay_hooks.py` |
| `capture_targets_resolver` | Multiple IIO devices share a name; disambiguate by reg address or scan order | `resolve_adrv9009_rx_tpl` in `_overlay_hooks.py` |
| `dmesg_filter` | Strip benign kernel noise before `assert_no_probe_errors` | `_filter_si570_probe_noise` in `test_adrv9009_zc706_overlay.py` |
| `pyadi_factory` | pyadi-iio's default `adi.<chip>(uri=...)` doesn't work because IIO names differ | `_create_ad9081` in `test_ad9081_zcu102_overlay.py` |
| `fft_failure_diagnostics` | Need on-target debug prints when capture fails (GPIO / IRQ / register state) | `_dmac_irq_failure_probe` in `test_adrv9371_zc706_overlay.py` |

If a hook is reusable across boards in the same family, move it to `_overlay_hooks.py`. If it's truly one-off, keep it inline in the board file.

### 5. Verify

Run the unit-only test (no hardware required):

```sh
uv run pytest test/hw/xsa/test_<board>_<carrier>_overlay.py::test_overlay_generation_unit -v
```

This exercises the XSA → pipeline → DTSO → DTBO chain. If the XSA isn't on disk and Kuiper download fails, the test skips with a clear message.

Run the full suite against the lab:

```sh
LG_COORDINATOR=10.0.0.41:20408 \
LG_ENV=test/hw/env/<place>.yaml \
uv run pytest test/hw/xsa/test_<board>_<carrier>_overlay.py -v -s
```

Acquire the place first if it isn't already yours:

```sh
LG_COORDINATOR=10.0.0.41:20408 uv run labgrid-client -p <place> acquire
```

A clean run reports `6 passed`. Two partial-pass shapes are expected and documented:

- `1 fail / 5 skip` — `test_configfs_overlay_support` failed because the kernel lacks `CONFIG_OF_OVERLAY`. Lifecycle tests skipped through `booted_board`'s configfs gate.
- `1 skip / 5 pass` — `test_overlay_generation_unit` skipped because no XSA is on disk and no Kuiper download path exists for this board.

## Worked example: AD9081 + ZCU102

`test/hw/xsa/test_ad9081_zcu102_overlay.py` is the densest example. It exercises every variation point: a pyadi-jif `cfg_builder`, an `acquire_or_local_xsa` resolver with a fallback name, `boot_mode="sd"`, `fft_mode="required"`, and a `pyadi_factory` that aliases sdtgen IIO names to pyadi-iio's hardcoded production names. Read it when you need to see how a less-common field is wired.

## `BoardOverlayProfile` field reference

| Field | Default | Purpose |
|---|---|---|
| `overlay_name` | — | configfs node name (`/sys/.../overlays/<name>`). |
| `lg_features` | — | labgrid place feature tuple, applied to every test by `xsa/conftest.py`. |
| `skip_reason_label` | — | Human-readable name in skip and log messages. |
| `cfg_builder` | — | Zero-arg callable returning the cfg dict for `XsaPipeline.run`. |
| `xsa_resolver` | — | `(tmp_path) -> Path` to the XSA file. Skips on failure. |
| `sdtgen_profile` | — | Pipeline profile name. |
| `boot_mode` | — | `"tftp"`, `"sd"`, or `"fabric_jtag"`. |
| `topology_assert` | no-op | `(XsaTopology) -> None`; raises or skips on unexpected topology. |
| `sdtgen_timeout` | 300 | Pipeline `sdtgen` timeout in seconds. |
| `dtso_must_contain_all` | `()` | Substrings the unit test asserts are all present in the DTSO. |
| `dtso_must_contain_any` | `()` | Substrings the unit test asserts at least one is present. |
| `kernel_fixture_name` | `None` | Name of a kernel-image fixture. `None` for `fabric_jtag`. |
| `settle_after_apply_s` | 5.0 | Seconds to sleep after overlay apply. Bump to 8.0 for Mykonos / Talise re-init. |
| `iio_required_all` | `()` | IIO device names that must all be present after overlay apply. |
| `iio_required_any` | `()` | IIO device names of which at least one must be present. |
| `iio_frontend_label` | `"RX frontend"` | Used in failure messages when `iio_required_any` mismatches. |
| `dmesg_filter` | identity | `(text) -> text` to strip benign noise before probe-error assertion. |
| `fft_mode` | `"skip"` | `"required"`, `"optional"`, or `"skip"`. |
| `pre_capture_hook` | `None` | `(shell, tmp_path) -> bool`. `True` re-asserts JESD DATA after. |
| `capture_targets_resolver` | `None` | `(iio.Context) -> Sequence[str]` to disambiguate IIO targets. |
| `capture_target_names` | `()` | Fallback target names when `capture_targets_resolver` is unset. |
| `pyadi_class_name` | `None` | Class name in `adi.*` for the FFT phase (e.g. `"ad9081"`). |
| `pyadi_factory` | `None` | `(uri) -> dev` overriding the default `adi.<class>(uri=uri)`. |
| `dds_tone_hz` | 1_000_000 | DDS tone frequency for the FFT phase. |
| `dds_scale` | 0.5 | DDS tone amplitude (0..1). |
| `rx_buffer_size` | 16384 | Capture buffer depth for the FFT phase. |
| `fft_failure_diagnostics` | `None` | `(shell) -> None` invoked when phase 1 capture fails. |
