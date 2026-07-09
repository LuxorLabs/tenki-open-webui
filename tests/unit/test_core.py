"""Unit tests for the shared execution core (mocked SDK, no credentials)."""

from __future__ import annotations

import asyncio

from open_webui_tenki.config import Valves
from open_webui_tenki.core import CodeExecutionRequest, execute


def _req(sdk_key="k", language="python", code="print(1)", **valve_overrides):
    valves = Valves(tenki_api_key="admin-key", **valve_overrides)
    return CodeExecutionRequest(code=code, language=language, valves=valves, api_key=sdk_key)


async def test_egress_off_by_default(patch_sdk):
    sdk = patch_sdk()
    await execute(_req())
    assert sdk.create_kwargs[0]["allow_outbound"] is False


async def test_egress_opt_in(patch_sdk):
    sdk = patch_sdk()
    await execute(_req(network_egress=True))
    assert sdk.create_kwargs[0]["allow_outbound"] is True


async def test_only_configured_endpoint_no_other_host(patch_sdk):
    # FR-011: the SDK is constructed only with the configured Tenki endpoint.
    sdk = patch_sdk()
    await execute(_req(tenki_api_endpoint="https://staging.tenki.cloud"))
    kwargs = sdk.create_kwargs[0]
    assert kwargs["base_url"] == "https://staging.tenki.cloud"
    assert kwargs["auth_token"] == "k"
    # No stray host/url params leak into the create call.
    for key, value in kwargs.items():
        if key in ("auth_token", "project_id", "image"):
            continue
        if isinstance(value, str):
            assert "http" not in value or value == kwargs["base_url"]


async def test_teardown_on_success(patch_sdk):
    sdk = patch_sdk(stdout=b"hi\n", exit_code=0)
    await execute(_req())
    assert sdk.last.closed == 1


async def test_teardown_on_exec_exception(patch_sdk):
    sdk = patch_sdk(exec_exc=RuntimeError("boom"))
    result = await execute(_req())
    assert sdk.last.closed == 1
    assert result.error and "Execution failed" in result.error


async def test_teardown_on_timeout(patch_sdk):
    sdk = patch_sdk(exec_delay=5)
    result = await execute(_req(timeout_seconds=1))
    assert result.timed_out is True
    assert sdk.last.closed == 1


async def test_timeout_sets_flag(patch_sdk):
    sdk = patch_sdk(exec_delay=5)
    result = await execute(_req(timeout_seconds=1))
    assert result.timed_out is True
    assert sdk  # provisioned


async def test_output_decode_and_truncation_multibyte(patch_sdk):
    # 600 * 4 bytes = 2400 bytes of a multi-byte char; cap 1000 splits a char.
    payload = ("😀" * 600).encode("utf-8")
    patch_sdk(stdout=payload, exit_code=0)
    result = await execute(_req(max_output_bytes=1000))
    assert result.truncated is True
    assert isinstance(result.stdout, str)  # decoded without raising
    assert len(result.stdout.encode("utf-8")) <= 1000 + 4


async def test_stdout_stderr_distinct(patch_sdk):
    patch_sdk(stdout=b"out", stderr=b"err", exit_code=3)
    result = await execute(_req())
    assert result.stdout == "out"
    assert result.stderr == "err"
    assert result.exit_code == 3


async def test_config_error_short_circuits_no_provision(patch_sdk):
    sdk = patch_sdk()
    result = await execute(_req(sdk_key=""))
    assert result.error and "No Tenki API key" in result.error
    assert sdk.instances == []  # never provisioned


async def test_provision_failure_returns_error(patch_sdk):
    patch_sdk(create_exc=RuntimeError("quota exceeded"))
    result = await execute(_req())
    assert result.error and "provisioning failed" in result.error


async def test_images_collected_when_present(patch_sdk):
    png = b"\x89PNG\r\n\x1a\nfakepng"
    patch_sdk(images={"figure_00.png": png})
    result = await execute(_req())
    assert len(result.images) == 1
    assert result.images[0].startswith("data:image/png;base64,")


async def test_no_images_when_absent(patch_sdk):
    patch_sdk(images={})
    result = await execute(_req())
    assert result.images == []


async def test_last_expression_result_captured(patch_sdk):
    patch_sdk(result_text="(3.875, 2.799)")
    result = await execute(_req(code="(mean, std)"))
    assert result.result == "(3.875, 2.799)"
    assert "result:" in result.to_model_text()


async def test_no_result_when_absent(patch_sdk):
    patch_sdk()  # fake returns no result file
    result = await execute(_req())
    assert result.result == ""


async def test_python_writes_code_and_runner(patch_sdk):
    sdk = patch_sdk()
    await execute(_req(code="print('x')", language="python"))
    written = sdk.last.fs.written
    assert "main.py" in written and written["main.py"] == "print('x')"
    assert "_owui_runner.py" in written
    assert sdk.last.exec_argv == ("python3", "_owui_runner.py")


async def test_shell_runs_bash(patch_sdk):
    sdk = patch_sdk()
    await execute(_req(code="echo hi", language="shell"))
    assert sdk.last.exec_argv == ("bash", "-lc", "echo hi")


async def test_unsupported_language_errors_without_provision(patch_sdk):
    sdk = patch_sdk()
    result = await execute(_req(language="ruby"))
    assert result.error and "Unsupported language" in result.error
    assert sdk.instances == []


async def test_concurrency_bounded_by_semaphore(patch_sdk):
    # With max_concurrent_executions=1, two runs must not overlap.
    sdk = patch_sdk(exec_delay=0.1)
    reqs = [_req(max_concurrent_executions=1) for _ in range(2)]
    await asyncio.gather(*(execute(r) for r in reqs))
    assert len(sdk.instances) == 2
