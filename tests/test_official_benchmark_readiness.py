from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.endpoint_readiness import JsonValue  # noqa: E402
from evaluation.official_benchmark_readiness import (  # noqa: E402
    ToolAvailability,
    evaluate_benchmark_readiness,
)


class OfficialBenchmarkReadinessTests(unittest.TestCase):
    def test_ready_when_official_checkout_env_tools_and_serving_are_ready(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as config_root:
            upstream = Path(root)
            for item in [
                "benchmark/evaluation/bench_mini_swe_agent.py",
                "benchmark/evaluation/configs/example.env",
                "benchmark/evaluation/run_score.py",
                "benchmark/swebench/bench_fastcontext.py",
                "benchmark/swebench/run.sh.sample",
                "prompts/gpt-multi-fc.yaml",
                "prompts/gpt-pro-fc.yaml",
                "third_party/mini-swe-agent",
                "dist/fastcontext-0.1.0-py3-none-any.whl",
            ]:
                path = upstream / item
                path.parent.mkdir(parents=True, exist_ok=True)
                if "." in path.name:
                    _ = path.write_text("placeholder\n", encoding="utf-8")
                else:
                    path.mkdir(exist_ok=True)
            config = Path(config_root) / ".env"
            _ = config.write_text(
                "\n".join(
                    [
                        "MAIN_MODEL=gpt-5",
                        "OPENAI_API_KEY=sk-test",
                        "FASTCONTEXT_MODEL=microsoft/FastContext-1.0-4B-SFT",
                        "FASTCONTEXT_API_KEY=sk-fastcontext",
                        "FASTCONTEXT_BASE_URL=https://endpoint.example/v1",
                    ]
                ),
                encoding="utf-8",
            )
            serving: dict[str, JsonValue] = {"ready": True}

            result = evaluate_benchmark_readiness(
                upstream_root=upstream,
                config_path=config,
                serving_preflight=serving,
                tools=ToolAvailability(uv=True, docker=True, docker_daemon=True),
            )

        self.assertTrue(result.ready)
        self.assertEqual(result.blockers, [])
        self.assertEqual(result.missing_upstream_files, [])
        self.assertIsNone(result.upstream_commit)

    def test_local_missing_official_inputs_reports_actionable_blockers(self) -> None:
        serving: dict[str, JsonValue] = {"ready": False}

        result = evaluate_benchmark_readiness(
            upstream_root=None,
            config_path=None,
            serving_preflight=serving,
            tools=ToolAvailability(uv=True, docker=False, docker_daemon=False),
        )

        self.assertFalse(result.ready)
        self.assertIn("official FastContext upstream checkout was not provided", result.blockers)
        self.assertIn("Docker is not available on PATH", result.blockers)
        self.assertIn("official benchmark .env config was not provided", result.blockers)
        self.assertIn("official serving preflight is not ready", result.blockers)
        self.assertIn(
            "benchmark/evaluation/bench_mini_swe_agent.py",
            result.missing_upstream_files,
        )

    def test_docker_binary_without_daemon_reports_blocker(self) -> None:
        serving: dict[str, JsonValue] = {"ready": True}

        result = evaluate_benchmark_readiness(
            upstream_root=None,
            config_path=None,
            serving_preflight=serving,
            tools=ToolAvailability(uv=True, docker=True, docker_daemon=False),
        )

        self.assertIn("Docker daemon is not reachable", result.blockers)


if __name__ == "__main__":
    _ = unittest.main()
