"""Start `npx -y @withone/mcp` with its stderr redacted.

The local MCP server prints the whole failed request, including the plaintext
`x-one-secret`, to stderr on a 4xx or 5xx. This wrapper keeps stdin and stdout
untouched (the MCP transport) and copies stderr to mcp-stderr.log with every
secret and connection key replaced before a byte reaches the disk.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading

LOG = os.environ.get("MCP_STDERR_LOG", "mcp-stderr.log")


def _patterns() -> list[re.Pattern]:
    # Shapes first, then the exact values this process can see. The model keys are not passed to
    # the child (see tools.one_mcp_params), but redact them anyway in case a parent leaks them in.
    pats = [
        re.compile(r"sk_(?:live|test)_[A-Za-z0-9_-]+"),
        re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
        re.compile(r"(live|test)::[a-z0-9-]+::default::[0-9a-f]{32}(\|[0-9a-f-]{36})?"),
    ]
    for var in ("ONE_SECRET", "ONE_CONNECTION_KEYS", "ONE_ACTION_IDS", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        for value in (os.environ.get(var) or "").split(","):
            value = value.strip()
            if len(value) >= 12:
                pats.append(re.compile(re.escape(value)))
    return pats


def _pump(stream, sink, pats):
    for raw in iter(stream.readline, b""):
        line = raw.decode("utf-8", "replace")
        for p in pats:
            line = p.sub("<redacted>", line)
        sink.write(line)
        sink.flush()


def main() -> int:
    proc = subprocess.Popen(["npx", "-y", "@withone/mcp"], stdin=sys.stdin, stdout=sys.stdout, stderr=subprocess.PIPE)
    with open(LOG, "a", encoding="utf-8") as sink:
        t = threading.Thread(target=_pump, args=(proc.stderr, sink, _patterns()), daemon=True)
        t.start()
        code = proc.wait()
        t.join(timeout=2)
    return code


if __name__ == "__main__":
    sys.exit(main())
