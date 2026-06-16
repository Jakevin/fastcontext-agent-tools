# FastContext Agent Tools

MCP server and Codex skill for using Microsoft's FastContext as a read-only
repository exploration subagent.

![Architecture](docs/assets/architecture.svg)

FastContext answers one narrow question for a coding agent:

> Which files and line ranges should the main agent inspect before solving this task?

This repository provides the complete integration:

- `fastcontext-mcp`: a Python stdio MCP server that installs Microsoft FastContext as a pinned runtime dependency.
- `skills/fastcontext-explorer`: a Codex skill that teaches an agent when to delegate repository exploration.
- Evaluation artifacts for the wrapper layer.
- MCP setup guides in English, Traditional Chinese, and Japanese.

It does not bundle model weights, run inference, or modify repositories. The MCP
server runs the bundled `fastcontext.cli` module in the same Python environment
and returns candidate file-line citations for the main agent to verify.

## One-Line LLM Agent Install Prompt

Ask an LLM agent:

> Install FastContext Agent Tools from `https://github.com/Jakevin/fastcontext-agent-tools`; its package installation includes Microsoft FastContext. Configure `python -m fastcontext_mcp` as a stdio MCP server with `BASE_URL`, `MODEL`, `API_KEY`, and `FASTCONTEXT_ALLOWED_ROOTS`, then enable `skills/fastcontext-explorer`.

Direct install command for Codex-style local skills:

```bash
git clone https://github.com/Jakevin/fastcontext-agent-tools && cd fastcontext-agent-tools && python -m pip install -e . && mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills" && ln -sfn "$(pwd)/skills/fastcontext-explorer" "${CODEX_HOME:-$HOME/.codex}/skills/fastcontext-explorer"
```

## Why This Exists

Microsoft FastContext separates repository exploration from code solving. The
upstream project describes a dedicated explorer that uses read-only `READ`,
`GLOB`, and `GREP` tools, issues parallel tool calls, and returns compact
`<final_answer>` citations. Microsoft reports Mini-SWE-Agent integration gains
of up to 5.5 score improvement and up to 60% main-agent token reduction.

Primary sources:

- Microsoft FastContext: <https://github.com/microsoft/fastcontext>
- Model card: <https://huggingface.co/microsoft/FastContext-1.0-4B-SFT>
- Paper: <https://arxiv.org/abs/2606.14066>

## Quick Install

```bash
git clone https://github.com/Jakevin/fastcontext-agent-tools
cd fastcontext-agent-tools
python -m pip install -e .
python -m fastcontext_mcp --print-health
```

If your Python scripts directory is on `PATH`, `fastcontext-mcp --print-health`
works too.

## Requirements

- Python 3.12+.
- An OpenAI-compatible endpoint serving a FastContext-compatible model.

Installing this package also installs Microsoft FastContext from the pinned
official source revision. No separate FastContext checkout or CLI installation
is required.

Endpoint environment:

```bash
export BASE_URL="http://127.0.0.1:30000/v1"
export MODEL="microsoft/FastContext-1.0-4B-SFT"
export API_KEY="your-api-key"
export FASTCONTEXT_ALLOWED_ROOTS="/path/to/repos"
```

`FASTCONTEXT_ALLOWED_ROOTS` is an `os.pathsep` separated allowlist. If unset,
the MCP server only allows repositories under the directory where the server was
started.

## MCP Configuration

Example stdio config:

```json
{
  "mcpServers": {
    "fastcontext": {
      "command": "python",
      "args": ["-m", "fastcontext_mcp"],
      "env": {
        "BASE_URL": "http://127.0.0.1:30000/v1",
        "MODEL": "microsoft/FastContext-1.0-4B-SFT",
        "API_KEY": "your-api-key",
        "FASTCONTEXT_ALLOWED_ROOTS": "/path/to/repos"
      }
    }
  }
}
```

Localized MCP guides:

- Traditional Chinese: [docs/mcp.zh-TW.md](docs/mcp.zh-TW.md)
- Japanese: [docs/mcp.ja.md](docs/mcp.ja.md)

## MCP Tools

### `fastcontext_health`

Checks whether the bundled `fastcontext.cli` module is importable and whether
the endpoint environment is set.

### `fastcontext_explore`

Runs FastContext against a repository and returns parsed citations plus raw
output.

```json
{
  "repo_path": "/path/to/repo",
  "query": "Locate the request validation logic for uploaded files",
  "max_turns": 6,
  "citation": true,
  "timeout_seconds": 300
}
```

### `fastcontext_explore_with_trace`

Same as `fastcontext_explore`, but saves a FastContext JSONL trajectory. Relative
`trajectory_path` values are resolved inside `repo_path`.

## Codex Skill

The bundled skill lives at:

```text
skills/fastcontext-explorer
```

Install by copying or symlinking that folder into your Codex skills directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$(pwd)/skills/fastcontext-explorer" "${CODEX_HOME:-$HOME/.codex}/skills/fastcontext-explorer"
```

Use the skill when a coding task requires repository localization before
editing. FastContext citations are candidate evidence; the main agent should
still read the cited files before changing code.

## Evaluation

![Evaluation summary](docs/assets/evaluation-summary.svg)

The graphic separates official benchmark data from this repository's local QA
checks. The local checks are not a FastContext before/after benchmark.

Official Microsoft FastContext data:

- Up to 5.5 Mini-SWE-Agent score improvement.
- Up to 60.3% fewer main-agent tokens.

Local integration QA:

- 7 local wrapper checks passed.
- Unit tests cover parser, runtime, server, and wrapper behavior.
- MCP stdio checks verify initialize, tool discovery, health response,
  citation parsing, trace output, and path allowlist rejection.

Local before/after FastContext impact data:

- Two local smoke benchmarks have been run so far.
- Latest aggregate run: MICE check-in localization used 7,039 direct tokens;
  FastContext missed the endpoint and required 10,910 tokens after verification
  plus fallback (+55.0%).
- Latest aggregate run: FanPlan Android FCM localization used 2,279 direct
  tokens; FastContext cited nonexistent paths and required 2,360 tokens after
  fallback (+3.6%).
- `FanPlan` is an anonymized local Android app fixture name used for reporting.
- Query-variant matrix on the MICE task: 3 query styles, 2 repeats each, 0/6
  successful ground-truth hits. The local endpoint exposed
  `fastcontext-tools-64k:latest`, not the official
  `microsoft/FastContext-1.0-4B-SFT` SGLang 262K setup.
- Endpoint readiness check: local `/v1/models` is not official-ready because it
  does not expose `microsoft/FastContext-1.0-4B-SFT`.
- Official serving preflight: local runtime is not official-ready because the
  project env lacks SGLang and no CUDA/NVIDIA runtime is available.
- Official benchmark readiness: upstream `microsoft/fastcontext` checkout,
  wheel build, safe benchmark CLI probes, and one-sample official dataset
  probes are present, but benchmark credentials and official serving readiness
  are still missing.
- These local smoke tests do not match Microsoft's benchmark harness and do not
  reproduce the official gains yet.

Wrapper evaluation is repeatable:

```bash
python -m evaluation.run_wrapper_eval
```

Current committed result:

- 7 checks total.
- 7 checks passed.
- 0 checks failed.

Artifacts:

- Evaluation notes: [docs/EVALUATION.md](docs/EVALUATION.md)
- Result JSON: [evaluation/wrapper-eval.json](evaluation/wrapper-eval.json)
- MICE before/after token smoke test: [evaluation/mice-checkin-before-after.json](evaluation/mice-checkin-before-after.json)
- FanPlan before/after token smoke test: [evaluation/fanplan-fcm-before-after.json](evaluation/fanplan-fcm-before-after.json)
- Latest aggregate before/after run: [evaluation/local-before-after-results.json](evaluation/local-before-after-results.json)
- Local endpoint readiness: [evaluation/local-endpoint-readiness.json](evaluation/local-endpoint-readiness.json)
- Official serving preflight: [evaluation/local-official-serving-preflight.json](evaluation/local-official-serving-preflight.json)
- Official benchmark readiness: [evaluation/local-official-benchmark-readiness.json](evaluation/local-official-benchmark-readiness.json)
- MICE query-variant matrix: [evaluation/local-query-matrix-results.json](evaluation/local-query-matrix-results.json)
- Matrix task spec: [evaluation/token-benchmark-matrix-tasks.json](evaluation/token-benchmark-matrix-tasks.json)
- Repeatable benchmark harness: [evaluation/token_benchmark.py](evaluation/token_benchmark.py)
- Endpoint readiness checker: [evaluation/endpoint_readiness.py](evaluation/endpoint_readiness.py)
- Official serving preflight checker: [evaluation/official_serving_preflight.py](evaluation/official_serving_preflight.py)
- Official benchmark readiness checker: [evaluation/official_benchmark_readiness.py](evaluation/official_benchmark_readiness.py)
- Full report: [docs/REPORT.md](docs/REPORT.md)

The local evaluation uses a fake `fastcontext.cli` package so it can validate
the MCP wrapper without a GPU or model endpoint. FastContext model-quality
claims are attributed to Microsoft FastContext and are not reproduced here.

## Development

Run tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Validate the bundled Codex skill:

```bash
python /path/to/skill-creator/scripts/quick_validate.py skills/fastcontext-explorer
```

Run the wrapper evaluation:

```bash
python -m evaluation.run_wrapper_eval
```

## Safety Notes

- The MCP server exposes no edit/write tools.
- `repo_path` must resolve under `FASTCONTEXT_ALLOWED_ROOTS`.
- Secrets are read from environment variables only.
- Trajectories are written only when requested.

## License

MIT
