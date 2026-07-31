"""Per-language run strategies.

Each language produces a ``RunPlan``: files to write into the sandbox before
execution, plus the argv to exec. Python is run via a small runner that executes
the user's file, echoes the last top-level expression (REPL/notebook style), and
auto-captures any open matplotlib figures into the per-run output directory —
prompt-independent, so it works for both entry points.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .constants import CODE_FILENAME, OUTPUT_DIR, RESULT_FILENAME, RUNNER_FILENAME

SUPPORTED_LANGUAGES = ("python", "shell")

# Runner executed for Python runs. It runs the user's code as __main__; if the
# code ends in a bare expression (e.g. `(mean, std)`), its repr is written to the
# result file so notebook-style snippets return a value even without print().
# Finally, it saves any open matplotlib figures (no-op when matplotlib is absent).
# All paths are workdir-relative so they resolve inside the sandbox workdir.
_PY_RUNNER = """\
import ast
import os

os.makedirs({outdir!r}, exist_ok=True)
with open({codefile!r}) as _f:
    _src = _f.read()
_ns = {{"__name__": "__main__", "__file__": {codefile!r}}}
try:
    _tree = ast.parse(_src)
    _result = None
    if _tree.body and isinstance(_tree.body[-1], ast.Expr):
        _last = _tree.body.pop()
        exec(compile(_tree, {codefile!r}, "exec"), _ns)
        _expr = ast.fix_missing_locations(ast.Expression(_last.value))
        _val = eval(compile(_expr, {codefile!r}, "eval"), _ns)
        if _val is not None:
            _result = repr(_val)[:{maxbytes}]
    else:
        exec(compile(_tree, {codefile!r}, "exec"), _ns)
    if _result is not None:
        with open({resultfile!r}, "w") as _rf:
            _rf.write(_result)
finally:
    try:
        import matplotlib.pyplot as _plt

        for _i, _num in enumerate(_plt.get_fignums()):
            _plt.figure(_num).savefig(os.path.join({outdir!r}, "figure_%02d.png" % _i))
    except Exception:
        pass
"""


@dataclass(frozen=True)
class RunPlan:
    """A concrete plan to run one snippet in a sandbox."""

    argv: tuple[str, ...]
    files: dict[str, str] = field(default_factory=dict)


def normalize_language(language: str | None, default: str = "python") -> str:
    """Map a caller/fence language hint to a supported language."""
    lang = (language or default or "python").strip().lower()
    if lang in ("py", "python3"):
        return "python"
    if lang in ("sh", "bash", "shell", "zsh"):
        return "shell"
    return lang


def build_run_plan(language: str, code: str, max_output_bytes: int = 100_000) -> RunPlan:
    """Build the run plan for a supported language, else raise ``ValueError``."""
    lang = normalize_language(language)
    if lang == "python":
        runner = _PY_RUNNER.format(
            outdir=OUTPUT_DIR,
            codefile=CODE_FILENAME,
            resultfile=RESULT_FILENAME,
            maxbytes=max_output_bytes,
        )
        return RunPlan(
            argv=("python3", RUNNER_FILENAME),
            files={CODE_FILENAME: code, RUNNER_FILENAME: runner},
        )
    if lang == "shell":
        return RunPlan(argv=("bash", "-lc", code))
    raise ValueError(
        f"Unsupported language {language!r}. Supported: {', '.join(SUPPORTED_LANGUAGES)}."
    )
