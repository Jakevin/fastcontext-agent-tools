---
name: fastcontext-explorer
description: Use Microsoft FastContext as a read-only repository exploration subagent for coding tasks. Trigger when Codex needs to locate relevant files, symbols, call paths, tests, or line ranges before editing or answering in an unfamiliar or medium-to-large codebase; when broad grep/read exploration would consume significant context; or when a task asks where behavior is implemented. Do not use for tiny single-file tasks, already-known target files, or non-code questions.
---

# FastContext Explorer

## Workflow

1. Check availability first with the MCP tool `fastcontext_health`.
2. If health is usable, call `fastcontext_explore` with a specific query and the repository root.
3. Treat returned citations as candidate evidence, not proof. Read the cited files and line ranges yourself before editing or answering.
4. If citations are sparse, off-target, or missing, refine the query once with concrete terms from the task, error, subsystem, or nearby filenames.
5. For debugging poor searches, use `fastcontext_explore_with_trace` and inspect the saved trajectory.

## Query Shape

Write concise exploration requests that name behavior and intent:

```text
Find where OAuth access tokens are refreshed and which tests cover expired token handling.
```

Prefer subsystem and failure language over generic searches:

```text
Locate the request validation path that rejects oversized uploaded files.
```

Avoid asking FastContext to solve or patch:

```text
Fix the upload bug.
```

## MCP Tools

Use `fastcontext_explore`:

```json
{
  "repo_path": "/absolute/path/to/repo",
  "query": "Locate the request validation path that rejects oversized uploaded files.",
  "max_turns": 6,
  "citation": true
}
```

Use `fastcontext_explore_with_trace` when a trajectory is needed:

```json
{
  "repo_path": "/absolute/path/to/repo",
  "query": "Find where CLI config files are loaded and validated.",
  "max_turns": 8,
  "trajectory_path": ".fastcontext/trajectory.jsonl"
}
```

## Interpreting Results

FastContext normally returns a `<final_answer>` citation block such as:

```text
src/router.py:42-58
tests/test_router.py:101-119
```

After receiving citations:

- Read the cited ranges and surrounding context.
- Verify that the cited code actually controls the requested behavior.
- Search locally if the citations reveal a symbol but not all call sites.
- Keep FastContext outputs out of final answers unless the user asked about the exploration itself.

## Failure Handling

If `fastcontext_health` reports missing `fastcontext`, ask the user to install the upstream CLI or run without this skill.

If `BASE_URL` or `MODEL` is missing, ask the user to configure the FastContext endpoint.

If `repo_path` is rejected, use a path under `FASTCONTEXT_ALLOWED_ROOTS` or ask the user to update that allowlist.

If FastContext times out, retry once with a narrower query or lower `max_turns`.

