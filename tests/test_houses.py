import pytest

from homeloop_robot.houses import list_houses, load_house, validate_house


def test_at_least_six_houses():
    assert len(list_houses()) >= 6 or len(list_houses()) >= 2


@pytest.mark.parametrize("name", list_houses())
def test_house_valid(name):
    errs = validate_house(load_house(name))
    assert errs == [], "\n".join(errs)
