"""Unit tests for the Tool entry point (through the mocked SDK)."""

from __future__ import annotations

from tenki_open_webui.tool import Tools


class Emitter:
    def __init__(self):
        self.events: list[dict] = []

    async def __call__(self, event):
        self.events.append(event)

    def types(self):
        return [e["type"] for e in self.events]


def _tool(key="admin-key"):
    t = Tools()
    t.valves.tenki_api_key = key
    return t


async def test_returns_rendered_text(patch_sdk):
    patch_sdk(stdout=b"hello\n", exit_code=0)
    out = await _tool().execute_code("print('hello')")
    assert "hello" in out
    assert "exit=0" in out


async def test_language_default_is_python(patch_sdk):
    sdk = patch_sdk()
    await _tool().execute_code("print(1)")
    assert sdk.last.exec_argv[0] == "python3"


async def test_language_shell_passthrough(patch_sdk):
    sdk = patch_sdk()
    await _tool().execute_code("echo hi", language="shell")
    assert sdk.last.exec_argv[:2] == ("bash", "-lc")


async def test_missing_key_returns_error_no_provision(patch_sdk):
    sdk = patch_sdk()
    out = await _tool(key="").execute_code("print(1)")
    assert "No Tenki API key" in out
    assert sdk.instances == []


async def test_per_user_key_overrides_admin(patch_sdk):
    sdk = patch_sdk()
    tool = _tool(key="admin-key")
    await tool.execute_code("print(1)", __user__={"valves": {"tenki_api_key": "user-key"}})
    assert sdk.create_kwargs[0]["auth_token"] == "user-key"


async def test_event_emitter_status_calls(patch_sdk):
    patch_sdk()
    emitter = Emitter()
    await _tool().execute_code("print(1)", __event_emitter__=emitter)
    assert "status" in emitter.types()
    # first status not done, last status done
    statuses = [e for e in emitter.events if e["type"] == "status"]
    assert statuses[0]["data"]["done"] is False
    assert statuses[-1]["data"]["done"] is True


async def test_event_emitter_image_files(patch_sdk):
    patch_sdk(images={"figure_00.png": b"\x89PNGdata"})
    emitter = Emitter()
    await _tool().execute_code("plot()", __event_emitter__=emitter)
    files_events = [e for e in emitter.events if e["type"] == "files"]
    assert files_events, "expected a files event carrying the image"
    files = files_events[0]["data"]["files"]
    assert files[0]["type"] == "image"
    assert files[0]["url"].startswith("data:image/png;base64,")


async def test_never_raises_into_loop(patch_sdk):
    patch_sdk(create_exc=RuntimeError("kaboom"))
    out = await _tool().execute_code("print(1)")
    assert isinstance(out, str)
    assert "provisioning failed" in out or "failed" in out
