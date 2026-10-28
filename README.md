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

## The full swarm, measured live

`SIM_TICKS=2 python main.py --dry-run` — the real CrewAI crew (Sentinel, Analyst, Dispatcher) on a
real model, no Parasail needed:

```
Outbreaks contained               2/2
Mean ticks to containment         1.0
Mean seconds to containment       14.6
False alarms                      0
Civilians saved                   31 of 31 at risk
Civilians lost                    0
Outbreaks missed                  0
```

The Analyst held the motion-only and audio-only anomalies as false alarms and named the mundane
cause each time ("intern in a ghost costume", "Halloween party playlist"), while the two real
outbreaks were ordered contained on the tick they appeared on multi-channel evidence.

## Inference: Parasail first, OpenRouter if Parasail refuses

Parasail is the event's inference partner and stays the configured default. A Parasail key without a
payment method lists models and then refuses every inference call:

```
403 Inference not allowed. Please add a valid payment method
```

That would stop the crew on its first thought, so `llm.py` probes Parasail once before the run. If it
answers, the swarm runs on Parasail. If it refuses, the run falls back to OpenRouter and states which
provider served it, on stdout and in the trace. Nothing is hidden, and the Parasail path is a real
code path rather than a comment.

## The live run, and the false alarm that justifies the gate

First live run, seed 31, dispatch on: **2/2 contained, but 1 false alarm.** The Dispatcher ordered an
exorcism in the Server Vault on a single-channel motion anomaly. The field team found nothing, and
the run filed `ARL-7 [False alarm] Server Vault` in Linear.

That is the exact failure the design anticipates, so the gate was given the last word: before any
order reaches the feed, `main.py` asks `policy.zone_verdict()` for its read, and holds the order when
the anomaly sits in a single channel. The swarm still argues, explains and dispatches; it no longer
gets to spend a false alarm.

Same seed, same live dispatch, after the gate:

```
Outbreaks contained               2/2
Mean ticks to containment         1.0
Mean seconds to containment       74.1
False alarms                      0
Civilians saved                   31 of 31 at risk
Civilians lost                    0
Outbreaks missed                  0
```

Held that run, with the gate's own reasoning: a motion-only spike with a witness report of a person
in a ghost costume; an audio-only spike identified as the Halloween party playlist.

## Verified end to end, outside this machine

The dispatch is not a print statement. Read back through One after the live run:

- Slack `#loft-incident` — 15 messages: the Sentinel's raw sightings, the Analyst's verdicts, the
  Dispatcher's orders, each with its Linear link
- Linear team ARL — `ARL-5` and `ARL-6` contained (first run), `ARL-7` the false alarm, `ARL-8` and
  `ARL-9` contained (the gated run)
- You.com — reached both directly and through One's `you` platform

## Demo video

2 minutes 7 seconds, rendered from the repo's own `make_demo.py` (PIL frames piped into ffmpeg, so it
is reproducible from source rather than screen-recorded):

https://cdn.jsdelivr.net/gh/dmitrypehovski/exorcism-swarm@main/demo/exorcism-swarm-demo.mp4

The same file is committed at `demo/exorcism-swarm-demo.mp4`.

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
| `policy.py` | the deterministic gate: sensors in, real or benign out; the last word before an order |
| `play_gate.py` | rehearsal: the gate alone against the simulation |
| `validate.py` | the 200-seed distribution |
| `main.py` | the supervised crew and the tick loop |
| `facility_sim.py`, `feed.py` | the facility feed (local mock or `FEED_URL`) |
| `one_cli.py`, `mcp_wrapper.py`, `tools.py` | One: the three-tool loop, dispatch and search |
| `parasail.py`, `llm.py` | Parasail inference, and the provider probe with the OpenRouter fallback |

## Status

- Deterministic gate: **done and measured** (200/200 seeds perfect)
- Swarm: **runs and scores live** (2/2 contained, 0 false alarms, 31/31 civilians saved)
- Inference: Parasail primary, OpenRouter fallback verified live
- One dispatch: **verified in Slack and Linear** (ARL-5 through ARL-9)
- Deterministic gate: wired into the order path as the final veto
