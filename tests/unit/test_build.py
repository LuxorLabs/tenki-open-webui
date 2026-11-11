"""The built distributables are self-contained: no local package imports, have
frontmatter, define the expected class, and import cleanly."""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_FILE = ROOT / "open-webui" / "tools" / "tenki_code_execution.py"
ACTION_FILE = ROOT / "open-webui" / "functions" / "tenki_run_code.py"

# (distributable path, expected class name, expected entry attribute)
TARGETS = [
    (TOOL_FILE, "Tools", "execute_code"),
    (ACTION_FILE, "Action", "action"),
]


@pytest.fixture(scope="module", autouse=True)
def _build_once():
    subprocess.run([sys.executable, "scripts/build.py"], cwd=ROOT, check=True)


@pytest.mark.parametrize("path,_class,_attr", TARGETS)
def test_no_local_package_imports(path, _class, _attr):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import leaked into distributable"
            assert not (node.module or "").startswith("tenki_open_webui")


@pytest.mark.parametrize("path,_class,_attr", TARGETS)
def test_has_frontmatter(path, _class, _attr):
    src = path.read_text()
    assert src.lstrip().startswith('"""')
    assert "requirements: luxor-ai[async]" in src
    assert "title:" in src and "author: LuxorLabs" in src


@pytest.mark.parametrize("path,class_name,attr", TARGETS)
def test_defines_class_and_loads(path, class_name, attr):
    mod_name = f"built_{class_name.lower()}_module"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    cls = getattr(module, class_name)
    instance = cls()
    assert hasattr(instance, attr)
    assert instance.valves.network_egress is False  # secure default preserved


def _load_built(path, mod_name):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def test_built_tool_runs_end_to_end():
    """Regression: the inliner must preserve decorators (e.g. @dataclass) so the
    built single-file plugin actually *runs*, not just imports. A dropped
    @dataclass previously made `CodeExecutionRequest()` raise 'takes no arguments'
    at call time — which unit tests against src/ never saw."""
    import asyncio
    from dataclasses import is_dataclass

    module = _load_built(TOOL_FILE, "built_tool_e2e")
    assert is_dataclass(module.CodeExecutionRequest)
    assert is_dataclass(module.RunPlan)

    class _Cmd:
        stdout, stderr, exit_code = b"hi\n", b"", 0

    class _FS:
        async def write_text(self, *a, **k): ...
        async def mkdir(self, *a, **k): ...
        async def list(self, *a, **k):
            raise FileNotFoundError

        async def read_bytes(self, *a, **k):
            raise FileNotFoundError

    class _Sandbox:
        fs = _FS()

        async def exec(self, *a, **k):
            return _Cmd()

        async def close(self): ...

    class _SDK:
        async def create(self, **k):
            return _Sandbox()

    module.AsyncSandbox = _SDK()

    tool = module.Tools()
    tool.valves.tenki_api_key = "k"
    out = asyncio.run(tool.execute_code("print('hi')"))
    assert "hi" in out
    assert "takes no arguments" not in out
    assert "failed" not in out.lower()
