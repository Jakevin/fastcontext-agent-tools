# FastContext Agent Tools Report

## Executive Summary

FastContext Agent Tools packages Microsoft FastContext for practical agent use:

- A Python MCP stdio server with Microsoft FastContext pinned as a runtime dependency.
- A Codex skill that teaches an agent when to delegate repository exploration.
- English-first documentation plus Chinese and Japanese MCP setup guides.
- Repeatable wrapper QA with committed JSON and SVG evidence.

The project is intentionally narrow. It does not reimplement FastContext, download model weights, or modify repositories. It installs the official FastContext package and runs `fastcontext.cli` with the MCP server's Python interpreter, returning file-line citations for the main coding agent to verify.

![Architecture](assets/architecture.svg)

## Background

FastContext separates repository exploration from code solving. Microsoft describes it as a lightweight exploration subagent that uses read-only `READ`, `GLOB`, and `GREP` tools, issues parallel tool calls, and returns compact file paths and line ranges for the main agent.

Primary sources:

- Microsoft FastContext repository: <https://github.com/microsoft/fastcontext>
- Hugging Face model card: <https://huggingface.co/microsoft/FastContext-1.0-4B-SFT>
- arXiv paper: <https://arxiv.org/abs/2606.14066>

The `microsoft/FastContext-1.0-4B-SFT` model card identifies the model as a 4B-parameter, BF16, MIT-licensed repository exploration model with up to 262K context. Microsoft reports Mini-SWE-Agent integration gains of up to 5.5 score and up to 60.3% main-agent token reduction.

## What Was Built

### MCP Server

The MCP server exposes:

- `fastcontext_health`: check the bundled FastContext module, endpoint variables, and allowed roots.
- `fastcontext_explore`: run FastContext and return parsed citations plus raw output.
- `fastcontext_explore_with_trace`: run FastContext and write a trajectory JSONL file.

Security posture:

- No write/edit tool is exposed.
- `repo_path` must resolve under `FASTCONTEXT_ALLOWED_ROOTS`.
- API keys stay in environment variables.
- Trajectories are written only when requested.

### Codex Skill

The bundled `fastcontext-explorer` skill instructs Codex to use FastContext for repository localization in unfamiliar or medium-to-large codebases. It also tells Codex to treat citations as candidate evidence and to read cited files before editing.

### Documentation

The repository includes:

- English README as the main GitHub entry point.
- Traditional Chinese MCP guide: `docs/mcp.zh-TW.md`.
- Japanese MCP guide: `docs/mcp.ja.md`.
- Evaluation notes: `docs/EVALUATION.md`.
- This report: `docs/REPORT.md`.
- GitHub Actions CI for unit tests and wrapper QA.

## Evaluation

![Evaluation summary](assets/evaluation-summary.svg)

Local wrapper QA was run on 2026-06-16 and committed as `evaluation/wrapper-eval.json`.

Results:

- 7 total checks.
- 7 passed.
- 0 failed.

The local QA starts the MCP server over stdio, sends JSON-RPC framed requests, and records separate checks for initialization, tool discovery, health behavior, citation parsing, trace output, and path allowlist rejection. The exploration calls use a fake `fastcontext.cli` package, so the result proves wrapper behavior without requiring a GPU or model endpoint.

This wrapper QA is not a FastContext before/after benchmark.

Separate local token smoke tests are committed under `evaluation/*before-after*.json`. In the latest aggregate run, the MICE check-in task used 7,039 estimated direct main-agent context tokens; FastContext missed `app/routers/logs.js`, and the correct fallback workflow used 10,910 tokens, or 55.0% more than direct exploration. In the FanPlan Android FCM task, direct exploration used 2,279 tokens; FastContext cited nonexistent paths, so the correct fallback workflow used 2,360 tokens, or 3.6% more than direct exploration.

The newer MICE query-variant matrix adds three query styles with two repeats each. All 6 FastContext runs missed `app/routers/logs.js`; one run timed out. The local endpoint exposed `fastcontext-tools-64k:latest`, which is not the official `microsoft/FastContext-1.0-4B-SFT` SGLang 262K configuration documented by Microsoft.

`evaluation/local-endpoint-readiness.json` makes that setup gap repeatable: the current local `/v1/models` response is `ready=false`, observes only `fastcontext-tools-64k:latest`, and is missing `microsoft/FastContext-1.0-4B-SFT`.

`evaluation/local-official-serving-preflight.json` extends that check to the local runtime. It is also `ready=false`: the project environment has no SGLang install and no CUDA/NVIDIA runtime, so it should not be compared directly with the official SGLang 262K serving setup.

`evaluation/local-official-benchmark-readiness.json` checks the official benchmark surfaces directly. It is `ready=false`, but the upstream checkout is now present at `936c0052f19b0936be51a24f8a76cfe2c47580e6`, the wheel builds, Docker is reachable, safe probes for the official benchmark CLIs pass, and one-sample probes can load the official Verified, Multilingual, and Pro datasets. The remaining blockers are placeholder benchmark credentials, no usable main-agent credential, and the official serving preflight still being false.

Model-quality and broader task-impact claims remain sourced from Microsoft FastContext because this repository has not re-run the full benchmark setup.

## Installation Contract

For an LLM agent, the intended instruction is:

> Install FastContext Agent Tools from `https://github.com/Jakevin/fastcontext-agent-tools`; its package installation includes Microsoft FastContext. Configure `python -m fastcontext_mcp` as a stdio MCP server with `BASE_URL`, `MODEL`, `API_KEY`, and `FASTCONTEXT_ALLOWED_ROOTS`, then enable `skills/fastcontext-explorer`.

## Known Limitations

- A FastContext-compatible OpenAI endpoint must already be running.
- This wrapper currently supports stdio MCP only.
- The package is not yet published to PyPI.
- The bundled skill is Codex-oriented, although the MCP server can be used by other MCP clients.

## Recommended Next Steps

- Publish a tagged release after the first external smoke test against a real FastContext endpoint.
- Add example configs for specific MCP clients once target clients are known.
- Consider a small CLI command to print ready-to-paste MCP config from current environment variables.
