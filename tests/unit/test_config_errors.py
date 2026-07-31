"""Misconfiguration path: clear errors, never a crash, never a provision (FR-010)."""

from __future__ import annotations

from tenki_open_webui.config import Valves, resolve_effective_key
from tenki_open_webui.tool import Tools


def test_credential_precedence_user_wins():
    valves = Valves(tenki_api_key="admin")
    assert resolve_effective_key(valves, {"valves": {"tenki_api_key": "mine"}}) == "mine"


def test_credential_falls_back_to_admin():
    valves = Valves(tenki_api_key="admin")
    assert resolve_effective_key(valves, {"valves": {"tenki_api_key": ""}}) == "admin"
    assert resolve_effective_key(valves, None) == "admin"


def test_no_credential_resolves_empty():
    assert resolve_effective_key(Valves(), None) == ""


async def test_tool_no_key_clear_error_no_provision(patch_sdk):
    sdk = patch_sdk()
    tool = Tools()  # default valves, empty key
    out = await tool.execute_code("print(1)")
    assert "No Tenki API key" in out
    assert sdk.instances == []
