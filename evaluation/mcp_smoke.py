from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def make_check(name: str, passed: bool, evidence: str, **details: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "evidence": evidence,
        **details,
    }


def write_fake_fastcontext(package_root: Path) -> None:
    package_dir = package_root / "fastcontext"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    fake_cli = package_dir / "cli.py"
    fake_cli.write_text(
        """import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--query", required=True)
parser.add_argument("--max-turns", default="6")
parser.add_argument("--citation", action="store_true")
parser.add_argument("--traj")
args = parser.parse_args()

if args.traj:
    traj = Path(args.traj)
    traj.parent.mkdir(parents=True, exist_ok=True)
    traj.write_text(json.dumps({
        "query": args.query,
        "max_turns": int(args.max_turns),
        "event": "fake-fastcontext-eval"
    }) + "\\n")

print("<final_answer>")
print("src/app.py:1-2")
print("tests/test_app.py:1-2")
print("</final_answer>")
""",
        encoding="utf-8",
    )


def send_message(process: subprocess.Popen[bytes], message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    frame = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    assert process.stdin is not None
    process.stdin.write(frame)
    process.stdin.flush()


def read_message(process: subprocess.Popen[bytes]) -> dict[str, Any]:
    assert process.stdout is not None
    headers: dict[str, str] = {}
    while True:
        line = process.stdout.readline()
        if line == b"":
            raise EOFError("MCP server closed stdout while waiting for a response")
        if line in {b"\r\n", b"\n"}:
            break
        name, _, value = line.decode("ascii").partition(":")
        headers[name.lower()] = value.strip()
    length = int(headers["content-length"])
    return json.loads(process.stdout.read(length).decode("utf-8"))


def call_mcp(process: subprocess.Popen[bytes], method: str, params: dict[str, Any] | None = None, request_id: int = 1) -> dict[str, Any]:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    send_message(process, message)
    return read_message(process)


def run_mcp_smoke() -> list[dict[str, Any]]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as temp_root_text:
        temp_root = Path(temp_root_text)
        repo = temp_root / "sample-repo"
        (repo / "src").mkdir(parents=True)
        (repo / "tests").mkdir()
        (repo / "src" / "app.py").write_text("def handler():\n    return 'ok'\n", encoding="utf-8")
        (repo / "tests" / "test_app.py").write_text("def test_handler():\n    assert True\n", encoding="utf-8")
        write_fake_fastcontext(temp_root / "fake-site")

        process = subprocess.Popen(
            [sys.executable, "-m", "fastcontext_mcp"],
            cwd=ROOT,
            env=smoke_env(temp_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            return run_mcp_checks(process, repo, started)
        except (AssertionError, EOFError, json.JSONDecodeError, KeyError, OSError, TypeError, ValueError) as exc:
            return [
                {
                    "name": "mcp_stdio_smoke",
                    "status": "fail",
                    "duration_seconds": round(time.perf_counter() - started, 3),
                    "evidence": "The MCP stdio smoke test failed before granular checks completed.",
                    "error": str(exc),
                }
            ]
        finally:
            stop_process(process)


def smoke_env(temp_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": os.pathsep.join([str(temp_root / "fake-site"), str(ROOT / "src")]),
            "BASE_URL": "http://127.0.0.1:30000/v1",
            "MODEL": "microsoft/FastContext-1.0-4B-SFT",
            "API_KEY": "eval-key",
            "FASTCONTEXT_ALLOWED_ROOTS": str(temp_root),
        }
    )
    return env


def run_mcp_checks(process: subprocess.Popen[bytes], repo: Path, started: float) -> list[dict[str, Any]]:
    initialize = call_mcp(process, "initialize", {"clientInfo": {"name": "wrapper-eval"}}, 1)
    tools_list = call_mcp(process, "tools/list", request_id=2)
    health = call_mcp(process, "tools/call", {"name": "fastcontext_health", "arguments": {}}, 3)
    explore = call_mcp(
        process,
        "tools/call",
        {"name": "fastcontext_explore", "arguments": {"repo_path": str(repo), "query": "Locate handler and its tests", "max_turns": 4, "citation": True}},
        4,
    )
    trace = call_mcp(
        process,
        "tools/call",
        {"name": "fastcontext_explore_with_trace", "arguments": {"repo_path": str(repo), "query": "Locate handler and write trajectory", "max_turns": 4, "trajectory_path": ".fastcontext/eval.jsonl"}},
        5,
    )
    with tempfile.TemporaryDirectory() as outside:
        rejected = call_mcp(process, "tools/call", {"name": "fastcontext_explore", "arguments": {"repo_path": outside, "query": "This should be rejected"}}, 6)
    return build_check_results(initialize, tools_list, health, explore, trace, rejected, started)


def build_check_results(
    initialize: dict[str, Any],
    tools_list: dict[str, Any],
    health: dict[str, Any],
    explore: dict[str, Any],
    trace: dict[str, Any],
    rejected: dict[str, Any],
    started: float,
) -> list[dict[str, Any]]:
    tool_names = {tool["name"] for tool in tools_list["result"]["tools"]}
    required_tools = {"fastcontext_health", "fastcontext_explore", "fastcontext_explore_with_trace"}
    health_payload = json.loads(health["result"]["content"][0]["text"])
    expected_command = [sys.executable, "-m", "fastcontext_mcp.fastcontext_cli"]
    explore_payload = json.loads(explore["result"]["content"][0]["text"])
    trace_payload = json.loads(trace["result"]["content"][0]["text"])
    trace_path = Path(trace_payload["trajectory_path"])
    citations = explore_payload["citations"]

    return [
        make_check("mcp_initialize", "result" in initialize, "JSON-RPC initialize returned a result.", duration_seconds=round(time.perf_counter() - started, 3)),
        make_check("mcp_tool_discovery", required_tools <= tool_names, "tools/list exposed the three FastContext MCP tools.", tools=sorted(tool_names)),
        make_check("health_uses_bundled_cli", health_matches(health_payload, expected_command), "fastcontext_health points at the bundled wrapper module.", command=expected_command),
        make_check("citation_parsing", explore_payload["ok"] is True and len(citations) == 2, "fastcontext_explore parsed two FastContext-style file-line citations.", citations=citations),
        make_check("trace_output", trace_payload["ok"] is True and trace_path.exists(), "fastcontext_explore_with_trace wrote a trajectory under the repo.", trajectory_path=str(trace_path)),
        make_check("path_allowlist_guard", rejected["error"]["code"] == -32602, "A repo outside FASTCONTEXT_ALLOWED_ROOTS was rejected.", error=rejected.get("error")),
    ]


def health_matches(payload: dict[str, Any], expected_command: list[str]) -> bool:
    return (
        payload["ok"] is True
        and payload["fastcontext_module"] == "fastcontext_mcp.fastcontext_cli"
        and payload["fastcontext_command"] == expected_command
    )


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.stdin is not None:
        process.stdin.close()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
