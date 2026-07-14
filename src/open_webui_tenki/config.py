"""Configuration models (Valves / UserValves) and credential resolution.

Both the Tool and the Action expose identical ``Valves`` (admin) and
``UserValves`` (per-user) so behavior is consistent between the two entry points.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Valves(BaseModel):
    """Admin / instance-level configuration edited in the plugin's settings."""

    tenki_api_key: str = Field(
        default="",
        description="Required. Your Tenki API key. Stored server-side; never logged.",
    )
    tenki_api_endpoint: str = Field(
        default="https://api.tenki.cloud",
        description="Tenki API endpoint. Override for self-hosted/staging.",
    )
    tenki_workspace_id: str = Field(
        default="",
        description="Optional Tenki workspace ID. Uses the account default when empty.",
    )
    tenki_project_id: str = Field(
        default="",
        description="Optional Tenki project ID. Uses the account default when empty.",
    )
    default_language: Literal["python", "shell"] = Field(
        default="python",
        description="Language used when the caller does not specify one.",
    )
    cpu_cores: int = Field(default=1, ge=1, le=16, description="Sandbox vCPU count (1-16).")
    memory_mb: int = Field(
        default=512, ge=128, le=65536, description="Sandbox memory in MiB (128-65536, even)."
    )
    disk_size_gb: int = Field(
        default=5, ge=5, le=100, description="Sandbox disk size in GiB (5-100)."
    )
    timeout_seconds: int = Field(
        default=300, ge=1, le=600, description="Max execution time per run."
    )
    network_egress: bool = Field(
        default=False,
        description="Allow sandbox outbound network access. Off by default for safety.",
    )
    sandbox_image: str = Field(
        default="",
        description="Optional Tenki image/template ref providing python3 + bash.",
    )
    max_concurrent_executions: int = Field(
        default=5, ge=1, description="Max simultaneous sandboxes per instance."
    )
    max_output_bytes: int = Field(
        default=100_000, ge=1_000, description="Truncation cap for captured output."
    )

    @field_validator("memory_mb")
    @classmethod
    def _memory_even(cls, value: int) -> int:
        # Tenki requires memory aligned to 2 MiB; fail fast with a clear message.
        if value % 2 != 0:
            raise ValueError("memory_mb must be aligned to 2 MiB (an even number)")
        return value


class UserValves(BaseModel):
    """Per-user override. A user's own key takes precedence over the admin key."""

    tenki_api_key: str = Field(
        default="",
        description="Your own Tenki API key. If set, overrides the admin key for your executions.",
    )


def _user_key(__user__: dict | None) -> str:
    """Extract a per-user Tenki key from the Open WebUI ``__user__`` payload.

    ``__user__["valves"]`` may be a ``UserValves`` instance or a plain dict.
    """
    if not __user__:
        return ""
    valves = __user__.get("valves") if isinstance(__user__, dict) else None
    if valves is None:
        return ""
    if isinstance(valves, dict):
        return (valves.get("tenki_api_key") or "").strip()
    return (getattr(valves, "tenki_api_key", "") or "").strip()


def resolve_effective_key(valves: Valves, __user__: dict | None = None) -> str:
    """Effective credential: per-user key wins, else the admin key. ``""`` if none."""
    return _user_key(__user__) or (valves.tenki_api_key or "").strip()
