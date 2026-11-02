"""``python -m homeloop_robot.profiles {validate [--strict], consistency [--strict], show NAME, list}``."""

from __future__ import annotations

import argparse
import json
import sys

from . import list_profiles, load_profile


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homeloop_robot.profiles")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check the profiles against the rules of docs/profiles.md")
    v.add_argument("--strict", action="store_true", help="warnings fail too")
    s = sub.add_parser("show", help="print a resolved profile as sorted JSON")
    s.add_argument("name")
    sub.add_parser("list", help="profile names")
    c = sub.add_parser("consistency", help="simulated outcome rates vs the profile; physical possibility of traces")
    c.add_argument("--strict", action="store_true", help="any failed check fails (the default reports too)")
    c.add_argument("--n", type=int, default=20000, help="calls per rate check (>= 20000 for the acceptance check)")
    c.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        from .validate import run
        return run(strict=a.strict)
    if a.cmd == "consistency":
        from ..consistency import run as run_consistency
        return run_consistency(n=a.n, seed=a.seed, strict=a.strict)
    if a.cmd == "show":
        p = load_profile(a.name)
        print(json.dumps({"name": p.name, "sha": p.sha, "params": p.values()}, sort_keys=True,
                         ensure_ascii=False, indent=1, default=str))
        return 0
    print("\n".join(list_profiles()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
