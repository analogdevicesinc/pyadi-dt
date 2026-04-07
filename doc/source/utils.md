# Utilities

This module contains utilities for ADI prototyping platforms, used by development teams and automation systems for repetitive tasks like SD card management.

## SD Card BOOT Files

### sd-move

Switch a running board to a different reference design by moving the
appropriate boot files into the SD card root:

```bash
adidtc -i analog.local -c remote_sd sd-move zynq-zc706-adv7511-fmcdaq2 -r
```

Options:

- `-r` / `--reboot` — Reboot the board after moving files
- `-s` / `--show` — Print commands as they run
- `-d` / `--dry-run` — Show what would be done without executing

### sd-remote-copy

Copy local boot files (BOOT.BIN, image.ub, custom DTBs, etc.) to a
remote board's SD card over SSH:

```bash
adidtc -i 192.168.2.1 -c remote_sd sd-remote-copy BOOT.BIN,image.ub -r
```

Pass a comma-separated list of local file paths. The same `-r`, `-s`, and
`-d` flags are available.

### Python API

```python
from adidt import dt

# Switch reference design on a remote board
d = dt(dt_source="remote_sd", ip="192.168.2.1")
d.update_existing_boot_files("zynq-zc706-adv7511-fmcdaq2")

# Copy custom boot files to a remote board
d = dt(dt_source="remote_sd", ip="192.168.2.1")
d.copy_local_files_to_remote_sd_card(["BOOT.BIN", "image.ub"])
```
