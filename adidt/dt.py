"""Device tree interface class."""
import fdt
from fabric import Connection
import random
import string
import os.path


class dt:
    """Device tree interface and management."""
    def __init__(
        self,
        arch="arm",
        dt_source="fs",
        ip="192.168.2.1",
        username="root",
        password="analog",
        local_dt_filepath="",
    ):
        self.local_dt_filepath = local_dt_filepath
        if arch not in ["arm", "arm64"]:
            raise Exception("arch can only by arm or arm64")
        if dt_source not in ["fs", "remote_fs", "remote_sd"]:
            raise Exception(f"Invalid dt_source {dt_source}")
        self.dt_source = dt_source
        self.arch = arch
        self._hide = False
        self.warn = False
        self._dt_filename = "system.dtb" if arch == "arm64" else "devicetree.dtb"
        if self.dt_source != "fs":
            self._con = Connection(
                "{username}@{ip}:{port}".format(
                    username=username,
                    ip=ip,
                    port=22,
                    connect_timeout=5,
                ),
                connect_kwargs={"password": password},
            )
            if self.dt_source == "remote_fs":
                self._import_remote_fs()
            else:
                self._import_remote_sd()
        else:
            self._import()

    def _runr(self, cmd, warn=False):
        if self._hide:
            hide = "out"
        else:
            hide = None
        o = self._con.run(cmd, hide=hide, warn=warn)
        return o.return_code

    def _remote_dtc(self, cmd):
        # Check if dtc exists on remote system
        out = self._con.run("which dtc", hide="out", warn=True)
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

    def _import_remote_fs(self):
        # Tell dtc to export DT from filesystem
        self._remote_dtc(
            "dtc -I fs -O dtb /sys/firmware/devicetree/base -o /tmp/out.dtb"
        )

        with self._con as c, c.sftp() as sftp, sftp.open("/tmp/out.dtb", "rb") as file:
            self._dtb_data_file = file.read()
            self._dt = fdt.parse_dtb(self._dtb_data_file)

    def _import(self):
        if not os.path.isfile(self.local_dt_filepath):
            raise Exception(f"Local DT not found at {self.local_dt_filepath}")

        with open(self.local_dt_filepath, "rb") as f:
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

    def write_out_dts(self,filename):
        with open(filename, "w") as f:
            f.write(self._dt.to_dts())


# node = dt1.search('hmc7044@0')[0]
# for prop in node.props:
#     print(prop)
# print('---------------')
# for chan in node.nodes:
#      print('----:',chan.name)
#      for prop in chan.props:
#          print(prop)
