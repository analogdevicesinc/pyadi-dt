# Release hardware validation

The completed 2026-09-05 qualification applies to candidate
[`c4e9a605f540dcf6d0f7882627a82765b4207e94`](https://github.com/analogdevicesinc/pyadi-dt/commit/c4e9a605f540dcf6d0f7882627a82765b4207e94)
on `release/readiness-20260905`. These results describe that candidate and the
specified board images; rerun affected checks when the code or boot artifacts change.

## Verified scope

| Board | Completed checks | Required environment |
|---|---|---|
| AD9371 / ZC706 | Six overlay tests; 20 reload cycles with JESD DATA and DMA on each cycle, followed by removal | Patched modular kernel and matching modules |
| ADRV9009 / ZC706 | Six overlay tests; 20 reload cycles, plus a six-test rerun after the radio DMA-selection fix | Patched modular kernel and matching modules |
| FMCDAQ3 / VCU118 | Six overlay tests; 20 reload cycles with JESD DATA and DMA on each cycle, followed by removal | Matching MicroBlaze runtime image and embedded modules; TX-first initialization |
| ADRV9009-ZU11EG / ADRV2CRR-FMC | Full XSA pipeline and generated-DTB boot; RAM CRC and boot markers; four CPUs; two PHYs; two RX/observation and one TX JESD links in DATA; 4,096 samples on eight RX channels | Production JTAG boot artifacts, stock SD kernel/rootfs, serial console and a connected Ethernet port |

All four places were powered off and released. See
[runtime overlay validation](runtime_overlay_validation.md) for reproducible
kernel builds, artifact overrides, and `ADIDT_OVERLAY_RELOAD_CYCLES=20`.

Overlay qualification covers the tested 20-cycle sequence. The pinned kernel
reports possible property leaks on removal, so reboot after that sequence;
unlimited cycling remains unqualified. AD9081 was excluded from this follow-up
and has no generated-tree hardware qualification in this evidence set. Other
profiles' presence in the package does not extend this hardware coverage.

## ZU11EG generated-tree test

The `adrv9009_zu11eg` profile describes the dual-radio SoM and its carrier
HMC7044 clock tree, including the 245.76 MSPS reference profile. Its JSON records
the ADI Linux source revision and license. The builder preserves 64-bit DDR
ranges and selects radio DMA engines deterministically, excluding audio DMA
engines that coexist in the XSA.

`test/hw/test_adrv9009zu11eg_adrv2crr-fmc_hw.py` generates and compiles a device
tree from the committed XSA. `BootZynqMPJTAG` reaches production U-Boot; the helper transfers
the DTB to RAM with the serial S-record loader and verifies its complete CRC.
A second JTAG transfer was observed to strand CPU1 even with the reference DTB,
so the DTB transfer uses serial. The helper retains the stock `cpuidle.off=1`
boot argument and writes no SD files or persistent U-Boot settings.

From a Bash shell at the repository root, set `LG_ENV` to an existing private
configuration for the ZU11EG place, then run:

```bash
export VENV_DIR="$HOME/.cache/adidt-ci/adidt-venv"
export LG_COORDINATOR=10.0.0.41:20408
export BOARD=adrv9009zu11eg CARRIER=adrv2crr-fmc
export ADI_XSA_BUILD_KERNEL=0
source .github/scripts/prepare-hardware-env.sh
"$VENV_DIR/bin/labgrid-client" -p tron acquire
trap '"$VENV_DIR/bin/labgrid-client" -p tron release' EXIT
"$VENV_DIR/bin/python" -m pytest -p no:genalyzer -v -s -o addopts='' \
    test/hw/test_adrv9009zu11eg_adrv2crr-fmc_hw.py \
    --junitxml=/tmp/zu11eg.xml
"$VENV_DIR/bin/python" .github/scripts/check_hardware_results.py /tmp/zu11eg.xml
```

The runner needs `sdtgen`, `dtc`, the pinned labgrid plugin, and the production
boot artifacts advertised by the place. Either Ethernet port can provide IIO.
If an exporter alias resolves incorrectly, set `ADIDT_JTAG_HOST` to its verified
hostname before running the test. This override is local to the test process.
The final qualified test took about seven minutes.

## Software and packaging evidence

The local Python 3.12 suite passed **933 tests**, with 14 skips, one network test
excluded, and no expected failures. For the same candidate:

- [Release dry run](https://github.com/analogdevicesinc/pyadi-dt/actions/runs/34004002437): Python 3.10–3.14, wheel/source builds, metadata, checksums, and distribution validation passed.
- [Native packages](https://github.com/analogdevicesinc/pyadi-dt/actions/runs/34004003767): macOS 14 installer, Debian 12 DEB, and Fedora 42 RPM build/install checks passed.

These were validation runs; no release tag or package publication was performed.
The [release runbook](release_runbook.md) describes publication separately.

The lab evidence archive is at
`~/.cache/adidt/release-validation/2026-09-05/non-ad9081-evidence/`.
It contains `validation-summary.json`, the committed candidate source, tested
source hashes, passing and failed logs, JUnit reports, booted DTBs, hosted
artifacts, and `SHA256SUMS`. Private labgrid configurations are excluded.
The [readiness audit](release_readiness_2026-09-05.md) retains the investigation
history and individual fixes.
