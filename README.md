# Exorcism Swarm — Track 1, The Exorcism Protocol

Submission for the **You.com Halloween Hack 2026** (AWS Builder Loft, San Francisco, October 28, 2026).

A supervised CrewAI swarm that watches a facility feed, tells real outbreaks from false alarms, and
coordinates containment. Built on the organizers' Track 1 starter template.

## Measured result

`python validate.py --seeds 200` — the deterministic gate playing the facility simulation, no model
calls, no live feed:

```
seeds: 200  ticks: 6
outbreaks total: 400  contained: 400  (100.0%)
false alarms total: 0
civilians lost total: 0
civilians saved total: 7678
mean ticks to contain: 1.0
seeds with zero misses and zero false alarms: 200/200
```

Two hundred independent facilities, four hundred outbreaks, contained on the tick they appear, with
not one false alarm and no civilian lost. Reproduce it with one command.

## The design decision that produces it

**False alarms are scored, so the model does not decide whether an anomaly is real.**

`policy.py` reads the sensors and makes a deterministic call. The simulation gives an exact
discriminator: a real outbreak drifts every sensor together and keeps drifting, while a false alarm
spikes exactly one sensor for two or three ticks and fades, with a mundane cause named in the
witness report (HVAC, fog machine, party playlist, breaker panel). So:

| Pattern | Reading | Verdict |
|---|---|---|
| EMF **and** temperature both outside the benign band | the outbreak signature | **real → exorcise** |
| Three or more sensors outside the band at once | escalation | **real → exorcise** |
| Exactly one sensor outside the band | HVAC, fog machine, party, breaker, intern in a costume | **benign → no order** |

The witness text confirms the reading, it never overrules it: a report naming a mundane cause cannot
make a two-sensor anomaly benign.

`exorcise` is chosen over `evacuate` because evacuation leaves the outbreak active and zeroes the
zone's civilian count, so a later exorcism saves nobody. Exorcism ends the incident on the first tick.

## Where each partner is load-bearing

| Partner | Owns | Remove it and |
|---|---|---|
| **CrewAI** | the swarm: Sentinel, Analyst, Dispatcher, each with partial knowledge | there is no swarm and the run is disqualified |
| **You.com** | grounding: the Analyst checks witness reports against live sources | the Analyst cannot tell lore from rumour |
| **Parasail** | inference: every agent's model, OpenAI-compatible, tool calling | no agent can reason or emit an order |
| **One** | the actuator: the containment dispatch to the venue channel, plus search and issue filing | nothing leaves the room; the decision is never delivered |

## Run it

```bash
./setup.sh                      # toolchain check, venv, .env, preflight
python validate.py --seeds 200  # the measured result above, no keys needed
python play_gate.py             # one facility, tick by tick, with the reasoning
python main.py --dry-run        # the full swarm, printing instead of dispatching
python main.py                  # the live run
```

## What is here

| File | Role |
|---|---|
| `policy.py` | the deterministic gate: sensors in, real or benign out |
| `play_gate.py` | rehearsal: the gate alone against the simulation |
| `validate.py` | the 200-seed distribution |
| `main.py` | the supervised crew and the tick loop |
| `facility_sim.py`, `feed.py` | the facility feed (local mock or `FEED_URL`) |
| `one_cli.py`, `mcp_wrapper.py`, `tools.py` | One: the three-tool loop, dispatch and search |
| `parasail.py` | Parasail inference |

## Status

- Deterministic gate: **done and measured** (200/200 seeds perfect)
- Swarm, One dispatch, You.com grounding: wired, awaiting live credentials
- Parasail inference: blocked on billing (`403 Inference not allowed` until a payment method or
  event credits are on the account)
