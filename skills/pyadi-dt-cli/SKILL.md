---
name: pyadi-dt-cli
description: Use the pyadi-dt adidtc CLI to inspect, generate, validate, and safely deploy Analog Devices Linux device trees. Trigger for Vivado XSA-to-DTS generation, built-in board profiles, Kuiper support discovery, DTS include analysis, local DTB inspection, live-board property reads, SD-card updates, or pyadi-jif clock updates.
---

# pyadi-dt CLI

Use `adidtc` to inspect, generate, validate, and deploy Linux device trees for
Analog Devices hardware. Prefer discovery and read-only commands first. Treat SD
card writes, property writes, and reboots as hardware-changing operations.

## Start here

1. Confirm the executable and inspect the current command surface:

   ```bash
   command -v adidtc
   adidtc --help
   ```

2. If it is unavailable, from the pyadi-dt repository create an isolated
   environment instead of modifying the system Python:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -e .
   .venv/bin/adidtc --help
   ```

   For XSA generation, install the XSA extra and ensure `sdtgen` is available:

   ```bash
   .venv/bin/pip install -e '.[xsa]'
   command -v sdtgen
   ```

3. Ask for or discover the input path, board/profile, desired output, and whether
   hardware mutation is allowed. Do not guess a board, IP address, credential,
   PetaLinux project, or output path.

4. Run the narrow command's `--help` before composing an unfamiliar invocation.

## Route the task

| Goal | Command | Safe first action |
|---|---|---|
| Discover supported Kuiper designs | `kuiper-boards` | `adidtc kuiper-boards --json-output` |
| Discover XSA profiles | `xsa-profiles`, `xsa-profile-show` | List, then inspect one profile |
| Generate from Vivado XSA | `xsa2dt` | Validate XSA/config/profile and write to a new directory |
| Generate without Vivado/XSA | `gen-dts` | Write a new `.dts`; add `--compile` only when `dtc` exists |
| Analyze DTS includes | `deps` | Use tree or JSON output; do not modify source files |
| Inspect one node/property | `prop` | Use `local_file`, `local_sysfs`, or `remote_sysfs` |
| Navigate nested nodes | `props` | Read without `--value` first |
| Apply pyadi-jif clocks | `jif`, then `jif clock` | Inspect its help and inputs before writing |
| Switch an SD reference design | `sd-move` | Always run `--dry-run --show` first |
| Copy boot files to an SD card | `sd-remote-copy` | Always run `--dry-run --show` first |

See `reference/commands.md` for copy/pasteable recipes and output checks.

## XSA-to-DTS workflow

1. Verify inputs exist and preserve them unchanged:

   ```bash
   test -f design.xsa
   test -f cfg.json
   python -m json.tool cfg.json >/dev/null
   adidtc xsa-profiles
   adidtc xsa-profile-show ad9081_zcu102
   ```

2. Use a fresh output directory. Prefer linting, and use strict validation for a
   release or hardware-bound artifact:

   ```bash
   adidtc xsa2dt \
     -x design.xsa \
     -c cfg.json \
     --profile ad9081_zcu102 \
     -o generated/ad9081-zcu102 \
     --strict-lint
   ```

3. When a trusted DTS exists, request parity evidence:

   ```bash
   adidtc xsa2dt \
     -x design.xsa \
     -c cfg.json \
     --profile ad9081_zcu102 \
     --reference-dts reference.dts \
     --strict-parity \
     --strict-lint \
     -o generated/ad9081-zcu102
   ```

4. Verify the command exited successfully and inspect every reported artifact.
   Expected outputs can include a generated overlay (`.dtso`), merged source
   (`.dts`), HTML report, map/coverage reports, and PetaLinux files when that
   format is selected. Do not claim the tree boots until it has actually been
   compiled and tested on the intended hardware.

5. Use `--format petalinux` without `--petalinux-project` to review generated
   integration files first. Copy into a real project only when the user supplied
   and approved its path.

## Inspection workflow

Choose the least invasive context:

- `local_file`: read a supplied `.dts` or `.dtb`; no hardware access.
- `local_sysfs`: inspect `/proc/device-tree` on the current target.
- `remote_sysfs`: inspect a running board over SSH; read-only.
- `local_sd` / `remote_sd`: persistent boot media; writes are possible.

Examples:

```bash
adidtc -c local_file -f system.dtb prop -cp adi,ad9081 clock-output-names
adidtc -c remote_sysfs -i BOARD_IP prop -cp adi,ad9361 clock-output-names
adidtc -c local_file -f system.dtb props amba spi0
```

Replace `BOARD_IP` with a user-provided or independently discovered address.
Keep global options before the subcommand. First identify nodes, then read the
property, then propose any change.

## Hardware mutation guardrails

- Do not write a property, alter SD contents, or reboot unless the user explicitly
  requested that side effect and identified the target.
- Never place passwords, tokens, or private keys in files, command history,
  reports, or the skill. Prefer existing SSH configuration or an interactive
  credential mechanism. Do not print secrets.
- Before `sd-move` or `sd-remote-copy`, run the identical operation with
  `--dry-run --show`, review source files and destination target, then run the
  real command only after explicit approval.
- Omit `--reboot` on the first real write unless reboot was explicitly requested.
- Preserve original XSA, DTS/DTB, boot files, and configs. Generate into a new
  path and report it.
- A successful generation is not hardware validation. A successful copy is not
  proof of a successful boot. Verify each stage separately.

## Failure handling

- `adidtc: command not found`: use the repository venv or install in a fresh venv.
- Missing `sdtgen`: install lopper/XSA dependencies or source the correct
  Vivado/Vitis environment; do not substitute a fabricated base DTS.
- Missing `dtc`: generation may still produce DTS, but `--compile` cannot be
  claimed successful.
- Unknown profile: run `adidtc xsa-profiles`; do not invent profile names.
- Invalid config or parity/lint failure: preserve the output and report the exact
  diagnostic. Do not disable strict checks merely to get a green command.
- Remote connection failure: distinguish address/authentication/network failures
  from device-tree errors before changing the invocation.

## Completion checklist

- [ ] Used an isolated environment and the actual `adidtc --help` surface.
- [ ] Confirmed input files, target/profile, and output path.
- [ ] Preserved source artifacts and wrote generated files to a new path.
- [ ] Used read-only context or dry-run before hardware-changing operations.
- [ ] Ran applicable lint, parity, JSON, DTS/DTB, or hardware validation.
- [ ] Reported the executed command, exit status, artifact paths, and limitations.
