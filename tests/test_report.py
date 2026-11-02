import math

from homeloop_robot.profiles import load_profile
from homeloop_robot.report import OKROBOT_HW_PER_TRIAL, hw_episode_rates, hw_rates_table, oracle_mix


def test_hw_rates_closed_form_and_okrobot():
    q = load_profile("real").get("hw.p_per_motion_call")
    r4 = hw_episode_rates(q, 0.5, 4)
    assert math.isclose(r4["any_fault"], 1 - (1 - q) ** 4)
    # 4-call no-retry rate stays within one binomial SE (171 trials) of OK-Robot's 7.5 %
    se = math.sqrt(OKROBOT_HW_PER_TRIAL * (1 - OKROBOT_HW_PER_TRIAL) / 171)
    assert abs(r4["any_fault"] - OKROBOT_HW_PER_TRIAL) < se
    assert hw_episode_rates(q, 0.0, 12)["lost"] == 0.0
    assert math.isclose(hw_episode_rates(q, 1.0, 8)["lost"], hw_episode_rates(q, 1.0, 8)["any_fault"])
    lost = [hw_episode_rates(q, p, 8)["lost"] for p in (0.2, 0.5, 0.94)]
    assert lost == sorted(lost)
    t = hw_rates_table()
    assert {r["p_persistent"] for r in t["rows"]} >= {0.2, 0.5, 0.94}


def test_oracle_mix_deterministic_and_ideal_clean():
    a = oracle_mix(0, 12, "real")
    assert a == oracle_mix(0, 12, "real")
    assert a["n_calls"] > 0 and 0.0 < a["ok"] <= 1.0
    i = oracle_mix(0, 12, "ideal")
    assert i["ok"] == 1.0 and i["by_code"] == {} and i["success"] == 1.0
    lo = oracle_mix(0, 12, "real", {"hw.p_persistent": 0.0})
    assert lo["hw_persistent_episode_rate"] == 0.0
