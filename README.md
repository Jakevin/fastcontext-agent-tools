# FastContext Agent Tools

MCP server and Codex skill for using Microsoft's FastContext as a repository
exploration subagent.

FastContext is designed to answer: "Which files and line ranges should the main
coding agent inspect?" This repo keeps that separation intact:

- `fastcontext-mcp` exposes read-only FastContext exploration as MCP tools.
- `skills/fastcontext-explorer` tells Codex when and how to use the explorer.
- The MCP server calls the official `fastcontext` CLI; it does not bundle model
  weights or run inference itself.

## Requirements

- Python 3.10+ for this MCP wrapper.
- Python 3.12+ for the upstream FastContext CLI.
- The upstream FastContext CLI installed from
  <https://github.com/microsoft/fastcontext>.
- An OpenAI-compatible endpoint serving a FastContext-compatible model.

Typical upstream setup:

```bash
git clone https://github.com/microsoft/fastcontext
cd fastcontext
uv tool install .
```

Endpoint environment:

```bash
export BASE_URL="https://your-endpoint.example/v1"
export MODEL="microsoft/FastContext-1.0-4B-SFT"
export API_KEY="your-api-key"
export FASTCONTEXT_ALLOWED_ROOTS="/path/to/repos"
```

`FASTCONTEXT_ALLOWED_ROOTS` is an `os.pathsep` separated allowlist. If unset,
the MCP server only allows repositories under the directory where the server was
started.

## Install Locally

From this repo:

```bash
python -m pip install -e .
fastcontext-mcp --print-health
```

If your Python scripts directory is not on `PATH`, use:

```bash
python -m fastcontext_mcp --print-health
```

## MCP Configuration

Example stdio config:

```json
{
  "mcpServers": {
    "fastcontext": {
      "command": "fastcontext-mcp",
      "env": {
        "BASE_URL": "https://your-endpoint.example/v1",
        "MODEL": "microsoft/FastContext-1.0-4B-SFT",
        "API_KEY": "your-api-key",
        "FASTCONTEXT_ALLOWED_ROOTS": "/path/to/repos"
      }
    }
  }
}
```

If `fastcontext-mcp` is not on `PATH`, set `command` to your Python executable
and `args` to `["-m", "fastcontext_mcp"]`.

## Tools

### `fastcontext_health`

Checks whether the wrapper can find the upstream `fastcontext` CLI and whether
the endpoint environment is set.

### `fastcontext_explore`

Input:

```json
{
  "repo_path": "/path/to/repo",
  "query": "Locate the request validation logic for uploaded files",
  "max_turns": 6,
  "citation": true,
  "timeout_seconds": 300
}
```

Output is JSON text containing `citations`, `raw_output`, `stderr`, and process
status. Citations are parsed from FastContext's `<final_answer>` block.

### `fastcontext_explore_with_trace`

Same as `fastcontext_explore`, but saves a FastContext JSONL trajectory. Relative
`trajectory_path` values are resolved inside `repo_path`.

## Codex Skill

The bundled skill lives at:

```text
skills/fastcontext-explorer
```

Install by copying or symlinking that folder into your Codex skills directory,
for example:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$(pwd)/skills/fastcontext-explorer" "${CODEX_HOME:-$HOME/.codex}/skills/fastcontext-explorer"
```

Use it when a coding task requires repository localization before editing.
FastContext citations should be treated as candidate evidence; the main agent
should still read the cited files before making changes.

## Development

Run tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Validate the bundled Codex skill:

```bash
python /path/to/skill-creator/scripts/quick_validate.py skills/fastcontext-explorer
```
