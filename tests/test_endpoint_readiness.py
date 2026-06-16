from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.endpoint_readiness import JsonValue, evaluate_models  # noqa: E402


class EndpointReadinessTests(unittest.TestCase):
    def test_official_model_is_ready(self) -> None:
        payload: dict[str, JsonValue] = {
            "object": "list",
            "data": [
                {
                    "id": "microsoft/FastContext-1.0-4B-SFT",
                    "object": "model",
                    "created": 1781537589,
                    "owned_by": "sglang",
                }
            ],
        }

        result = evaluate_models(payload)

        self.assertTrue(result.ready)
        self.assertEqual(result.observed_model_ids, ["microsoft/FastContext-1.0-4B-SFT"])
        self.assertEqual(result.missing_required_model_ids, [])

    def test_local_ollama_model_is_not_official_ready(self) -> None:
        payload: dict[str, JsonValue] = {
            "object": "list",
            "data": [
                {
                    "id": "fastcontext-tools-64k:latest",
                    "object": "model",
                    "created": 1781537589,
                    "owned_by": "library",
                }
            ],
        }

        result = evaluate_models(payload)

        self.assertFalse(result.ready)
        self.assertEqual(result.observed_model_ids, ["fastcontext-tools-64k:latest"])
        self.assertEqual(
            result.missing_required_model_ids,
            ["microsoft/FastContext-1.0-4B-SFT"],
        )
        self.assertIn(
            "official FastContext model is not exposed by /v1/models",
            result.reasons,
        )


if __name__ == "__main__":
    _ = unittest.main()
