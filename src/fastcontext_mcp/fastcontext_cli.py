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


def configure_read_safety() -> None:
    # ReadTool, unlike Grep/Glob, has no working-directory containment check
    # upstream, so a tool call can read files anywhere on disk (path traversal
    # outside the workspace). Add one so reads stay scoped to the target repo's
    # working directory, matching Grep/Glob.
    try:
        import json as _json
        from pathlib import Path as _Path

        from fastcontext.agent.tool.read import ReadTool
    except ModuleNotFoundError:
        return

    original_call = ReadTool.call

    async def patched_call(self, parameters, *args, **kwargs):
        cwd = kwargs.get("cwd")
        if cwd and isinstance(parameters, str):
            try:
                data = _json.loads(parameters or "{}")
            except _json.JSONDecodeError:
                data = None
            if isinstance(data, dict) and isinstance(data.get("path"), str):
                wd = _Path(cwd).resolve()
                try:
                    resolved = _Path(data["path"]).resolve()
                    inside = resolved == wd or wd in resolved.parents
                except (OSError, ValueError):
                    inside = False
                if not inside:
                    return (
                        f"Permission error: `{data['path']}` is not within the "
                        f"working directory `{cwd}`."
                    )
        return await original_call(self, parameters, *args, **kwargs)

    ReadTool.call = patched_call


def main() -> None:
    configure_ripgrep()
    configure_read_safety()
    runpy.run_module("fastcontext.cli", run_name="__main__")


if __name__ == "__main__":
    main()
