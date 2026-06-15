from __future__ import annotations

import shutil

from fastcontext.agent.tool.grep import GrepTool
from fastcontext.cli import main as fastcontext_main


def configure_ripgrep() -> None:
    ripgrep_path = shutil.which("rg")
    if ripgrep_path is not None:
        setattr(GrepTool, "_rg_path", ripgrep_path)


def main() -> None:
    configure_ripgrep()
    fastcontext_main()


if __name__ == "__main__":
    main()
