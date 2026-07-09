"""ExecutionResult model and its two renderings (Tool text / Action markdown)."""

from __future__ import annotations

from pydantic import BaseModel, Field


def _fenced(text: str) -> str:
    """Wrap untrusted text in a code fence longer than any backtick run inside it,
    so the text cannot break out of the block and render as live markdown."""
    longest = run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{text}\n{fence}"


class ExecutionResult(BaseModel):
    """Outcome of a single code execution. Rendered for the Tool and the Action."""

    stdout: str = ""
    stderr: str = ""
    result: str = ""
    images: list[str] = Field(default_factory=list)  # base64 "data:image/...;base64,..." URIs
    exit_code: int | None = None
    duration_ms: int = 0
    timed_out: bool = False
    truncated: bool = False
    error: str | None = None  # set only when execution never ran (config/provision failure)

    def _duration_text(self) -> str:
        return f"{self.duration_ms / 1000:.1f}s"

    def to_model_text(self) -> str:
        """Compact text the LLM can read and iterate on (used by the Tool)."""
        if self.error:
            return f"Error: {self.error}"

        lines: list[str] = []
        if self.timed_out:
            lines.append(f"[timed out after {self._duration_text()}]")
        else:
            lines.append(f"[exit={self.exit_code}, {self._duration_text()}]")

        stdout_label = "partial stdout:" if self.timed_out else "stdout:"
        if self.stdout:
            lines.append(f"{stdout_label}\n{self.stdout}")
        if self.stderr:
            lines.append(f"stderr:\n{self.stderr}")
        if self.result:
            lines.append(f"result:\n{self.result}")
        if self.images:
            lines.append(f"({len(self.images)} image(s) produced, shown inline)")
        if self.truncated:
            lines.append("(output truncated)")

        if len(lines) == 1:  # only the status line — no captured output
            lines.append("(no output)")
        return "\n".join(lines)

    def to_chat_markdown(self) -> str:
        """Rich text rendering for the Action (images go via a `files` event)."""
        if self.error:
            return f"**Error**\n\n{_fenced(self.error)}"

        # Text only. Images are delivered via a separate `files` event (see the
        # Action/Tool) because Open WebUI renders message `files` regardless of the
        # content-vs-output precedence that hides plain `content` for Responses-API
        # messages; a `![](data:...)` in content would silently not render there.
        # Untrusted output goes through _fenced() so backticks in it can't break
        # out of the code block and render as live markdown.
        parts: list[str] = []
        if self.timed_out:
            parts.append(f"⏱️ **Timed out** after {self._duration_text()}.")
        else:
            parts.append(
                f"**Exit code:** `{self.exit_code}` · **Duration:** {self._duration_text()}"
            )
        if self.images:
            parts.append(f"_{len(self.images)} image(s) shown below._")

        if self.result:
            parts.append(f"**result**\n{_fenced(self.result)}")
        if self.stdout:
            parts.append(f"**stdout**\n{_fenced(self.stdout)}")
        if self.stderr:
            parts.append(f"**stderr**\n{_fenced(self.stderr)}")
        if self.truncated:
            parts.append("_Output was truncated._")
        if not (self.images or self.stdout or self.stderr or self.result):
            parts.append("_No output._")

        return "\n\n".join(parts)

    def image_files(self) -> list[dict]:
        """Images as Open WebUI message `files` entries (renders reliably)."""
        return [{"type": "image", "url": uri} for uri in self.images]
