from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from fastcontext.agent.tool.grep import GrepTool

from fastcontext_mcp import fastcontext_cli
from fastcontext_mcp import runtime
from fastcontext_mcp.runtime import (
    health,
    parse_citations,
    resolve_repo_path,
    run_fastcontext,
    validate_citations,
)
from fastcontext_mcp.server import handle_request, read_message, write_message


import io


class _FakeStream:
    """Minimal stand-in for sys.stdin/sys.stdout exposing a binary .buffer."""

    def __init__(self, data: bytes = b"") -> None:
        self.buffer = io.BytesIO(data)


class ServerTests(unittest.TestCase):
    def test_parse_citations_from_final_answer(self) -> None:
        text = """
        notes
        <final_answer>
        src/router.py:42-58
        tests/test_router.py:101
        </final_answer>
        """
        citations = parse_citations(text)
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0].path, "src/router.py")
        self.assertEqual(citations[0].start_line, 42)
        self.assertEqual(citations[0].end_line, 58)
        self.assertEqual(citations[1].end_line, 101)

    def test_parse_citations_with_trailing_relevance_note(self) -> None:
        text = (
            "<final_answer>\n"
            "src/router.py:42-58 (router.post('/add') implementation)\n"
            "</final_answer>"
        )

        citations = parse_citations(text)

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].path, "src/router.py")
        self.assertEqual(citations[0].start_line, 42)
        self.assertEqual(citations[0].end_line, 58)

    def test_fastcontext_cli_uses_ripgrep_from_path(self) -> None:
        original_path = GrepTool._rg_path
        self.addCleanup(setattr, GrepTool, "_rg_path", original_path)

        with mock.patch(
            "fastcontext_mcp.fastcontext_cli.shutil.which",
            return_value="/opt/homebrew/bin/rg",
        ):
            fastcontext_cli.configure_ripgrep()

        self.assertEqual(GrepTool._rg_path, "/opt/homebrew/bin/rg")

    def test_validate_citations_normalizes_repo_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "app" / "router.py"
            source.parent.mkdir()
            source.write_text("one\ntwo\nthree\n", encoding="utf-8")
            citations = parse_citations("app/router.py:2-3")

            valid, warnings = validate_citations(Path(root), citations)

        self.assertEqual(warnings, [])
        self.assertEqual(valid[0]["path"], str(source.resolve()))
        self.assertEqual(valid[0]["start_line"], 2)
        self.assertEqual(valid[0]["end_line"], 3)

    def test_validate_citations_rejects_missing_or_outside_paths(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            outside_file = Path(outside) / "router.py"
            outside_file.write_text("one\n", encoding="utf-8")
            citations = parse_citations(
                f"{outside_file}:1\n"
                "missing.py:1\n"
            )

            valid, warnings = validate_citations(Path(root), citations)

        self.assertEqual(valid, [])
        self.assertEqual(len(warnings), 2)

    def test_repo_path_must_be_under_allowed_roots(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            with mock.patch.dict(os.environ, {"FASTCONTEXT_ALLOWED_ROOTS": root}):
                with self.assertRaises(Exception):
                    resolve_repo_path(other)

    def test_read_message_parses_newline_delimited_json(self) -> None:
        stdin = _FakeStream(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n')
        message = read_message(stdin)
        assert message is not None
        self.assertEqual(message["method"], "tools/list")

    def test_read_message_skips_blank_lines_and_signals_eof(self) -> None:
        stdin = _FakeStream(b'\n\n{"jsonrpc":"2.0","id":2}\n')
        first = read_message(stdin)
        assert first is not None
        self.assertEqual(first["id"], 2)
        self.assertIsNone(read_message(_FakeStream(b"")))

    def test_write_message_emits_single_newline_delimited_line(self) -> None:
        stdout = _FakeStream()
        write_message(stdout, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        out = stdout.buffer.getvalue()
        # MCP stdio: one message per line, no Content-Length framing, no
        # embedded newlines.
        self.assertNotIn(b"Content-Length", out)
        self.assertTrue(out.endswith(b"\n"))
        self.assertEqual(out.count(b"\n"), 1)
        self.assertEqual(json.loads(out.decode("utf-8"))["result"], {"ok": True})

    def test_read_tool_blocks_paths_outside_working_dir(self) -> None:
        import asyncio

        from fastcontext.agent.tool.read import ReadTool

        original_call = ReadTool.call
        self.addCleanup(setattr, ReadTool, "call", original_call)
        fastcontext_cli.configure_read_safety()

        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            inside = Path(root) / "a.py"
            inside.write_text("hello\n", encoding="utf-8")
            outside_file = Path(outside) / "secret.py"
            outside_file.write_text("secret\n", encoding="utf-8")

            def call(path: str) -> str:
                return asyncio.run(ReadTool().call(json.dumps({"path": path}), cwd=root))

            self.assertFalse(call(str(inside)).startswith("Permission error"))
            self.assertTrue(call(str(outside_file)).startswith("Permission error"))

    def test_reroot_under_strips_invented_basename(self) -> None:
        from fastcontext_mcp.runtime import reroot_under

        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            got = reroot_under(f"/{root.name}/src/x.py", root)
            self.assertEqual(got, str(root / "src" / "x.py"))

    def test_reroot_under_bare_basename_returns_root(self) -> None:
        from fastcontext_mcp.runtime import reroot_under

        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            self.assertEqual(reroot_under(f"/{root.name}", root), str(root))

    def test_reroot_under_leaves_valid_in_repo_path(self) -> None:
        from fastcontext_mcp.runtime import reroot_under

        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            inside = str(root / "a" / "b.py")
            self.assertEqual(reroot_under(inside, root), inside)

    def test_tools_list(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response is not None
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("fastcontext_health", names)
        self.assertIn("fastcontext_explore", names)

    def test_health_tool_returns_json_text(self) -> None:
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "fastcontext_health", "arguments": {}},
            }
        )
        assert response is not None
        text = response["result"]["content"][0]["text"]
        payload = json.loads(text)
        self.assertIn("fastcontext_module", payload)

    def test_health_uses_bundled_fastcontext_module_without_path_cli(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"BASE_URL": "https://example.test/v1", "MODEL": "fastcontext"},
            clear=True,
        ):
            with mock.patch.object(runtime, "_fastcontext_available", return_value=True):
                payload = health()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["fastcontext_module"], "fastcontext_mcp.fastcontext_cli")

    def test_run_fastcontext_uses_current_python_module(self) -> None:
        completed = CompletedProcess(
            args=[],
            returncode=0,
            stdout="<final_answer>\nsrc/app.py:1-3\n</final_answer>\n",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.dict(os.environ, {"FASTCONTEXT_ALLOWED_ROOTS": root}):
                with mock.patch.object(runtime, "_fastcontext_available", return_value=True):
                    with mock.patch(
                        "fastcontext_mcp.runtime.subprocess.run",
                        return_value=completed,
                    ) as run:
                        result = run_fastcontext(
                            {"repo_path": root, "query": "Locate app"},
                        )

        self.assertTrue(result["ok"])
        command = run.call_args.args[0]
        self.assertEqual(
            command[:3],
            [sys.executable, "-m", "fastcontext_mcp.fastcontext_cli"],
        )

    def test_run_fastcontext_augments_query_with_repo_root(self) -> None:
        completed = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.dict(os.environ, {"FASTCONTEXT_ALLOWED_ROOTS": root}):
                with mock.patch.object(runtime, "_fastcontext_available", return_value=True):
                    with mock.patch(
                        "fastcontext_mcp.runtime.subprocess.run",
                        return_value=completed,
                    ) as run:
                        run_fastcontext(
                            {"repo_path": root, "query": "Locate CanonProject"},
                        )

        command = run.call_args.args[0]
        query = command[command.index("--query") + 1]
        self.assertIn(f"Workspace root: {Path(root).resolve()}", query)
        self.assertIn("Do not shorten this path", query)
        self.assertIn("primary source tree", query)
        self.assertIn("explicit file path", query)
        self.assertIn("Locate CanonProject", query)

    def test_run_fastcontext_uses_temp_trajectory_without_trace(self) -> None:
        completed = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.dict(os.environ, {"FASTCONTEXT_ALLOWED_ROOTS": root}):
                with mock.patch.object(runtime, "_fastcontext_available", return_value=True):
                    with mock.patch(
                        "fastcontext_mcp.runtime.subprocess.run",
                        return_value=completed,
                    ) as run:
                        run_fastcontext(
                            {"repo_path": root, "query": "Locate app"},
                        )

        command = run.call_args.args[0]
        trajectory_path = Path(command[command.index("--traj") + 1])
        self.assertFalse(trajectory_path.is_relative_to(Path(root)))

    def test_relative_allowed_root_defaults_to_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            cwd = Path(root)
            child = cwd / "repo"
            child.mkdir()
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("os.getcwd", return_value=str(cwd)):
                    self.assertEqual(resolve_repo_path(str(child)), child.resolve())


if __name__ == "__main__":
    unittest.main()
