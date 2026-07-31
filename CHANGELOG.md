# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions track the `version:` frontmatter of both single-file distributables;
`scripts/check_version.py` keeps those in step with `pyproject.toml`, and
`scripts/check_changelog.py` requires the declared version to appear below.

## 0.1.0 — 2026-07-31

First release. Ships two self-contained Open WebUI plugins that run Python and
shell code in isolated, ephemeral [Tenki](https://tenki.cloud) microVM sandboxes:
a **Tool** (`tenki_code_execution`) the model calls itself to write code, read the
output — stdout, stderr, tracebacks, and inline charts — and iterate, and an
**Action Function** (`tenki_run_code`) that adds a **Run code** button under any
message with a code block. Both share one async execution core, so every run gets
a fresh sandbox with no state carried between runs, a timeout, and guaranteed
teardown. Network egress is off by default; the API key lives in Open WebUI's
plugin settings and is never logged, and users may supply their own key to run
executions on their own Tenki account.
