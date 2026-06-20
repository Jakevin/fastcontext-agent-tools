from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FASTCONTEXT_MODULE = "fastcontext_mcp.fastcontext_cli"


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def reroot_under(value: str, root: Path) -> str:
    """Map a model-mangled path back under ``root``.

    Small / heavily-quantised models often truncate the workspace path in tool
    arguments and citations (e.g. ``/mnt/a/b/repo/x`` -> ``/repo/x``). This
    rewrites such a path to sit under the real workspace root by dropping a
    leading invented ``/<workspace-basename>`` segment, leaving already-valid
    in-workspace paths untouched. Gated by callers on FASTCONTEXT_REROOT_PATHS.
    """
    if not isinstance(value, str) or not value:
        return value
    root = root.resolve()
    try:
        if Path(value).resolve().is_relative_to(root):
            return value
    except (OSError, ValueError):
        pass
    parts = [p for p in value.replace("\\", "/").split("/") if p and p != "."]
    if parts and parts[0] == root.name:
        parts = parts[1:]
    return str(root.joinpath(*parts)) if parts else str(root)


class McpError(Exception):
    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass(frozen=True, slots=True)
class Citation:
    path: str
    start_line: int | None = None
    end_line: int | None = None


def parse_citations(text: str) -> list[Citation]:
    match = re.search(r"<final_answer>\s*(.*?)\s*</final_answer>", text, re.S)
    body = match.group(1) if match else text
    citations: list[Citation] = []
    pattern = re.compile(
        r"^\s*(?P<path>[^:\n]+):(?P<start>\d+)(?:-(?P<end>\d+))?"
        r"(?:\s+.*)?$"
    )
    for line in body.splitlines():
        candidate = line.strip().strip("`")
        if not candidate:
            continue
        parsed = pattern.match(candidate)
        if parsed is None:
            continue
        start = int(parsed.group("start"))
        end_text = parsed.group("end")
        citations.append(
            Citation(
                path=parsed.group("path"),
                start_line=start,
                end_line=int(end_text) if end_text else start,
            )
        )
    return citations


def _line_count(path: Path) -> int:
    with path.open(encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def validate_citations(repo: Path, citations: list[Citation]) -> tuple[list[dict[str, int | str]], list[str]]:
    valid: list[dict[str, int | str]] = []
    warnings: list[str] = []
    repo_root = repo.resolve()
    reroot = truthy(os.getenv("FASTCONTEXT_REROOT_PATHS"))
    for citation in citations:
        path_str = reroot_under(citation.path, repo_root) if reroot else citation.path
        candidate = Path(path_str).expanduser()
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        resolved = candidate.resolve()
        if not (resolved == repo_root or repo_root in resolved.parents):
            warnings.append(f"citation outside repo: {citation.path}")
            continue
        if not resolved.is_file():
            warnings.append(f"citation file does not exist: {citation.path}")
            continue
        start_line = citation.start_line
        end_line = citation.end_line
        if start_line is None or end_line is None or start_line < 1 or end_line < start_line:
            warnings.append(f"citation has invalid line range: {citation.path}")
            continue
        if end_line > _line_count(resolved):
            warnings.append(f"citation line range exceeds file length: {citation.path}")
            continue
        valid.append(
            {
                "path": str(resolved),
                "start_line": start_line,
                "end_line": end_line,
            }
        )
    return valid, warnings


def _env_present(name: str) -> bool:
    return bool(os.environ.get(name))


def _fastcontext_available() -> bool:
    try:
        return importlib.util.find_spec(FASTCONTEXT_MODULE) is not None
    except ModuleNotFoundError:
        return False


def allowed_roots() -> list[Path]:
    raw = os.environ.get("FASTCONTEXT_ALLOWED_ROOTS")
    values = (
        [item for item in raw.split(os.pathsep) if item]
        if raw
        else [os.getcwd()]
    )
    return [Path(value).expanduser().resolve() for value in values]


def resolve_repo_path(repo_path: str) -> Path:
    repo = Path(repo_path).expanduser().resolve()
    if not repo.exists():
        raise McpError(-32602, f"repo_path does not exist: {repo}")
    if not repo.is_dir():
        raise McpError(-32602, f"repo_path is not a directory: {repo}")

    roots = allowed_roots()
    if not any(repo == root or root in repo.parents for root in roots):
        roots_text = ", ".join(str(root) for root in roots)
        raise McpError(
            -32602,
            f"repo_path is outside FASTCONTEXT_ALLOWED_ROOTS: {repo}",
            {"allowed_roots": roots_text},
        )
    return repo


def build_fastcontext_prompt(repo: Path, query: str) -> str:
    return (
        f"Workspace root: {repo}\n"
        "Do not shorten this path in tool arguments. Use absolute paths under "
        "the workspace root for Read, Grep, and Glob.\n"
        "Only cite files and line ranges that appeared in successful tool "
        "results. If a path lookup fails, correct the path and search again. "
        "Prefer source files over generated output when both represent the "
        "same implementation. When several candidates match, prefer the "
        "workspace's primary source tree over nested sample, legacy, build, "
        "or generated application copies unless the user names that nested "
        "application explicitly. If the user names an explicit file path, "
        "inspect that exact path under the workspace root before broad search.\n\n"
        f"User query: {query}"
    )


def health() -> dict[str, Any]:
    available = _fastcontext_available()
    return {
        "ok": bool(available and _env_present("BASE_URL") and _env_present("MODEL")),
        "fastcontext_module": FASTCONTEXT_MODULE if available else None,
        "fastcontext_command": [sys.executable, "-m", FASTCONTEXT_MODULE],
        "env": {
            "BASE_URL": _env_present("BASE_URL"),
            "MODEL": _env_present("MODEL"),
            "API_KEY": _env_present("API_KEY"),
            "FASTCONTEXT_ALLOWED_ROOTS": [str(root) for root in allowed_roots()],
        },
        "notes": [
            "Microsoft FastContext is installed with this MCP package.",
            "Set BASE_URL and MODEL for the OpenAI-compatible endpoint.",
            "Set API_KEY when your endpoint requires authentication.",
        ],
    }


def run_fastcontext(args: dict[str, Any], *, force_trace: bool = False) -> dict[str, Any]:
    if not _fastcontext_available():
        raise McpError(
            -32000,
            "Bundled FastContext module is unavailable. Reinstall fastcontext-agent-tools.",
        )

    repo = resolve_repo_path(str(args.get("repo_path", "")))
    query = str(args.get("query", "")).strip()
    if not query:
        raise McpError(-32602, "query is required")

    max_turns = int(args.get("max_turns", 6))
    if max_turns < 1 or max_turns > 20:
        raise McpError(-32602, "max_turns must be between 1 and 20")

    timeout_seconds = int(args.get("timeout_seconds", 300))
    if timeout_seconds < 10 or timeout_seconds > 3600:
        raise McpError(-32602, "timeout_seconds must be between 10 and 3600")

    citation = bool(args.get("citation", True))
    effective_query = build_fastcontext_prompt(repo, query)
    command = [
        sys.executable,
        "-m",
        FASTCONTEXT_MODULE,
        "--query",
        effective_query,
        "--max-turns",
        str(max_turns),
    ]
    if citation:
        command.append("--citation")

    trajectory_path = args.get("trajectory_path")
    if force_trace or trajectory_path:
        if trajectory_path:
            traj = Path(str(trajectory_path)).expanduser()
            if not traj.is_absolute():
                traj = repo / traj
        else:
            traj = repo / ".fastcontext" / "trajectory.jsonl"
        traj.parent.mkdir(parents=True, exist_ok=True)
    else:
        traj = Path(tempfile.gettempdir()) / f"fastcontext-mcp-{os.getpid()}.jsonl"
    command.extend(["--traj", str(traj)])

    try:
        completed = subprocess.run(
            command,
            cwd=str(repo),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise McpError(
            -32001,
            f"fastcontext timed out after {timeout_seconds} seconds",
            {"stdout": exc.stdout, "stderr": exc.stderr},
        ) from exc

    output = completed.stdout.strip()
    citations, citation_warnings = validate_citations(repo, parse_citations(output))
    result = {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "repo_path": str(repo),
        "query": query,
        "citations": citations,
        "citation_warnings": citation_warnings,
        "raw_output": output,
        "stderr": completed.stderr.strip(),
        "trajectory_path": str(traj),
    }
    return result
