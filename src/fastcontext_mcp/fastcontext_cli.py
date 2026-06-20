from __future__ import annotations

import os
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


def configure_max_tokens() -> None:
    # FastContext hardcodes max_completion_tokens=32000 (agent/llm.py) with no
    # config hook, which exceeds the served --max-model-len on small GPUs and
    # makes every call 400. Cap it via FASTCONTEXT_MAX_TOKENS by injecting the
    # value into LLM.__init__ before the agent is built.
    raw = os.getenv("FASTCONTEXT_MAX_TOKENS")
    if not raw:
        return
    try:
        max_tokens = int(raw)
    except ValueError:
        return
    try:
        from fastcontext.agent import llm as _llm
    except ModuleNotFoundError:
        return
    original_init = _llm.LLM.__init__

    def patched_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("max_tokens", max_tokens)
        original_init(self, *args, **kwargs)

    _llm.LLM.__init__ = patched_init


def configure_path_tolerance() -> None:
    # Small / heavily-quantised models often mangle the workspace path in tool
    # arguments -- e.g. truncating "/mnt/a/b/repo" to "/repo" -- so every Read,
    # Grep, and Glob is rejected as "outside the working directory" and the
    # agent never reads anything. When FASTCONTEXT_REROOT_PATHS is enabled,
    # re-root such paths under the real working directory before the tool runs.
    # Off by default: full-precision models on larger GPUs follow the path
    # instructions correctly and should keep the strict upstream behaviour.
    from fastcontext_mcp.runtime import reroot_under, truthy

    if not truthy(os.getenv("FASTCONTEXT_REROOT_PATHS")):
        return
    try:
        import json as _json
        from pathlib import Path as _Path

        from fastcontext.agent.tool.glob import GlobTool
        from fastcontext.agent.tool.grep import GrepTool
    except ModuleNotFoundError:
        return

    # Read is handled separately by configure_read_safety (it also needs a
    # containment check). Grep/Glob already enforce containment themselves.
    for cls, keys in ((GrepTool, ("path",)), (GlobTool, ("directory",))):
        original_call = cls.call

        async def patched_call(self, parameters, *args, _orig=original_call, _keys=keys, **kwargs):
            cwd = kwargs.get("cwd")
            if cwd and isinstance(parameters, str):
                try:
                    data = _json.loads(parameters or "{}")
                except _json.JSONDecodeError:
                    data = None
                if isinstance(data, dict):
                    changed = False
                    for key in _keys:
                        if isinstance(data.get(key), str):
                            fixed = reroot_under(data[key], _Path(cwd))
                            if fixed != data[key]:
                                data[key] = fixed
                                changed = True
                    if changed:
                        parameters = _json.dumps(data)
            return await _orig(self, parameters, *args, **kwargs)

        cls.call = patched_call


def configure_read_safety() -> None:
    # ReadTool, unlike Grep/Glob, has no working-directory containment check
    # upstream, so a run can read files anywhere on disk (path traversal). Add
    # one here, unconditionally, so reads stay scoped to the target repo. When
    # FASTCONTEXT_REROOT_PATHS is set we also re-root the path first (so a
    # mangled-but-in-repo path is corrected before the containment check).
    try:
        import json as _json
        from pathlib import Path as _Path

        from fastcontext.agent.tool.read import ReadTool
    except ModuleNotFoundError:
        return

    from fastcontext_mcp.runtime import reroot_under, truthy

    reroot_on = truthy(os.getenv("FASTCONTEXT_REROOT_PATHS"))
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
                path = reroot_under(data["path"], wd) if reroot_on else data["path"]
                try:
                    resolved = _Path(path).resolve()
                    inside = resolved == wd or wd in resolved.parents
                except (OSError, ValueError):
                    inside = False
                if not inside:
                    return (
                        f"Permission error: `{data['path']}` is not within the "
                        f"working directory `{cwd}`."
                    )
                if path != data["path"]:
                    data["path"] = path
                    parameters = _json.dumps(data)
        return await original_call(self, parameters, *args, **kwargs)

    ReadTool.call = patched_call


def main() -> None:
    configure_ripgrep()
    configure_max_tokens()
    configure_path_tolerance()
    configure_read_safety()
    runpy.run_module("fastcontext.cli", run_name="__main__")


if __name__ == "__main__":
    main()
