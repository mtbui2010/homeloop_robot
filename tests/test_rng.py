from homeloop_robot.rng import Streams, derive_seed, r6, rng_for


def test_derive_seed_stable():
    assert derive_seed("a", 1) == derive_seed("a", 1)
    assert derive_seed("a", 1) != derive_seed("a", 2)
    # fixed value: a change of the hashing scheme would silently change every trace
    assert derive_seed("x") == int.from_bytes(__import__("hashlib").sha256(b"x").digest()[:8], "big")


def test_rng_for_and_streams():
    assert rng_for(1, "k").random() == rng_for(1, "k").random()
    s1, s2 = Streams(5, "ep"), Streams(5, "ep")
    assert [s1.stream("a").random() for _ in range(3)] == [s2.stream("a").random() for _ in range(3)]
    assert s1.rng_for("x", 1).random() == s2.rng_for("x", 1).random()
    assert Streams(5, "ep").rng_for("x").random() != Streams(5, "other").rng_for("x").random()


def test_r6():
    assert r6(1.23456789) == 1.234568
    assert str(r6(-0.0000001)) == "0.0"
