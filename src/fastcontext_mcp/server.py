from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "fastcontext-mcp"
SERVER_VERSION = "0.1.0"


class McpError(Exception):
    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass(frozen=True)
class Citation:
    path: str
    start_line: int | None = None
    end_line: int | None = None


def parse_citations(text: str) -> list[Citation]:
    match = re.search(r"<final_answer>\s*(.*?)\s*</final_answer>", text, re.S)
    body = match.group(1) if match else text
    citations: list[Citation] = []
    pattern = re.compile(
        r"^\s*(?P<path>[^:\n]+):(?P<start>\d+)(?:-(?P<end>\d+))?\s*$"
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


def _env_present(name: str) -> bool:
    return bool(os.environ.get(name))


def allowed_roots() -> list[Path]:
    raw = os.environ.get("FASTCONTEXT_ALLOWED_ROOTS")
    if raw:
        values = [item for item in raw.split(os.pathsep) if item]
    else:
        values = [os.getcwd()]
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


def text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def json_text_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return text_result(json.dumps(payload, indent=2, sort_keys=True), is_error=is_error)


def health() -> dict[str, Any]:
    cli = shutil.which("fastcontext")
    return {
        "ok": bool(cli and _env_present("BASE_URL") and _env_present("MODEL")),
        "fastcontext_cli": cli,
        "env": {
            "BASE_URL": _env_present("BASE_URL"),
            "MODEL": _env_present("MODEL"),
            "API_KEY": _env_present("API_KEY"),
            "FASTCONTEXT_ALLOWED_ROOTS": [str(root) for root in allowed_roots()],
        },
        "notes": [
            "Install the Microsoft FastContext CLI separately.",
            "Set BASE_URL and MODEL for the OpenAI-compatible endpoint.",
            "Set API_KEY when your endpoint requires authentication.",
        ],
    }


def run_fastcontext(args: dict[str, Any], *, force_trace: bool = False) -> dict[str, Any]:
    cli = shutil.which("fastcontext")
    if cli is None:
        raise McpError(
            -32000,
            "fastcontext CLI not found on PATH. Install it from https://github.com/microsoft/fastcontext.",
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
    command = [cli, "--query", query, "--max-turns", str(max_turns)]
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
        command.extend(["--traj", str(traj)])
    else:
        traj = None

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
    citations = [
        {
            "path": citation_item.path,
            "start_line": citation_item.start_line,
            "end_line": citation_item.end_line,
        }
        for citation_item in parse_citations(output)
    ]
    result = {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "repo_path": str(repo),
        "query": query,
        "citations": citations,
        "raw_output": output,
        "stderr": completed.stderr.strip(),
    }
    if traj is not None:
        result["trajectory_path"] = str(traj)
    return result


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "fastcontext_health",
            "description": "Check whether the FastContext CLI and required endpoint environment variables are configured.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "fastcontext_explore",
            "description": "Run FastContext against a repository and return compact file-line citations for a natural-language code exploration query.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute or relative path to the repository to explore.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Specific exploration request naming the subsystem, behavior, error, or code path to locate.",
                    },
                    "max_turns": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 6,
                    },
                    "citation": {
                        "type": "boolean",
                        "default": True,
                        "description": "Return only FastContext's final citation block when supported by the CLI.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 10,
                        "maximum": 3600,
                        "default": 300,
                    },
                },
                "required": ["repo_path", "query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "fastcontext_explore_with_trace",
            "description": "Run FastContext and save its trajectory JSONL for debugging or prompt iteration.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "query": {"type": "string"},
                    "max_turns": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 6,
                    },
                    "trajectory_path": {
                        "type": "string",
                        "description": "Optional path for JSONL trajectory. Relative paths are resolved inside repo_path.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 10,
                        "maximum": 3600,
                        "default": 300,
                    },
                },
                "required": ["repo_path", "query"],
                "additionalProperties": False,
            },
        },
    ]


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    arguments = arguments or {}
    if name == "fastcontext_health":
        return json_text_result(health())
    if name == "fastcontext_explore":
        return json_text_result(run_fastcontext(arguments))
    if name == "fastcontext_explore_with_trace":
        return json_text_result(run_fastcontext(arguments, force_trace=True))
    raise McpError(-32601, f"Unknown tool: {name}")


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        elif method == "tools/list":
            result = {"tools": tools()}
        elif method == "tools/call":
            params = message.get("params") or {}
            result = call_tool(params.get("name", ""), params.get("arguments"))
        elif method == "ping":
            result = {}
        elif method in {"notifications/initialized", "notifications/cancelled"}:
            return None
        else:
            raise McpError(-32601, f"Method not found: {method}")
        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except McpError as exc:
        if request_id is None:
            return None
        error = {"code": exc.code, "message": exc.message}
        if exc.data is not None:
            error["data"] = exc.data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}
    except Exception as exc:  # pragma: no cover - defensive JSON-RPC boundary
        if request_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32603, "message": f"Internal error: {exc}"},
        }


def read_message(stdin: Any) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stdin.buffer.readline()
        if line == b"":
            return None
        if line in {b"\r\n", b"\n"}:
            break
        name, _, value = line.decode("ascii").partition(":")
        headers[name.lower()] = value.strip()

    length_text = headers.get("content-length")
    if length_text is None:
        raise McpError(-32700, "Missing Content-Length header")
    body = stdin.buffer.read(int(length_text))
    return json.loads(body.decode("utf-8"))


def write_message(stdout: Any, message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stdout.buffer.write(body)
    stdout.buffer.flush()


def serve() -> None:
    while True:
        incoming = read_message(sys.stdin)
        if incoming is None:
            return
        response = handle_request(incoming)
        if response is not None:
            write_message(sys.stdout, response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FastContext MCP stdio server")
    parser.add_argument(
        "--print-health",
        action="store_true",
        help="Print FastContext configuration health as JSON and exit.",
    )
    args = parser.parse_args(argv)
    if args.print_health:
        print(json.dumps(health(), indent=2, sort_keys=True))
        return 0
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

