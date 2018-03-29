import pytest

import pgmock.config


def test_contextable_config_value_stack():
    """
    Verifies that pgmock.config._ContextableConfigValue maintains old
    variables properly when used as a context manager
    """

    set_val = pgmock.config._ContextableConfigValue(False)
    get_val = lambda: set_val.value  # flake8: noqa

    with set_val(True):
        assert get_val() is True

        with set_val(None):
            assert get_val() is None

    assert get_val() is False


def test_cannot_use_as_cm():
    set_val = pgmock.config._ContextableConfigValue(False)
    with pytest.raises(TypeError) as errinfo:
        with set_val:
            pass

    assert str(errinfo.value) == 'value cannot be directly used as a context manager'
