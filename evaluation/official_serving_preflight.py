from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, cast

from evaluation.endpoint_readiness import JsonValue

OFFICIAL_MODEL_ID: Final = "microsoft/FastContext-1.0-4B-SFT"
OFFICIAL_REQUIREMENTS: Final = [
    "OpenAI-compatible /v1/chat/completions endpoint",
    "microsoft/FastContext-1.0-4B-SFT model exposed by /v1/models",
    "SGLang serving runtime",
    "qwen tool-call parser",
    "262K context length",
]


@dataclass(frozen=True, slots=True)
class EnvironmentProbe:
    system: str
    machine: str
    python_version: str
    has_uv: bool
    has_nvidia_smi: bool
    has_sglang: bool
    has_torch: bool
    torch_cuda_available: bool
    torch_mps_available: bool


@dataclass(frozen=True, slots=True)
class OfficialServingPreflight:
    ready: bool
    official_requirements: list[str]
    environment: EnvironmentProbe
    endpoint_ready: bool
    observed_model_ids: list[str]
    blockers: list[str]
    warnings: list[str]


def evaluate_preflight(
    environment: EnvironmentProbe,
    endpoint_readiness: dict[str, JsonValue] | None,
) -> OfficialServingPreflight:
    endpoint_ready = read_bool(endpoint_readiness, "ready") if endpoint_readiness else False
    observed_model_ids = read_string_list(endpoint_readiness, "observed_model_ids")

    blockers: list[str] = []
    warnings: list[str] = []
    if not endpoint_ready:
        blockers.append(
            f"endpoint is not official-ready; /v1/models must expose {OFFICIAL_MODEL_ID}",
        )
    if not environment.has_sglang:
        blockers.append("SGLang is not installed in the current Python environment")
    if not environment.has_nvidia_smi or not environment.torch_cuda_available:
        blockers.append("CUDA/NVIDIA runtime is not available for the documented serving path")
    if environment.torch_mps_available and not environment.torch_cuda_available:
        warnings.append(
            "Apple MPS is available, but this preflight treats it as separate "
            + "from the documented high-context SGLang/CUDA serving path",
        )
    if not environment.has_uv:
        warnings.append("uv is not installed or not on PATH")

    return OfficialServingPreflight(
        ready=not blockers,
        official_requirements=list(OFFICIAL_REQUIREMENTS),
        environment=environment,
        endpoint_ready=endpoint_ready,
        observed_model_ids=observed_model_ids,
        blockers=blockers,
        warnings=warnings,
    )


def collect_environment() -> EnvironmentProbe:
    torch_cuda_available = False
    torch_mps_available = False
    has_torch = importlib.util.find_spec("torch") is not None
    if has_torch:
        torch_cuda_available, torch_mps_available = query_torch_capabilities()

    return EnvironmentProbe(
        system=platform.system(),
        machine=platform.machine(),
        python_version=platform.python_version(),
        has_uv=shutil.which("uv") is not None,
        has_nvidia_smi=shutil.which("nvidia-smi") is not None,
        has_sglang=importlib.util.find_spec("sglang") is not None,
        has_torch=has_torch,
        torch_cuda_available=torch_cuda_available,
        torch_mps_available=torch_mps_available,
    )


def query_torch_capabilities() -> tuple[bool, bool]:
    code = (
        "import json, torch; "
        "print(json.dumps({"
        "'cuda': bool(torch.cuda.is_available()), "
        "'mps': bool(getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available())"
        "}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return False, False
    raw = cast(JsonValue, json.loads(completed.stdout))
    if not isinstance(raw, dict):
        return False, False
    return bool(raw.get("cuda")), bool(raw.get("mps"))


def load_endpoint_readiness(path: Path | None) -> dict[str, JsonValue] | None:
    if path is None:
        return None
    raw = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        raise SystemExit("endpoint readiness artifact must be a JSON object")
    return raw


def read_bool(payload: dict[str, JsonValue] | None, key: str) -> bool:
    if payload is None:
        return False
    value = payload.get(key)
    return value if isinstance(value, bool) else False


def read_string_list(payload: dict[str, JsonValue] | None, key: str) -> list[str]:
    if payload is None:
        return []
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def main() -> int:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument(
        "--endpoint-readiness",
        type=Path,
        default=Path("evaluation/local-endpoint-readiness.json"),
    )
    _ = parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/local-official-serving-preflight.json"),
    )
    args: argparse.Namespace = parser.parse_args()
    endpoint_readiness = cast(Path | None, args.endpoint_readiness)
    output = cast(Path, args.output)

    result = evaluate_preflight(
        collect_environment(),
        load_endpoint_readiness(endpoint_readiness),
    )
    text = json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n"
    _ = output.write_text(text, encoding="utf-8")
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
