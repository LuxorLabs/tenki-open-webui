"""The LLM-callable code-execution Tool.

This is the source form of the distributable ``open-webui/tools/tenki_code_execution.py``.
``scripts/build.py`` inlines the shared core into a single self-contained file for
one-click hub import; the frontmatter metadata is added by the build step.
"""

from __future__ import annotations

from .config import UserValves, Valves, resolve_effective_key
from .core import CodeExecutionRequest, execute
from .languages import normalize_language


async def _emit_status(emitter, description: str, done: bool) -> None:
    if emitter:
        await emitter({"type": "status", "data": {"description": description, "done": done}})


class Tools:
    Valves = Valves
    UserValves = UserValves

    def __init__(self):
        self.valves = self.Valves()

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        __user__: dict | None = None,
        __event_emitter__=None,
    ) -> str:
        """Execute code in an isolated, ephemeral Tenki microVM sandbox and return its output.

        Use this to run Python or shell code to compute answers, analyze data, or
        produce charts. Each call runs in a fresh sandbox with no state from
        previous calls.

        :param code: The source code to execute.
        :param language: "python" (default) or "shell".
        :return: The captured stdout/stderr/result (and a note if a chart image was produced).
        """
        try:
            key = resolve_effective_key(self.valves, __user__)
            if not key:
                return (
                    "Error: No Tenki API key configured. Set 'tenki_api_key' in the "
                    "plugin settings (Valves) or your personal settings (UserValves)."
                )

            language = normalize_language(language, self.valves.default_language)
            await _emit_status(__event_emitter__, "Provisioning Tenki sandbox…", False)

            request = CodeExecutionRequest(
                code=code,
                language=language,
                valves=self.valves,
                api_key=key,
            )
            result = await execute(request)

            if __event_emitter__ and result.images:
                # Surface images to the user via a `files` event (renders regardless
                # of the content-vs-output precedence for Responses-API messages).
                await __event_emitter__({"type": "files", "data": {"files": result.image_files()}})
            await _emit_status(
                __event_emitter__,
                "Timed out" if result.timed_out else "Done",
                True,
            )
            return result.to_model_text()
        except Exception as err:  # never raise into the model's tool loop
            return f"Error: code execution failed: {err}"
