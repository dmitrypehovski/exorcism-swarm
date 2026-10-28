#!/usr/bin/env bash
# One-time setup for a Halloween template: toolchain check, Python venv, .env, preflight.
# Run it from anywhere: ./setup.sh. Identical in exorcism-swarm and haunted-command-station;
# templates/check.sh compares the copies.
set -euo pipefail
cd "$(dirname "$0")"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1 ($2)"; exit 1; }; }
need node "install Node 22.23.4+, 24.22.1+ or 26.12.1+ from https://nodejs.org"
# The One CLI and MCP server refuse Node 18, 20, 23 and 25, and older patch releases of 22, 24 and 26.
node_ok() {
  local v major minor patch min mmin mpatch
  v="$(node -p 'process.versions.node')"
  IFS=. read -r major minor patch <<<"$v"
  case "$major" in
    22) min="23 4" ;; 24) min="22 1" ;; 26) min="12 1" ;;
    *) [ "$major" -gt 26 ] && [ $((major % 2)) = 0 ]; return ;;  # a later LTS line is assumed fine
  esac
  read -r mmin mpatch <<<"$min"
  [ "$minor" -gt "$mmin" ] || { [ "$minor" = "$mmin" ] && [ "$patch" -ge "$mpatch" ]; }
}
if ! node_ok; then
  echo "Node $(node -v) is too old or unsupported for the One CLI. Install 22.23.4+, 24.22.1+ or 26.12.1+"
  exit 1
fi
if ! command -v one >/dev/null 2>&1; then
  echo "installing the One CLI"
  npm i -g @withone/cli
fi

# CrewAI 1.15.2 needs Python 3.10 to 3.13. Use the newest of those that is installed.
PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1 && \
     [ "$("$cand" -c 'import sys; print(int((3,10) <= sys.version_info[:2] <= (3,13)))')" = "1" ]; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "need Python 3.10 to 3.13 (python3 is $(python3 --version 2>&1)). Install 3.12 or 3.13 and run this again"
  exit 1
fi

if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

if [ -f mcp_wrapper.py ]; then
  echo "downloading the One MCP server once, so the first crew run is not slow"
  # With stdin closed the stdio server exits at once; all this does is fill the npx cache.
  npx -y @withone/mcp </dev/null >/dev/null 2>&1 || echo "  could not pre-download @withone/mcp; the first run will fetch it"
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "created .env from .env.example. Fill it in, then run ./setup.sh again"
  exit 0
fi

# Read the two keys instead of sourcing .env: a value with spaces in an older, unquoted .env
# would otherwise run as a command. main.py loads the rest of .env itself.
envval() { sed -n "s/^$1=//p" .env | tail -n 1 | sed -e "s/^[\"']//" -e "s/[\"']\$//"; }
PARASAIL_API_KEY="$(envval PARASAIL_API_KEY)"
ONE_SECRET="$(envval ONE_SECRET)"
if [ -z "${PARASAIL_API_KEY:-}" ]; then
  echo "PARASAIL_API_KEY is empty in .env. Get a key at https://www.saas.parasail.io/keys"
  exit 1
fi
if [ -z "${ONE_SECRET:-}" ]; then
  echo "ONE_SECRET is empty in .env. Get a key at https://app.withone.ai/settings/api-keys"
  exit 1
fi

python main.py --check
echo "setup complete. Run: source .venv/bin/activate && python main.py"
