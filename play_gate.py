"""Play the facility simulation with the deterministic gate alone: no model, no keys.

This is the rehearsal path. It exists so the decision logic can be scored in seconds, repeatedly,
without spending a live feed or an inference credit.

    python play_gate.py            seed 31, six ticks
    python play_gate.py --seed 7 --ticks 8
"""
from __future__ import annotations

import argparse
import json

from feed import open_feed
from policy import tick_verdict


def play(seed: int, ticks: int, verbose: bool = True) -> dict:
    feed = open_feed(seed=seed, ticks=ticks)
    log = []
    while not feed.done:
        obs = feed.observe()
        verdict = tick_verdict(obs)
        orders = []
        for zone in verdict["hot"]:
            result = feed.contain(zone, "exorcise")
            orders.append({"zone": zone, "action": "exorcise", "outcome": result.get("outcome"),
                           "saved": result.get("civilians_saved")})
        log.append({"tick": obs["tick"], "hot": verdict["hot"], "orders": orders,
                    "rationale": verdict["rationale"]})
        if verbose:
            print(f"tick {obs['tick']}: hot={verdict['hot'] or 'none'} orders={len(orders)}")
            for v in verdict["zones"]:
                if v["flags"]:
                    print(f"    {v['zone']:<13} real={str(v['real']):<5} flags={list(v['flags'])}  {v['reason'][:70]}")
        feed.advance()
    score = feed.score()
    return {"seed": seed, "ticks": ticks, "score": score, "log": log}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--ticks", type=int, default=6)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    out = play(args.seed, args.ticks, verbose=not args.quiet)
    print("\nSCORE:", json.dumps(out["score"], ensure_ascii=False))
