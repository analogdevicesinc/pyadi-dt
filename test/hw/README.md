# Adding a new merged-DTB hardware test

You have a board + carrier combination running JESD204 + IIO + a Linux kernel, and you want to validate that the XSA pipeline produces a DTB that boots cleanly end-to-end (kernel probe + IIO discovery + JESD link DATA + RX capture).  This guide walks through writing a `test_<board>_<carrier>_hw.py` that uses the shared `BoardSystemProfile` flow.

For the runtime device-tree overlay test pattern (6 tests per board, configfs lifecycle), see `test/hw/xsa/README.md`.

## Prerequisites

- A labgrid place exposing the board with serial console, power control, and SD or TFTP staging.  The place's `features:` list must include the `lg_features` tuple you'll declare in the SPEC.
- An XSA from the HDL build, either committed under `test/hw/xsa/` or downloadable from a Kuiper boot-partition release.
- A profile JSON in `adidt/xsa/config/profiles/<profile>.json` if the board's SPI / clock / JESD topology is not already supported by an existing builder.
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

## PetaLinux variant

Each XSA-pipeline merged-DTB test has a sibling `test_<board>_<carrier>_petalinux_hw.py` that exercises the same overlay through the PetaLinux DTG path instead of `sdtgen`/lopper.  The pipeline is:

```
XSA → petalinux-create → petalinux-config --get-hw-description
    → pyadi-dt system-user.dtsi (PetalinuxFormatter, --format petalinux)
    → petalinux-build -c device-tree
    → images/linux/system.dtb
    → boot via labgrid (Kuiper kernel + rootfs)
    → standard verify (no kernel faults, IIO probe, JESD DATA, RX capture)
```

This catches regressions specific to PetaLinux's device-tree assembly (`amba_pl` vs `amba` bus-label rewrites, `system-conf.dtsi` include semantics, label resolution against the DTG-generated base) that the sdtgen path doesn't see.  The boot+verify half is the same `boot_and_verify_from_dtb` shared with the XSA tests, so a failure here points at the PetaLinux build/format step rather than the kernel side.

### Prerequisites

- PetaLinux 2023.2 (or newer) installed at `/opt/Xilinx/PetaLinux/2023.2`.  Override with `PETALINUX_INSTALL`.
- One-time smoke check:
  ```sh
  bash -lc "source $PETALINUX_INSTALL/settings.sh && petalinux-create --help" >/dev/null
  ```
  You do **not** need to source `settings.sh` in your test shell — the helper does it once per pytest session and merges the env into every PetaLinux subprocess.
- Same `LG_COORDINATOR` / `LG_ENV` as the XSA tests (see `.env.example`).

### Cache layout

PetaLinux project creation + hardware import takes 5-10 minutes.  Cached under `${PETALINUX_PROJECT_CACHE_DIR}` (default `~/.cache/adidt/petalinux`), keyed by sha256 of the XSA bytes:

```
${PETALINUX_PROJECT_CACHE_DIR}/
  zynqMP/<sha16-of-xsa>/proj/             # petalinux-create + --get-hw-description product
  zynqMP/<sha16-of-xsa>/proj/xsa_import/  # private XSA copy used for --get-hw-description
  zynq/<sha16-of-xsa>/proj/...
```

Cache hit ⇒ skip `petalinux-create` and `petalinux-config --get-hw-description`.  The pyadi-dt overlay injection and `petalinux-build -c device-tree` always re-run because the overlay can change for the same XSA.  Set `PETALINUX_PROJECT_CACHE=0` to force a clean re-create (e.g. after a PetaLinux upgrade).

### Test file template

```python
from __future__ import annotations
import dataclasses
import pytest

from test.hw._petalinux_base import (
    requires_lg,
    requires_petalinux,
    run_petalinux_build_and_verify,
)
from test.hw.test_<board>_<carrier>_xsa_hw import SPEC as XSA_SPEC

SPEC = dataclasses.replace(XSA_SPEC, out_label="<board>_<carrier>_petalinux")


@requires_lg
@requires_petalinux
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_<board>_<carrier>_petalinux_hw(board, tmp_path, request):
    run_petalinux_build_and_verify(SPEC, board=board, request=request, tmp_path=tmp_path)
```

The `out_label` rename keeps the PetaLinux-variant `dmesg_<label>.log` files distinct from the XSA-variant ones in `test/hw/output/`.  If the XSA test appends a per-board diagnostic tail (ILAS dump, sysfs snapshots), copy that tail into the PetaLinux test verbatim — the helper returns the same `(shell, ctx, dmesg_txt)` tuple as `run_xsa_boot_and_verify`.

### Run commands

| Board | Place | Env yaml | Run from |
|---|---|---|---|
| AD9081 / ZCU102 | `mini2` | `test/hw/env/mini2.yaml` | any host (USBSDMux) |
| ADRV9009 / ZC706 | `nemo`  | `test/hw/env/nemo.yaml`  | `nemo` (local TFTP) |
| ADRV9371 / ZC706 | `bq`    | `test/hw/env/bq.yaml`    | `bq` (local TFTP) |

```sh
# AD9081 / ZCU102 — any host
LG_COORDINATOR=10.0.0.41:20408 \
LG_ENV=test/hw/env/mini2.yaml \
PETALINUX_INSTALL=/opt/Xilinx/PetaLinux/2023.2 \
uv run pytest test/hw/test_ad9081_zcu102_petalinux_hw.py -v -s

# ADRV9009 / ZC706 — run on the nemo host
LG_COORDINATOR=10.0.0.41:20408 \
LG_ENV=test/hw/env/nemo.yaml \
PETALINUX_INSTALL=/opt/Xilinx/PetaLinux/2023.2 \
uv run pytest test/hw/test_adrv9009_zc706_petalinux_hw.py -v -s

# ADRV9371 / ZC706 — run on the bq host
LG_COORDINATOR=10.0.0.41:20408 \
LG_ENV=test/hw/env/bq.yaml \
PETALINUX_INSTALL=/opt/Xilinx/PetaLinux/2023.2 \
uv run pytest test/hw/test_adrv9371_zc706_petalinux_hw.py -v -s
```

Expected runtime: ~10-12 min/board on first cache miss (5-10 min create + import, ~3 min device-tree build, 1-2 min boot+verify); ~5 min/board on warm cache.

### Common failures specific to the PetaLinux path

- `Reference to non-existent node or label "amba"` during `petalinux-build` — the pipeline didn't rewrite `&amba` to `&amba_pl` because `topology.inferred_platform()` returned `"unknown"` for a ZynqMP XSA.  The helper fails fast with a clearer hint when it sees this on a `boot_mode="sd"` board.
- `petalinux-create not found` — `PETALINUX_INSTALL` is unset and `petalinux-create` isn't on PATH; the test reports `SKIPPED [requires_petalinux]`.
- First-ever build on a host hits the network for sstate; allow up to 30 min.  Subsequent builds are ~3 min.

### Post-build DTB fixups

`run_petalinux_build_and_verify` patches the produced ``images/linux/system.dtb`` in place via `_apply_dtb_fixups` before staging it for boot.  The fixups paper over PetaLinux 2023.2's stock DTG output not matching the board-level wiring our reference Kuiper rootfs / U-Boot expects:

- **Strip `/chosen/bootargs`** — PetaLinux bakes `bootargs = "earlycon ... root=/dev/ram0 rw"` into the DTB (driven by `CONFIG_SUBSYSTEM_BOOTARGS_AUTO`).  Most U-Boot builds don't overwrite an existing `/chosen/bootargs`, so the kernel ends up with `root=/dev/ram0` and panics with `Unable to mount root fs on unknown-block(179,2)` when the SD-card rootfs is on `/dev/mmcblk0p2`.  Removing the property lets U-Boot's own `bootargs` env var (set by `uEnv.txt`) flow through.

- **Add `no-1-8-v` to `mmc@ff170000` on ZynqMP boards** — the ZCU102 SD slot has 3.3 V-only level translators.  Without `no-1-8-v` the kernel negotiates UHS-I SDR104 at 1.8 V; the SD card then throws read I/O errors during the rootfs mount with the same panic shape.  PetaLinux's stock DTG emits the SDHCI1 node without this property; Kuiper's hand-written DTB does include it.

The proper long-term fix for both is a per-board PetaLinux fragment (BSP/template tweak) rather than a runtime DTB rewrite, but the workaround keeps the hw test path self-contained and obvious.

### Other host-side prerequisites (TFTP boards)

The TFTP-boot boards (`nemo`, `bq`) don't need ssh access to the exporter host (boot files travel over TFTP, console+power are proxied by labgrid), but a few host-local pieces still matter:

- **`libiio0` system package**: `pylibiio` (the python ``iio`` module) loads `libiio.so.0` via ctypes; without it, every test that opens an IIO context fails with `undefined symbol: iio_get_backends_count`.
  ```sh
  sudo apt install -y libiio0
  ```

- **`/var/lib/tftpboot` writable by the test user**: the labgrid `TFTPServerDriver` (a pure-python `SimpleTFTPServer`) writes the staged kernel/DTB into the directory configured on `TFTPServerResource`.
  ```sh
  sudo install -d -o $USER -g $USER /var/lib/tftpboot
  ```

- **Pre-built kernel uImage** when the `pyadi-build` package isn't available: set `ADIDT_KERNEL_IMAGE_ZYNQ` (Zynq-7000) or `ADIDT_KERNEL_IMAGE_ZYNQMP` (ZynqMP) to a local kernel image path.  The corresponding fixture returns it directly and `deploy_and_boot` uploads it via the same path the built kernel would have taken.

- **iptables UDP 69→3069 redirect** if the board's U-Boot (typically pre-2019) ignores `tftpdstport` and always queries the well-known TFTP port.  The labgrid `SimpleTFTPServer` listens on the unprivileged port 3069 (per `TFTPServerResource.port`); a one-line redirect bridges the two without running the test as root:
  ```sh
  sudo iptables -t nat -A PREROUTING -p udp --dport 69 -j REDIRECT --to-port 3069
  ```
  Symptom when missing: U-Boot logs `TFTP server died; starting again` after the RRQ.  `tcpdump 'udp port 69'` will show the request hitting your host on port 69 with nothing answering.

- **SD-boot boards** (`mini2`'s `USBSDMuxDriver`) currently shell out to ssh on the exporter host (e.g. `ssh mini2 usbsdmux ...`) to operate the SD card mux.  This requires a passwordless ssh key for the runner-user → exporter-user path.  Without it the test fails with `BootFPGASoC is in broken state` and `Permission denied (publickey,password)` in the labgrid log.  This is the same blocker for both the XSA and PetaLinux variants of the SD-boot tests.

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
