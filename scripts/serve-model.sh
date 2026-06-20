#!/usr/bin/env bash
# serve-model.sh — serve the FastContext model on a local OpenAI-compatible
# endpoint (port 30000) with vLLM, for the MCP server to call.
#
# Long-running. Run in its own terminal; wait for the Uvicorn
# "Application startup complete" line on :30000, then run
# ./scripts/kickoff.sh explore in another terminal.
#
# vLLM lives in its OWN venv ($FC_SERVE_VENV) so its heavy GPU deps never
# collide with the lightweight MCP venv.
#
# WHY THESE FLAGS: fastcontext/agent/llm.py reads server-side `tool_calls`,
# which vLLM only emits with --enable-auto-tool-choice + a tool parser.
# FastContext-4B is built on Qwen3-4B-Instruct, so `hermes` is correct. If
# explore returns no citations, try --tool-call-parser qwen3_xml.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/env.sh"

MODEL_ID="$MODEL"
# Model supports up to 262144; default smaller to keep KV cache modest. Override
# with CTX_LEN=... if your card has headroom.
CTX_LEN="${CTX_LEN:-65536}"

# Quantisation. FastContext-4B is ~8GB of BF16 weights, which does NOT fit on an
# 8GB card (the weights alone OOM before any KV cache is allocated). Set
# QUANT=bitsandbytes for in-flight 4-bit (~2.5GB weights) so it fits on small
# cards. Leave empty for full-precision BF16 on cards with >=~12GB free.
QUANT="${QUANT:-}"

# Fraction of VRAM vLLM may consume for weights + KV cache. The default 0.9 is
# too aggressive on small cards: it leaves no headroom for CUDA-graph capture
# and the CUDA context, which then OOMs *after* the weights load. Drop to ~0.85
# on an 8GB card.
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.9}"

# Skip CUDA-graph capture (adds --enforce-eager). Graph capture needs a chunk of
# spare VRAM at startup; on a tight card it's the step that OOMs. Setting
# ENFORCE_EAGER=1 trades a little decode latency for that headroom. Recommended
# on <=8GB cards.
ENFORCE_EAGER="${ENFORCE_EAGER:-}"

# GPU selection. vLLM picks the device via CUDA_VISIBLE_DEVICES. Honour an
# explicit GPU=... (or a pre-set CUDA_VISIBLE_DEVICES); otherwise prompt from
# the cards nvidia-smi reports. Set GPU=all to expose every card (tensor
# parallel), or GPU=0,1 for a specific subset.
select_gpu() {
  # Already chosen, or running non-interactively (no TTY): don't prompt.
  if [[ -n "${GPU:-}" ]]; then
    [[ "$GPU" == "all" ]] && { unset CUDA_VISIBLE_DEVICES; return; }
    export CUDA_VISIBLE_DEVICES="$GPU"
    return
  fi
  if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
    echo ">> using CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES (from environment)"
    return
  fi
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo ">> nvidia-smi not found; letting vLLM auto-select the GPU"
    return
  fi

  mapfile -t gpus < <(nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader)
  if [[ ${#gpus[@]} -eq 0 ]]; then
    echo ">> no GPUs reported by nvidia-smi; letting vLLM auto-select"
    return
  fi
  if [[ ${#gpus[@]} -eq 1 ]]; then
    local idx="${gpus[0]%%,*}"
    export CUDA_VISIBLE_DEVICES="$idx"
    echo ">> single GPU detected: ${gpus[0]} (CUDA_VISIBLE_DEVICES=$idx)"
    return
  fi
  if [[ ! -t 0 ]]; then
    echo ">> multiple GPUs detected but no TTY to prompt; letting vLLM auto-select"
    echo ">> (set GPU=N, GPU=0,1, or GPU=all to choose explicitly)"
    return
  fi

  echo "Available GPUs:"
  for g in "${gpus[@]}"; do
    echo "  $g"
  done
  local choice
  read -rp "Select GPU index (or comma-separated list, 'all') [${gpus[0]%%,*}]: " choice
  choice="${choice:-${gpus[0]%%,*}}"
  if [[ "$choice" == "all" ]]; then
    unset CUDA_VISIBLE_DEVICES
    echo ">> exposing all GPUs to vLLM"
  else
    export CUDA_VISIBLE_DEVICES="$choice"
    echo ">> using CUDA_VISIBLE_DEVICES=$choice"
  fi
}
select_gpu

if [[ ! -x "$FC_SERVE_VENV/bin/python" ]]; then
  echo ">> creating serving venv ($FC_SERVE_VENV)"
  uv venv --python 3.12 "$FC_SERVE_VENV"
fi
source "$FC_SERVE_VENV/bin/activate"

if ! python -c "import vllm" 2>/dev/null; then
  echo ">> installing vLLM (large; pulls a CUDA PyTorch build for Blackwell)"
  uv pip install vllm
fi

# Assemble vLLM args; append quantisation only when requested.
VLLM_ARGS=(
    --port 30000
    --enable-auto-tool-choice
    --tool-call-parser hermes
    --max-model-len "$CTX_LEN"
    --gpu-memory-utilization "$GPU_MEM_UTIL"
    --trust-remote-code
)
if [[ -n "$QUANT" ]]; then
  if ! python -c "import bitsandbytes" 2>/dev/null; then
    echo ">> installing bitsandbytes (needed for QUANT=$QUANT)"
    uv pip install bitsandbytes
  fi
  VLLM_ARGS+=(--quantization "$QUANT")
  echo ">> quantisation enabled: $QUANT"
fi
if [[ -n "$ENFORCE_EAGER" && "$ENFORCE_EAGER" != "0" ]]; then
  VLLM_ARGS+=(--enforce-eager)
  echo ">> CUDA graphs disabled (--enforce-eager)"
fi
echo ">> gpu-memory-utilization=$GPU_MEM_UTIL"

echo ">> launching vLLM for $MODEL_ID (ctx=$CTX_LEN) on port 30000"
exec vllm serve "$MODEL_ID" "${VLLM_ARGS[@]}"
