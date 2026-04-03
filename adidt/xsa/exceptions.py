"""Custom exception types for the XSA-to-DeviceTree pipeline."""


class SdtgenNotFoundError(Exception):
    """Raised when sdtgen/lopper binary is not found on PATH."""

    INSTALL_URL = "https://github.com/devicetree-org/lopper"

    def __init__(self, message: str = "sdtgen not found on PATH"):
        """Initialize with an optional custom *message* and the install URL hint."""
        super().__init__(f"{message}\nInstall lopper/sdtgen from: {self.INSTALL_URL}")


class SdtgenError(Exception):
    """Raised when sdtgen exits with a non-zero status or produces no output."""

    def __init__(self, message: str, stderr: str = ""):
        """Initialize with a human-readable *message* and optional *stderr* text."""
        super().__init__(message)
        self.stderr = stderr


class XsaParseError(Exception):
    """Raised when the XSA file cannot be parsed."""

    pass


class ConfigError(Exception):
    """Raised when the pyadi-jif JSON config is missing required fields."""

    def __init__(self, missing_field: str):
        """Initialize with the name of the *missing_field* in the config."""
        super().__init__(f"Missing required config field: '{missing_field}'")
        self.missing_field = missing_field


class ProfileError(Exception):
    """Raised when a board profile cannot be loaded or is invalid."""

    pass


class ParityError(Exception):
    """Raised when strict manifest parity checks fail."""

    pass


class DtsLintError(Exception):
    """Raised when strict DTS lint checks find errors."""

    def __init__(self, message: str, diagnostics: list | None = None):
        """Initialize with a summary *message* and optional list of :class:`LintDiagnostic`."""
        super().__init__(message)
        self.diagnostics = diagnostics or []
