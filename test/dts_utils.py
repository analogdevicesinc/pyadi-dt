import os
import shutil
import subprocess
import urllib.request
import tarfile
from pathlib import Path

# ARM GNU Toolchain configuration for cross-compiling ARM64 device trees
# Vivado/Vitis 2023.2
TOOLCHAIN_2023_R2_URL_ARM64 = "https://developer.arm.com/-/media/Files/downloads/gnu/12.2.rel1/binrel/arm-gnu-toolchain-12.2.rel1-x86_64-aarch64-none-elf.tar.xz"
TOOLCHAIN_2023_R2_VERSION = "12.2.rel1"
TOOLCHAIN_2023_R2_ARCH_ARM64 = "aarch64-none-elf"

# ARM GNU Toolchain configuration for cross-compiling ARM32 device trees
# Vivado/Vitis 2023.2
TOOLCHAIN_2023_R2_URL_ARM32 = "https://developer.arm.com/-/media/Files/downloads/gnu/12.2.rel1/binrel/arm-gnu-toolchain-12.2.rel1-x86_64-arm-none-eabi.tar.xz"
TOOLCHAIN_2023_R2_ARCH_ARM32 = "arm-none-eabi"

# ARM GNU Toolchain configuration for cross-compiling ARM64 device trees
# Vivado/Vitis 2025.1
TOOLCHAIN_2025_R1_URL_ARM64 = "https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/arm-gnu-toolchain-13.3.rel1-x86_64-aarch64-none-elf.tar.xz"
TOOLCHAIN_2025_R1_VERSION = "13.3.rel1"
TOOLCHAIN_2025_R1_ARCH_ARM64 = "aarch64-none-elf"


def download_and_cache_toolchain(arch: str = "arm64", version: str = "2023.2", cache_dir: Path = None) -> Path:
    """Download and cache ARM GNU toolchain for cross-compilation.

    Downloads the ARM GNU toolchain for arm or arm64 from ARM's official site
    and extracts it to a cache directory. If already cached, skips download.

    Args:
        arch: Target architecture ('arm' or 'arm64')
        version: Target version ('2023.2' or '2025.1')
        cache_dir: Directory to cache toolchain. Defaults to ~/.cache/pyadi-dt/

    Returns:
        Path to toolchain bin directory containing cross-compiler

    Raises:
        RuntimeError: If download or extraction fails or arch is invalid
    """
    # Select toolchain based on architecture
    if version == "2023.2": 
        if arch == "arm64":
            toolchain_url = TOOLCHAIN_2023_R2_URL_ARM64
            toolchain_version = TOOLCHAIN_2023_R2_VERSION
            toolchain_arch = TOOLCHAIN_2023_R2_ARCH_ARM64
        elif arch == "arm":
            toolchain_url = TOOLCHAIN_2023_R2_URL_ARM32
            toolchain_version = TOOLCHAIN_2023_R2_VERSION
            toolchain_arch = TOOLCHAIN_2023_R2_ARCH_ARM32
        else:
            raise ValueError(f"Unsupported architecture: {arch}. Must be 'arm' or 'arm64'")
    elif version == "2025.1":
        if arch == "arm64":
            toolchain_url = TOOLCHAIN_2025_R1_URL_ARM64
            toolchain_version = TOOLCHAIN_2025_R1_VERSION
            toolchain_arch = TOOLCHAIN_2025_R1_ARCH_ARM64
        else:
            raise ValueError(f"Unsupported architecture: {arch}. Must be 'arm64'")
    else:
        raise ValueError(f"Unsupported version: {version}. Must be '2023.2' or '2025.1'")

    if toolchain_url == "":
        raise ValueError(f"Toolchain URL not found for version: {version}")

    # Determine cache directory
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "pyadi-dt" / "toolchains"
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Expected toolchain directory after extraction
    toolchain_name = f"arm-gnu-toolchain-{toolchain_version}-x86_64-{toolchain_arch}"
    toolchain_dir = cache_dir / toolchain_name
    toolchain_bin = toolchain_dir / "bin"

    # Check if already cached
    if toolchain_bin.exists():
        print(f"      Using cached toolchain: {toolchain_dir}")
        return toolchain_bin

    # Download toolchain
    print(f"      Downloading ARM GNU toolchain {toolchain_version} ({arch})...")
    tarball_path = cache_dir / f"{toolchain_name}.tar.xz"

    try:
        with urllib.request.urlopen(toolchain_url) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            with open(tarball_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"      Progress: {percent:.1f}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)", end='\r')

        print(f"\n      Download complete: {tarball_path}")

        # Extract toolchain
        print(f"      Extracting toolchain...")
        with tarfile.open(tarball_path, 'r:xz') as tar:
            tar.extractall(cache_dir)

        # Verify extraction
        if not toolchain_bin.exists():
            raise RuntimeError(f"Toolchain extraction failed: {toolchain_bin} not found")

        # Clean up tarball to save space
        tarball_path.unlink()
        print(f"      Toolchain ready: {toolchain_bin}")

        return toolchain_bin

    except Exception as e:
        # Clean up on failure
        if tarball_path.exists():
            tarball_path.unlink()
        raise RuntimeError(f"Failed to download/extract toolchain: {e}")


def compile_dts_to_dtb(dts_path: Path, dtb_path: Path, kernel_path: str, arch: str = "arm64", version: str = "2023.2", platform: str = "vpk180", cross_compile: str = None) -> None:
    """Compile DTS to DTB using kernel build system with cross-compiler.
    """
    # Validate architecture
    if arch not in ["arm", "arm64"]:
        raise ValueError(f"Unsupported architecture: {arch}. Must be 'arm' or 'arm64'")

    if platform not in ["vpk180", "zcu102", "zc706"]:
        raise ValueError(f"Unsupported platform: {platform}. Must be 'vpk180', 'zcu102', or 'zc706'")

    # Download and cache cross-compiler if not provided
    if cross_compile is None:
        print(f"      Setting up {arch.upper()} cross-compiler...")
        toolchain_bin = download_and_cache_toolchain(arch=arch, version=version)

        if version == "2023.2":
            if arch == "arm64":
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_2023_R2_ARCH_ARM64}-"
            else:  # arch == "arm"
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_2023_R2_ARCH_ARM32}-"
        elif version == "2025.1":
            if arch == "arm64":
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_2025_R1_ARCH_ARM64}-"
            else:  # arch == "arm"
                # Assuming 2025.1 arm32 follows same pattern or is not supported yet?
                # The file didn't define TOOLCHAIN_2025_R1_ARCH_ARM32, so we might fail here if used.
                # Lines 81-87 in download_and_cache_toolchain suggest 2025.1 only supports arm64 for now.
                raise ValueError("ARM32 not supported for version 2025.1")
        else:
            raise ValueError(f"Unsupported version: {version}. Must be '2023.2' or '2025.1'")

        print(f"      ✓ Cross-compiler ready: {cross_compile}")

    # Set up environment for kernel compilation
    env = os.environ.copy()
    env['ARCH'] = arch
    env['CROSS_COMPILE'] = cross_compile

    # Determine platform-specific paths
    dts_filename = dts_path.name
    if arch == "arm64":
        kernel_dts_dir = Path(kernel_path) / "arch" / arch / "boot" / "dts" / "xilinx"
    else:
        kernel_dts_dir = Path(kernel_path) / "arch" / arch / "boot" / "dts"
    kernel_dts_path = kernel_dts_dir / dts_filename

    # DTB will be compiled to same location with .dtb extension
    kernel_dtb_path = kernel_dts_path.with_suffix('.dtb')

    # Step 1: Copy DTS file into kernel tree
    shutil.copy2(dts_path, kernel_dts_path)

    # Step 2: Ensure kernel is configured
    print("      Configuring kernel...")

    if platform == 'vpk180':
        defconfig = "adi_versal_apollo_defconfig"
    elif platform == 'zcu102':
        defconfig = "adi_zynqmp_defconfig"
    elif platform == 'zc706':
        defconfig = "zynq_xcomm_adv7511_defconfig"
    else:
        raise ValueError(f"Unsupported platform: {platform}")

    config_cmd = ["make", defconfig]
    print(f"      Running: {' '.join(config_cmd)}")
    config_result = subprocess.run(
        config_cmd,
        cwd=kernel_path,
        capture_output=True,
        text=True,
        env=env
    )
    if config_result.returncode != 0:
        raise RuntimeError(f"Kernel configuration failed: {config_result.stderr}")
    print("      Kernel configured.")

    # Step 3: Compile DTB using kernel make system
    print("      Compiling DTB...")
    if arch == "arm64":
        make_target = f"xilinx/{dts_filename.replace('.dts', '.dtb')}"
    else:
        make_target = f"{dts_filename.replace('.dts', '.dtb')}"
    make_cmd = ["make", make_target]
    print(f"      Running: {' '.join(make_cmd)}")

    make_result = subprocess.run(
        make_cmd,
        cwd=kernel_path,
        capture_output=True,
        text=True,
        env=env
    )

    if make_result.returncode != 0:
        raise RuntimeError(
            f"DTB compilation failed:\n"
            f"Command: {' '.join(make_cmd)}\n"
            f"ARCH={env['ARCH']} CROSS_COMPILE={env['CROSS_COMPILE']}\n"
            f"Error: {make_result.stderr}"
        )

    # Step 4: Verify DTB was created
    if not kernel_dtb_path.exists():
        raise RuntimeError(f"DTB file not created at {kernel_dtb_path}")

    # Step 5: Copy compiled DTB to desired output location
    shutil.copy2(kernel_dtb_path, dtb_path)


def verify_dts_match(gen_dtb: Path, ref_dtb: Path, kernel_path: str, dtb_output_dir: Path) -> None:
    """Verify generated DTB matches reference DTB line-by-line after decompilation.

    Args:
        gen_dtb: Path to generated DTB file
        ref_dtb: Path to reference DTB file
        kernel_path: Path to kernel source (to find dtc)
        dtb_output_dir: Directory to store intermediate flat DTS files
    
    Raises:
        Exception: If mismatches are found
    """
    print(f"      Generated DTB Size: {gen_dtb.stat().st_size}")
    print(f"      Reference DTB Size: {ref_dtb.stat().st_size}")

    print(f"[Content Verification] Comparing decompiled DTS...")
    
    dtc_path = Path(kernel_path) / "scripts/dtc/dtc"
    if not dtc_path.exists():
            dtc_path = "dtc"
    
    def dtb_to_dts(dtb, output):
        cmd = [str(dtc_path), "-I", "dtb", "-O", "dts", "-o", str(output), "-s", str(dtb)]
        subprocess.run(cmd, check=True, capture_output=True)
        
    gen_dts_flat = dtb_output_dir / "generated_flat.dts"
    ref_dts_flat = dtb_output_dir / "reference_flat.dts"
    
    try:
        dtb_to_dts(gen_dtb, gen_dts_flat)
        dtb_to_dts(ref_dtb, ref_dts_flat)
        
        # Read and Compare text
        with open(gen_dts_flat) as f: gen_text = f.readlines()
        with open(ref_dts_flat) as f: ref_text = f.readlines()
        
        print("      Comparing flattened DTS content...")
        
        mismatches = []
        
        ref_set = set([l.strip() for l in ref_text])
        
        for line in gen_text:
            l = line.strip()
            if not l: continue
            # Skip phandle noise if it varies
            if "phandle =" in l: continue 
            if "linux,phandle" in l: continue
            
            if l not in ref_set:
                    mismatches.append(f"Excess in GEN: {l}")
        
        # Also check if REF has lines missing in GEN (Critical!)
        gen_set = set([l.strip() for l in gen_text])
        for line in ref_text:
            l = line.strip()
            if not l: continue
            if "phandle =" in l: continue 
            if "linux,phandle" in l: continue
            
            if l not in gen_set:
                    mismatches.append(f"Missing in GEN: {l}")

        if mismatches:
            # Dump first few
            print("      Mismatch details:")
            for m in mismatches[:50]:
                print(f"      {m}")
            raise Exception(f"Found {len(mismatches)} mismatches in generated DTS content")

        print("      ✓ DTS Content Matches Reference")
        
    except Exception as e:
        print(f"      Warning: DTC comparison failed: {e}")
        raise e
