from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .runtime import (
    McpError,
    health,
    run_fastcontext,
)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "fastcontext-mcp"
SERVER_VERSION = "0.2.0"


def text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def json_text_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return text_result(json.dumps(payload, indent=2, sort_keys=True), is_error=is_error)


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "fastcontext_health",
            "description": "Check whether bundled FastContext and required endpoint environment variables are configured.",
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
    except Exception as exc:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK; pragma: no cover
        if request_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32603, "message": f"Internal error: {exc}"},
        }


def read_message(stdin: Any) -> dict[str, Any] | None:
    # MCP stdio transport: one JSON-RPC message per line, newline-delimited,
    # with no embedded newlines. (Not LSP-style Content-Length framing.)
    while True:
        line = stdin.buffer.readline()
        if line == b"":
            return None
        line = line.strip()
        if not line:
            continue
        return json.loads(line.decode("utf-8"))


def write_message(stdout: Any, message: dict[str, Any]) -> None:
    # Compact JSON keeps the message on a single line (no embedded newlines),
    # then a trailing newline delimits it per the MCP stdio spec.
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    stdout.buffer.write(body + b"\n")
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
