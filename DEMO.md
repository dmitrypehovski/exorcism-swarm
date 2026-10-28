# Demo script

Two minutes, in this order. Everything runs on the venue machine with the repo's own `.env`.

## 1. The decision logic, no model, no keys (20 seconds)

```bash
python validate.py --seeds 200
```

```
outbreaks total: 400  contained: 400  (100.0%)
false alarms total: 0
civilians lost total: 0
mean ticks to contain: 1.0
seeds with zero misses and zero false alarms: 200/200
```

The point to say out loud: false alarms are a scored failure, so the decision whether an anomaly is
real is deterministic. Two hundred facilities, not one lucky seed.

## 2. The reasoning, tick by tick (20 seconds)

```bash
python play_gate.py
```

Watch the two false alarms get held with their mundane cause named, and the two outbreaks ordered
contained on the tick they appear.

## 3. The swarm (60 seconds)

```bash
SIM_TICKS=2 python main.py --dry-run     # or without --dry-run for the live dispatch
```

Five things to point at:

1. The provider line: Parasail first, OpenRouter if Parasail refuses inference.
2. The Sentinel posting raw sightings, the Analyst holding the benign ones with the mundane cause,
   the Dispatcher issuing the orders.
3. Two outbreaks contained on their first tick, mean 14.6 seconds.
4. The dispatch leaving the room through One to the channel.
5. `out/runs.jsonl` — the trace of the run, one line per tick.

## 4. The failure case (10 seconds)

```bash
python play_gate.py --seed 3    # any seed: the gate still holds the false alarms
```

## What each partner does, if asked

- **CrewAI** runs the swarm: three roles with partial knowledge, hierarchical process.
- **You.com** grounds the Analyst: witness reports are checked against live sources.
- **Parasail** is the brain: every agent's model.
- **One** is the actuator: the containment dispatch, the search call and the issue filing.

## Recorded output

`demo/run-output.txt` is a real run of step 3, captured from the terminal.
