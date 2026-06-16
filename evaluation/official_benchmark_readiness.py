from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, cast

from evaluation.endpoint_readiness import JsonValue
from evaluation.official_benchmark_datasets import (
    DatasetProbe,
    collect_official_dataset_probes,
    dataset_probes_passed,
)
from evaluation.official_benchmark_env import EnvConfigCheck, check_env_config
from evaluation.official_benchmark_probes import (
    CommandProbe,
    collect_official_command_probes,
    probes_passed,
)
from evaluation.official_serving_preflight import read_bool

REQUIRED_UPSTREAM_FILES: Final = [
    "benchmark/evaluation/bench_mini_swe_agent.py",
    "benchmark/evaluation/configs/example.env",
    "benchmark/evaluation/run_score.py",
    "benchmark/swebench/bench_fastcontext.py",
    "benchmark/swebench/run.sh.sample",
    "prompts/gpt-multi-fc.yaml",
    "prompts/gpt-pro-fc.yaml",
    "third_party/mini-swe-agent",
    "dist/fastcontext-0.1.0-py3-none-any.whl",
]
OFFICIAL_COMMANDS: Final = [
    (
        "uv run --group benchmark python benchmark/evaluation/bench_mini_swe_agent.py "
        "--bench swebench-multilingual --agent-config prompts/gpt-multi-fc.yaml "
        "--config .env --output preds.json --logs-dir logs --workers 1"
    ),
    (
        "cd benchmark/swebench && uv run --group benchmark python bench_fastcontext.py "
        "--bench swebench-multilingual --experiment fastcontext-eval "
        "--prediction-file predictions.jsonl --local-mount-dir /absolute/path/to/output "
        "--num-threads 1"
    ),
    (
        "uv run --group benchmark python benchmark/evaluation/run_score.py "
        "swebench-multilingual result_finial_response.jsonl"
    ),
]


@dataclass(frozen=True, slots=True)
class ToolAvailability:
    uv: bool
    docker: bool
    docker_daemon: bool


@dataclass(frozen=True, slots=True)
class OfficialBenchmarkReadiness:
    ready: bool
    upstream_root: str | None
    upstream_commit: str | None
    required_upstream_files: list[str]
    missing_upstream_files: list[str]
    tools: ToolAvailability
    env_config: EnvConfigCheck
    official_serving_ready: bool
    command_probes: list[CommandProbe]
    dataset_probes: list[DatasetProbe]
    official_commands: list[str]
    blockers: list[str]
    warnings: list[str]


def evaluate_benchmark_readiness(
    upstream_root: Path | None,
    config_path: Path | None,
    serving_preflight: Mapping[str, JsonValue] | None,
    tools: ToolAvailability,
    command_probes: list[CommandProbe] | None = None,
    dataset_probes: list[DatasetProbe] | None = None,
) -> OfficialBenchmarkReadiness:
    missing_files = missing_required_files(upstream_root)
    env_config = check_env_config(config_path)
    serving_ready = read_bool(dict(serving_preflight) if serving_preflight else None, "ready")
    probes = list(command_probes or [])
    datasets = list(dataset_probes or [])
    blockers = collect_blockers(
        upstream_root=upstream_root,
        missing_files=missing_files,
        tools=tools,
        env_config=env_config,
        serving_ready=serving_ready,
        command_probes=probes,
        dataset_probes=datasets,
    )
    warnings = collect_warnings(upstream_root, probes, datasets)
    return OfficialBenchmarkReadiness(
        ready=not blockers,
        upstream_root=str(upstream_root.resolve()) if upstream_root else None,
        upstream_commit=read_upstream_commit(upstream_root),
        required_upstream_files=list(REQUIRED_UPSTREAM_FILES),
        missing_upstream_files=missing_files,
        tools=tools,
        env_config=env_config,
        official_serving_ready=serving_ready,
        command_probes=probes,
        dataset_probes=datasets,
        official_commands=list(OFFICIAL_COMMANDS),
        blockers=blockers,
        warnings=warnings,
    )


def missing_required_files(upstream_root: Path | None) -> list[str]:
    if upstream_root is None:
        return list(REQUIRED_UPSTREAM_FILES)
    return [item for item in REQUIRED_UPSTREAM_FILES if not (upstream_root / item).exists()]


def read_upstream_commit(upstream_root: Path | None) -> str | None:
    if upstream_root is None or not (upstream_root / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(upstream_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def collect_blockers(
    *,
    upstream_root: Path | None,
    missing_files: list[str],
    tools: ToolAvailability,
    env_config: EnvConfigCheck,
    serving_ready: bool,
    command_probes: list[CommandProbe],
    dataset_probes: list[DatasetProbe],
) -> list[str]:
    blockers: list[str] = []
    if upstream_root is None:
        blockers.append("official FastContext upstream checkout was not provided")
    elif missing_files:
        blockers.append("official upstream checkout is missing required benchmark files or built wheel")
    if not tools.uv:
        blockers.append("uv is not available on PATH")
    if not tools.docker:
        blockers.append("Docker is not available on PATH")
    elif not tools.docker_daemon:
        blockers.append("Docker daemon is not reachable")
    if env_config.config_path is None:
        blockers.append("official benchmark .env config was not provided")
    if env_config.missing_keys:
        blockers.append("official benchmark .env is missing required FastContext/main model keys")
    if env_config.placeholder_keys:
        blockers.append("official benchmark .env still contains placeholder credential values")
    if not env_config.has_main_credential:
        blockers.append("official benchmark .env has no usable main-agent credential")
    if not serving_ready:
        blockers.append("official serving preflight is not ready")
    if command_probes and not probes_passed(command_probes):
        blockers.append("official benchmark CLI smoke probes failed")
    if dataset_probes and not dataset_probes_passed(dataset_probes):
        blockers.append("official benchmark dataset probes failed")
    return blockers


def collect_warnings(
    upstream_root: Path | None,
    command_probes: list[CommandProbe],
    dataset_probes: list[DatasetProbe],
) -> list[str]:
    if upstream_root is None:
        return ["Run against a clone of https://github.com/microsoft/fastcontext after uv build."]
    warnings: list[str] = []
    if not command_probes:
        warnings.append("Official benchmark CLI smoke probes were not run.")
    if not dataset_probes:
        warnings.append("Official benchmark dataset probes were not run.")
    return warnings


def collect_tools() -> ToolAvailability:
    has_docker = shutil.which("docker") is not None
    return ToolAvailability(
        uv=shutil.which("uv") is not None,
        docker=has_docker,
        docker_daemon=has_docker and docker_daemon_available(),
    )


def docker_daemon_available() -> bool:
    try:
        completed = subprocess.run(
            ["docker", "info"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def load_json_object(path: Path | None) -> Mapping[str, JsonValue] | None:
    if path is None or not path.exists():
        return None
    raw = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        raise SystemExit("serving preflight artifact must be a JSON object")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--upstream-root", type=Path)
    _ = parser.add_argument("--config", type=Path)
    _ = parser.add_argument(
        "--serving-preflight",
        type=Path,
        default=Path("evaluation/local-official-serving-preflight.json"),
    )
    _ = parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/local-official-benchmark-readiness.json"),
    )
    _ = parser.add_argument(
        "--probe-commands",
        action="store_true",
        help="Run safe official benchmark CLI smoke probes and record their output excerpts.",
    )
    _ = parser.add_argument(
        "--probe-datasets",
        action="store_true",
        help="Load one sample from each official benchmark dataset and record access evidence.",
    )
    args: argparse.Namespace = parser.parse_args()
    upstream_root = cast(Path | None, args.upstream_root)
    config_path = cast(Path | None, args.config)
    serving_preflight = cast(Path | None, args.serving_preflight)
    output = cast(Path, args.output)
    probe_commands = cast(bool, args.probe_commands)
    probe_datasets = cast(bool, args.probe_datasets)

    result = evaluate_benchmark_readiness(
        upstream_root=upstream_root,
        config_path=config_path,
        serving_preflight=load_json_object(serving_preflight),
        tools=collect_tools(),
        command_probes=collect_official_command_probes(upstream_root) if probe_commands else None,
        dataset_probes=collect_official_dataset_probes(upstream_root) if probe_datasets else None,
    )
    text = json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n"
    _ = output.write_text(text, encoding="utf-8")
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
