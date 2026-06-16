from __future__ import annotations

import json
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from evaluation.endpoint_readiness import JsonValue
from evaluation.official_benchmark_probes import probe_env, truncate


DATASET_TIMEOUT_SECONDS: Final = 240
OFFICIAL_DATASETS: Final = {
    "swebench-verified": "princeton-nlp/SWE-Bench_Verified",
    "swebench-multilingual": "SWE-bench/SWE-bench_Multilingual",
    "swebench-pro": "ScaleAI/SWE-bench_Pro",
}


@dataclass(frozen=True, slots=True)
class DatasetProbe:
    name: str
    dataset: str
    split: str
    command: str
    cwd: str | None
    returncode: int | None
    duration_seconds: float
    sample_count: int | None
    first_instance_id: str | None
    stdout_excerpt: str
    stderr_excerpt: str


def collect_official_dataset_probes(
    upstream_root: Path | None,
    *,
    timeout_seconds: int = DATASET_TIMEOUT_SECONDS,
) -> list[DatasetProbe]:
    if upstream_root is None:
        return []
    return [
        run_dataset_probe(alias, dataset, upstream_root, timeout_seconds)
        for alias, dataset in OFFICIAL_DATASETS.items()
    ]


def run_dataset_probe(
    alias: str,
    dataset: str,
    cwd: Path,
    timeout_seconds: int,
) -> DatasetProbe:
    code = (
        "import json; "
        "from datasets import load_dataset; "
        f"sample = load_dataset({dataset!r}, split='test[:1]'); "
        "first = sample[0].get('instance_id') if len(sample) else None; "
        "print(json.dumps({'sample_count': len(sample), 'first_instance_id': first}))"
    )
    command = ["uv", "run", "--group", "benchmark", "python", "-c", code]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=probe_env(),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        duration = time.monotonic() - started
        return make_failed_dataset_probe(alias, dataset, command, cwd, duration, str(exc))
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return DatasetProbe(
            name=alias,
            dataset=dataset,
            split="test[:1]",
            command=shlex.join(command),
            cwd=str(cwd.resolve()),
            returncode=None,
            duration_seconds=round(duration, 3),
            sample_count=None,
            first_instance_id=None,
            stdout_excerpt=truncate(stdout),
            stderr_excerpt=truncate(stderr or f"timed out after {timeout_seconds}s"),
        )

    duration = time.monotonic() - started
    sample_count, first_instance_id = parse_dataset_probe_stdout(completed.stdout)
    return DatasetProbe(
        name=alias,
        dataset=dataset,
        split="test[:1]",
        command=shlex.join(command),
        cwd=str(cwd.resolve()),
        returncode=completed.returncode,
        duration_seconds=round(duration, 3),
        sample_count=sample_count,
        first_instance_id=first_instance_id,
        stdout_excerpt=truncate(completed.stdout),
        stderr_excerpt=truncate(completed.stderr),
    )


def make_failed_dataset_probe(
    alias: str,
    dataset: str,
    command: list[str],
    cwd: Path,
    duration_seconds: float,
    stderr: str,
) -> DatasetProbe:
    return DatasetProbe(
        name=alias,
        dataset=dataset,
        split="test[:1]",
        command=shlex.join(command),
        cwd=str(cwd.resolve()),
        returncode=None,
        duration_seconds=round(duration_seconds, 3),
        sample_count=None,
        first_instance_id=None,
        stdout_excerpt="",
        stderr_excerpt=truncate(stderr),
    )


def parse_dataset_probe_stdout(stdout: str) -> tuple[int | None, str | None]:
    for line in reversed(stdout.splitlines()):
        try:
            raw = cast(JsonValue, json.loads(line))
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        sample_count = raw.get("sample_count")
        first_instance_id = raw.get("first_instance_id")
        return (
            sample_count if isinstance(sample_count, int) else None,
            first_instance_id if isinstance(first_instance_id, str) else None,
        )
    return None, None


def dataset_probes_passed(dataset_probes: list[DatasetProbe]) -> bool:
    return all(
        probe.returncode == 0 and probe.sample_count is not None and probe.sample_count > 0
        for probe in dataset_probes
    )
