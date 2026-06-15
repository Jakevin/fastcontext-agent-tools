# Evaluation

This project has two evaluation layers:

1. Wrapper evaluation for this MCP server and Codex skill package.
2. Model-quality evidence from the upstream Microsoft FastContext project.

![Evaluation summary](assets/evaluation-summary.svg)

## Local Wrapper Evaluation

The repeatable local check is:

```bash
python evaluation/run_wrapper_eval.py
```

Last checked result committed in `evaluation/wrapper-eval.json`:

| Check | Result | Evidence |
| --- | --- | --- |
| Unit tests | PASS | 5 tests covering citation parsing, tool listing, health response, and path allowlist behavior |
| MCP stdio smoke | PASS | Starts the server, sends JSON-RPC framed requests, verifies three tools, parses two citations, writes a trajectory, and rejects a repo outside the allowlist |

Scope:

- MCP protocol basics: `initialize`, `tools/list`, and `tools/call`.
- Tool contract: `fastcontext_health`, `fastcontext_explore`, and `fastcontext_explore_with_trace`.
- Citation parsing from a FastContext-style `<final_answer>` block.
- Read-safety guard through `FASTCONTEXT_ALLOWED_ROOTS`.
- Trace file creation when `trajectory_path` is supplied.

Limitation:

- This wrapper evaluation uses a fake `fastcontext` CLI so it can run without a GPU or model endpoint.
- It proves the integration wrapper, not FastContext model quality.

## Upstream Model Evidence

The model-quality claims should be attributed to Microsoft FastContext:

- Project: <https://github.com/microsoft/fastcontext>
- Model card: <https://huggingface.co/microsoft/FastContext-1.0-4B-SFT>
- Paper: <https://arxiv.org/abs/2606.14066>

Microsoft reports that FastContext is a lightweight repository-exploration subagent using read-only `READ`, `GLOB`, and `GREP` tools, returning compact file-line citations. Their reported Mini-SWE-Agent integration results include up to 5.5 score improvement and up to 60% main-agent token reduction across SWE-bench Multilingual, SWE-bench Pro, and SWE-QA.

This repository does not re-run those benchmarks. Reproducing them requires the upstream benchmark harness, task datasets, and configured main-agent and FastContext model endpoints.

