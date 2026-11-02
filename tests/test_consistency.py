from homeloop_robot.consistency import binom_two_sided_p, rate_checks, trace_checks


def test_binomial_test():
    assert binom_two_sided_p(50, 100, 0.5) > 0.9
    assert binom_two_sided_p(80, 100, 0.5) < 1e-6
    assert binom_two_sided_p(0, 1000, 0.0) == 1.0 and binom_two_sided_p(1, 1000, 0.0) == 0.0


def test_rates_match_profile_small_n():
    checks = rate_checks(n=1500, seed=11)
    bad = [c.to_json() for c in checks if not c.ok and c.n > 0]
    assert not bad, bad
    assert len(checks) >= 30


def test_traces_physically_possible():
    tr = trace_checks(episodes=4, calls=25, seed=3)
    assert tr["calls"] == 3 * 4 * 25
    assert tr["violations"] == 0, tr["examples"]
