"""Device tree interface class."""
import fdt
from fabric import Connection
import random
import string
import os.path
import os


class dt:
    """Device tree interface and management.

    Args:
        arch Optional[str]: Architecture of remote target board. Must be arm or arm64
        dt_source Optional[str]: Location of device tree. Options are:
            local_sysfs: Import from local sysfs
            local_sd: Import from local SD card (this is ADI specific)
            local_file: Import from local file
            remote_sysfs: Import from remote sysfs
            remote_sd: Import from remote board's SD card
        ip Optional[str]: IP address of remote board
        username Optional[str]: username to use with remote board SSH session
        password Optional[str]: password to use with remote board SSH session
        local_dt_filepath Optional[str]: Path to local DT file
    """

    def __init__(
        self,
        arch="arm",
        dt_source="local_sysfs",
        ip="192.168.2.1",
        username="root",
        password="analog",
        local_dt_filepath="",
    ):
        self.local_dt_filepath = local_dt_filepath
        if arch not in ["arm", "arm64"]:
            raise Exception("arch can only by arm or arm64")
        if dt_source not in [
            "local_sysfs",
            "local_file",
            "local_sd",
            "remote_sysfs",
            "remote_sd",
        ]:
            raise Exception(f"Invalid dt_source {dt_source}")
        self.dt_source = dt_source
        self.arch = arch
        self._hide = False
        self.warn = False
        self._dt_filename = "system.dtb" if arch == "arm64" else "devicetree.dtb"
        if "remote" in self.dt_source:
            self._con = Connection(
                "{username}@{ip}:{port}".format(
                    username=username,
                    ip=ip,
                    port=22,
                    connect_timeout=5,
                ),
                connect_kwargs={"password": password},
            )
            if self.dt_source == "remote_sysfs":
                self._import_remote_sysfs()
            else:
                self._import_remote_sd()
        else:
            if "sysfs" in dt_source:
                self._import_sysfs()
            elif dt_source == "local_file":
                self._import_file()
            else:
                self._import_local_sd()

    def _runr(self, cmd, warn=False):
        hide = "out" if self._hide else None
        if "remote" in self.dt_source:
            o = self._con.run(cmd, hide=hide, warn=warn)
        else:
            o = self._con.local(cmd, hide=hide, warn=warn)
        return o.return_code

    def _remote_dtc(self, cmd):
        # Check if dtc exists on remote system
        if "remote" in self.dt_source:
            out = self._con.run("which dtc", hide="out", warn=True)
        else:
            out = self._con.local("which dtc", hide="out", warn=True)
        if out.return_code:
            raise Exception("Device tree compiler not availabe on remote system")
        self._con.run(cmd, hide="out")

    def _handle_sd_mount(self):
        if self._runr("grep -qs '/dev/mmcblk0p1' /proc/mounts", warn=True) == 0:
            # Mount so let re-mount to a known location
            self._runr("umount /dev/mmcblk0p1")
        # Not mounted so lets mount it
        letters = string.ascii_letters
        folder = "/tmp/" + ("".join(random.choice(letters) for i in range(10)))
        self._runr(f"mkdir {folder}")
        self._runr(f"mount /dev/mmcblk0p1 {folder}")
        return folder

    def _import_remote_sd(self):
        # Mount SD and get path
        folder = self._handle_sd_mount()
        with self._con as c, c.sftp() as sftp, sftp.open(
            f"{folder}/{self._dt_filename}", "rb"
        ) as file:
            self._dtb_data_file = file.read()
            self._dt = fdt.parse_dtb(self._dtb_data_file)
        self._con._sftp = None
        self._runr(f"umount /dev/mmcblk0p1")
        self._runr(f"rm -rf {folder}")

    def _import_remote_sysfs(self):
        # Tell dtc to export DT from filesystem
        self._remote_dtc(
            "dtc -I fs -O dtb /sys/firmware/devicetree/base -o /tmp/out.dtb"
        )

        with self._con as c, c.sftp() as sftp, sftp.open("/tmp/out.dtb", "rb") as file:
            self._dtb_data_file = file.read()
            self._dt = fdt.parse_dtb(self._dtb_data_file)

    def _import_file(self):
        if not os.path.isfile(self.local_dt_filepath):
            raise Exception(f"Local DT not found at {self.local_dt_filepath}")

        with open(self.local_dt_filepath, "rb") as f:
            self._dtb_data_file = f.read()
            self._dt = fdt.parse_dtb(self._dtb_data_file)

    def _import_local_sd(self):
        # Mount SD and get path
        folder = self._handle_sd_mount()
        with open(f"{folder}/{self._dt_filename}", "rb") as f:
            self._dtb_data_file = f.read()
            self._dt = fdt.parse_dtb(self._dtb_data_file)
        self._con._sftp = None
        self._runr(f"umount /dev/mmcblk0p1")
        self._runr(f"rm -rf {folder}")

    def _import_sysfs(self):
        if os.name == "nt":
            raise Exception("local_sysfs is not support on Windows")

        e = os.system("dtc -I fs -O dtb /sys/firmware/devicetree/base -o /tmp/out.dtb")
        if e != 0:
            raise Exception("Unable to export device tree locally")

        with open("/tmp/out.dtb", "rb") as f:
            self._dtb_data_file = f.read()
            self._dt = fdt.parse_dtb(self._dtb_data_file)

    def list_node_props(self, node):
        for prop in node.props:
            try:
                print(prop.name, prop.value)
            except:
                print(prop.name)

    def list_child_props(self, node):
        for node in node.parent.nodes:
            for prop in node.props:
                try:
                    print(prop.name, prop.value)
                except:
                    print(prop.name)

    def get_node_by_compatible(self, compatible_id: str):
        """Get node from dt with specific compatible id

        Args:
            compatible_id (str): Name in compatible field of node

        Returns:
            List[fdt.items.PropStrings]: List of device tree nodes found

        """
        nodes = self._dt.search("compatible")
        return [node.parent for node in nodes if compatible_id in node.value]

    def _update_sd(self, reboot=False):
        folder = self._handle_sd_mount()
        with self._con as c, c.sftp() as sftp, sftp.open(
            f"{folder}/{self._dt_filename}", "wb"
        ) as file:
            file.write(self._dt.to_dtb())
        self._con._sftp = None
        self._runr(f"umount /dev/mmcblk0p1")
        self._runr(f"rm -rf {folder}")
        if reboot:
            self._runr(f"reboot")
            print("Device rebooting")

    def _update_fs(self):
        ...

    def update_current_dt(self, reboot=False):
        if self.dt_source == "remote_sd":
            self._update_sd(reboot=reboot)
        else:
            raise Exception("Updating only works on remote_sd right now")

    def write_out_dts(self, filename: str):
        """Write out current DT structure to file"""
        with open(filename, "w") as f:
            f.write(self._dt.to_dts())
