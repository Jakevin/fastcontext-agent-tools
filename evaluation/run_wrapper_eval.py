from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mcp_smoke import run_mcp_smoke
from .render_summary import render_svg


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "evaluation" / "wrapper-eval.json"
SVG_PATH = ROOT / "docs" / "assets" / "evaluation-summary.svg"


def run_command(command: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "returncode": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    unit = run_command([sys.executable, "-m", "unittest", "discover", "-s", "tests"], env=env)
    mcp_checks = run_mcp_smoke()

    checks = [
        {
            "name": "unit_tests",
            "evidence": "Runs the repository unit-test suite for parser, runtime, server, and wrapper behavior.",
            **unit,
        },
        *mcp_checks,
    ]
    passed = sum(1 for check in checks if check["status"] == "pass")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": "fastcontext-agent-tools",
        "scope": "MCP wrapper and bundled Codex skill",
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "summary": {
            "checks_total": len(checks),
            "checks_passed": passed,
            "checks_failed": len(checks) - passed,
        },
        "checks": checks,
        "limitations": [
            "This evaluation uses a fake fastcontext.cli package to verify wrapper behavior without a GPU or model endpoint.",
            "FastContext model-quality claims are not reproduced here; see the Microsoft FastContext paper and model card.",
        ],
    }

    RESULT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    SVG_PATH.write_text(render_svg(summary), encoding="utf-8")
    print(json.dumps(summary["summary"], indent=2))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
