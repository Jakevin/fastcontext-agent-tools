# Shared environment for running FastContext locally.
# Source from the other scripts:  source "$(dirname "$0")/env.sh"
#
# This file ships safe, committable defaults. Machine-specific values
# (allowlist, HF_TOKEN, a remote endpoint) belong in scripts/env.local.sh,
# which is gitignored and sourced last so it overrides these.

# Repo root, derived from this file's location (scripts/ -> repo root).
export FC_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export FC_VENV="$FC_REPO/.venv"             # lightweight MCP venv
export FC_SERVE_VENV="$FC_REPO/.venv-serve" # heavy vLLM serving venv

# OpenAI-compatible endpoint serving the FastContext model (vLLM/SGLang port).
export BASE_URL="${BASE_URL:-http://127.0.0.1:30000/v1}"

# Prefer the RL variant: higher accuracy + bigger token cuts than -SFT.
export MODEL="${MODEL:-microsoft/FastContext-1.0-4B-RL}"

# Local serving needs no auth; placeholder keeps the OpenAI client happy.
export API_KEY="${API_KEY:-local-no-auth}"

# Fail-closed allowlist. Defaults to the repo's parent directory; set the real
# location of your repos in env.local.sh.
export FASTCONTEXT_ALLOWED_ROOTS="${FASTCONTEXT_ALLOWED_ROOTS:-$(cd "$FC_REPO/.." && pwd)}"

# Machine-specific overrides (gitignored): allowlist, HF_TOKEN, remote BASE_URL/API_KEY.
if [[ -f "$FC_REPO/scripts/env.local.sh" ]]; then
  # shellcheck disable=SC1091
  source "$FC_REPO/scripts/env.local.sh"
fi
