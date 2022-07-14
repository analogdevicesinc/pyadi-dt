# Access Models

**adidt** supports a number of different access models depending on where your device tree is located and how you want to apply changes. For example, the device tree can be directly read from the sysfs with *local_sysfs* and *remote_sysfs*. Remote calls will always utilize an SSH connect to access and run commands on remote systems. **adidt** does not support overlay loading at runtime (yet), so writes should be performed with *local_sd* or *remote_sd*. Note that the SD card management features are only supported on ADI platforms where the DT has a known location.

## Supported modes

* `local_sysfs` - DT extracted from sysfs.
* `local_sd` - DT extracted from locally attach ADI SD card.
* `remote_sysfs` - DT extracted from remote board sysfs.
* `remote_sd` - DT extracted from remote board with attached ADI SD card.

## Examples

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
