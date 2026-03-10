class SdtgenNotFoundError(Exception):
    """Raised when sdtgen/lopper binary is not found on PATH."""
    INSTALL_URL = "https://github.com/devicetree-org/lopper"

    def __init__(self, message: str = "sdtgen not found on PATH"):
        super().__init__(
            f"{message}\nInstall lopper/sdtgen from: {self.INSTALL_URL}"
        )


class SdtgenError(Exception):
    """Raised when sdtgen exits with a non-zero status or produces no output."""

    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


class XsaParseError(Exception):
    """Raised when the XSA file cannot be parsed."""
    pass


class ConfigError(Exception):
    """Raised when the pyadi-jif JSON config is missing required fields."""

    def __init__(self, missing_field: str):
        super().__init__(f"Missing required config field: '{missing_field}'")
        self.missing_field = missing_field
