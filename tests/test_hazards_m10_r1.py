"""Milestone 10 round 1: a bedside table is no `electrical` place (docs/hazards.md); a TV stand and a microwave are."""
import glob
import os

import pytest
import yaml

HOUSES = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "homeloop_robot", "houses", "*.yaml")))


@pytest.mark.parametrize("path", HOUSES)
def test_nightstands_carry_no_electrical_tag(path):
    d = yaml.safe_load(open(path))
    places = d.get("places") or {}
    for k, v in places.items():
        if k.split("@")[0] == "nightstand":
            assert "electrical" not in (v.get("tags") or []), (path, k)
