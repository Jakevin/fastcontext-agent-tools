from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastcontext_mcp.server import handle_request, parse_citations, resolve_repo_path


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

    def test_repo_path_must_be_under_allowed_roots(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            with mock.patch.dict(os.environ, {"FASTCONTEXT_ALLOWED_ROOTS": root}):
                with self.assertRaises(Exception):
                    resolve_repo_path(other)

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
        self.assertIn("fastcontext_cli", payload)

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

