#!/usr/bin/env bash
# kickoff.sh — verify the FastContext MCP server locally, unchanged.
#
#   ./scripts/kickoff.sh            # health check only (no model needed)
#   ./scripts/kickoff.sh explore    # also run a real explore call (needs a served model)
#
# Installs (if needed), checks health, and optionally fires one
# fastcontext_explore against this repo as a smoke test.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/env.sh"

# --- ensure the venv + editable install exist -------------------------------
if [[ ! -x "$FC_VENV/bin/python" ]]; then
  echo ">> creating venv ($FC_VENV) with Python 3.12"
  uv venv --python 3.12 "$FC_VENV"
fi
source "$FC_VENV/bin/activate"
if ! python -c "import fastcontext_mcp" 2>/dev/null; then
  echo ">> installing fastcontext-agent-tools (editable) + Microsoft FastContext"
  (cd "$FC_REPO" && uv pip install -e .)
fi

# --- Checkpoint A: health (no model required) -------------------------------
echo ">> health check:"
python -m fastcontext_mcp --print-health

# --- Checkpoint B: live explore (only with the model served) ----------------
if [[ "${1:-}" == "explore" ]]; then
  echo
  echo ">> smoke-testing a live explore against $FC_REPO"
  echo "   (requires the model server from serve-model.sh on $BASE_URL)"
  python - "$FC_REPO" <<'PY'
import sys
from fastcontext_mcp.runtime import run_fastcontext
res = run_fastcontext({
    "repo_path": sys.argv[1],
    "query": "Where is the MCP JSON-RPC request routing and tool dispatch implemented?",
    "max_turns": 6,
    "citation": True,
    "timeout_seconds": 300,
})
print("ok:", res["ok"], "returncode:", res["returncode"])
print("citations:", res["citations"])
if res["citation_warnings"]:
    print("warnings:", res["citation_warnings"])
if not res["ok"]:
    print("stderr:", res["stderr"][:1000])
PY
fi
