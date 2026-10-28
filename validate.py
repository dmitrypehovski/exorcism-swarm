"""Run the gate across many seeds and report the distribution.

A single lucky seed proves nothing: the judges may run any seed. This prints the aggregate so the
claim "zero false alarms, one tick to contain" is a measured statement, not a demo.

    python validate.py --seeds 200
"""
from __future__ import annotations

import argparse
import statistics

from play_gate import play


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--ticks", type=int, default=6)
    args = ap.parse_args()

    rows = []
    for seed in range(1, args.seeds + 1):
        rows.append(play(seed, args.ticks, verbose=False)["score"])

    def agg(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(statistics.mean(vals), 2) if vals else None

    total_out = sum(r["outbreaks"] for r in rows)
    total_cont = sum(r["contained"] for r in rows)
    print(f"seeds: {args.seeds}  ticks: {args.ticks}")
    print(f"outbreaks total: {total_out}  contained: {total_cont}  "
          f"({100 * total_cont / total_out:.1f}%)")
    print(f"false alarms total: {sum(r['false_alarms'] for r in rows)}")
    print(f"civilians lost total: {sum(r['civilians_lost'] for r in rows)}")
    print(f"civilians saved total: {sum(r['civilians_saved'] for r in rows)}")
    print(f"mean ticks to contain: {agg('mean_ticks_to_contain')}")
    perfect = sum(1 for r in rows if r["missed"] == 0 and r["false_alarms"] == 0)
    print(f"seeds with zero misses and zero false alarms: {perfect}/{args.seeds}")


if __name__ == "__main__":
    main()
