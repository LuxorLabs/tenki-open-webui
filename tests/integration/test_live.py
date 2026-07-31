"""Live integration tests against a real Tenki API.

Gated on ``TENKI_API_KEY`` — skipped entirely when it is unset, so ``pytest``
stays green without credentials. These hit the real async SDK and provision real
microVMs (they cost quota and take seconds each).

Env:
- ``TENKI_API_KEY``       (required to run)
- ``TENKI_API_ENDPOINT``  (optional; defaults to https://api.tenki.cloud)
"""

from __future__ import annotations

import base64
import os

import pytest

from tenki_open_webui.config import Valves
from tenki_open_webui.core import CodeExecutionRequest, execute

API_KEY = os.getenv("TENKI_API_KEY", "")

pytestmark = pytest.mark.skipif(not API_KEY, reason="TENKI_API_KEY not set")

# A valid 1x1 PNG — lets us test image collection without depending on matplotlib.
_ONE_PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _valves(**overrides) -> Valves:
    return Valves(
        tenki_api_key=API_KEY,
        tenki_api_endpoint=os.getenv("TENKI_API_ENDPOINT", "https://api.tenki.cloud"),
        **overrides,
    )


def _req(code: str, language: str = "python", **overrides) -> CodeExecutionRequest:
    return CodeExecutionRequest(
        code=code, language=language, valves=_valves(**overrides), api_key=API_KEY
    )


async def _raw_sandbox():
    """Provision a raw AsyncSandbox with the same knobs the core uses."""
    from tenki import AsyncSandbox

    v = _valves()
    return await AsyncSandbox.create(
        auth_token=API_KEY,
        base_url=v.tenki_api_endpoint,
        cpu_cores=v.cpu_cores,
        memory_mb=v.memory_mb,
        disk_size_gb=v.disk_size_gb,
        allow_outbound=v.network_egress,
        max_duration=120,
    )


async def test_python_stdout():
    result = await execute(_req("print(sum(range(1, 6)))"))
    assert result.error is None, result.error
    assert result.exit_code == 0
    assert "15" in result.stdout


async def test_shell_stdout():
    result = await execute(_req("echo hello-from-shell", language="shell"))
    assert result.error is None, result.error
    assert result.exit_code == 0
    assert "hello-from-shell" in result.stdout


async def test_error_traceback_captured():
    result = await execute(_req("raise ValueError('boom')"))
    assert result.error is None, result.error
    assert result.exit_code != 0
    assert "ValueError" in result.stderr and "boom" in result.stderr


async def test_timeout_terminates():
    result = await execute(_req("import time; time.sleep(30)", timeout_seconds=5))
    assert result.timed_out is True


async def test_image_collection_from_output_dir():
    # Write a real PNG into the output dir; the core should collect it as a data URI.
    b64 = base64.b64encode(_ONE_PX_PNG).decode("ascii")
    code = (
        "import base64, os\n"
        "os.makedirs('owui_tenki_out', exist_ok=True)\n"
        f"open('owui_tenki_out/pixel.png','wb').write(base64.b64decode('{b64}'))\n"
        "print('wrote image')\n"
    )
    result = await execute(_req(code))
    assert result.error is None, result.error
    assert result.images, "expected at least one collected image"
    assert result.images[0].startswith("data:image/png;base64,")


async def test_matplotlib_autocapture_if_available():
    probe = await execute(_req("import matplotlib  # noqa"))
    if probe.exit_code != 0:
        pytest.skip("matplotlib not available in the sandbox image")
    code = (
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "plt.plot([0, 1, 4, 9, 16])\n"
        "print('plotted')\n"  # no savefig — the runner epilogue must capture it
    )
    result = await execute(_req(code))
    assert result.error is None, result.error
    assert result.images, "expected the matplotlib figure to be auto-captured"


async def test_action_path_end_to_end():
    # Exercise the user-invoked Action against a real sandbox (parity with the Tool).
    from tenki_open_webui.action import Action

    events: list[dict] = []

    async def emitter(event):
        events.append(event)

    action = Action()
    action.valves = _valves()
    body = {"messages": [{"role": "assistant", "content": "```python\nprint(6 * 7)\n```"}]}
    await action.action(body, __event_emitter__=emitter)

    replaces = [e for e in events if e["type"] == "replace"]
    statuses = [e for e in events if e["type"] == "status"]
    assert replaces, "action should emit a replace event with output"
    assert "42" in replaces[-1]["data"]["content"]
    assert statuses[-1]["data"]["done"] is True


async def test_fs_mkdir_is_writable_by_exec_user():
    # Guest-agent ownership fix: a dir created via sb.fs.mkdir (guest agent) must be
    # writable by the exec user (uid 1000), not left root-owned. Exercises the fix
    # directly, since the plugin core intentionally uses exec-mkdir as a workaround.
    sb = await _raw_sandbox()
    try:
        await sb.fs.mkdir("probe_dir")
        res = await sb.exec("bash", "-lc", "echo hi > probe_dir/f.txt && cat probe_dir/f.txt")
        assert res.exit_code == 0, res.stderr_text
        assert "hi" in res.stdout_text
        owner = await sb.exec("bash", "-lc", "stat -c '%U' probe_dir")
        assert owner.stdout_text.strip() == "tenki", owner.stdout_text
    finally:
        await sb.close()


async def test_fs_mkdir_recursive_is_writable_by_exec_user():
    # Recursive mkdir must chown every created level, not just the leaf.
    sb = await _raw_sandbox()
    try:
        await sb.fs.mkdir("a/b/c", recursive=True)
        res = await sb.exec("bash", "-lc", "echo deep > a/b/c/f.txt && cat a/b/c/f.txt")
        assert res.exit_code == 0, res.stderr_text
        assert "deep" in res.stdout_text
    finally:
        await sb.close()


async def test_no_sandbox_leak():
    # Snapshot RUNNING sessions before/after; the run's sandbox must be torn down.
    from tenki import AsyncClient

    endpoint = os.getenv("TENKI_API_ENDPOINT", "https://api.tenki.cloud")

    async def running_ids() -> set[str]:
        async with AsyncClient(auth_token=API_KEY, base_url=endpoint) as client:
            return {sb.id for sb in await client.list() if sb.state == "RUNNING"}

    before = await running_ids()
    result = await execute(_req("print('ok')"))
    assert result.error is None, result.error
    after = await running_ids()
    assert after - before == set(), "a sandbox was left running (leak)"
