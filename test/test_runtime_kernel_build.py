"""The overlay-kernel helper must apply its patch once before building."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    sys.platform != "linux"
    or not all(shutil.which(tool) for tool in ("bash", "patch", "tar", "sha256sum")),
    reason="Linux kernel-build tools required",
)
def test_kernel_helper_applies_patch_and_preserves_it_on_retry(tmp_path):
    repository = tmp_path / "consumer"
    scripts = repository / ".github/scripts"
    patches = repository / ".github/patches"
    scripts.mkdir(parents=True)
    patches.mkdir()
    original = Path(__file__).parents[1] / ".github/scripts/build-runtime-overlay-kernel.sh"
    helper = scripts / original.name
    shutil.copyfile(original, helper)
    (patches / "jesd204-skip-unregistered-callbacks.patch").write_text(
        "--- a/driver.c\n+++ b/driver.c\n@@ -1 +1 @@\n-old\n+patched\n"
    )
    source = tmp_path / "linux"
    (source / "scripts").mkdir(parents=True)
    driver = source / "driver.c"
    driver.write_text("old\n")
    config = source / "scripts/config"
    config.write_text("#!/bin/sh\nexit 0\n")
    config.chmod(0o755)
    tools = tmp_path / "tools"
    tools.mkdir()
    compiler = tools / "test-gcc"
    compiler.write_text("#!/bin/sh\nexit 0\n")
    compiler.chmod(0o755)
    make = tools / "make"
    make.write_text(
        "#!/bin/sh\n"
        "for argument in \"$@\"; do\n"
        "    case \"$argument\" in O=*) test_output=${argument#O=} ;; esac\n"
        "done\n"
        "mkdir -p \"$test_output/arch/arm64/boot\" \"$test_output/modules-root/lib/modules/test\"\n"
        "echo config > \"$test_output/.config\"\n"
        "echo kernel > \"$test_output/arch/arm64/boot/Image\"\n"
        "echo module > \"$test_output/modules-root/lib/modules/test/kernel.ko\"\n"
    )
    make.chmod(0o755)
    output = tmp_path / "build"
    environment = {
        **os.environ,
        "PATH": f"{tools}:{os.environ['PATH']}",
        "CROSS_COMPILE": str(tools / "test-"),
    }
    for _ in range(2):
        result = subprocess.run(
            ["bash", str(helper), str(source), str(output), "zynqmp"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert driver.read_text() == "patched\n"
        assert (output / "Image").read_text() == "kernel\n"
