from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.endpoint_readiness import JsonValue  # noqa: E402
from evaluation.official_serving_preflight import (  # noqa: E402
    EnvironmentProbe,
    evaluate_preflight,
)


class OfficialServingPreflightTests(unittest.TestCase):
    def test_ready_when_endpoint_and_runtime_match_official_path(self) -> None:
        environment = EnvironmentProbe(
            system="Linux",
            machine="x86_64",
            python_version="3.12.8",
            has_uv=True,
            has_nvidia_smi=True,
            has_sglang=True,
            has_torch=True,
            torch_cuda_available=True,
            torch_mps_available=False,
        )
        endpoint: dict[str, JsonValue] = {
            "ready": True,
            "observed_model_ids": ["microsoft/FastContext-1.0-4B-SFT"],
        }

        result = evaluate_preflight(environment, endpoint)

        self.assertTrue(result.ready)
        self.assertEqual(result.blockers, [])
        self.assertEqual(
            result.observed_model_ids,
            ["microsoft/FastContext-1.0-4B-SFT"],
        )

    def test_current_like_mac_mps_setup_reports_blockers(self) -> None:
        environment = EnvironmentProbe(
            system="Darwin",
            machine="arm64",
            python_version="3.12.8",
            has_uv=True,
            has_nvidia_smi=False,
            has_sglang=False,
            has_torch=True,
            torch_cuda_available=False,
            torch_mps_available=True,
        )
        endpoint: dict[str, JsonValue] = {
            "ready": False,
            "observed_model_ids": ["fastcontext-tools-64k:latest"],
        }

        result = evaluate_preflight(environment, endpoint)

        self.assertFalse(result.ready)
        endpoint_blocker = (
            "endpoint is not official-ready; /v1/models must expose "
            + "microsoft/FastContext-1.0-4B-SFT"
        )
        self.assertIn(
            endpoint_blocker,
            result.blockers,
        )
        self.assertIn(
            "SGLang is not installed in the current Python environment",
            result.blockers,
        )
        self.assertIn(
            "CUDA/NVIDIA runtime is not available for the documented serving path",
            result.blockers,
        )
        self.assertEqual(result.observed_model_ids, ["fastcontext-tools-64k:latest"])
        self.assertEqual(len(result.warnings), 1)


if __name__ == "__main__":
    _ = unittest.main()
