from adidt.xsa.exceptions import SdtgenNotFoundError, SdtgenError, XsaParseError, ConfigError


def test_sdtgen_not_found_error_is_exception():
    err = SdtgenNotFoundError("sdtgen not found")
    assert isinstance(err, Exception)
    assert "sdtgen not found" in str(err)


def test_sdtgen_error_carries_stderr():
    err = SdtgenError("failed", stderr="error output")
    assert err.stderr == "error output"


def test_xsa_parse_error_is_exception():
    err = XsaParseError("no hwh found")
    assert isinstance(err, Exception)


def test_config_error_names_missing_field():
    err = ConfigError("sample_clock")
    assert "sample_clock" in str(err)
