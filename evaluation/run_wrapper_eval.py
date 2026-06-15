from __future__ import annotations

import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "evaluation" / "wrapper-eval.json"
SVG_PATH = ROOT / "docs" / "assets" / "evaluation-summary.svg"


def run_command(command: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "returncode": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def write_fake_fastcontext(bin_dir: Path) -> Path:
    fake_cli = bin_dir / "fastcontext"
    fake_cli.write_text(
        """#!/usr/bin/env python3
import argparse
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
print("src/app.py:1-3")
print("tests/test_app.py:5-7")
print("</final_answer>")
""",
        encoding="utf-8",
    )
    fake_cli.chmod(fake_cli.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return fake_cli


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
            raise RuntimeError("MCP server closed stdout while waiting for a response")
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


def run_mcp_smoke() -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as temp_root_text:
        temp_root = Path(temp_root_text)
        repo = temp_root / "sample-repo"
        (repo / "src").mkdir(parents=True)
        (repo / "tests").mkdir()
        (repo / "src" / "app.py").write_text("def handler():\n    return 'ok'\n", encoding="utf-8")
        (repo / "tests" / "test_app.py").write_text("def test_handler():\n    assert True\n", encoding="utf-8")

        bin_dir = temp_root / "bin"
        bin_dir.mkdir()
        fake_cli = write_fake_fastcontext(bin_dir)

        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(ROOT / "src"),
                "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                "BASE_URL": "http://127.0.0.1:30000/v1",
                "MODEL": "microsoft/FastContext-1.0-4B-SFT",
                "API_KEY": "eval-key",
                "FASTCONTEXT_ALLOWED_ROOTS": str(temp_root),
            }
        )

        process = subprocess.Popen(
            [sys.executable, "-m", "fastcontext_mcp"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            initialize = call_mcp(process, "initialize", {"clientInfo": {"name": "wrapper-eval"}}, 1)
            tools_list = call_mcp(process, "tools/list", request_id=2)
            health = call_mcp(
                process,
                "tools/call",
                {"name": "fastcontext_health", "arguments": {}},
                3,
            )
            explore = call_mcp(
                process,
                "tools/call",
                {
                    "name": "fastcontext_explore",
                    "arguments": {
                        "repo_path": str(repo),
                        "query": "Locate handler and its tests",
                        "max_turns": 4,
                        "citation": True,
                    },
                },
                4,
            )
            trace = call_mcp(
                process,
                "tools/call",
                {
                    "name": "fastcontext_explore_with_trace",
                    "arguments": {
                        "repo_path": str(repo),
                        "query": "Locate handler and write trajectory",
                        "max_turns": 4,
                        "trajectory_path": ".fastcontext/eval.jsonl",
                    },
                },
                5,
            )

            with tempfile.TemporaryDirectory() as outside:
                rejected = call_mcp(
                    process,
                    "tools/call",
                    {
                        "name": "fastcontext_explore",
                        "arguments": {
                            "repo_path": outside,
                            "query": "This should be rejected",
                        },
                    },
                    6,
                )

            assert "result" in initialize
            tool_names = {tool["name"] for tool in tools_list["result"]["tools"]}
            assert {"fastcontext_health", "fastcontext_explore", "fastcontext_explore_with_trace"} <= tool_names

            health_payload = json.loads(health["result"]["content"][0]["text"])
            assert health_payload["ok"] is True
            assert Path(health_payload["fastcontext_cli"]) == fake_cli

            explore_payload = json.loads(explore["result"]["content"][0]["text"])
            assert explore_payload["ok"] is True
            assert len(explore_payload["citations"]) == 2

            trace_payload = json.loads(trace["result"]["content"][0]["text"])
            assert trace_payload["ok"] is True
            assert Path(trace_payload["trajectory_path"]).exists()

            assert rejected["error"]["code"] == -32602

            return {
                "status": "pass",
                "duration_seconds": round(time.perf_counter() - started, 3),
                "tools": sorted(tool_names),
                "citations_returned": len(explore_payload["citations"]),
                "trace_created": True,
                "path_guard_rejected_outside_repo": True,
            }
        except Exception as exc:
            return {
                "status": "fail",
                "duration_seconds": round(time.perf_counter() - started, 3),
                "error": str(exc),
            }
        finally:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def render_svg(summary: dict[str, Any]) -> str:
    checks = summary["checks"]
    rows = []
    width = 860
    y = 122
    for check in checks:
        passed = check["status"] == "pass"
        color = "#1f9d55" if passed else "#c43b3b"
        label = check["name"].replace("_", " ").title()
        duration = check.get("duration_seconds", 0)
        bar_width = max(28, min(460, int(float(duration) * 120) + 44))
        rows.append(
            f'<text x="44" y="{y}" class="label">{label}</text>'
            f'<rect x="286" y="{y - 17}" width="{bar_width}" height="24" rx="4" fill="{color}"/>'
            f'<text x="{304 + bar_width}" y="{y}" class="value">{check["status"].upper()} · {duration}s</text>'
        )
        y += 48
    generated = summary["generated_at"].replace("T", " ").replace("+00:00", " UTC")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="360" viewBox="0 0 {width} 360" role="img" aria-labelledby="title desc">
  <title id="title">FastContext Agent Tools evaluation summary</title>
  <desc id="desc">Wrapper evaluation showing unit tests, MCP smoke test, and generated documentation artifacts.</desc>
  <style>
    .title {{ font: 700 28px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #17202a; }}
    .subtitle {{ font: 400 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #52616b; }}
    .label {{ font: 600 15px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #1f2933; }}
    .value {{ font: 600 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #1f2933; }}
    .note {{ font: 400 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #52616b; }}
  </style>
  <rect width="860" height="360" fill="#f8faf9"/>
  <rect x="24" y="24" width="812" height="312" rx="8" fill="#ffffff" stroke="#d6dde2"/>
  <text x="44" y="68" class="title">FastContext MCP Wrapper Evaluation</text>
  <text x="44" y="94" class="subtitle">Generated {generated}</text>
  {''.join(rows)}
  <text x="44" y="306" class="note">Scope: wrapper protocol, citation parsing, trace output, and path safety.</text>
  <text x="44" y="326" class="note">Model-quality results are cited separately from Microsoft FastContext.</text>
</svg>
"""


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    unit = run_command([sys.executable, "-m", "unittest", "discover", "-s", "tests"], env=env)
    mcp = run_mcp_smoke()

    checks = [
        {"name": "unit_tests", **unit},
        {"name": "mcp_stdio_smoke", **mcp},
    ]
    passed = sum(1 for check in checks if check["status"] == "pass")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": "fastcontext-agent-tools",
        "scope": "MCP wrapper and bundled Codex skill",
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "summary": {
            "checks_total": len(checks),
            "checks_passed": passed,
            "checks_failed": len(checks) - passed,
        },
        "checks": checks,
        "limitations": [
            "This evaluation uses a fake fastcontext CLI to verify wrapper behavior without a GPU or model endpoint.",
            "FastContext model-quality claims are not reproduced here; see the Microsoft FastContext paper and model card.",
        ],
    }

    RESULT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    SVG_PATH.write_text(render_svg(summary), encoding="utf-8")
    print(json.dumps(summary["summary"], indent=2))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
