# Exorcism swarm

A starting point for Track 1, The Exorcism Protocol. A supervised CrewAI swarm watches a facility feed, decides which anomalies are real outbreaks, contains them, and scores itself the way the judges do: time to containment, false alarms, civilians saved.

Three agents, each with its own role, its own tools and only part of the picture:

| Agent | Sees | Can do |
|---|---|---|
| Sentinel | Sensor readings only (EMF, temperature, audio, motion) | Post a sighting to the shared channel, mirrored to Slack through One |
| Analyst | Witness reports and the shared channel, never raw sensors | Search the web with You.com through One (its own MCP server, scoped to one connection and one action) |
| Dispatcher | The civilian roster only | Manages the crew (`Process.hierarchical`): asks the other two, then issues the containment orders |

The code carries out each order against the feed, files it as a Linear issue and posts the decision to Slack, both through One. Writes go only to the channel and team you set in `.env`.

## The four tools

| Tool | What it does here |
|---|---|
| You.com | The Analyst checks sightings against the outside world with Search (`GET /v1/search`) on One's `you` platform |
| One | Every app call: You.com search through the local MCP server inside CrewAI, Slack posts and Linear issues through the One CLI. Managed auth, one key |
| CrewAI | Runs the swarm: a hierarchical crew with the Dispatcher as manager |
| Parasail | Runs the model behind all three agents, through its OpenAI-compatible API |

## Setup

Node 22.23.4+, 24.22.1+ or 26.12.1+ (the One CLI and MCP server refuse older releases; setup checks), One CLI 2.9+, Python 3.10 to 3.13 (setup picks 3.13 or 3.12 if you have them), a One account, a Parasail key, and three connections:

```bash
one add you      # key from https://api.you.com
one add slack    # then invite the bot to your channel
one add linear

cd templates/exorcism-swarm
./setup.sh       # creates .venv and .env; fill .env in, then run ./setup.sh again
```

Fill in `.env`:

- `PARASAIL_API_KEY` from https://www.saas.parasail.io/keys
- `PARASAIL_MODEL`, default `parasail-kimi-k26`
- `ONE_SECRET` from https://app.withone.ai/settings/api-keys
- `SLACK_CHANNEL` (a channel id like `C0123...`) and `LINEAR_TEAM_KEY` (the short key, like `ENG`)
- the `ONE_*_CONNECTION_KEY` lines only if you have more than one connection for that platform

The second `./setup.sh` runs `python main.py --check`: it confirms the Parasail model exists for your key, that each platform is connected, and that the Linear team resolves. It also writes `.onerc` so the One CLI only sees these three connections.

### Picking a Parasail model

Agents call tools, so the model must support tool (function) calling. Model ids change; list the ones your key can use:

```bash
curl -s https://api.parasail.io/v1/models -H "Authorization: Bearer $PARASAIL_API_KEY" | jq -r '.data[].id'
```

`parasail-kimi-k26` is the default. `parasail-deepseek-v4-flash`, `parasail-qwen3p6-35b-a3b` and `parasail-glm-52` also list tool calling in Parasail's docs (https://docs.parasail.io/parasail-docs/guides/tool-function-calling.md). If an agent never calls a tool, try another.

`parasail.py` builds the CrewAI LLM as `LLM(model=<id>, provider="openai", base_url="https://api.parasail.io/v1", api_key=...)`. Use `provider="openai"` with the bare id, not `model="openai/<id>"`: in crewai 1.15.2 the prefix form only works for model names CrewAI already knows, and anything else falls through to LiteLLM, which plain `crewai` does not install.

## Run

```bash
source .venv/bin/activate
python main.py --baseline   # no keys needed: a naive rule plays the sim, so you can see the feed and the bar to beat
python main.py --dry-run    # the swarm, but Slack posts and Linear issues are printed instead of sent
python main.py              # the real thing: posts to SLACK_CHANNEL, files in LINEAR_TEAM_KEY
python main.py --verbose    # every agent step
python facility_sim.py      # just print the mock feed, tick by tick
```

`--dry-run` still needs `PARASAIL_API_KEY`. With `ONE_SECRET` set it also uses You.com search (a read); without it, the Analyst works from the reports alone.

Each tick is one crew run, so a 6-tick run makes a few dozen model calls and takes a few minutes. `--ticks 3` is quicker while you iterate.

## What you will see

A dry run on the default seed (abridged and illustrative: the feed lines are exact, the agents' wording and choices depend on your model):

```text
Feed: local mock (facility_sim.py). Mode: dry-run.
Parasail model: parasail-kimi-k26
One account: you@example.com (live, https://api.withone.ai)
  you: live::you::default::1a2b…

tick 0/6: the swarm is looking
  [dry-run] Slack #containment: :ghost: Sentinel, tick 0, Greenhouse (medium): audio 72 dB, other sensors normal
  held Greenhouse: witness says it is the Halloween party playlist
  no containment orders this tick

tick 1/6: the swarm is looking
  [dry-run] Slack #containment: :ghost: Sentinel, tick 1, Atrium (high): EMF 6.9, temp 16.5, audio 58, motion 6
  [dry-run] Slack #containment: :ghost: Sentinel, tick 1, Chapel (high): EMF 8.5, temp 16.6, audio 55, motion 7
  exorcise Atrium: contained. outbreak in the Atrium contained, 8 civilians safe
  [dry-run] Linear issue: [Contained] Atrium: poltergeist (tick 1)
  ...

==================================================
  SCOREBOARD  (dry-run)
==================================================
  Outbreaks contained               2/2
  Mean ticks to containment         1.0
  Mean seconds to containment       48.3
  False alarms                      0
  Civilians saved                   31 of 31 at risk
  Civilians lost                    0
  Outbreaks missed                  0
==================================================
appended to out/runs.jsonl
```

A live run posts the same lines to Slack and files one Linear issue per containment order, titled `[Contained]`, `[Evacuated]` or `[False alarm]`, with the order, the reasoning and the outcome in the body. The Slack decision line carries the Linear link.

The naive baseline on the default seed contains both outbreaks but sends five teams after false alarms. That is the number the swarm should beat.

Every run appends one line to `out/runs.jsonl`: mode, model, feed, outbreaks, contained, mean ticks and seconds to containment, false alarms, civilians saved, lost and at risk, plus how many Slack posts and Linear issues went out.

## How it is built

- `main.py` runs the loop: observe a tick, run the crew, check its JSON orders, carry them out, advance. It ends with the scoreboard.
- `tools.py` holds the skill's `one_mcp_params`, `dropping_nulls` and `harden_execute`, a `capped` wrapper (two web searches per tick), the per-agent feed tools, and the `Outbox` that sends or prints every write. Of the MCP server's three tools the Analyst gets two: `find_one_actions` to read the search action's documentation and `execute_one_action` to run it.
- `facility_sim.py` is the mock facility: six zones, sensors, witness reports, civilians, two real outbreaks and two false alarms per seed. An outbreak left running costs civilians every tick. `python facility_sim.py --serve 8077` serves it over HTTP.
- `feed.py` picks the source: the in-process mock, or `FEED_URL` over HTTP.
- `parasail.py` is the model helper (shared with the Track 2 template). `one_cli.py` (it finds every action id in one `one actions find` call) and `mcp_wrapper.py` are the helpers every template vendors.

Design choices worth keeping:

- The Dispatcher has no tools. CrewAI rejects a manager agent with tools, and it is the right split anyway: the manager decides, the code acts.
- Orders are checked in code before they touch the feed. An unknown zone, an unknown action or a zone already contained is dropped and logged, never guessed.
- Writes are never retried blindly. If One reports a timeout or a gateway error on a Slack post or a Linear issue, the run says so and moves on, because the write may have landed (see `WriteUncertain` in `one_cli.py`).
- `mcp_wrapper.py` copies the MCP server's stderr to `mcp-stderr.log` with secrets and connection keys redacted, because the server prints the whole failed request on a 4xx.

## Plugging in the real facility simulation

The starter repo's simulation was not published when this was written. When it is, set `FEED_URL` in `.env`. `feed.HttpFeed` expects four routes:

| Route | Returns |
|---|---|
| `GET /observe` | `{tick, ticks_total, zones[], sensors{zone: {...}}, reports[], roster{zone: civilians}}` |
| `POST /advance` | the next observation |
| `POST /contain` with `{zone, action}` | `{ok, outcome, ticks_to_contain, civilians_saved, ...}` |
| `GET /score` | the running score |

If the real sim names things differently, adapt `HttpFeed` only. To try the HTTP path today: `python facility_sim.py --serve 8077` in one terminal and `FEED_URL=http://127.0.0.1:8077 python main.py --dry-run` in another.

## How to extend

- Give each agent its own One scope. Today only the Analyst has an MCP server. Start a second `MCPServerAdapter` with the Slack connection for the Sentinel, so the scope is enforced by One, not just by which tools it holds.
- Read the channel back. Have the Analyst read Slack history through One, so a human can post "false alarm, it's the fog machine" and the swarm listens.
- Keep shared state in Notion: one row per zone, updated every tick, so a fresh crew run starts from what the last one knew.
- Tune for the scoreboard: try a cheaper, faster Parasail model for the Sentinel and a stronger one for the Dispatcher.
