import pytest

import pgmock.mocker


@pytest.mark.parametrize('side_effect, expected_side_effect', [
    ([], []),
    ([None], [None]),
    pytest.mark.xfail(('invalid_type', None), raises=TypeError),
    pytest.mark.xfail(([('no', 'tuples', 'allowed')], None), raises=TypeError)
])
def test_side_effect_init(side_effect, expected_side_effect):
    mocker = pgmock.mocker.SideEffect(side_effect)
    assert mocker.side_effect == expected_side_effect
