"""The user-invoked "Run code" Action Function.

This is the source form of the distributable ``open-webui/functions/tenki_run_code.py``.
``scripts/build.py`` inlines the shared core into a single self-contained file;
the frontmatter metadata is added by the build step.
"""

from __future__ import annotations

import re

from .config import UserValves, Valves, resolve_effective_key
from .core import CodeExecutionRequest, execute
from .languages import normalize_language
from .result import ExecutionResult

# Fenced code block: captures the info string and the body.
_FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)

# Markers wrapping our injected output, so a re-run replaces the previous output
# instead of stacking a new copy under it.
_OUT_START = "<!-- tenki-output-start -->"
_OUT_END = "<!-- tenki-output-end -->"
_OUT_RE = re.compile(re.escape(_OUT_START) + r".*?" + re.escape(_OUT_END), re.DOTALL)


def extract_last_code_block(text: str) -> tuple[str, str] | None:
    """Return (code, language_hint) for the last fenced block, or None if absent."""
    matches = _FENCE_RE.findall(text or "")
    if not matches:
        return None
    info, code = matches[-1]
    hint = info.strip().split()[0] if info.strip() else ""
    return code.strip("\n"), hint


def _content_to_text(content) -> str:
    """A message's content as text (handles multimodal list content)."""
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content if isinstance(content, str) else ""


def _messages(body: dict | None) -> list[dict]:
    if not isinstance(body, dict):
        return []
    messages = body.get("messages")
    return messages if isinstance(messages, list) else []


def _target_text(body: dict | None) -> str:
    """Text of the message the action was invoked on (``body['id']``), which is
    what the emitter's replace event overwrites; falls back to the last message."""
    messages = _messages(body)
    target_id = body.get("id") if isinstance(body, dict) else None
    if target_id:
        for m in messages:
            if m.get("id") == target_id:
                return _content_to_text(m.get("content"))
    if messages:
        return _content_to_text(messages[-1].get("content"))
    return _content_to_text(body.get("content")) if isinstance(body, dict) else ""


def find_runnable_code(body: dict | None) -> tuple[str, str] | None:
    """Locate a runnable code block: prefer the clicked message, else the most
    recent message (any role) that contains a fenced code block."""
    messages = _messages(body)
    target_id = body.get("id") if isinstance(body, dict) else None
    if target_id:
        for m in messages:
            if m.get("id") == target_id:
                found = extract_last_code_block(_content_to_text(m.get("content")))
                if found:
                    return found
    for m in reversed(messages):
        found = extract_last_code_block(_content_to_text(m.get("content")))
        if found:
            return found
    return extract_last_code_block(_target_text(body))  # legacy single-content body


def _compose(original: str, result: ExecutionResult) -> str:
    """Original message with any prior output block replaced by the fresh one."""
    base = _OUT_RE.sub("", original).rstrip()
    block = (
        f"{_OUT_START}\n\n---\n\n### 🧪 Tenki sandbox output\n\n"
        f"{result.to_chat_markdown()}\n\n{_OUT_END}"
    )
    return f"{base}\n\n{block}" if base else block


class Action:
    Valves = Valves
    UserValves = UserValves

    def __init__(self):
        self.valves = self.Valves()
        # Message IDs with a run currently in flight, to reject double-clicks on the
        # same message. The Action instance is cached/reused by Open WebUI, so this
        # persists across invocations. asyncio is single-threaded, so the
        # check-then-add below is atomic (no await between them).
        self._inflight: set[str] = set()

    async def _status(self, emitter, description: str, done: bool) -> None:
        if emitter:
            await emitter({"type": "status", "data": {"description": description, "done": done}})

    async def action(
        self,
        body: dict,
        __user__: dict | None = None,
        __event_emitter__=None,
        __event_call__=None,
    ) -> None:
        """Run the code block in the message in an isolated Tenki sandbox and show the output."""
        message_id = body.get("id") if isinstance(body, dict) else None
        if message_id is not None and message_id in self._inflight:
            await self._status(
                __event_emitter__, "A Tenki run is already in progress for this message…", True
            )
            return
        if message_id is not None:
            self._inflight.add(message_id)
        try:
            await self._run(body, __user__, __event_emitter__)
        finally:
            if message_id is not None:
                self._inflight.discard(message_id)

    async def _run(self, body, __user__, __event_emitter__) -> None:
        try:
            original = _target_text(body)
            extracted = find_runnable_code(body)
            if extracted is None:
                await self._status(
                    __event_emitter__, "No runnable code block found in this conversation.", True
                )
                return

            code, hint = extracted
            language = normalize_language(hint, self.valves.default_language)

            key = resolve_effective_key(self.valves, __user__)
            if not key:
                result = ExecutionResult(
                    error=(
                        "No Tenki API key configured. Set 'tenki_api_key' in the plugin "
                        "settings (Valves) or your personal settings (UserValves)."
                    )
                )
                await self._emit_result(__event_emitter__, original, result)
                await self._status(__event_emitter__, "Configuration error", True)
                return

            await self._status(__event_emitter__, "Provisioning Tenki sandbox…", False)
            request = CodeExecutionRequest(
                code=code, language=language, valves=self.valves, api_key=key
            )
            result = await execute(request)

            await self._emit_result(__event_emitter__, original, result)
            await self._status(
                __event_emitter__,
                "Timed out" if result.timed_out else "Done",
                True,
            )
        except Exception as err:  # never surface a raw traceback to the UI
            await self._status(__event_emitter__, f"Run failed: {err}", True)

    async def _emit_result(self, emitter, original: str, result: ExecutionResult) -> None:
        if not emitter:
            return
        await emitter({"type": "replace", "data": {"content": _compose(original, result)}})
        # Images go through a `files` event so they render even when the message's
        # `content` is shadowed by the model's Responses-API `output`.
        if result.images:
            await emitter({"type": "files", "data": {"files": result.image_files()}})
