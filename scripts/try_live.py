#!/usr/bin/env python3
"""Run one snippet against a real Tenki sandbox and print the result.

Exercises the same shared core the plugins use — a quick, eyeball-able live check
without needing Open WebUI. Any collected images are written to ``./live_out/``.

Usage:
    export TENKI_API_KEY=sk-...
    # optional: export TENKI_API_ENDPOINT=https://api.tenki.cloud

    python scripts/try_live.py                          # default demo snippet
    python scripts/try_live.py -l shell -c 'uname -a'
    python scripts/try_live.py -f path/to/snippet.py
    python scripts/try_live.py --egress -c 'import urllib.request; ...'
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import sys
from pathlib import Path

# Allow running from a checkout without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tenki_open_webui.config import Valves  # noqa: E402
from tenki_open_webui.core import CodeExecutionRequest, execute  # noqa: E402

_DEFAULT_CODE = """\
import sys
print("python:", sys.version.split()[0])
print("sum 1..5 =", sum(range(1, 6)))
"""


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run a snippet in a live Tenki sandbox.")
    parser.add_argument("-l", "--language", default="python", choices=["python", "shell"])
    parser.add_argument("-c", "--code", help="Inline code to run.")
    parser.add_argument("-f", "--file", help="Path to a file whose contents to run.")
    parser.add_argument("-t", "--timeout", type=int, default=60)
    parser.add_argument("--egress", action="store_true", help="Enable sandbox network egress.")
    args = parser.parse_args()

    key = os.getenv("TENKI_API_KEY", "")
    if not key:
        print("ERROR: set TENKI_API_KEY", file=sys.stderr)
        return 2

    if args.file:
        code = Path(args.file).read_text()
    elif args.code:
        code = args.code
    else:
        code = _DEFAULT_CODE

    valves = Valves(
        tenki_api_key=key,
        tenki_api_endpoint=os.getenv("TENKI_API_ENDPOINT", "https://api.tenki.cloud"),
        timeout_seconds=args.timeout,
        network_egress=args.egress,
    )
    request = CodeExecutionRequest(code=code, language=args.language, valves=valves, api_key=key)

    print(f"→ running {args.language} against {valves.tenki_api_endpoint} …\n")
    result = await execute(request)

    print("── result " + "─" * 50)
    print(result.to_model_text())
    print("─" * 60)

    if result.images:
        out_dir = Path("live_out")
        out_dir.mkdir(exist_ok=True)
        for i, uri in enumerate(result.images):
            data = base64.b64decode(uri.split(",", 1)[1])
            ext = uri.split("/", 1)[1].split(";", 1)[0]
            path = out_dir / f"image_{i:02d}.{ext}"
            path.write_bytes(data)
            print(f"saved {path}")

    return 0 if result.error is None else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
