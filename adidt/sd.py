"""ADI SD Card Manipulation Utilies"""
import click


class sd:
    def find(self, loc, ext=None):
        if ext:
            out = self._runr_o(f"find {loc} | grep .{ext}", warn=True)
        else:
            out = self._runr_o(f"find {loc}", warn=True)
        out = out.stdout.split("\n")
        return list(filter(lambda c: "*" not in c and c != "", out))

    def list(self, loc, ext=None):
        if ext:
            out = self._runr_o(f"for i in {loc}/*.{ext}; do echo $i; done", warn=True)
        else:
            out = self._runr_o(f"for i in {loc}/*; do echo $i; done", warn=True)
        out = out.stdout.split("\n")
        return list(filter(lambda c: "*" not in c and c != "", out))

    def update_existing_boot_files(self, reference_design, show=False, dryrun=False):
        # Mount remote SD
        folder = self._handle_sd_mount()
        try:
            self._hide = True
            out = self._runr_o(f"for i in {folder}/*; do echo $i; done")
            boards = out.stdout.split("\n")
            filtered = []
            filtered_full = []
            # Remove DTBs and pull out only zynq (for now)
            for board in boards:
                if board[-3:] != ".dtb" and "zynq" in board:
                    filtered_full.append(board)
                    filtered.append(board.split("/")[-1])

            if reference_design not in filtered:
                cmd = f"Reference design '{reference_design}' not found.\nThe following were found:\n-- "
                cmd += "\n-- ".join(filtered)
                print(cmd)
                return

            for board_full, board in zip(filtered_full, filtered):
                if reference_design == board:

                    # Move BOOT.BIN
                    if self._runr(f"test -f {board_full}/BOOT.BIN") != 0:
                        raise Exception(f"BOOT.BIN not found on SD card for {board}")
                    if show:
                        print(f"cp {board_full}/BOOT.BIN {folder}/")
                    if not dryrun:
                        self._runr(f"cp {board_full}/BOOT.BIN {folder}")

                    # Device tree
                    dtbs = self.list(board_full, "dtb")
                    if not dtbs:
                        subfolders = self.find(board_full, "dtb")
                        if subfolders:
                            subfolders = [
                                "/".join(f.split("/")[4:]) for f in subfolders
                            ]
                            dtbs = click.prompt(
                                "Subfolder found. Select devicetree:",
                                type=click.Choice(subfolders, case_sensitive=False),
                                show_choices=True,
                            )
                            dtbs = board_full + "/" + dtbs
                    if isinstance(dtbs, list):
                        dtbs = dtbs[0]
                    if not dtbs:
                        raise Exception(f"No device tree found for {board}")

                    if self._runr(f"test -f {dtbs}", warn=False) != 0:
                        raise Exception(f"system.dtb not found on SD card for {board}")

                    if dtbs.split("/")[-1] not in ["system.dtb", "devicetree.dtb"]:
                        dt = "devicetree.dtb" if self.arch == "arm" else "system.dtb"
                        if show:
                            print(f"cp {dtbs} {folder}/{dt}")
                        if not dryrun:
                            self._runr(f"cp {dtbs} {folder}/{dt}")
                    else:
                        if show:
                            print(f"cp {dtbs} {folder}/")
                        if not dryrun:
                            self._runr(f"cp {dtbs} {folder}/")

                    # Kernel
                    if self._arch == "arm":
                        kernel = "zynq-common/uImage"
                    else:
                        kernel = "zynqmp-common/Image"

                    if self._runr(f"test -f {folder}/{kernel}", warn=False) != 0:
                        raise Exception(f"{kernel} not found on SD card")
                    if show:
                        print(f"cp {folder}/{kernel} {folder}/")
                    if not dryrun:
                        self._runr(f"cp {folder}/{kernel} {folder}/")

                    break

        finally:
            self._runr(f"umount /dev/mmcblk0p1")
            self._runr(f"rm -rf {folder}")
