# Release readiness audit — 2026-09-05

Candidate: `0.0.1`, baseline `ee5d7b9`, plus the working-tree fixes below.
No version bump, tag, upload, or publication was performed.

**Software checks, ZC706 generated-DTB boots, and runtime overlay lifecycles
on AD9371/ZC706, ADRV9009/ZC706, and FMCDAQ3/VCU118 pass.** Runtime validation
requires the private modular kernels and JESD lifetime patch documented in
[runtime overlay validation](runtime_overlay_validation.md). Installing this
Python package alone does not update the board kernel.

Earlier overlay runs that appeared to pass were invalidated by stronger checks:
neither configfs write success nor its `applied` status proves that the live tree
changed. The final runs below require exact live-tree markers and their removal.

## Confirmed defects addressed

| Finding | Fix |
|---|---|
| PyPI staging included `SHA256SUMS`, which Twine rejects as an unknown distribution. | Stage and publish only wheels/source distributions; retain checksums with GitHub assets. |
| CLI dependency-parser exceptions and unknown profile names returned success. | Raise Click errors with nonzero exit codes and stderr diagnostics. |
| Empty hardware selections and all-skipped pytest runs passed CI. | Reject empty selections and require passing JUnit evidence with no failures/errors. |
| FMCDAQ3 overlay markers requested `fmcdaq3`; the coordinator advertises `daq3`. | Correct the feature and pin it with a regression check. |
| The coordinator's old environment renderer inferred recovery strategies despite TFTP place tags. | Render the installed plugin's canonical TFTP template from live tags; disable SD autoboot for generated-tree tests. |
| Serial connected after U-Boot's countdown; repeated deployments reused a running board. | Open serial before bootstrap and power off before every deployment. |
| Stock U-Boot ignored the managed TFTP port, sometimes reaching an unrelated stock service. | Add a reproducible private ZC706 U-Boot build with `tftpdstport` support and an explicit exporter-side image override. |
| Staging files did not prove that Linux booted them. | Stamp each DTB with a unique property and require that exact property in Linux. |
| XSA parsing selected the first HWH, which can describe a scoped interconnect instead of the complete design. | Select the manifest's `DEFAULT_BD` handoff; reject ambiguous archives. |
| FMCDAQ3 MicroBlaze clocks rendered `<&clk_bus_0 None>`. | Omit the specifier for zero-cell clocks. |
| AD9371 observation DMA lacked its ADI binding and interrupt override; generic IIO names confused primary RX and observation. | Emit the observation DMA binding and reference IRQ; assign distinct reference IIO node names. |
| Overlay tests treated an existing configfs directory or successful `path` write as application evidence. | Use binary `dtbo` writes, require `applied` status, and verify a unique property in the live tree. Verify its removal on unload. Preserve base DTB symbols. |
| Minimal MicroBlaze userspace lacks `stat`, and configfs was not mounted. | Use `wc -c` for transfers and mount configfs before probing support. |
| Missing FMCDAQ3 handoff prevented generation coverage. | Supply the pre-synthesis XSA under `test/hw/xsa/ref_data/`, with source/tool/framing provenance. |
| Documentation used the wrong PyPI name and stale hardware claims. | Correct `pyadi-dt`, the AD9081 inventory, ZU11EG compile-only coverage, and the audit toctree entry. |
| JESD module teardown called unloaded client callbacks and repeated sysfs cleanup. | Supply a pinned kernel lifetime patch and reproducible ARM/MicroBlaze modular kernel builds. Preserve the notifier guards. |
| Runtime bases already contained overlay SPI children, and repeated fragments updated the same properties. | Remove overlay-owned children from private boot DTBs; emit AD9371/ADRV9009 clock and DMA properties once. |
| FMCDAQ3 clock selector constants, dividers, and JESD clock ownership differed from the reference board. | Correct binding values and the VCU118 clock/SYSREF/converter configuration; verify the full live lifecycle. |
| Kernel overrides could deploy under the wrong basename or disappear before deferred staging. | Keep the override at the bootloader's expected name for the fixture lifetime. Separate ordinary and overlay kernel selection. |

## Software verification

- Final full Python 3.12 suite: **917 passed, 14 skipped, no expected failures**;
  one network test excluded. Focused harness checks were repeated after the
  overlay-specific kernel selection changes.
- Affected parser, board-builder, and hardware-harness tests: **74 passed**
  on each of Python 3.10, 3.11, 3.13, and 3.14. The final overlay marker
  checks were also verified on Python 3.12. After the runtime fixes, the
  affected clock, builder, and deployment set passed **44 tests** on each
  of Python 3.10, 3.11, 3.13, and 3.14.
- After the System-API and provisioning changes, the affected set passed
  **75 tests** on each of Python 3.10, 3.11, 3.13, and 3.14.
- Initial clean wheel installs with `test,xsa,mcp` extras passed the full
  suite on Python 3.10–3.14; minimal wheel and source installs passed CLI,
  metadata, profile, and board-manifest smoke checks outside the checkout.
- The online Kuiper XSA test passed with `ADI_XSA_KUIPER_ONLINE=1`.
- Earlier audit **Debian 12 DEB** and **Fedora 42 RPM** packages built, installed,
  and passed the native-package smoke checks. After the runtime fixes, the
  wheel/source distributions were rebuilt and passed Twine checks; the final
  installed wheel passed model, packaged-profile, and CLI smoke checks.
- Sphinx HTML documentation built with warnings treated as errors. Build,
  Twine staging, checksum, release-preflight, Ruff, and shell checks passed.

The 14 skips comprise 12 AD9081 parity properties absent from the reference
DTS and two tests requiring live IP inputs. The four former AD9371 System-API
expected failures are now ordinary passing
assertions. A new System-API hardware test passed on `bq`, verifying a live
generated-DTB marker, IIO enumeration, both RX links plus TX in JESD DATA,
and RX DMA capture. It uses the reference ZC706 profile; asymmetric custom
framing remains the responsibility of the XSA/profile pipeline.

## Hardware evidence

Coordinator: `10.0.0.41:20408`. Tests used matching places, isolated checkout
copies, exclusive acquisition, power-down teardown, and place release.

| Place | Verified result | Boundary |
|---|---|---|
| `nemo` / ADRV9009 + ZC706 | Generated-DTB boot/RX and two CLI tests passed. Final modular runtime overlay suite: **6 passed**, including live application, JESD DATA, DMA, removal, and reload. | Requires the patched modular kernel and matching module bundle. |
| `bq` / AD9371 + ZC706 | Ordinary suite: **2 passed, 5 skipped, 1 expected failure**. Final modular runtime overlay suite: **6 passed**. Primary RX/TX pass; observation enumerates, reaches DATA, and completes DMA. | Optional sweeps disabled; observation's zero samples retain the no-stimulus expected failure. Runtime requires the patched kernel/modules. |
| `nuc` / FMCDAQ3 + VCU118 | Stock RX passed (4,096 samples, two nonzero channels). Final generated runtime overlay suite: **6 passed**, including DMA, removal, and reload. | Uses the matching reference bitstream and patched MicroBlaze image with embedded modules and runtime base. |
| `tron` / ADRV9009-ZU11EG | XSA pipeline and DTB compilation passed. After reconnecting JTAG, the stock SD image boots through production U-Boot: both PHYs initialize, all three JESD links report DATA, and local DMA captures 65,536 bytes. | Generated-DTB boot remains unvalidated. The investigation uses a newer local plugin; its default network check assumes eth0, while this setup connects through eth1. |
| AD9081 | No matching available place. | `mini2` is currently ADRV9002. |

The first apparent `bq` TFTP passes used its stock port-69 service and are
**not generated-DTB evidence**. Likewise, earlier six-test overlay passes on
all three boards are **not runtime-overlay evidence**. Unique live-tree
markers supersede those results.

The original kernels rejected overlay application with `-95`: the JESD notifier
requires its topology unregistered before the live tree changes. The harness now
stops IIO users, unbinds consumers, unloads clients and the JESD core, and checks
that its bus is absent before changing the tree. This exposed kernel callbacks
into unloaded client modules and repeated cleanup during core exit. The supplied
patch fixes those lifetime defects without bypassing the notifier.

A combined AD9371 ordinary-boot and runtime-overlay invocation also passed:
**8 passed, 5 skipped, 1 expected failure** (`bq-combined-final.log`). This
verifies that overlay kernel overrides coexist with ordinary kernel selection.

Final passing runtime logs are `bq-modular-lifetime.log`,
`nemo-modular-lifetime.log`, and `nuc-runtime-topology.log`. The checks remain
strict; no failing path was converted to a passing skip. The pinned kernel still
warns about memory leaks when properties on boot-time nodes are removed: these
runs qualify the tested bounded lifecycle, not unlimited production cycling.

## Reproducible test artifacts

ZC706 tests used a private U-Boot built from ADI revision
`f06dec3cab5b3ba295a3d171527b7b45fe692469`, enabling `CONFIG_TFTP_PORT` and
using the managed driver's `tftpdstport` variable. Build it on the exporter:

```sh
# Put an ARM Linux cross compiler on PATH first.
bash .github/scripts/build-zc706-test-uboot.sh "$HOME/.cache/adidt/zc706-tftp"
export ADIDT_ZYNQ_UBOOT_IMAGE="$HOME/.cache/adidt/zc706-tftp/u-boot.elf"
source .github/scripts/prepare-hardware-env.sh
```

Set `VENV_DIR`, `LG_ENV`, and `LG_COORDINATOR` before preparing the environment.
The U-Boot override is an absolute **exporter-side** path. Shared recovery
images and coordinator tags were not changed.

FMCDAQ3 XSA provenance is next to the fixture:
`test/hw/xsa/ref_data/system_top_fmcdaq3_vcu118.provenance.json`.
It was exported from HDL `2023_R2_p1`, `projects/daq3/vcu118`, default RX/TX
M=2/L=4/S=1, using Vivado 2025.1 with the source's version check overridden.
This is a pre-synthesis handoff, **not** a newly implemented bitstream. Its
RX/TX JESD addresses match the stock reference kernel. The tool mismatch is
recorded rather than hidden.

The private kernels use ADI Linux revision
`2e8908932dfd9faf40ec9220a508aa1ce02699a8`, the supplied JESD lifetime patch,
and modular IIO/JESD clients. Both architecture builds were executed successfully.
The MicroBlaze image preserves the stock initramfs and appends matching modules;
its wrapper retains the PL nodes and supplies eight XSA aliases while removing
overlay-owned SPI children. See the [build and deployment procedure](runtime_overlay_validation.md).

`ADIDT_OVERLAY_KERNEL_IMAGE_ZYNQ` selects a runner-local ZC706 runtime image;
`ADIDT_OVERLAY_FABRIC_KERNEL_IMAGE` selects an absolute exporter-side MicroBlaze
runtime image. These apply only to overlay tests, allowing ordinary boot tests
in the same invocation. Resource paths are restored at teardown.
`ADIDT_XSA_DIR` optionally selects external XSAs; missing configured files fail.

## Release scope and retained limitations

1. Preserve the matching patched runtime kernels/modules and per-board runner
   configuration on `bq`, `nemo`, and `nuc`. The original built-in kernels do
   not support this overlay lifecycle. Reboot after the qualified 20-cycle
   sequence; unlimited cycling remains unqualified because OF reports property
   allocations that may leak on removal.
2. AD9081 generated-tree hardware validation remains outside this follow-up's
   scope and is not claimed for the current release candidate.

## Retained evidence

Initial audit: `/tmp/pyadi-dt-release-20260905/`.
Follow-up: `/tmp/pyadi-dt-followup-20260905/`, including software/native-package
logs, JUnit, generated trees, and per-run hardware logs. Hardware artifacts
are also copied under `~/.cache/adidt/release-validation/2026-09-05/` with
checksums. Archive reviewed evidence with the final release candidate.
Coordinator YAML contains operational configuration and is excluded from
reviewed evidence bundles.

Useful software checks:

```sh
python -m pytest -q -o addopts='' -m 'not network' -ra
ADI_XSA_KUIPER_ONLINE=1 python -m pytest -q -o addopts='' -m network -ra
python .github/scripts/release_preflight.py --tag v0.0.1
bash .github/scripts/stage-pypi-artifacts.sh dist pypi-dist
twine check pypi-dist/*
python .github/scripts/check_hardware_results.py path/to/junit.xml
```

The staging destination must be empty. Preserve failed hardware JUnit reports
as well as passing evidence. Local twiki context was checked during planning;
repository inspection and live inventory superseded its older notes.


## Applicable-hardware follow-up

The AD9371 System path now shares the complete board wiring with the XSA builder,
preserving the composed clock and converter devices. It supplies clock generators,
observation wiring, the Mykonos profile, and the TX TPL dependency. The reference
composition requires one FMC on ZC706, canonical device labels, a 122.88 MHz VCXO,
and the reference clock/SPI wiring. Unsupported or ambiguous connections fail
explicitly instead of producing a partial boot tree. Use `apply_xsa_topology`
when merging with a specific HDL design.

The labgrid environment used for ZU11EG initially selected an obsolete strategy.
A private environment using the newer local `BootZynqMPJTAG` implementation was
created for investigation. Runner SSH alias `tron` points at another host;
`tron.local` reaches the exporter. After correcting that destination in the test
process, initial scans returned an all-zero chain with no PSU/Cortex-A53 targets.
The user reconnected the board, after which production U-Boot and the stock SD
Linux image booted successfully. The stock image exposes both
`adrv9009-phy` and `adrv9009-phy-b`; both initialize via the JESD FSM. Two RX
(including observation) and one TX link report DATA. Local `iio_readdev` captures
4,096 frames (65,536 bytes). A 256-frame excerpt transferred over UART has
varying samples on all eight I/Q channels (standard deviations 10.43–19.08
LSBs). The final probe passed and powered off/released the board. An earlier
full-buffer UART transfer exceeded the console timeout after successful DMA;
the shorter excerpt avoids that transport limit. Ethernet is connected through `eth1`, which obtained
`10.0.0.59` on one boot; `eth0` has no carrier. The plugin's default eth0-only
IPv4 check therefore fails despite a working Linux boot. The private serial
probe checks the devices and JESD links directly.

No shared plugin checkout, coordinator tags, or SD contents were changed.
These were stock-image results. The subsequent generated-tree qualification
below supersedes the earlier plugin/deployment gap.

Follow-up logs: `/tmp/pyadi-dt-hardware-gaps-20260905/`; hardware run logs are also
under `/tmp/pyadi-dt-followup-20260905/` on their respective runners.


The provisioned ZC706 setups each passed all six runtime tests using the temporary
module server. FMCDAQ3 initially reproduced RX stuck in CGS. Its TX topology runs
the shared AD9528 output synchronization callbacks; starting RX first can disturb
an already initialized RX link. Loading the TX converter/TPL before the ADC fixed
the observed failure, and the complete lifecycle passed again. Kernel log wrap
also exposed an empty post-overlay diagnostic slice; the harness now retains all
available messages when the earlier prefix has rolled out of the ring buffer.


Final provisioned hardware results: `bq` **6 passed**, `nemo` **6 passed**,
and `nuc` **6 passed on each of two consecutive cold boots** with TX-first
initialization. All boards were powered off and released. The complete software
suite passed 917 tests, skipped 14, and excluded one network test; no expected
failures remain. Unlimited overlay cycling is still not qualified.


## Non-AD9081 completion follow-up

All three provisioned overlay places passed the complete six-test module with
`ADIDT_OVERLAY_RELOAD_CYCLES=20`: AD9371-ZC706 (`bq`, 6 passed),
ADRV9009-ZC706 (`nemo`, 6 passed), and FMCDAQ3-VCU118 (`nuc`, 6 passed).
Every cycle checked JESD DATA and a 4,096-sample DMA capture; final removal left
no configfs overlay entry. FMCDAQ3 first failed because UART Lite dropped the
last bytes of a command. With 2 ms per-byte transmission pacing, it completed
all 20 cycles. Earlier failed attempts are retained alongside passing logs.
All three boards were powered off and released.

ZU11EG now uses the pinned labgrid plugin's `BootZynqMPJTAG` strategy. The test
regenerates the complete device tree, compiles it, uploads only the DTB to RAM,
and verifies a unique marker in U-Boot and Linux before checking both PHYs,
two RX/observation JESD links, one TX link, and RX DMA. The stock SD kernel and
root filesystem are retained. The final integrated test passed after a fresh
pipeline run: complete RAM CRC and boot marker verification, all four A53 CPUs
online, both PHYs initialized, all three JESD links in DATA, and a 4,096-sample
capture across eight RX channels. It passed **1 test** in 396.89 seconds and
powered off/released the board.

Live testing exposed and fixed deletion of DDR during CPU deduplication,
truncation of 64-bit DDR registers, FMComms8 wiring used for the SoM, duplicate
HMC7044 output names, incorrect dual-radio JESD dependencies/profile, and missing
carrier Ethernet/SD configuration. The 245.76 MSPS profile records the exact
ADI Linux source revision and license in its JSON metadata. Distinct IIO names
prevent selecting the inactive observation frontend as primary RX. Early boots
also lost CPU1 after a second JTAG connection, including a boot of the ADI
reference DTB and a PSU-only upload without an explicit CPU halt. A serial
S-record transfer of the same generated tree restored all four CPUs. The final
helper uses serial transfer with a complete RAM CRC check and retains the stock
`cpuidle.off=1` boot argument.

The next capture failure exposed nondeterministic selection of the audio DMA
engines from the XSA's unordered labels. DMA selection now filters radio names
and sorts candidates; the real-XSA test checks all three radio DMA labels and
passes with multiple Python hash seeds. ADRV9009-ZC706 then passed all six
hardware tests again with the updated builder and was powered off/released.

The complete local software suite passed **933 tests**, with 14 skips, one
network test excluded, and no expected failures. Independent S-record decoding,
CRC rejection, incremental serial-field parsing, and multi-hash-seed DMA checks
also passed. Ruff and whitespace checks passed.

Candidate `11e0bb24ff186302d74017d88d05e0783e8d0d10` passed the
[release dry run](https://github.com/analogdevicesinc/pyadi-dt/actions/runs/34000952089)
(Python 3.10–3.14 and distribution checks) and
[native packaging](https://github.com/analogdevicesinc/pyadi-dt/actions/runs/34000953667)
(macOS 14 package/install, Debian 12, Fedora 42). These initial runs precede the
final SoM fixes. Updated candidate `8471d70d2ceda5ad10085c08e365d2b656214b3d`
also passed [release validation](https://github.com/analogdevicesinc/pyadi-dt/actions/runs/34002650654)
and [native packaging](https://github.com/analogdevicesinc/pyadi-dt/actions/runs/34002652062).
The final serial-transfer/DMA fixes are validated on the final committed candidate
as recorded in the evidence summary. No tag,
release, PyPI publication, or native release attachment was created.

Evidence is archived under
`~/.cache/adidt/release-validation/2026-09-05/non-ad9081-evidence/`, including
failed attempts, passing JUnit/serial logs, booted DTBs, source provenance and
SHA256 checksums. `validation-summary.json` records the final candidate SHA and
hosted workflow URLs; `candidate-source.tar.gz` preserves that committed source.
Private labgrid environments are excluded. Working logs remain under
`/tmp/pyadi-dt-release-final-20260905/`.
