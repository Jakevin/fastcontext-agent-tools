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
REQUIRED_ENV_KEYS: Final = [
    "MAIN_MODEL",
    "FASTCONTEXT_MODEL",
    "FASTCONTEXT_API_KEY",
    "FASTCONTEXT_BASE_URL",
]
MAIN_CREDENTIAL_KEYS: Final = ["AZURE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
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
class EnvConfigCheck:
    config_path: str | None
    required_keys: list[str]
    main_credential_options: list[str]
    missing_keys: list[str]
    placeholder_keys: list[str]
    has_main_credential: bool


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
    official_commands: list[str]
    blockers: list[str]
    warnings: list[str]


def evaluate_benchmark_readiness(
    upstream_root: Path | None,
    config_path: Path | None,
    serving_preflight: Mapping[str, JsonValue] | None,
    tools: ToolAvailability,
) -> OfficialBenchmarkReadiness:
    missing_files = missing_required_files(upstream_root)
    env_config = check_env_config(config_path)
    serving_ready = read_bool(dict(serving_preflight) if serving_preflight else None, "ready")
    blockers = collect_blockers(
        upstream_root=upstream_root,
        missing_files=missing_files,
        tools=tools,
        env_config=env_config,
        serving_ready=serving_ready,
    )
    warnings = collect_warnings(upstream_root)
    return OfficialBenchmarkReadiness(
        ready=not blockers,
        upstream_root=str(upstream_root.resolve()) if upstream_root else None,
        upstream_commit=read_upstream_commit(upstream_root),
        required_upstream_files=list(REQUIRED_UPSTREAM_FILES),
        missing_upstream_files=missing_files,
        tools=tools,
        env_config=env_config,
        official_serving_ready=serving_ready,
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


def check_env_config(config_path: Path | None) -> EnvConfigCheck:
    values = read_env_file(config_path)
    missing = [key for key in REQUIRED_ENV_KEYS if not values.get(key)]
    placeholder = [
        key
        for key, value in values.items()
        if is_placeholder(value) and key in [*REQUIRED_ENV_KEYS, *MAIN_CREDENTIAL_KEYS]
    ]
    has_main_credential = any(values.get(key) and not is_placeholder(values[key]) for key in MAIN_CREDENTIAL_KEYS)
    return EnvConfigCheck(
        config_path=str(config_path.resolve()) if config_path else None,
        required_keys=list(REQUIRED_ENV_KEYS),
        main_credential_options=list(MAIN_CREDENTIAL_KEYS),
        missing_keys=missing,
        placeholder_keys=sorted(placeholder),
        has_main_credential=has_main_credential,
    )


def read_env_file(config_path: Path | None) -> dict[str, str]:
    if config_path is None or not config_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized.startswith("your-") or "your-" in normalized


def collect_blockers(
    *,
    upstream_root: Path | None,
    missing_files: list[str],
    tools: ToolAvailability,
    env_config: EnvConfigCheck,
    serving_ready: bool,
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
    return blockers


def collect_warnings(upstream_root: Path | None) -> list[str]:
    if upstream_root is None:
        return ["Run against a clone of https://github.com/microsoft/fastcontext after uv build."]
    return []


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
    args: argparse.Namespace = parser.parse_args()
    upstream_root = cast(Path | None, args.upstream_root)
    config_path = cast(Path | None, args.config)
    serving_preflight = cast(Path | None, args.serving_preflight)
    output = cast(Path, args.output)

    result = evaluate_benchmark_readiness(
        upstream_root=upstream_root,
        config_path=config_path,
        serving_preflight=load_json_object(serving_preflight),
        tools=collect_tools(),
    )
    text = json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n"
    _ = output.write_text(text, encoding="utf-8")
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
