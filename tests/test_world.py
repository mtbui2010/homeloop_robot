import pytest

from homeloop_robot.houses import list_houses
from homeloop_robot.world import from_house, norm


@pytest.mark.parametrize("name", list_houses())
def test_seed0_is_yaml_default(name):
    w = from_house(name, 0)
    for o in w.house.objects:
        assert w.objects[o.id].at == o.at
    assert w.robot.at == w.house.robot_start


@pytest.mark.parametrize("name", list_houses())
def test_from_house_deterministic_and_varies(name):
    a = [(o.id, o.at) for o in from_house(name, 17).objects.values()]
    b = [(o.id, o.at) for o in from_house(name, 17).objects.values()]
    assert a == b
    layouts = {tuple(sorted((o.id, o.at) for o in from_house(name, s).objects.values())) for s in range(1, 30)}
    assert len(layouts) > 1


def test_resolvers():
    w = from_house("senior_flat", 0)
    assert w.resolve_object("mug_1") == "mug_1"
    assert w.resolve_object("red mug") == "mug_1"
    assert w.resolve_object("빨간 머그컵") == "mug_1"
    assert sorted(w.resolve_object("mug")) == ["mug_1", "mug_2"]
    assert w.resolve_object("unicorn") is None
    assert w.resolve_place("counter") == "counter@kitchen"
    assert w.resolve_place("부엌 조리대") == "counter@kitchen"
    assert w.resolve_place("kitchen counter") == "counter@kitchen"
    assert w.resolve_person("할머니") == "grandma"
    assert norm("부엌 조리대") == norm("부엌조리대")


def test_paths_through_doors():
    w = from_house("senior_flat", 0)
    a = w.place("counter@kitchen").pos
    b = w.place("bed@bedroom").pos
    p = w.path(a, b)
    assert p[0] == a and p[-1] == b and len(p) == 4          # two doors
    assert w.path_length(a, b) > 0
    assert w.room_of(a) == "kitchen"
    same = w.path(w.place("counter@kitchen").pos, w.place("stove@kitchen").pos)
    assert len(same) == 2


def test_copy_is_deep():
    w = from_house("senior_flat", 0)
    c = w.copy()
    c.objects["mug_1"].at = "robot"
    c.opened.add("fridge@kitchen")
    assert w.objects["mug_1"].at == "counter@kitchen" and "fridge@kitchen" not in w.opened
    assert c.house is w.house
