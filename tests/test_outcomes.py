from homeloop_robot.outcomes import U, Ctx, N_UNIFORMS, container_class, p_fail, sample_outcome, split_code
from homeloop_robot.profiles import load_profile
from homeloop_robot.rng import rng_for
from homeloop_robot.types import FailureCode as F

REAL = load_profile("real")


def u_with(**slots):
    u = [0.999] * N_UNIFORMS
    for k, v in slots.items():
        u[getattr(U, k)] = v
    return u


def test_p_fail_tables():
    assert p_fail(REAL, Ctx("move", clutter="high")) == 0.025
    assert p_fail(REAL, Ctx("pick", clutter="low")) == 0.0534
    assert p_fail(REAL, Ctx("pick", clutter="low", grasp_class="deformable")) == 0.16
    assert p_fail(REAL, Ctx("open", container_type="drawer")) == 0.167
    assert p_fail(REAL, Ctx("open", container_type="fridge")) == 0.21
    assert container_class("box") == "door"


def test_sample_outcome_branches():
    assert sample_outcome(REAL, Ctx("pick", clutter="high"), u_with(FAIL=0.1, SPLIT=0.0)).code == F.ABSENT
    assert sample_outcome(REAL, Ctx("pick", clutter="high"), u_with(FAIL=0.9)).kind == "ok"
    assert sample_outcome(REAL, Ctx("pick", clutter="high"), u_with(FAIL=0.9, SILENT=0.01)).kind == "silent_fail"
    # retry after a sticky failure: success p = pick.p_retry_success (0.376)
    sticky = Ctx("pick", clutter="low", attempt=2, sticky=True)
    assert sample_outcome(REAL, sticky, u_with(FAIL=0.30)).kind == "ok"
    assert sample_outcome(REAL, sticky, u_with(FAIL=0.40)).kind == "fail"


def test_split_shares_match_profile():
    rng = rng_for("split")
    n = 20000
    counts = {}
    for _ in range(n):
        c = split_code(REAL, "pick", rng.random())
        counts[c.value] = counts.get(c.value, 0) + 1
    for k, share in REAL.get("pick.split").items():
        assert abs(counts.get(k, 0) / n - share) < 0.02


def test_empirical_failure_rate():
    rng = rng_for("rate")
    n = 20000
    fails = sum(sample_outcome(REAL, Ctx("move", clutter="medium"), [rng.random() for _ in range(N_UNIFORMS)]).kind
                == "fail" for _ in range(n))
    assert abs(fails / n - 0.02) < 0.004
