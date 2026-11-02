from homeloop_robot import realism
from homeloop_robot.catalog import CLASSES, REALISM, RECEPTACLES, is_typical, size_fits
from homeloop_robot.houses import list_houses, load_house


def test_catalog_complete():
    assert set(REALISM) == set(CLASSES)
    assert realism.check_catalog() == []
    assert REALISM["mug"]["mass_kg"] == 0.118                    # YCB Table II
    assert REALISM["mug"]["typical_receptacles"]["CounterTop"]["url"].startswith("https://ai2thor")


def test_every_house_plausible():
    for h in list_houses():
        assert realism.check_house(load_house(h)) == [], h


def test_report_ok():
    rep = realism.report()
    assert rep["ok"] and rep["checked"]["houses"] == len(list_houses())
    assert set(rep["rules"]) == {"R-a", "R-b", "R-c", "R-d", "R-h"}


def test_placement_rules():
    h = load_house("family_house")
    assert realism.placement_ok(h, "mug", "counter@kitchen")[0]
    ok, why = realism.placement_ok(h, "mug", "kids_bed@kids")
    assert not ok and "not typically" in why
    assert size_fits("plate", "Microwave")                        # plate (m) fits a microwave (m)
    assert not size_fits("houseplant", "Drawer")                  # l > m
    assert is_typical("knife", "Drawer") and not is_typical("knife", "Bed")
    assert RECEPTACLES["Chair"]["capacity_size_class"] is None
