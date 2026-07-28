# Testing & End-to-End Validation

This plugin is validated at three layers, from fastest/cheapest to most realistic.

| Layer | What it proves | Credentials |
| --- | --- | --- |
| **Unit** (`tests/unit`) | Logic, config, rendering, build integrity — against a mocked SDK | none |
| **Live integration** (`tests/integration`) | The real path: provisioning, exec, output capture, image collection, timeout, teardown — against real microVMs | `TENKI_API_KEY` |
| **Full Open WebUI** (Docker) | The end-user experience: import, configure, and run from the UI | `TENKI_API_KEY` + an LLM (for the Tool) |

## 1. Unit tests (no credentials)

```bash
pip install -e ".[dev]"
pytest tests/unit          # ~45 tests, mocked SDK
ruff check src scripts tests
ruff format --check src scripts tests
python scripts/build.py    # regenerate the single-file distributables
```

The unit suite covers: egress-off-by-default, data sent only to the configured
endpoint, guaranteed teardown (success / exception / timeout), timeout handling,
UTF-8 truncation, credential precedence, config-error short-circuit (no
provisioning), image collection, code-block extraction, and that the built
distributables are self-contained.

## 2. Live integration tests (real sandboxes)

These provision real microVMs, so they cost quota and take a few seconds each.
They are **skipped automatically** when `TENKI_API_KEY` is unset, so CI stays
green without secrets.

```bash
export TENKI_API_KEY=sk-...
# optional, for a self-hosted or non-default deployment:
# export TENKI_API_ENDPOINT=https://api.tenki.cloud

pytest tests/integration -v          # full gated suite
python scripts/try_live.py           # ad-hoc single run; images saved to ./live_out/
python scripts/try_live.py -l shell -c 'uname -a'
```

What the live suite validates end-to-end:

- **Python** and **shell** execution with correct stdout.
- **Tracebacks** captured on error (stderr distinct from stdout).
- **Timeout** terminates the run and returns a clear timed-out result.
- **Image collection** — a file written to the per-run output directory is
  returned as an inline base64 data URI.
- **matplotlib auto-capture** — open figures are saved and returned without any
  prompt instruction (skips automatically if the sandbox image lacks matplotlib).
- **Both entry points** — the model-invoked **Tool** and the user-invoked
  **Action** produce equivalent results through the shared core.
- **No leaked sandboxes** — every run's sandbox is torn down (verified by
  snapshotting running sessions before/after).

> **Self-hosted / private-CA note.** The gRPC client uses its own trust store and
> DNS resolver. If you point `TENKI_API_ENDPOINT` at an instance served with a
> private/internal CA, set `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH` to your CA bundle.
> If the API hostname resolves only via a non-standard system resolver, set
> `GRPC_DNS_RESOLVER=native`. Neither is needed for the default public endpoint.

### How this was validated

The live suite was run against a real Tenki account: Python and shell snippets,
an error/traceback case, a timeout, an inline-image round-trip, and both the Tool
and Action paths — each confirming the sandbox was provisioned fresh, produced
correct output, and was torn down with no leak.

## 3. Full Open WebUI (Docker)

Run the real platform and drive the plugin from the UI. This is the most
realistic check and the source of demo screenshots.

### Run Open WebUI

```bash
docker run -d -p 3000:8080 \
  -v open-webui:/app/backend/data \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

Open <http://localhost:3000> and create the first (admin) account.

> Open WebUI installs the plugin's declared `tenki[async]` dependency
> automatically on import (from the `requirements:` frontmatter) — no manual
> install, no restart.

### Import and configure

1. **Tool** — Workspace → Tools → **+** → paste
   `open-webui/tools/tenki_code_execution.py` → save.
2. **Action** (optional) — Admin Panel → Functions → **+** → paste
   `open-webui/functions/tenki_run_code.py` → save.
3. Open the plugin's **Valves** and paste your `tenki_api_key`. Optionally adjust
   resources, `timeout_seconds`, `network_egress`, and `sandbox_image`.

### Drive it

- **Tool (agentic).** Enable the Tool for a tool-calling-capable model, then ask a
  computation question — e.g. *"Use the code tool to compute the mean of
  \[3, 1, 4, 1, 5, 9] and show the code."* The model runs code in a sandbox and
  answers with the executed result.
- **Action (manual).** Under any assistant message containing a fenced code
  block, click **Run code**. The output appears inline; edit the block and click
  again for fresh output. (The Action needs no LLM.)

### Charts / matplotlib

The plugin captures matplotlib figures automatically (no prompt needed), but the
**sandbox image must include matplotlib**. A minimal base image may not. To render
charts, point the `sandbox_image` valve at an image/template that has matplotlib
(and numpy), or install it as part of the run if your image includes a package
manager.

## Definition of done (maps to success criteria)

- [ ] Computation prompt returns a correct executed answer, including an inline
      chart for a plotting prompt.
- [ ] The **Run code** button executes and re-runs a code block.
- [ ] Two runs cannot observe each other's state (fresh sandbox each time).
- [ ] Sandboxes are always torn down; none orphaned.
- [ ] Misconfiguration yields a clear error, never a crash.
- [ ] Both a Tool and an Action ship and function.
