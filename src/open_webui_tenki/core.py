"""Shared async execution core.

Both entry points (the Tool and the Action) delegate to :func:`execute` so their
results are identical. One fresh, isolated Tenki microVM per run; egress off
unless enabled; bounded concurrency; guaranteed teardown; timeout enforced.
"""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
from os.path import splitext

from tenki_sandbox import AsyncSandbox

from .config import Valves
from .constants import (
    IMAGE_MIME_TYPES,
    MAX_IMAGE_BYTES,
    OUTPUT_DIR,
    RESULT_FILENAME,
    SANDBOX_LIFETIME_BUFFER,
)
from .languages import build_run_plan
from .result import ExecutionResult

# One semaphore per concurrency bound, created lazily on the running loop. Caps
# simultaneous sandboxes per instance without serializing independent users.
_semaphores: dict[int, asyncio.Semaphore] = {}


def _get_semaphore(limit: int) -> asyncio.Semaphore:
    sem = _semaphores.get(limit)
    if sem is None:
        sem = asyncio.Semaphore(limit)
        _semaphores[limit] = sem
    return sem


@dataclass
class CodeExecutionRequest:
    """A resolved request to execute one snippet."""

    code: str
    language: str
    valves: Valves
    api_key: str  # already-resolved effective key ("" means unconfigured)


def _decode_capped(data: bytes, cap: int) -> tuple[str, bool]:
    """Decode bytes as UTF-8 (multi-byte-safe on truncation), capped at ``cap``."""
    if data is None:
        return "", False
    truncated = len(data) > cap
    if truncated:
        data = data[:cap]
    return data.decode("utf-8", errors="replace"), truncated


async def _collect_images(sandbox: AsyncSandbox) -> list[str]:
    """Read image files from the per-run output dir and return base64 data URIs."""
    try:
        entries = await sandbox.fs.list(OUTPUT_DIR)
    except Exception:
        return []  # dir absent / unreadable — no images

    uris: list[str] = []
    total = 0
    for entry in sorted(entries, key=lambda e: e.path):
        if getattr(entry, "is_dir", False):
            continue
        mime = IMAGE_MIME_TYPES.get(splitext(entry.path)[1].lower())
        if mime is None:
            continue
        try:
            raw = await sandbox.fs.read_bytes(f"{OUTPUT_DIR}/{entry.path}")
        except Exception:
            continue
        total += len(raw)
        if total > MAX_IMAGE_BYTES:
            break
        encoded = base64.b64encode(raw).decode("ascii")
        uris.append(f"data:{mime};base64,{encoded}")
    return uris


async def _run_in_sandbox(sandbox: AsyncSandbox, request: CodeExecutionRequest):
    """Write the code, ensure the output dir, and exec. Returns the CommandResult."""
    plan = build_run_plan(request.language, request.code)
    # Create the output dir via exec (runs as the sandbox user) rather than the fs
    # RPC (runs as the guest agent / root), so the code can write images into it.
    await sandbox.exec("mkdir", "-p", OUTPUT_DIR)
    for name, content in plan.files.items():
        await sandbox.fs.write_text(name, content)
    return await sandbox.exec(*plan.argv, timeout=request.valves.timeout_seconds)


async def execute(request: CodeExecutionRequest) -> ExecutionResult:
    """Provision a fresh Tenki sandbox, run code, collect output, always tear down."""
    if not request.api_key:
        return ExecutionResult(
            error=(
                "No Tenki API key configured. Set 'tenki_api_key' in the plugin "
                "settings (Valves) or your personal settings (UserValves)."
            )
        )

    try:
        build_run_plan(request.language, request.code)  # validate language early
    except ValueError as err:
        return ExecutionResult(error=str(err))

    valves = request.valves
    async with _get_semaphore(valves.max_concurrent_executions):
        return await _provision_and_run(request)


async def _provision_and_run(request: CodeExecutionRequest) -> ExecutionResult:
    valves = request.valves
    started = time.monotonic()

    try:
        sandbox = await AsyncSandbox.create(
            auth_token=request.api_key,
            base_url=valves.tenki_api_endpoint,  # data goes only to the configured endpoint
            workspace_id=valves.tenki_workspace_id or None,
            project_id=valves.tenki_project_id or None,
            cpu_cores=valves.cpu_cores,
            memory_mb=valves.memory_mb,
            disk_size_gb=valves.disk_size_gb,
            allow_outbound=valves.network_egress,  # egress off by default
            image=valves.sandbox_image or None,
            max_duration=valves.timeout_seconds + SANDBOX_LIFETIME_BUFFER,
        )
    except Exception as err:  # provisioning / auth / quota — execution never ran
        return ExecutionResult(error=f"Sandbox provisioning failed: {err}")

    timed_out = False
    exec_result = None
    images: list[str] = []
    result_text = ""
    run_error: str | None = None
    try:
        try:
            exec_result = await asyncio.wait_for(
                _run_in_sandbox(sandbox, request),
                timeout=valves.timeout_seconds + 5,
            )
        except TimeoutError:
            timed_out = True
        except Exception as err:  # SDK/run failure — surface, don't crash the caller
            run_error = f"Execution failed: {err}"
        # Guest-side timeout returns a CommandResult; treat a full-window run as timed out.
        if exec_result is not None and (time.monotonic() - started) >= valves.timeout_seconds - 0.5:
            timed_out = True

        if run_error is None:
            try:
                images = await _collect_images(sandbox)
            except Exception:
                images = []
            try:  # REPL-style last-expression echo (Python runner writes this)
                result_text = (await sandbox.fs.read_text(RESULT_FILENAME)).strip()
            except Exception:
                result_text = ""
    finally:
        try:
            await sandbox.close()  # always released (even on timeout/exception)
        except Exception:
            pass

    duration_ms = int((time.monotonic() - started) * 1000)

    if run_error is not None:
        return ExecutionResult(error=run_error, duration_ms=duration_ms)

    if exec_result is None:  # timed out before any result came back
        return ExecutionResult(
            timed_out=timed_out,
            duration_ms=duration_ms,
            images=images,
        )

    stdout, out_trunc = _decode_capped(exec_result.stdout, valves.max_output_bytes)
    stderr, err_trunc = _decode_capped(exec_result.stderr, valves.max_output_bytes)
    return ExecutionResult(
        stdout=stdout,
        stderr=stderr,
        result=result_text,
        images=images,
        exit_code=exec_result.exit_code,
        duration_ms=duration_ms,
        timed_out=timed_out,
        truncated=out_trunc or err_trunc,
    )
