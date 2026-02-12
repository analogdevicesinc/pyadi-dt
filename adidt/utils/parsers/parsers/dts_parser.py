"""
DTS/DTSI File Parser

Parses device tree source files to extract include dependencies.
"""

import re
import os
from typing import List
from ..dependency_types import Dependency, DependencyType


class IncludeStatement:
    """Represents a single include statement in a DTS file."""

    def __init__(self, file: str, line_number: int, include_type: str):
        """
        Initialize include statement.

        Args:
            file: The included file path
            line_number: Line number in source file
            include_type: Type of include ('system' for <>, 'local' for "", 'legacy' for /include/)
        """
        self.file = file
        self.line_number = line_number
        self.include_type = include_type

    def __repr__(self) -> str:
        return (
            f"Include({self.file}, line={self.line_number}, type={self.include_type})"
        )


class DTSParser:
    """
    Parser for DTS/DTSI source files.

    Extracts #include and /include/ statements to build dependency information.
    """

    # Regular expressions for different include formats
    INCLUDE_PATTERNS = [
        (r"^\s*#include\s+<([^>]+)>", "system"),  # System: #include <file.h>
        (r'^\s*#include\s+"([^"]+)"', "local"),  # Local: #include "file.dtsi"
        (r'^\s*/include/\s+"([^"]+)"', "legacy"),  # Legacy: /include/ "file.dtsi"
    ]

    def __init__(self):
        """Initialize DTS parser."""
        self.compiled_patterns = [
            (re.compile(pattern, re.MULTILINE), inc_type)
            for pattern, inc_type in self.INCLUDE_PATTERNS
        ]

    def parse_file(self, file_path: str) -> List[IncludeStatement]:
        """
        Parse a DTS file and extract all include statements.

        Args:
            file_path: Path to the DTS/DTSI file

        Returns:
            List of IncludeStatement objects

        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file can't be read
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"DTS file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as e:
            raise IOError(f"Failed to read DTS file {file_path}: {e}")

        return self.parse_content(content)

    def parse_content(self, content: str) -> List[IncludeStatement]:
        """
        Parse DTS content string and extract include statements.

        Args:
            content: DTS file content as string

        Returns:
            List of IncludeStatement objects
        """
        includes = []

        # Split into lines for line number tracking
        lines = content.split("\n")

        for line_num, line in enumerate(lines, start=1):
            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # Try each pattern
            for pattern, inc_type in self.compiled_patterns:
                match = pattern.search(line)
                if match:
                    included_file = match.group(1)
                    includes.append(
                        IncludeStatement(
                            file=included_file,
                            line_number=line_num,
                            include_type=inc_type,
                        )
                    )
                    break  # Only match one pattern per line

        return includes

    def extract_includes_as_dependencies(
        self, file_path: str, source_file: str
    ) -> List[Dependency]:
        """
        Parse a DTS file and return dependencies.

        Args:
            file_path: Path to the DTS/DTSI file to parse
            source_file: Name of the source file for dependency tracking

        Returns:
            List of Dependency objects
        """
        includes = self.parse_file(file_path)
        dependencies = []

        for inc in includes:
            dep = Dependency(
                target=inc.file,
                type=DependencyType.FILE_INCLUDE,
                source_file=source_file,
                line_number=inc.line_number,
                resolved=False,  # Will be resolved by main parser
                metadata={"include_type": inc.include_type},
            )
            dependencies.append(dep)

        return dependencies

    @staticmethod
    def is_system_include(include_path: str) -> bool:
        """
        Determine if an include path is a system include.

        System includes typically start with dt-bindings/ or similar.

        Args:
            include_path: The include path string

        Returns:
            True if it's a system include
        """
        system_prefixes = ["dt-bindings/", "linux/", "asm/"]
        return any(include_path.startswith(prefix) for prefix in system_prefixes)

    @staticmethod
    def normalize_path(include_path: str) -> str:
        """
        Normalize an include path.

        Args:
            include_path: The include path

        Returns:
            Normalized path
        """
        # Remove leading/trailing whitespace
        path = include_path.strip()

        # Normalize path separators
        path = path.replace("\\", "/")

        # Remove redundant slashes
        while "//" in path:
            path = path.replace("//", "/")

        return path
