"""Regression on the published ticks.

Every assertion here is a judgment the venue feed actually returned, so the test is the feed's own
arithmetic, not our opinion of it. Run it before any change to policy.py:

    python tests/test_decisions.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from feed_mcp import fixtures  # noqa: E402
from policy import decide_tick, swarm_budget, within_budget, engaged, severity_of  # noqa: E402

FAILURES = []


def check(name: str, got, want) -> None:
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {name}: got {got!r}, want {want!r}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    control = {t["tick_id"]: t for t in fixtures("control-tick")["ticks"]}
    outbreak = {t["tick_id"]: t for t in fixtures("outbreak-level-5")["ticks"]}

    print("the control tick: a crowd of 41 motion events and 3 mG is not an incident")
    check("tick 900 action", decide_tick(control[900])[0], "observe")
    check("tick 900 no sector engaged", any(engaged(r) for r in control[900]["sector_reports"]), False)

    print("the outbreak: civilians trapped decide the action")
    check("tick 142 action", decide_tick(outbreak[142])[0], "evacuate")
    check("tick 143 action", decide_tick(outbreak[143])[0], "evacuate")

    print("the decoy: a residual echo at 0.35 is not escalated")
    entrance = next(r for r in outbreak[143]["sector_reports"] if r["sector"] == "entrance")
    check("entrance engaged", engaged(entrance), False)
    check("entrance sighting class", (entrance["sighting"] or {}).get("entity_class"), "residual-echo")

    print("severity alone must never trigger: motion inflates the control tick")
    check("control tick severity above the outbreak's floor",
          severity_of(control[900]["sector_reports"][0]) > 10, True)

    print("the tick's budget is a scored limit, not decoration")
    check("no budget stated means no limit", swarm_budget({})["max_active_agents"], 0)
    check("a stated cap is read", swarm_budget({"swarm_budget": {"max_active_agents": 2}})["max_active_agents"], 2)
    check("one agent may go out under a cap of two", within_budget(0, 2), True)
    check("the third is refused under a cap of two", within_budget(2, 2), False)
    check("no cap never refuses", within_budget(9, 0), True)

    print(f"\n{'all checks passed' if not FAILURES else str(len(FAILURES)) + ' FAILED: ' + ', '.join(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
