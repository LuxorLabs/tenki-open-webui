# Open WebUI Tenki — Code Execution in Isolated microVM Sandboxes

Run **Python and shell code** from [Open WebUI](https://openwebui.com) inside
**isolated, ephemeral [Tenki](https://tenki.cloud) microVM sandboxes** — a secure
code interpreter / code execution sandbox that keeps arbitrary, LLM- or
user-written code off your Open WebUI host.

This repository ships two self-contained plugins that share one async execution
core (mirroring the shape of `EtiennePerot/safe-code-execution`):

- **Tool** — `open-webui/tools/tenki_code_execution.py`: an LLM-callable code
  executor. The model writes code, runs it in a fresh sandbox, reads the output
  (stdout, stderr, tracebacks, and inline charts), and iterates — autonomously.
- **Action Function** — `open-webui/functions/tenki_run_code.py`: a **Run code**
  button under a message that executes its code block, streams the output back
  inline, and replaces the previous output on re-run.

Each execution runs in a **fresh, isolated microVM** with **no state carried
between runs**, is **non-blocking** (async), enforces a **timeout**, and is
**always torn down** afterward — so sandboxes never accumulate.

## Security posture

- **Network egress is OFF by default.** Sandboxes are created without outbound
  network access; enable it explicitly with the `network_egress` valve only if
  you trust the code being run.
- **Isolation.** Every run gets its own ephemeral microVM, separate from the
  Open WebUI host and from every other run. Two runs cannot observe each other's
  files or memory.
- **Your credential, your account.** Executions run on **your own Tenki
  account** using **your own API key** — Tenki does not host or operate any
  shared execution infrastructure for this integration. You are responsible for
  the code your users and models run and for the resulting Tenki usage.
- **Secrets.** The API key is stored in Open WebUI's plugin settings server-side.
  It is never logged, echoed in output, or embedded in error messages.
- **Data flow.** Code and data are sent **only** to the configured Tenki
  endpoint — never to any other third party.

## Install (operator)

1. **Get a Tenki API key** at [app.tenki.cloud](https://app.tenki.cloud).
2. **Import the plugin** into Open WebUI:
   - **Tool** — Workspace → Tools → import _Tenki Sandbox — Code Execution_ from
     the [community hub](https://openwebui.com), or paste the contents of
     `open-webui/tools/tenki_code_execution.py`.
   - **Action** (optional) — Admin Panel → Functions → import _Tenki Run Code_,
     or paste the contents of `open-webui/functions/tenki_run_code.py`.
   - Open WebUI installs the declared `tenki[async]` dependency
     automatically on import — no manual `pip install`, no server restart.
     _(Multi-replica deployments may prefer to bake the dependency into their
     image and set `ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS=False` to avoid
     per-worker install races.)_
3. **Configure** (open the plugin's ⚙️ settings / Valves): paste your
   `tenki_api_key`. Optionally adjust resources, `timeout_seconds`, and
   `network_egress`.
4. **Use it**:
   - **Agentic (Tool)**: enable the Tool for a model, then ask a computation
     question ("plot the trend in this data"). The model runs code in a Tenki
     microVM and answers, including inline charts.
   - **Manual (Action)**: click **Run code** under any assistant message that
     contains a code block; the output appears inline. Edit the block and click
     again for fresh output.

### Smoke test

- _"Run Python that prints the numbers 1–5 and their sum."_ → `1 2 3 4 5` and `15`.
- _"Plot y = x² for x in 0..10 with matplotlib."_ → an inline chart image.
- _"Run `raise ValueError('boom')`."_ → the traceback is returned, not a crash.

## Configuration (Valves)

| Setting | Default | Description |
| --- | --- | --- |
| `tenki_api_key` | _(empty)_ | **Required** (unless every user sets their own). Instance-wide Tenki key. |
| `tenki_api_endpoint` | `https://api.tenki.cloud` | Override for self-hosted / staging. |
| `tenki_workspace_id` | _(empty)_ | Optional workspace scope; uses the account default when empty. |
| `default_language` | `python` | `python` or `shell`, used when the caller doesn't specify. |
| `cpu_cores` / `memory_mb` / `disk_size_gb` | `1` / `512` / `5` | Sandbox resource size (disk 5–100 GiB). |
| `timeout_seconds` | `300` | Max execution time per run (1–600). |
| `network_egress` | `false` | Allow outbound network. **Off by default.** |
| `sandbox_image` | _(SDK default)_ | Optional image/template ref providing `python3` + `bash`. |
| `max_concurrent_executions` | `5` | Cap on simultaneous sandboxes per instance. |
| `max_output_bytes` | `100000` | Truncation cap for captured output. |

### Per-user keys (UserValves)

Each user may set their **own** Tenki key under their personal plugin settings.
When present, the user's key overrides the admin key and their executions run on
and attribute to **their** account:

```
effective key = UserValves.tenki_api_key or Valves.tenki_api_key
```

If neither is set, an execution returns a clear configuration error — it never
crashes or silently does nothing.

## Sandbox image & libraries

Everything your code runs against — the Python version, the shell, and the
available libraries — comes from the **Tenki sandbox image**, not from this
plugin. The `requirements:` frontmatter only installs the plugin's own dependency
(`tenki[async]`) on the Open WebUI host; it does **not** add packages to
the sandbox.

The default image ships a common set of libraries. To use a different set, point
the **`sandbox_image`** valve at an image/template that includes what you need —
this is the recommended approach: the libraries are present immediately, every
run is fast, and no network access is required.

### Installing an extra library at runtime

For the occasional one-off, code can install a package itself as part of the run.
This needs **`network_egress` enabled** (off by default) and an image that has a
package manager. Because each execution is a fresh sandbox, the install happens on
every run — fine for a quick experiment, but for anything regular, bake it into an
image instead.

```python
# Requires network_egress = true in the plugin settings.
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "<package>"], check=True)

import <package>
# ... use it ...
```

For a system package on an image with `apt`, the equivalent is
`sudo apt-get update && sudo apt-get install -y <package>` (also requires egress).

## Develop & test

```bash
git clone https://github.com/LuxorLabs/open-webui-tenki
cd open-webui-tenki
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Unit tests (no credentials; mocked SDK)
pytest tests/unit

# Integration tests (live; needs a real key)
export TENKI_API_KEY=sk-...
pytest tests/integration

# Rebuild the self-contained distributable(s)
python scripts/build.py
```

### Architecture

The logic lives once in `src/open_webui_tenki/` (`config.py`, `result.py`,
`languages.py`, `core.py`, plus the `tool.py` entry point). `scripts/build.py`
**inlines** that core into each single-file distributable under `open-webui/`,
so hub users can one-click import a self-contained file. Edit `src/`, then run
`python scripts/build.py` — CI verifies the committed distributables match the
source.

## License

MIT — see [LICENSE](./LICENSE).
