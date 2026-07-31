"""Unit tests for the Action Function (through the mocked SDK)."""

from __future__ import annotations

from tenki_open_webui.action import Action, extract_last_code_block, find_runnable_code


class Emitter:
    def __init__(self):
        self.events: list[dict] = []

    async def __call__(self, event):
        self.events.append(event)

    def types(self):
        return [e["type"] for e in self.events]

    def replaces(self):
        return [e for e in self.events if e["type"] == "replace"]

    def statuses(self):
        return [e for e in self.events if e["type"] == "status"]


def _action(key="admin-key"):
    a = Action()
    a.valves.tenki_api_key = key
    return a


def _body(content: str) -> dict:
    return {"messages": [{"role": "assistant", "content": content}]}


# ---- extraction / language inference ---------------------------------------


def test_extract_single_block():
    code, hint = extract_last_code_block("text\n```python\nprint(1)\n```\n")
    assert code == "print(1)"
    assert hint == "python"


def test_extract_last_of_multiple():
    text = "```python\nprint('a')\n```\nand\n```bash\necho b\n```"
    code, hint = extract_last_code_block(text)
    assert code == "echo b"
    assert hint == "bash"


def test_extract_none_when_absent():
    assert extract_last_code_block("no code here") is None


def test_extract_no_info_string():
    code, hint = extract_last_code_block("```\nplain\n```")
    assert code == "plain"
    assert hint == ""


# ---- code selection across messages -----------------------------------------


def test_find_code_prefers_clicked_message():
    body = {
        "id": "a1",
        "messages": [
            {"id": "u1", "role": "user", "content": "```python\nprint('user')\n```"},
            {"id": "a1", "role": "assistant", "content": "```python\nprint('clicked')\n```"},
        ],
    }
    code, _ = find_runnable_code(body)
    assert code == "print('clicked')"


def test_find_code_scans_back_when_clicked_message_empty():
    # The real-world case: the action is on an empty assistant message; the code
    # lives in the preceding user message.
    body = {
        "id": "a1",
        "messages": [
            {"id": "u1", "role": "user", "content": "run this\n```python\nprint('from user')\n```"},
            {"id": "a1", "role": "assistant", "content": ""},
        ],
    }
    code, _ = find_runnable_code(body)
    assert code == "print('from user')"


def test_find_code_none_when_no_fences():
    body = {"id": "a1", "messages": [{"id": "a1", "role": "assistant", "content": "just text"}]}
    assert find_runnable_code(body) is None


# ---- action behavior --------------------------------------------------------


async def test_runs_user_message_code_from_empty_assistant(patch_sdk):
    sdk = patch_sdk(stdout=b"from user\n")
    emitter = Emitter()
    body = {
        "id": "a1",
        "messages": [
            {"id": "u1", "role": "user", "content": "```python\nprint('from user')\n```"},
            {"id": "a1", "role": "assistant", "content": ""},
        ],
    }
    await _action().action(body, __event_emitter__=emitter)
    assert sdk.last.exec_argv[0] == "python3"  # provisioned and ran
    assert "from user" in emitter.replaces()[0]["data"]["content"]


async def test_images_emitted_as_files_event(patch_sdk):
    patch_sdk(images={"figure_00.png": b"\x89PNGdata"})
    emitter = Emitter()
    await _action().action(_body("```python\nplot()\n```"), __event_emitter__=emitter)
    files_events = [e for e in emitter.events if e["type"] == "files"]
    assert files_events, "expected a files event with the chart image"
    f = files_events[0]["data"]["files"][0]
    assert f["type"] == "image" and f["url"].startswith("data:image/png;base64,")


async def test_inflight_guard_rejects_concurrent_click(patch_sdk):
    import asyncio

    sdk = patch_sdk(exec_delay=0.2)
    action = _action()
    body = {
        "id": "m1",
        "messages": [{"id": "m1", "role": "assistant", "content": "```python\nx=1\n```"}],
    }
    e1, e2 = Emitter(), Emitter()
    # Two clicks on the same message id, overlapping in time.
    await asyncio.gather(
        action.action(body, __event_emitter__=e1), action.action(body, __event_emitter__=e2)
    )
    # Exactly one actually provisioned; the other was rejected.
    assert len(sdk.instances) == 1
    rejected = [
        e
        for e in (e1, e2)
        if any("already in progress" in ev["data"].get("description", "") for ev in e.statuses())
    ]
    assert len(rejected) == 1


async def test_inflight_cleared_after_run(patch_sdk):
    patch_sdk()
    action = _action()
    body = {
        "id": "m2",
        "messages": [{"id": "m2", "role": "assistant", "content": "```python\nx=1\n```"}],
    }
    await action.action(body, __event_emitter__=Emitter())
    assert "m2" not in action._inflight  # a second click later is allowed


async def test_no_code_block_graceful(patch_sdk):
    sdk = patch_sdk()
    emitter = Emitter()
    await _action().action(_body("just prose"), __event_emitter__=emitter)
    assert sdk.instances == []  # never provisioned
    assert emitter.replaces() == []
    last = emitter.statuses()[-1]
    assert last["data"]["done"] is True
    assert "No runnable code block" in last["data"]["description"]


async def test_runs_and_replaces_with_output(patch_sdk):
    patch_sdk(stdout=b"hello\n", exit_code=0)
    emitter = Emitter()
    await _action().action(_body("```python\nprint('hello')\n```"), __event_emitter__=emitter)
    replaces = emitter.replaces()
    assert len(replaces) == 1
    content = replaces[0]["data"]["content"]
    assert "print('hello')" in content  # original code preserved
    assert "hello" in content  # output included
    assert emitter.statuses()[-1]["data"]["done"] is True


async def test_language_inferred_from_fence(patch_sdk):
    sdk = patch_sdk()
    await _action().action(_body("```bash\necho hi\n```"), __event_emitter__=Emitter())
    assert sdk.last.exec_argv[:2] == ("bash", "-lc")


async def test_rerun_replaces_prior_output(patch_sdk):
    patch_sdk(stdout=b"second\n", exit_code=0)
    emitter = Emitter()
    # Message already contains a previous output block from an earlier run.
    prior = (
        "```python\nprint('x')\n```\n\n"
        "<!-- tenki-output-start -->\n\nold output: first\n\n<!-- tenki-output-end -->"
    )
    await _action().action(_body(prior), __event_emitter__=emitter)
    content = emitter.replaces()[0]["data"]["content"]
    assert "first" not in content  # stale output removed
    assert "second" in content  # fresh output present
    assert content.count("tenki-output-start") == 1  # exactly one block


async def test_missing_key_clear_error_no_provision(patch_sdk):
    sdk = patch_sdk()
    emitter = Emitter()
    await _action(key="").action(_body("```python\nprint(1)\n```"), __event_emitter__=emitter)
    assert sdk.instances == []
    content = emitter.replaces()[0]["data"]["content"]
    assert "No Tenki API key" in content


async def test_event_order_status_first_and_last(patch_sdk):
    patch_sdk()
    emitter = Emitter()
    await _action().action(_body("```python\nprint(1)\n```"), __event_emitter__=emitter)
    assert emitter.types()[0] == "status"
    assert emitter.statuses()[0]["data"]["done"] is False
    assert emitter.types()[-1] == "status"
    assert emitter.statuses()[-1]["data"]["done"] is True
