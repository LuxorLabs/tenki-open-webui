"""Credential and endpoint lookup shared by ``try_live.py`` and the live tests."""

from __future__ import annotations

import os
from collections.abc import Mapping

DEFAULT_ENDPOINT = "https://api.tenki.cloud"

# LUXOR_API_KEY is also the Luxor Mining Pool key name; only these are ours.
_API_KEY_PREFIXES = ("lx_", "tk_")


def _get(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def api_key(env: Mapping[str, str] | None = None) -> str:
    """Return the API key from the environment, or ``""`` when none is set."""
    env = os.environ if env is None else env
    key = _get(env, "LUXOR_API_KEY")
    if key.startswith(_API_KEY_PREFIXES):
        return key
    return _get(env, "TENKI_API_KEY")


def endpoint(env: Mapping[str, str] | None = None) -> str:
    """Return the API endpoint from the environment, or the default."""
    env = os.environ if env is None else env
    return _get(env, "LUXOR_API_ENDPOINT") or _get(env, "TENKI_API_ENDPOINT") or DEFAULT_ENDPOINT
