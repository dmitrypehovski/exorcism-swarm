"""Small wrapper around the One CLI plus One memory helpers.

Vendored into every template folder so a folder runs on its own. Keep the
copies identical; templates/check.sh compares them.

Everything goes through `one --agent ...`, which prints JSON and never prompts.
Action ids are resolved at run time with `one actions find` and picked by
method and path (and title when several actions share a path), never pasted
from a previous session. Needs One CLI 2.9+ on Node 22.23.4+, 24.22.1+ or 26.12.1+.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Failures where the request may have reached the platform even though no answer came back.
# Safe to retry a read; never safe to repeat a write without looking first.
UNCERTAIN = (
    "429", "bad gateway", "origin is overloaded", "temporarily",
    "timed out", "timeout", "etimedout",
    "printed nothing", "socket hang up", "econnreset", "econnrefused", "connection reset",
    "network", "fetch failed", "eai_again",
)
# Any 5xx: the platform may have applied the change before it failed to answer. This looks for a
# status code where One reports one, so an ordinary number in a message is not mistaken for one.
# Erring toward "uncertain" only ever costs a warning, so the rule stays deliberately simple.
SERVER_ERROR_RE = re.compile(r'(?:^|status\D{0,3}|error\D{0,3}|\()\s*5\d{2}\b', re.I)

SECRET_RE = re.compile(r"sk_(?:live|test)_[A-Za-z0-9_-]+")
ONERC = Path(".onerc")


class OneError(RuntimeError):
    """A One CLI call failed. The message never contains a secret."""


class WriteUncertain(OneError):
    """A write failed in a way that may still have been applied upstream.

    Raised instead of retrying, so the caller can look before it writes again.
    """


def redact(text: object) -> str:
    return SECRET_RE.sub("sk_***", str(text))


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def short_hash(text: str, n: int = 12) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:n]


def say(msg: str) -> None:
    print(redact(msg), flush=True)


def mask(key: str) -> str:
    """`test::you::default::c0b3…`: enough to recognise a key, not enough to reuse it."""
    head, sep, tail = key.partition("default::")
    return f"{head}{sep}{tail[:4]}…" if sep else key[:8] + "…"


def _parse_json(out: str):
    out = out.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        pass
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise OneError(f"could not parse CLI output: {redact(out[:300])}")


def _uncertain(message: str) -> bool:
    """True when the request may have been applied upstream despite the failure."""
    low = message.lower()
    return bool(SERVER_ERROR_RE.search(low)) or any(token in low for token in UNCERTAIN)


def one(*args: object, timeout: int = 300, retries: int = 0):
    """Run `one --agent <args>` and return the parsed JSON.

    `retries` defaults to 0 on purpose. A 502 or a timeout can hide a write that
    the platform already applied, so retrying blindly can send a second email or
    file a second issue. Callers that know the call is a read pass `retries`;
    `execute` does that automatically for GET, and never for anything else.
    """
    cmd = ["one", "--agent", *[str(a) for a in args]]
    label = " ".join(cmd[2:5])
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise OneError("the `one` CLI is not installed. Run: npm i -g @withone/cli") from exc
        except subprocess.TimeoutExpired as exc:
            # No answer came back, so there is no way to tell from here whether the platform
            # applied it. `execute` turns this into WriteUncertain for anything but a GET.
            message = f"`one {label} ...` timed out after {timeout}s"
            if attempt < retries:
                say(f"  {message}, retrying")
                continue
            raise OneError(message) from exc
        if not proc.stdout.strip():
            message = f"`one {label} ...` printed nothing: {redact(proc.stderr[:300])}"
            if attempt < retries:
                say("  no output from the CLI, retrying")
                continue
            raise OneError(message)
        result = _parse_json(proc.stdout)
        if isinstance(result, dict) and result.get("error"):
            detail = result.get("validation") or result.get("hint") or ""
            message = redact(f"{result['error']} {json.dumps(detail) if detail else ''}".strip())
            if attempt < retries and _uncertain(message):
                wait = 5 * (attempt + 1)
                say(f"  retryable error from One, waiting {wait}s (attempt {attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            raise OneError(message)
        return result


# --- connections -----------------------------------------------------------

def env_name(platform: str) -> str:
    return f"ONE_{platform.upper().replace('-', '_')}_CONNECTION_KEY"


def connections(platform: str) -> list[dict]:
    """Operational connections whose platform is exactly `platform`."""
    rows = one("list", "--search", platform, "--limit", "100").get("connections", [])
    return [c for c in rows if c.get("platform") == platform and c.get("state") == "operational"]


def connection(platform: str) -> str:
    """The connection key for a platform: the env var wins, else the only operational connection."""
    key = os.environ.get(env_name(platform), "").strip()
    if key:
        return key
    rows = connections(platform)
    if len(rows) == 1:
        return rows[0]["key"]
    if not rows:
        raise OneError(f"{platform} is not connected. Run `one add {platform}`, then put the key in .env as {env_name(platform)}")
    keys = "\n  ".join(f"{c['key']}  {c.get('name') or ''}" for c in rows)
    raise OneError(f"{platform} has {len(rows)} connections. Set {env_name(platform)} in .env to one of:\n  {keys}")


# --- actions ---------------------------------------------------------------

_ACTIONS: dict[tuple, str] = {}
_PATHS: dict[str, str] = {}
_METHODS: dict[str, str] = {}
_KNOWLEDGE: dict[str, str] = {}


def _norm(path: str) -> str:
    """Compare paths by shape: `{{pull_number}}`, `{pullNumber}` and `{id}` all become `{}`."""
    return re.sub(r"\{\{?\w+\}?\}", "{}", path).rstrip("/")


# What `actions find` is told the run is for, in general terms only: no names, ids or message text.
# Each template sets its own through `preflight(task=...)`; ONE_FIND_TASK overrides it.
TASK = "automate a workflow across connected apps"


def _cache_key(platform: str, method: str, path: str, title: str | None) -> tuple:
    return (platform, method.upper(), _norm(path), title)


def _pick(platform: str, query: str, method: str, path: str, title: str | None, acts: list[dict]) -> dict | None:
    hits = [a for a in acts if a["method"].upper() == method.upper() and _norm(a["path"]) == _norm(path)]
    hits = list({a["actionId"]: a for a in hits}.values())
    if title and len(hits) > 1:
        hits = [a for a in hits if a["title"].strip().lower() == title.strip().lower()]
    if len(hits) > 1:
        seen = "; ".join(a["title"] for a in hits)
        raise OneError(f"{len(hits)} {platform} actions match {method} {path}; pass title=. Candidates: {seen}")
    return hits[0] if hits else None


def resolve_all(wanted: list[tuple], task: str | None = None, agent_type: str = "execute") -> list[str]:
    """Find several action ids in one `actions find` call.

    Each item is (platform, query, method, path) or (platform, query, method, path, title). The
    answers come back one per pair, in order; every candidate (selected, alsoSelected, alternatives)
    is matched by method and path. Docs are left out here (`--no-knowledge`); `knowledge` loads them.
    """
    task = task or TASK
    items = [(w + (None,))[:5] for w in wanted]
    todo = [w for w in items if _cache_key(w[0], w[2], w[3], w[4]) not in _ACTIONS]
    todo = list(dict.fromkeys(todo))
    for start in range(0, len(todo), 10):  # `actions find` takes up to 10 pairs
        batch = todo[start:start + 10]
        pairs = [x for w in batch for x in (w[0], w[1])]
        answers = one("actions", "find", *pairs, "--task", task, "--no-knowledge", "-t", agent_type,
                      retries=2).get("answers", [])
        missing = []
        for (platform, query, method, path, title), ans in zip(batch, answers + [{}] * len(batch)):
            acts = [*ans.get("selected", []), *ans.get("alsoSelected", []), *ans.get("alternatives", [])]
            hit = _pick(platform, query, method, path, title, acts)
            if not hit:
                if agent_type == "execute":
                    missing.append((platform, query, method, path, title))
                    continue
                seen = "; ".join(f"{a['method']} {a['path']} ({a['title']})" for a in acts) or "none"
                raise OneError(f"no {platform} action matched {method} {path} for query '{query}'. Find returned: {seen}")
            _ACTIONS[_cache_key(platform, method, path, title)] = hit["actionId"]
            _PATHS[hit["actionId"]] = hit["path"]
            _METHODS[hit["actionId"]] = hit["method"].upper()
        if missing:
            resolve_all(missing, task, agent_type="knowledge")
    return [_ACTIONS[_cache_key(w[0], w[2], w[3], w[4])] for w in items]


def resolve(platform: str, query: str, method: str, path: str, title: str | None = None, task: str | None = None) -> str:
    """Find one action id at run time. Pick by method and path; use `title` when a path is shared."""
    return resolve_all([(platform, query, method, path, title)], task)[0]


def _canon(name: str) -> str:
    return name.replace("_", "").lower()


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(w.capitalize() for w in rest)


def _remap_path_vars(action_id: str, path_vars: dict) -> dict:
    """Send every path variable under each spelling an action might use.

    A path template may say `{{pullNumber}}` while the action's schema names
    the same variable `pull_number`; the CLI validates against the schema and
    substitutes the template, and extra keys are ignored, so sending
    `pullNumber`, `pull_number` and the template's own name covers all three.
    """
    out: dict = {}
    template_names = {_canon(n): n for n in re.findall(r"\{\{?(\w+)\}?\}", _PATHS.get(action_id, ""))}
    for k, v in path_vars.items():
        for name in {k, _snake(k), _camel(k), template_names.get(_canon(k), k)}:
            out[name] = v
    return out


def knowledge(platform: str, action_id: str) -> str:
    """The action's docs. Read before the first execute of every action."""
    if action_id not in _KNOWLEDGE:
        loaded = one("actions", "load", action_id, retries=2).get("loaded") or [{}]
        _KNOWLEDGE[action_id] = loaded[0].get("knowledge", "")
    return _KNOWLEDGE[action_id]


def execute(platform: str, action_id: str, key: str, data=None, path_vars=None, query=None,
            skip_validation: bool = False, timeout: int = 300, read_only: bool = False):
    """Execute one action and return the platform's response body.

    A GET is retried on a retryable server error. Anything that can change state
    is never retried here: a retryable failure raises `WriteUncertain`, because
    the write may have landed and only the response was lost.

    Some read-only actions still use POST because the query is too big for a URL
    (You.com's Research is one). Pass `read_only=True` for those, and only those:
    it says "repeating this call changes nothing", which is what makes a retry safe.
    """
    knowledge(platform, action_id)
    is_read = read_only or _METHODS.get(action_id, "POST") == "GET"
    args: list[object] = ["actions", "execute", platform, action_id, key]
    if data is not None:
        args += ["-d", json.dumps(data)]
    if path_vars:
        args += ["--path-vars", json.dumps(_remap_path_vars(action_id, path_vars))]
    if query:
        args += ["--query-params", json.dumps(query)]
    if skip_validation:
        args.append("--skip-validation")
    try:
        result = one(*args, timeout=timeout, retries=2 if is_read else 0)
    except OneError as exc:
        # One's custom actions (paths like /v1/gmail/send-email) take the connection key in the
        # body as well as the header. The validator names the missing field; add it and retry once.
        # This is safe for a write: a validation error means the request never reached the platform.
        if '"connectionKey"' in str(exc) and isinstance(data, dict) and "connectionKey" not in data:
            return execute(platform, action_id, key, {**data, "connectionKey": key}, path_vars, query,
                           skip_validation, timeout, read_only)
        if not is_read and _uncertain(str(exc)):
            raise WriteUncertain(
                f"{exc}\nThis was not a read, so it was not retried: the write may have been applied. "
                "Check the platform (or app.withone.ai/logs) before sending it again.") from exc
        raise
    return result.get("response") if isinstance(result, dict) else result


def b64_write_command(path: str, content: str) -> str:
    """A shell command that writes `content` to `path` without quoting problems."""
    payload = base64.b64encode(content.encode()).decode()
    return f"printf '%s' '{payload}' | base64 -d > {path}"


# --- .onerc allowlist for the CLI --------------------------------------------

def _write_onerc(keys: list[str] | None) -> list[str]:
    """Rewrite ./.onerc with ONE_CONNECTION_KEYS set to `keys` (None drops the line). Returns the old keys."""
    lines: list[str] = []
    previous: list[str] = []
    if ONERC.exists():
        for line in ONERC.read_text().splitlines():
            if line.startswith("ONE_CONNECTION_KEYS="):
                previous = [k.strip() for k in line.split("=", 1)[1].split(",") if k.strip()]
            else:
                lines.append(line)
    if keys is not None:
        lines.append("ONE_CONNECTION_KEYS=" + ",".join(keys))
    fd, tmp = tempfile.mkstemp(dir=".", prefix=".onerc.")
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(lines) + "\n" if lines else "")
    os.replace(tmp, ONERC)
    return previous


def clear_onerc() -> None:
    """Drop the allowlist a previous run wrote, so connection lookups see the whole account again.

    Without this, a dry run that narrowed .onerc to You.com leaves a live run unable to find Slack.
    """
    if ONERC.exists():
        _write_onerc(None)


def ensure_onerc(keys: list[str]) -> None:
    """Set ONE_CONNECTION_KEYS in ./.onerc to exactly `keys`, keep other lines, write atomically, verify."""
    wanted = sorted(set(keys))
    previous = _write_onerc(wanted)
    if previous and sorted(set(previous)) != wanted:
        say(f"narrowed .onerc from {len(previous)} to {len(wanted)} connection keys")
    effective = one("list", "--limit", "100")
    seen = sorted(c["key"] for c in effective.get("connections", []))
    if seen != wanted:
        raise OneError(f".onerc allowlist did not take effect. Expected {wanted}, the CLI sees {seen}")


# --- memory ----------------------------------------------------------------

def memory_ready() -> None:
    """Memory needs a One config file (env-only ONE_SECRET is not enough). The first call bootstraps the store."""
    try:
        one("mem", "list", "note", "--limit", 1, timeout=240)
    except OneError as exc:
        if "config" in str(exc).lower():
            raise OneError("One memory needs a One config file. Run ./setup.sh (it runs `one init`), then try again") from exc
        raise


def mem_add(rtype: str, data: dict, tags=(), keys=(), weight: int | None = None) -> dict:
    args: list[object] = ["mem", "add", rtype, json.dumps(data)]
    if tags:
        args += ["--tags", ",".join(tags)]
    if keys:
        args += ["--keys", ",".join(keys)]
    if weight:
        args += ["--weight", weight]
    return one(*args)


def mem_find(key: str, rtype: str | None = None) -> list[dict]:
    args: list[object] = ["mem", "find-by-key", key]
    if rtype:
        args += ["--type", rtype]
    by_type = one(*args, retries=2).get("byType", {})
    out: list[dict] = []
    for _, group in by_type.items():
        out.extend(group.get("items", group) if isinstance(group, dict) else group)
    return out


def mem_update(record_id: str, patch: dict) -> dict:
    return one("mem", "update", record_id, json.dumps(patch))


def mem_search(query: str, rtype: str | None = None, limit: int = 10) -> list[dict]:
    args: list[object] = ["mem", "search", query, "--limit", limit, "--no-track"]
    if rtype:
        args += ["--type", rtype]
    return one(*args, retries=2).get("items", [])


def mem_list(rtype: str, status: str = "active") -> list[dict]:
    """Every record of a type, paginated past the CLI's default of 100. The CLI offset is 1-based."""
    out: list[dict] = []
    fetched = 0
    while True:
        args: list[object] = ["mem", "list", rtype, "--limit", 100, "--status", status]
        if fetched:
            args += ["--offset", fetched + 1]
        page = one(*args, retries=2).get("items", [])
        out.extend(page)
        fetched += len(page)
        if len(page) < 100:
            return out


def mem_archive(record_id: str, reason: str = "demo-reset") -> dict:
    return one("mem", "archive", record_id, "--reason", reason)


def remember(template: str, rtype: str, data: dict, key: str | None = None, tags=(), weight: int = 6) -> str:
    """Store or refresh a record. With `key`, find-by-key then update, else add; add conflicts re-find and update."""
    payload = {**data, "template": template, "updated_at": now_iso()}
    all_tags = [f"template:{template}", *tags]
    if key:
        found = mem_find(key, rtype)
        if found:
            mem_update(found[0]["id"], payload)
            return found[0]["id"]
        try:
            return mem_add(rtype, payload, tags=all_tags, keys=[key], weight=weight)["id"]
        except OneError as exc:
            if "key" not in str(exc).lower():
                raise
            found = mem_find(key, rtype)
            if not found:
                raise
            mem_update(found[0]["id"], payload)
            return found[0]["id"]
    return mem_add(rtype, payload, tags=all_tags, weight=weight)["id"]


def recall(template: str, rtype: str, query: str | None = None, limit: int = 10) -> list[dict]:
    """This template's records of a type, newest first.

    A query ranks by search when the store's full-text index has a hit, but that
    index can miss short records, so we always fall back to the full list rather
    than trust an empty search.
    """
    items: list[dict] = []
    if query:
        items = [r for r in mem_search(query, rtype, limit * 3) if (r.get("data") or {}).get("template") == template]
    if not items:
        items = [r for r in mem_list(rtype) if (r.get("data") or {}).get("template") == template]
    items.sort(key=lambda r: (r.get("data") or {}).get("updated_at", ""), reverse=True)
    return items[:limit]


def forget(template: str, rtypes: list[str]) -> int:
    """Archive every record this template wrote. Archiving frees the record's keys."""
    count = 0
    for rtype in rtypes:
        for rec in mem_list(rtype):
            if (rec.get("data") or {}).get("template") == template or f"template:{template}" in (rec.get("tags") or []):
                mem_archive(rec["id"])
                count += 1
    return count


# --- preflight -------------------------------------------------------------

def preflight(template: str, platforms: list[str], need_memory: bool = True, task: str | None = None) -> dict[str, str]:
    """Check the toolchain, the account and the connections; write the allowlist; return platform -> key.

    `task` is the run's one-line purpose, sent with every `actions find`.
    """
    global TASK
    TASK = os.environ.get("ONE_FIND_TASK") or task or TASK
    for binary, fix in (("node", "install Node 22.23.4+, 24.22.1+ or 26.12.1+"), ("one", "npm i -g @withone/cli")):
        if not shutil.which(binary):
            raise OneError(f"`{binary}` is not on PATH: {fix}")
    who = one("whoami")
    say(f"One account: {who.get('user', {}).get('email')} ({who.get('env')}, {who.get('apiBase')})")
    clear_onerc()
    keys: dict[str, str] = {}
    for platform in platforms:
        keys[platform] = connection(platform)
        say(f"  {platform}: {mask(keys[platform])}")
    ensure_onerc(list(keys.values()))
    if need_memory:
        memory_ready()
    return keys


def load_env(path: str = ".env") -> None:
    """Tiny .env loader (KEY=VALUE, # comments). Does not override variables already set."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ and v:
            os.environ[k] = v


def die(msg: str, code: int = 1) -> None:
    print(f"error: {redact(msg)}", file=sys.stderr, flush=True)
    sys.exit(code)
