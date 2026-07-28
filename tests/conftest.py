"""Shared test fixtures: a fake async Tenki SDK (no credentials, no network)."""

from __future__ import annotations

import asyncio

import pytest

from open_webui_tenki.constants import OUTPUT_DIR


class FakeEntry:
    """Mimics tenki FileInfo for fs.list()."""

    def __init__(self, name: str, is_dir: bool = False, size: int = 0):
        self.path = name
        self.is_dir = is_dir
        self.size = size


class FakeCommandResult:
    """Mimics tenki CommandResult (stdout/stderr are bytes)."""

    def __init__(
        self,
        stdout: bytes = b"",
        stderr: bytes = b"",
        exit_code: int = 0,
        signal: str | None = None,
        reason: str | None = None,
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.signal = signal
        self.reason = reason

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.signal


class FakeFS:
    def __init__(self, images: dict[str, bytes], result_text: str | None = None):
        self.images = images
        self.result_text = result_text
        self.written: dict[str, str] = {}
        self.mkdirs: list[str] = []

    async def write_text(self, path, text, **kw):
        self.written[path] = text

    async def write_bytes(self, path, data):
        self.written[path] = data

    async def mkdir(self, path, **kw):
        self.mkdirs.append(path)

    async def list(self, path, **kw):
        if path == OUTPUT_DIR:
            return [FakeEntry(name, size=len(data)) for name, data in self.images.items()]
        raise FileNotFoundError(path)

    async def read_bytes(self, path):
        return self.images[path.split("/", 1)[1]]

    async def read_text(self, path, **kw):
        from open_webui_tenki.constants import RESULT_FILENAME

        if path == RESULT_FILENAME and self.result_text is not None:
            return self.result_text
        raise FileNotFoundError(path)


class FakeSandbox:
    def __init__(self, sdk: FakeSDK, create_kwargs: dict):
        self._sdk = sdk
        self.create_kwargs = create_kwargs
        self.fs = FakeFS(sdk.images, sdk.result_text)
        self.closed = 0
        self.exec_argv: tuple = ()
        self.exec_timeout = None

    async def exec(self, *argv, timeout=None, **kw):
        self.exec_argv = argv
        self.exec_timeout = timeout
        if self._sdk.exec_exc is not None:
            raise self._sdk.exec_exc
        if self._sdk.exec_delay:
            await asyncio.sleep(self._sdk.exec_delay)
        return FakeCommandResult(
            stdout=self._sdk.stdout,
            stderr=self._sdk.stderr,
            exit_code=self._sdk.exit_code,
        )

    async def close(self):
        self.closed += 1


class FakeSDK:
    """Stand-in for tenki.AsyncSandbox; patched into core."""

    def __init__(
        self,
        *,
        stdout=b"ok\n",
        stderr=b"",
        exit_code=0,
        exec_exc=None,
        exec_delay=0.0,
        images=None,
        create_exc=None,
        result_text=None,
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.exec_exc = exec_exc
        self.exec_delay = exec_delay
        self.images = images or {}
        self.create_exc = create_exc
        self.result_text = result_text
        self.instances: list[FakeSandbox] = []
        self.create_kwargs: list[dict] = []

    async def create(self, **kwargs):
        self.create_kwargs.append(kwargs)
        if self.create_exc is not None:
            raise self.create_exc
        sb = FakeSandbox(self, kwargs)
        self.instances.append(sb)
        return sb

    @property
    def last(self) -> FakeSandbox:
        return self.instances[-1]


@pytest.fixture
def patch_sdk(monkeypatch):
    """Return a factory that installs a configured FakeSDK into the core module."""

    def _apply(**cfg) -> FakeSDK:
        sdk = FakeSDK(**cfg)
        monkeypatch.setattr("open_webui_tenki.core.AsyncSandbox", sdk)
        return sdk

    return _apply
