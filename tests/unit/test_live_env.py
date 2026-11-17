"""Env lookup used by ``scripts/try_live.py`` and the live integration tests."""

from __future__ import annotations

import pytest

import live_env


@pytest.mark.parametrize("key", ["lx_abc123", "tk_abc123", "  lx_abc123\n"])
def test_luxor_api_key_with_known_prefix_is_used(key):
    env = {"LUXOR_API_KEY": key, "TENKI_API_KEY": "tenki-key"}
    assert live_env.api_key(env) == key.strip()


def test_luxor_api_key_without_known_prefix_falls_back_to_tenki():
    env = {"LUXOR_API_KEY": "pool-key-123", "TENKI_API_KEY": "tenki-key"}
    assert live_env.api_key(env) == "tenki-key"


def test_luxor_api_key_without_known_prefix_and_no_tenki_is_unset():
    assert live_env.api_key({"LUXOR_API_KEY": "pool-key-123"}) == ""


def test_tenki_api_key_is_not_prefix_checked():
    assert live_env.api_key({"TENKI_API_KEY": "sk-legacy"}) == "sk-legacy"


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_luxor_api_key_falls_back_to_tenki(blank):
    env = {"LUXOR_API_KEY": blank, "TENKI_API_KEY": "tenki-key"}
    assert live_env.api_key(env) == "tenki-key"


def test_api_key_reads_process_environment(monkeypatch):
    monkeypatch.setenv("LUXOR_API_KEY", "pool-key-123")
    monkeypatch.setenv("TENKI_API_KEY", "tenki-key")
    assert live_env.api_key() == "tenki-key"
    monkeypatch.setenv("LUXOR_API_KEY", "lx_abc123")
    assert live_env.api_key() == "lx_abc123"


def test_endpoint_precedence():
    luxor, tenki = "https://luxor.example", "https://tenki.example"
    assert live_env.endpoint({"LUXOR_API_ENDPOINT": luxor, "TENKI_API_ENDPOINT": tenki}) == luxor
    assert live_env.endpoint({"LUXOR_API_ENDPOINT": " ", "TENKI_API_ENDPOINT": tenki}) == tenki
    assert live_env.endpoint({}) == live_env.DEFAULT_ENDPOINT
