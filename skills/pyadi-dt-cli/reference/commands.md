# Command recipes

These recipes match the current `adidtc` Click command surface. Run
`adidtc <command> --help` before using newer installations.

## Discovery

```bash
# Machine-readable support inventory
adidtc kuiper-boards --json-output

# Narrow to fully supported designs
adidtc kuiper-boards --status full

# Discover and inspect XSA profiles
adidtc xsa-profiles
adidtc xsa-profile-show ad9081_zcu102
```

Use the reported board/profile names exactly. `profile_only` means an XSA profile
exists but a complete board-class workflow may not.

## Generate without an XSA

```bash
printf '{}\n' > cfg.json
adidtc gen-dts \
  --board ad9081_fmc \
  --platform zcu102 \
  --config cfg.json \
  --output generated/ad9081-zcu102.dts
```

Supported pairs are reported by `adidtc gen-dts --help`. To produce a DTB, first
check `command -v dtc`, then add `--compile`. Confirm the `.dts` and, when
requested, `.dtb` exist and are non-empty.

## Generate from a Vivado XSA

```bash
adidtc xsa2dt \
  --xsa design.xsa \
  --config cfg.json \
  --profile ad9081_zcu102 \
  --output generated/ad9081-zcu102 \
  --strict-lint
```

For comparison with a trusted design:

```bash
adidtc xsa2dt \
  --xsa design.xsa \
  --config cfg.json \
  --profile ad9081_zcu102 \
  --reference-dts reference.dts \
  --strict-parity \
  --strict-lint \
  --output generated/ad9081-zcu102
```

For PetaLinux, first generate reviewable files without modifying a project:

```bash
adidtc xsa2dt \
  --xsa design.xsa \
  --config cfg.json \
  --profile ad9081_zcu102 \
  --format petalinux \
  --output generated/petalinux
```

Only after reviewing them, add `--petalinux-project /approved/project/path`.

## Analyze include dependencies

```bash
adidtc deps system.dts
adidtc deps system.dts --format json --output dependencies.json
adidtc deps system.dts --format dot --output dependencies.dot
```

A DOT file is not a PNG. Render only when Graphviz is installed:

```bash
dot -Tpng dependencies.dot -o dependencies.png
```

## Read a local tree

```bash
# List compatible IDs
adidtc -c local_file -f system.dtb prop --compat

# Read one property by compatible ID
adidtc -c local_file -f system.dtb \
  prop --compat adi,ad9081 clock-output-names

# Navigate nested nodes
adidtc -c local_file -f system.dtb props amba spi0
```

`local_file` is read-only. Use it to inspect generated artifacts before touching
hardware.

## Read a live tree

```bash
adidtc -c remote_sysfs -i BOARD_IP \
  prop --compat adi,ad9361 clock-output-names
```

Use an existing SSH setup. Do not put passwords in documentation or shell
transcripts.

## Persistent SD-card changes

Preview switching a reference design:

```bash
adidtc -c remote_sd -i BOARD_IP \
  sd-move DESIGN_NAME --dry-run --show
```

Preview copying boot artifacts:

```bash
adidtc -c remote_sd -i BOARD_IP \
  sd-remote-copy BOOT.BIN,system.dtb,image.ub --dry-run --show
```

After explicit approval, remove `--dry-run`; retain `--show` for evidence. Add
`--reboot` only when requested. Confirm target identity before and boot health
afterward.

## Exit and artifact checks

A responsible completion report includes:

1. Exact command with secrets omitted.
2. Exit code.
3. Generated or modified paths.
4. Lint/parity/compile result.
5. Whether hardware was merely copied, rebooted, or actually boot-tested.
