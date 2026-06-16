from __future__ import annotations

import runpy
import shutil


def configure_ripgrep() -> None:
    ripgrep_path = shutil.which("rg")
    if ripgrep_path is None:
        return
    try:
        from fastcontext.agent.tool.grep import GrepTool
    except ModuleNotFoundError:
        return
    setattr(GrepTool, "_rg_path", ripgrep_path)


def main() -> None:
    configure_ripgrep()
    runpy.run_module("fastcontext.cli", run_name="__main__")


if __name__ == "__main__":
    main()
