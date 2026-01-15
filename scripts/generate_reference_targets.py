#!/usr/bin/env python3
"""
Generate reference_dts_targets.json from Linux kernel DTS files.

This script analyzes reference DTS files from the Linux kernel repository
and generates a structured JSON file documenting the reference implementations
used by pyadi-dt templates.

Usage:
    python generate_reference_targets.py --linux-path /path/to/linux
    python generate_reference_targets.py --linux-path ./linux --output custom.json
    python generate_reference_targets.py --add-target linux/arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-ad9081.dts
"""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict


@dataclass
class PlatformConfig:
    """Configuration for a specific board/platform combination."""
    architecture: str
    soc: str
    transceivers: str
    reference_dts: str
    base_includes: List[str]
    template: Optional[str]
    clock_reference: str
    spi_bus: str
    default_pll: str | Dict[str, str]
    additional_variants: List[str]


@dataclass
class BoardConfig:
    """Configuration for a board type."""
    description: str
    platforms: Dict[str, PlatformConfig]
    clock_chips: List[str]
    shared_dtsi: List[str]
    components: Optional[Dict[str, str]] = None


class DTSAnalyzer:
    """Analyzes DTS files to extract configuration information."""

    # Board detection patterns
    BOARD_PATTERNS = {
        'ad9081': r'ad9081|mxfe',
        'ad9084': r'ad9084|hifirf',
        'adrv9009': r'adrv9009',
        'daq2': r'daq2|fmcdaq2',
    }

    # Platform detection patterns
    PLATFORM_PATTERNS = {
        'zcu102': r'zcu102',
        'vpk180': r'vpk180',
        'vck190': r'vck190',
        'zc706': r'zc706',
        'zu11eg': r'zu11eg',
    }

    # Architecture from path
    ARCH_PATTERNS = {
        'arm64': r'/arm64/',
        'arm': r'/arm/',
    }

    # SoC type patterns
    SOC_PATTERNS = {
        'zynqmp': 'Zynq UltraScale+ MPSoC',
        'versal-vpk': 'Versal Premium',
        'versal-vck': 'Versal Premium Embedded',
        'zynq-7': 'Zynq-7000',
    }

    # Transceiver patterns (derived from platform)
    TRANSCEIVER_MAP = {
        'zcu102': 'GTH',
        'zu11eg': 'GTH',
        'vpk180': 'GTY',
        'vck190': 'GTY',
        'zc706': 'GTX',
    }

    def __init__(self, linux_path: Path):
        self.linux_path = Path(linux_path)
        if not self.linux_path.exists():
            raise ValueError(f"Linux path does not exist: {linux_path}")

    def identify_board(self, dts_path: str) -> Optional[str]:
        """Identify board type from DTS filename."""
        dts_lower = dts_path.lower()
        for board, pattern in self.BOARD_PATTERNS.items():
            if re.search(pattern, dts_lower):
                return board
        return None

    def identify_platform(self, dts_path: str) -> Optional[str]:
        """Identify platform from DTS filename."""
        dts_lower = dts_path.lower()
        for platform, pattern in self.PLATFORM_PATTERNS.items():
            if re.search(pattern, dts_lower):
                return platform
        return None

    def identify_architecture(self, dts_path: str) -> Optional[str]:
        """Identify architecture from DTS path."""
        for arch, pattern in self.ARCH_PATTERNS.items():
            if re.search(pattern, dts_path):
                return arch
        return None

    def identify_soc(self, dts_content: str, platform: str) -> str:
        """Identify SoC type from DTS content or platform."""
        content_lower = dts_content.lower()

        # Check content patterns
        for pattern, soc_name in self.SOC_PATTERNS.items():
            if pattern in content_lower:
                return soc_name

        # Fallback to platform-based detection
        if 'zcu102' in platform or 'zu11eg' in platform:
            return 'Zynq UltraScale+ MPSoC'
        elif 'vpk180' in platform:
            return 'Versal Premium'
        elif 'vck190' in platform:
            return 'Versal Premium Embedded'
        elif 'zc706' in platform:
            return 'Zynq-7000'

        return 'Unknown'

    def extract_includes(self, dts_content: str) -> List[str]:
        """Extract #include statements from DTS content."""
        includes = []

        # Match both #include <file> and #include "file"
        include_pattern = r'#include\s+[<"]([^>"]+)[>"]'

        for match in re.finditer(include_pattern, dts_content):
            include_file = match.group(1)
            # Only keep base DTS/DTSI files, not dt-bindings
            if not include_file.startswith('dt-bindings/'):
                # Extract just the filename
                base_name = os.path.basename(include_file)
                if base_name not in includes:
                    includes.append(base_name)

        return includes

    def identify_clock_reference(self, dts_content: str, platform: str) -> str:
        """Identify clock reference from DTS content."""
        # Look for clock references in the content
        if 'zynqmp_clk' in dts_content:
            return 'zynqmp_clk'
        elif 'versal_clk' in dts_content:
            return 'versal_clk'
        elif '&clkc' in dts_content or 'clkc' in dts_content:
            return 'clkc'

        # Fallback based on platform
        if 'zcu102' in platform or 'zu11eg' in platform:
            return 'zynqmp_clk'
        elif 'vpk180' in platform or 'vck190' in platform:
            return 'versal_clk'
        elif 'zc706' in platform:
            return 'clkc'

        return 'unknown'

    def identify_spi_bus(self, dts_content: str, board: str) -> str:
        """Identify SPI bus from DTS content."""
        # Check for spi bus references
        if '&spi1' in dts_content:
            return 'spi1'
        elif '&spi0' in dts_content:
            return 'spi0'

        # Fallback: ad9081 typically uses spi1 on ARM64, spi0 on ARM
        # adrv9009 typically uses spi0
        if board == 'ad9081':
            if '/arm64/' in dts_content or 'zynqmp' in dts_content.lower():
                return 'spi1'
            return 'spi0'

        return 'spi0'

    def identify_pll_config(self, dts_content: str, board: str) -> str | Dict[str, str]:
        """Identify default PLL configuration."""
        # ADRV9009 has separate PLLs for RX/TX/ORX
        if board == 'adrv9009':
            return {
                'rx': 'XCVR_CPLL',
                'tx': 'XCVR_QPLL',
                'orx': 'XCVR_CPLL'
            }

        # Check content for QPLL/CPLL references
        if 'XCVR_QPLL0' in dts_content:
            return 'XCVR_QPLL0'
        elif 'XCVR_QPLL' in dts_content:
            return 'XCVR_QPLL'
        elif 'XCVR_CPLL' in dts_content:
            return 'XCVR_CPLL'

        # Default to QPLL for most boards
        return 'XCVR_QPLL'

    def identify_clock_chips(self, dts_content: str, board: str) -> List[str]:
        """Identify clock chip ICs from DTS content."""
        chips = []

        chip_patterns = {
            'hmc7044': r'hmc7044',
            'ad9528': r'ad9528',
            'ad9523_1': r'ad9523',
            'adf4382': r'adf4382',
            'adf4030': r'adf4030',
        }

        content_lower = dts_content.lower()
        for chip, pattern in chip_patterns.items():
            if re.search(pattern, content_lower):
                chips.append(chip)

        return chips or ['unknown']

    def find_template(self, board: str, platform: str) -> Optional[str]:
        """Find corresponding template file."""
        # Try multiple naming patterns
        patterns = [
            f"{board}_fmc_{platform}.tmpl",  # ad9081_fmc_zcu102.tmpl
            f"{board}_{platform}.tmpl",       # daq2_zcu102.tmpl (if any)
            f"{board}.tmpl",                   # daq2.tmpl (generic)
        ]

        for template_name in patterns:
            template_path = self.linux_path.parent / 'adidt' / 'templates' / template_name
            if template_path.exists():
                return template_name

        return None

    def find_additional_variants(self, dts_path: str, board: str, platform: str) -> List[str]:
        """Find additional DTS variants for the same board/platform."""
        variants = []
        dts_dir = os.path.dirname(dts_path)
        dts_filename = os.path.basename(dts_path)

        # Search for similar files in the same directory
        if os.path.exists(dts_dir):
            for filename in os.listdir(dts_dir):
                if not filename.endswith('.dts'):
                    continue

                # Skip the main reference file
                if filename == os.path.basename(dts_filename):
                    continue

                # Check if it matches board and platform
                if board.replace('_', '') in filename.lower() and platform in filename.lower():
                    variants.append(filename)

        return sorted(variants)

    def analyze_dts_file(self, dts_relative_path: str) -> Optional[PlatformConfig]:
        """Analyze a DTS file and extract configuration."""
        # Build full path
        dts_full_path = self.linux_path / dts_relative_path

        if not dts_full_path.exists():
            print(f"Warning: DTS file not found: {dts_full_path}")
            return None

        # Read content
        with open(dts_full_path, 'r') as f:
            content = f.read()

        # Identify board and platform
        board = self.identify_board(dts_relative_path)
        platform = self.identify_platform(dts_relative_path)

        if not board or not platform:
            print(f"Warning: Could not identify board/platform for {dts_relative_path}")
            return None

        # Extract information
        arch = self.identify_architecture(dts_relative_path)
        soc = self.identify_soc(content, platform)
        transceivers = self.TRANSCEIVER_MAP.get(platform, 'Unknown')
        includes = self.extract_includes(content)
        clock_ref = self.identify_clock_reference(content, platform)
        spi_bus = self.identify_spi_bus(content, board)
        pll_config = self.identify_pll_config(content, board)
        template = self.find_template(board, platform)
        variants = self.find_additional_variants(str(dts_full_path), board, platform)

        return PlatformConfig(
            architecture=arch or 'unknown',
            soc=soc,
            transceivers=transceivers,
            reference_dts=dts_relative_path,
            base_includes=includes[:2] if includes else [],  # Keep first 2 includes
            template=template,
            clock_reference=clock_ref,
            spi_bus=spi_bus,
            default_pll=pll_config,
            additional_variants=variants[:6],  # Limit to 6 variants
        )

    def generate_targets_json(self, dts_files: List[str], output_path: Path, merge: bool = False) -> None:
        """Generate reference_dts_targets.json from list of DTS files.

        Args:
            dts_files: List of DTS file paths to analyze
            output_path: Path to output JSON file
            merge: If True, merge with existing file instead of overwriting
        """
        # Load existing data if merging
        existing_data = None
        if merge and output_path.exists():
            try:
                with open(output_path, 'r') as f:
                    existing_data = json.load(f)
                print(f"Merging with existing file: {output_path}")
            except Exception as e:
                print(f"Warning: Could not read existing file for merging: {e}")
                existing_data = None

        # Organize by board and platform
        boards = {}

        for dts_path in dts_files:
            config = self.analyze_dts_file(dts_path)
            if not config:
                continue

            board = self.identify_board(dts_path)
            platform = self.identify_platform(dts_path)

            if not board or not platform:
                continue

            # Initialize board if needed
            if board not in boards:
                # Read the DTS file to get clock chips
                dts_full_path = self.linux_path / dts_path
                with open(dts_full_path, 'r') as f:
                    content = f.read()

                boards[board] = BoardConfig(
                    description=self._get_board_description(board),
                    platforms={},
                    clock_chips=self.identify_clock_chips(content, board),
                    shared_dtsi=[],
                    components=self._get_board_components(board)
                )

            # Add platform config
            boards[board].platforms[platform] = config

        # Build final structure
        output = {
            '$schema': 'https://json-schema.org/draft/2020-12/schema',
            'description': 'Reference DTS files from Linux kernel used as templates for device tree generation',
            'version': '1.0.0',
            'boards': {},
            'base_platform_files': self._get_base_platform_files(),
            'transceiver_types': self._get_transceiver_types(),
        }

        # Convert dataclasses to dicts
        for board_name, board_config in boards.items():
            board_dict = {
                'description': board_config.description,
                'platforms': {},
                'clock_chips': board_config.clock_chips,
                'shared_dtsi': board_config.shared_dtsi,
            }

            if board_config.components:
                board_dict['components'] = board_config.components

            for platform_name, platform_config in board_config.platforms.items():
                board_dict['platforms'][platform_name] = asdict(platform_config)

            output['boards'][board_name] = board_dict

        # Merge with existing data if requested
        if existing_data:
            output = self._merge_json_data(existing_data, output)

        # Write output
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        if merge and existing_data:
            print(f"Updated {output_path} (merged with existing data)")
        else:
            print(f"Generated {output_path}")

    def _merge_json_data(self, existing: Dict, new: Dict) -> Dict:
        """Merge new data into existing data.

        Args:
            existing: Existing JSON data from file
            new: New data generated from DTS files

        Returns:
            Merged data structure
        """
        # Start with existing data
        merged = existing.copy()

        # Update metadata fields
        merged['$schema'] = new['$schema']
        merged['description'] = new['description']
        merged['version'] = new['version']

        # Merge boards
        if 'boards' not in merged:
            merged['boards'] = {}

        for board_name, new_board_data in new['boards'].items():
            if board_name not in merged['boards']:
                # New board - add entirely
                merged['boards'][board_name] = new_board_data
                print(f"  + Added new board: {board_name}")
            else:
                # Existing board - merge platforms
                existing_board = merged['boards'][board_name]

                # Update board-level fields
                existing_board['description'] = new_board_data.get('description', existing_board.get('description'))

                # Merge clock_chips (keep unique)
                existing_chips = set(existing_board.get('clock_chips', []))
                new_chips = set(new_board_data.get('clock_chips', []))
                merged_chips = sorted(existing_chips | new_chips)
                if merged_chips:
                    existing_board['clock_chips'] = merged_chips

                # Merge shared_dtsi (keep unique)
                existing_dtsi = set(existing_board.get('shared_dtsi', []))
                new_dtsi = set(new_board_data.get('shared_dtsi', []))
                merged_dtsi = sorted(existing_dtsi | new_dtsi)
                existing_board['shared_dtsi'] = merged_dtsi

                # Merge components if present
                if 'components' in new_board_data:
                    existing_board['components'] = new_board_data['components']

                # Merge platforms
                if 'platforms' not in existing_board:
                    existing_board['platforms'] = {}

                for platform_name, new_platform_data in new_board_data['platforms'].items():
                    if platform_name not in existing_board['platforms']:
                        existing_board['platforms'][platform_name] = new_platform_data
                        print(f"  + Added new platform: {board_name}/{platform_name}")
                    else:
                        # Update existing platform
                        existing_platform = existing_board['platforms'][platform_name]

                        # Merge additional_variants (keep unique)
                        existing_variants = set(existing_platform.get('additional_variants', []))
                        new_variants = set(new_platform_data.get('additional_variants', []))
                        merged_variants = sorted(existing_variants | new_variants)

                        # Update all fields from new data
                        existing_platform.update(new_platform_data)
                        existing_platform['additional_variants'] = merged_variants
                        print(f"  ↻ Updated platform: {board_name}/{platform_name}")

        # Update base_platform_files and transceiver_types
        merged['base_platform_files'] = new['base_platform_files']
        merged['transceiver_types'] = new['transceiver_types']

        return merged

    def _get_board_description(self, board: str) -> str:
        """Get human-readable board description."""
        descriptions = {
            'ad9081': 'AD9081/MxFE FMC Evaluation Board',
            'ad9084': 'AD9084/HiFiRF FMC Evaluation Board',
            'adrv9009': 'ADRV9009 RF Transceiver FMC Evaluation Board',
            'daq2': 'DAQ2 High-Speed ADC/DAC Evaluation Board (AD9680 + AD9144)',
        }
        return descriptions.get(board, f'{board.upper()} Evaluation Board')

    def _get_board_components(self, board: str) -> Optional[Dict[str, str]]:
        """Get board component information."""
        if board == 'daq2':
            return {'adc': 'ad9680', 'dac': 'ad9144'}
        return None

    def _get_base_platform_files(self) -> Dict:
        """Get base platform files structure."""
        return {
            'arm64': {
                'zcu102': {
                    'path': 'arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev1.0.dts',
                    'includes': ['zynqmp-zcu102-revB.dts', 'zynqmp.dtsi']
                },
                'vpk180': {
                    'path': 'arch/arm64/boot/dts/xilinx/versal-vpk180-revA.dts',
                    'includes': ['versal.dtsi', 'versal-clk.dtsi']
                },
                'vck190': {
                    'path': 'arch/arm64/boot/dts/xilinx/versal-vck190-revA.dts',
                    'includes': ['versal.dtsi', 'versal-clk.dtsi']
                }
            },
            'arm': {
                'zc706': {
                    'path': 'arch/arm/boot/dts/xilinx/zynq-zc706.dts',
                    'includes': ['zynq-zc706.dtsi', 'zynq-7000.dtsi']
                }
            }
        }

    def _get_transceiver_types(self) -> Dict:
        """Get transceiver types information."""
        return {
            'GTH': {
                'description': 'Gigabit Transceiver High-performance',
                'platforms': ['zcu102'],
                'max_rate_gbps': 16.3
            },
            'GTY': {
                'description': 'Gigabit Transceiver for Versal',
                'platforms': ['vpk180', 'vck190'],
                'max_rate_gbps': 32.75
            },
            'GTX': {
                'description': 'Gigabit Transceiver',
                'platforms': ['zc706'],
                'max_rate_gbps': 12.5
            }
        }


def discover_reference_dts_files(linux_path: Path) -> List[str]:
    """Discover reference DTS files in the Linux kernel tree."""
    dts_files = []

    search_patterns = [
        'arch/arm64/boot/dts/xilinx/*-ad9081.dts',
        'arch/arm64/boot/dts/xilinx/*-ad9084.dts',
        'arch/arm64/boot/dts/xilinx/*-adrv9009.dts',
        'arch/arm64/boot/dts/xilinx/*-fmcdaq2.dts',
        'arch/arm/boot/dts/xilinx/*-ad9081.dts',
        'arch/arm/boot/dts/xilinx/*-adrv9009.dts',
        'arch/arm/boot/dts/xilinx/*-fmcdaq2.dts',
    ]

    for pattern in search_patterns:
        for path in linux_path.glob(pattern):
            # Get relative path from linux root
            rel_path = path.relative_to(linux_path)
            dts_files.append(str(rel_path))

    return sorted(set(dts_files))


def main():
    parser = argparse.ArgumentParser(
        description='Generate reference_dts_targets.json from Linux kernel DTS files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-discover and generate from all reference DTS files
  python generate_reference_targets.py --linux-path ./linux

  # Generate from specific files
  python generate_reference_targets.py --linux-path ./linux \\
    --target arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-ad9081.dts \\
    --target arch/arm64/boot/dts/xilinx/versal-vpk180-reva-ad9081.dts

  # Custom output location
  python generate_reference_targets.py --linux-path ./linux --output custom.json

  # Merge/append to existing file (preserves existing boards/platforms)
  python generate_reference_targets.py --linux-path ./linux --merge \\
    --target arch/arm64/boot/dts/xilinx/versal-vck190-reva-ad9081.dts
"""
    )

    parser.add_argument(
        '--linux-path',
        type=Path,
        required=True,
        help='Path to Linux kernel source tree'
    )

    parser.add_argument(
        '--output',
        type=Path,
        default=Path('adidt/templates/reference_dts_targets.json'),
        help='Output JSON file path (default: adidt/templates/reference_dts_targets.json)'
    )

    parser.add_argument(
        '--target',
        action='append',
        dest='targets',
        help='Specific DTS file to analyze (relative to linux-path). Can be specified multiple times.'
    )

    parser.add_argument(
        '--discover',
        action='store_true',
        help='Auto-discover reference DTS files (default if no --target specified)'
    )

    parser.add_argument(
        '--merge',
        action='store_true',
        help='Merge with existing output file instead of overwriting. Preserves existing boards/platforms not in new data.'
    )

    args = parser.parse_args()

    # Initialize analyzer
    analyzer = DTSAnalyzer(args.linux_path)

    # Determine which files to analyze
    if args.targets:
        dts_files = args.targets
        print(f"Analyzing {len(dts_files)} specified DTS files...")
    else:
        print("Auto-discovering reference DTS files...")
        dts_files = discover_reference_dts_files(args.linux_path)
        print(f"Found {len(dts_files)} reference DTS files")

    if not dts_files:
        print("Error: No DTS files to analyze")
        return 1

    # Generate output
    analyzer.generate_targets_json(dts_files, args.output, merge=args.merge)

    return 0


if __name__ == '__main__':
    exit(main())
