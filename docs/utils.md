# Utilities

This module also contains a few utilities that are specific to ADI prototyping platforms, which are used by the development teams and automation systems. They can be handy for repetitive tasks.

## SD Card BOOT Files

These commands and methods are used to update running system's SD card to place designed reference design files in SD card root

```bash
adidtc -i analog.local -c remote_sd sd-move zynq-zc706-adv7511-fmcdaq2 -r
```
