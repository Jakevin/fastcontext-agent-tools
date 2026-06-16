from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, cast

REQUIRED_MODEL_IDS: Final = ["microsoft/FastContext-1.0-4B-SFT"]
OFFICIAL_SERVING_NOTES: Final = [
    "SGLang serving",
    "qwen tool-call parser",
    "262K context length",
]

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]


@dataclass(frozen=True, slots=True)
class EndpointReadiness:
    ready: bool
    observed_model_ids: list[str]
    required_model_ids: list[str]
    missing_required_model_ids: list[str]
    official_serving_notes: list[str]
    reasons: list[str]


def evaluate_models(payload: Mapping[str, JsonValue]) -> EndpointReadiness:
    model_ids = sorted(read_model_ids(payload))
    missing = [model_id for model_id in REQUIRED_MODEL_IDS if model_id not in model_ids]
    reasons: list[str] = []
    if missing:
        reasons.append("official FastContext model is not exposed by /v1/models")
    return EndpointReadiness(
        ready=not missing,
        observed_model_ids=model_ids,
        required_model_ids=list(REQUIRED_MODEL_IDS),
        missing_required_model_ids=missing,
        official_serving_notes=list(OFFICIAL_SERVING_NOTES),
        reasons=reasons,
    )


def read_model_ids(payload: Mapping[str, JsonValue]) -> set[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        return set()
    model_ids: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if isinstance(model_id, str):
            model_ids.add(model_id)
    return model_ids


def load_payload(path: Path) -> Mapping[str, JsonValue]:
    text = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")
    raw = cast(JsonValue, json.loads(text))
    if not isinstance(raw, dict):
        raise SystemExit("models payload must be a JSON object")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("models_json", type=Path)
    _ = parser.add_argument("--output", type=Path)
    args: argparse.Namespace = parser.parse_args()
    models_json = cast(Path, args.models_json)
    output = cast(Path | None, args.output)

    result = evaluate_models(load_payload(models_json))
    text = json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n"
    if output:
        _ = output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
