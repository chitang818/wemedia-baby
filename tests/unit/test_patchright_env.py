from tests.helpers.patchright_env import is_patchright_driver_environment_error


def test_patchright_driver_connection_closed_is_environment_error():
    exc = Exception("Connection closed while reading from the driver")

    assert is_patchright_driver_environment_error(exc) is True


def test_patchright_eperm_lstat_is_environment_error():
    exc = OSError("EPERM: operation not permitted, lstat 'C:\\Users\\chitang'")

    assert is_patchright_driver_environment_error(exc) is True


def test_regular_assertion_error_is_not_environment_error():
    exc = AssertionError("music row should be visible")

    assert is_patchright_driver_environment_error(exc) is False
