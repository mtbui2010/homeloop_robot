import json

from homeloop_robot.selftest import run


def test_selftest_deterministic_and_profiles_differ(tmp_path):
    a, b, c = tmp_path / "a.jsonl", tmp_path / "b.jsonl", tmp_path / "c.jsonl"
    assert run(3, 4, "real", str(a)) == 0
    assert run(3, 4, "real", str(b)) == 0
    assert run(3, 4, "ideal", str(c)) == 0
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes() != c.read_bytes()
    lines = [json.loads(x) for x in a.read_text().splitlines()]
    assert len(lines) == 4 * 26
    assert sum("summary" in x for x in lines) == 4
    for x in lines:
        if "summary" not in x:
            assert set(x) == {"ep", "house", "seed_state", "k", "skill", "args", "ok", "code", "injected", "t",
                              "dur", "data", "truth"}
    ideal = [json.loads(x) for x in c.read_text().splitlines()]
    assert not any(x.get("injected") for x in ideal)
