"""Rendering safety for ExecutionResult.to_chat_markdown (markdown injection)."""

from __future__ import annotations

from tenki_open_webui.result import ExecutionResult


def test_chat_markdown_fences_backticks_safely():
    # Output containing a ``` run must not break out of the code fence.
    r = ExecutionResult(stdout="```\nnot a real fence\n```", exit_code=0)
    md = r.to_chat_markdown()
    assert "````" in md  # a longer (4-backtick) fence was used
    assert md.count("````") == 2  # exactly one open + one close fence
    assert "not a real fence" in md


def test_chat_markdown_error_is_fenced():
    r = ExecutionResult(error="boom `x` [link](http://evil)")
    md = r.to_chat_markdown()
    assert md.startswith("**Error**")
    assert "```" in md  # error body wrapped in a fence, not interpolated raw
    assert "boom `x` [link](http://evil)" in md
