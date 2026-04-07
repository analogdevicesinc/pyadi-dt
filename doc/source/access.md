# Live Update Access Models

**adidt** supports a number of different access models depending on where your device tree is located and how you want to apply changes. For example, the device tree can be directly read from the sysfs with *local_sysfs* and *remote_sysfs*. Remote calls will always utilize an SSH connect to access and run commands on remote systems. **adidt** does not support overlay loading at runtime (yet), so writes should be performed with *local_sd* or *remote_sd*. Note that the SD card management features are only supported on ADI platforms where the DT has a known location.

## Supported modes

* `local_sysfs` - DT extracted from sysfs on the local machine.
* `local_file` - DT read from a local `.dts` or `.dtb` file (read-only).
* `local_sd` - DT extracted from a locally attached ADI SD card.
* `remote_sysfs` - DT extracted from a remote board's sysfs over SSH.
* `remote_sd` - DT extracted from a remote board's SD card over SSH.

## Choosing an access mode

| Mode | Reads from | Can write | Requires |
|------|-----------|-----------|----------|
| `local_sysfs` | `/proc/device-tree` | No | Running on target board |
| `local_file` | `.dts` / `.dtb` file | No | File path (`-f` flag) |
| `local_sd` | SD card boot partition | Yes | SD card mounted locally |
| `remote_sysfs` | `/proc/device-tree` over SSH | No | Network access to board |
| `remote_sd` | SD card over SSH | Yes | Network access to board |

Use `local_sysfs` or `remote_sysfs` for read-only inspection of a running
system. Use `local_sd` or `remote_sd` when you need to modify the device tree
and reboot. Use `local_file` to inspect a generated `.dts` or `.dtb` without
hardware.

## CLI examples

Set the default TX LO of a AD9361 based system to 1 GHz remotely:

```bash
adidtc -i ad9361.local -c remote_sd props -cp adi,ad9361 adi,tx-synthesizer-frequency-hz 1000000000
```

Set the default TX LO of a AD9361 based system to 1 GHz from the board itself:

```bash
adidtc -c local_sd props -cp adi,ad9361 adi,tx-synthesizer-frequency-hz 1000000000
```

Get the default RX LO of a AD9361 based system:

```bash
adidtc -c local_sysfs props -cp adi,ad9361 adi,rx-synthesizer-frequency-hz

2400000000
```

Read a property from a local DTS or DTB file:

```bash
adidtc -c local_file -f system.dtb prop -cp adi,ad9081 clock-output-names
```

## Copying boot files to a remote board

The `sd-remote-copy` command copies local boot files (BOOT.BIN, image.ub,
devicetree, etc.) to a remote board's SD card over SSH:

```bash
adidtc -i 192.168.2.1 -c remote_sd sd-remote-copy BOOT.BIN,image.ub -r
```

Options:

- `-r` / `--reboot` — Reboot the board after copying
- `-s` / `--show` — Print commands as they run
- `-d` / `--dry-run` — Show what would be done without executing

## Python API

The `dt` class provides programmatic access to the same functionality:

```python
from adidt import dt

# Read from live hardware over SSH
d = dt(dt_source="remote_sysfs", ip="192.168.2.1")
nodes = d.get_node_by_compatible("adi,ad9361")
print(nodes)

# Read from a local file
d = dt(dt_source="local_file", local_dt_filepath="system.dtb")
nodes = d.get_node_by_compatible("adi,ad9081")

# Update SD card boot files on a remote board
d = dt(dt_source="remote_sd", ip="192.168.2.1")
d.copy_local_files_to_remote_sd_card(["BOOT.BIN", "image.ub"])
```

See {doc}`api/core` for the full `dt` class API reference.
