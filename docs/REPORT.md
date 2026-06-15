# FastContext Agent Tools Report

## Executive Summary

FastContext Agent Tools packages Microsoft FastContext for practical agent use:

- A zero-dependency Python MCP stdio server.
- A Codex skill that teaches an agent when to delegate repository exploration.
- English-first documentation plus Chinese and Japanese MCP setup guides.
- A repeatable wrapper evaluation with committed JSON and SVG evidence.

The project is intentionally narrow. It does not reimplement FastContext, download model weights, or modify repositories. It exposes the upstream `fastcontext` CLI as a read-only localization tool that returns file-line citations for the main coding agent to verify.

![Architecture](assets/architecture.svg)

## Background

FastContext separates repository exploration from code solving. Microsoft describes it as a lightweight exploration subagent that uses read-only `READ`, `GLOB`, and `GREP` tools, issues parallel tool calls, and returns compact file paths and line ranges for the main agent.

Primary sources:

- Microsoft FastContext repository: <https://github.com/microsoft/fastcontext>
- Hugging Face model card: <https://huggingface.co/microsoft/FastContext-1.0-4B-SFT>
- arXiv paper: <https://arxiv.org/abs/2606.14066>

The `microsoft/FastContext-1.0-4B-SFT` model card identifies the model as a 4B-parameter, BF16, MIT-licensed repository exploration model with up to 262K context. Microsoft reports Mini-SWE-Agent integration gains of up to 5.5 score and up to 60% main-agent token reduction.

## What Was Built

### MCP Server

The MCP server exposes:

- `fastcontext_health`: check the upstream CLI, endpoint variables, and allowed roots.
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
- GitHub Actions CI for unit tests and wrapper evaluation.

## Evaluation

![Evaluation summary](assets/evaluation-summary.svg)

Local wrapper evaluation was run on 2026-06-15 and committed as `evaluation/wrapper-eval.json`.

Results:

- 2 total checks.
- 2 passed.
- 0 failed.

The evaluation starts the MCP server over stdio, sends JSON-RPC framed requests, verifies the tool list, checks health behavior, runs an exploration call through a fake upstream `fastcontext` CLI, parses two citations, writes a trajectory, and verifies that repositories outside the allowlist are rejected.

This is not a FastContext model benchmark. Model-quality claims are sourced from Microsoft FastContext because this environment does not provide a GPU endpoint or the full SWE-bench benchmark setup.

## Installation Contract

For an LLM agent, the intended instruction is:

> Install FastContext Agent Tools from `https://github.com/Jakevin/fastcontext-agent-tools`, run `python -m pip install -e .`, configure `python -m fastcontext_mcp` as a stdio MCP server with `BASE_URL`, `MODEL`, `API_KEY`, and `FASTCONTEXT_ALLOWED_ROOTS`, then enable `skills/fastcontext-explorer`.

## Known Limitations

- The upstream `fastcontext` CLI must be installed separately.
- A FastContext-compatible OpenAI endpoint must already be running.
- This wrapper currently supports stdio MCP only.
- The package is not yet published to PyPI.
- The bundled skill is Codex-oriented, although the MCP server can be used by other MCP clients.

## Recommended Next Steps

- Publish a tagged release after the first external smoke test against a real FastContext endpoint.
- Add example configs for specific MCP clients once target clients are known.
- Consider a small CLI command to print ready-to-paste MCP config from current environment variables.
