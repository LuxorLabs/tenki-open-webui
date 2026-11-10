# Contributing

## Development

The logic is written once under `src/tenki_open_webui/` and inlined into the two
single-file distributables under `open-webui/` by `scripts/build.py`. **Never edit
the files under `open-webui/` by hand** — they are generated.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ruff check src scripts tests          # lint
ruff format src scripts tests         # format
pytest tests/unit                     # unit tests (mocked SDK, no credentials)
python scripts/build.py               # regenerate the distributables
python scripts/check_changelog.py     # declared version has a CHANGELOG entry
python scripts/changelog_notes.py     # preview the release notes for that version
pipx run pip-audit .                  # known-vulnerability scan (as CI runs it)
```

After changing anything in `src/`, run `python scripts/build.py` and commit the
regenerated `open-webui/` files in the same change. CI's `build-sync` job fails
if they drift (`git diff --exit-code open-webui/`).

### Live integration tests

```bash
export TENKI_API_KEY=sk-...
# optional: export TENKI_API_ENDPOINT=https://api.tenki.cloud
pytest tests/integration              # provisions real microVMs; costs quota
python scripts/try_live.py            # ad-hoc single run; images saved to ./live_out/
```

## Cutting a release

1. Bump the version in these places (they must match — `scripts/check_version.py`
   enforces it): `pyproject.toml`, `src/tenki_open_webui/__init__.py`
   (`__version__`), and the `version:` frontmatter for both distributables (which
   lives in `scripts/build.py`).
2. Add the matching `CHANGELOG.md` section — `## X.Y.Z — YYYY-MM-DD`, newest
   first, changes grouped under Keep a Changelog headings (`### Added`,
   `### Changed`, `### Security`, …). This section becomes the release notes
   verbatim, so write it for operators. `scripts/check_changelog.py` requires the
   declared version to have an entry: CI runs it on every pull request, and the
   release workflow runs it as its first gate.
3. `python scripts/build.py` and commit the regenerated files.
4. `python scripts/check_version.py vX.Y.Z` to confirm consistency.
5. Run the **Release** workflow with `dry_run` left on. It runs every CI gate
   plus the version and changelog checks, and reports what it would tag and
   publish without touching the repo — a free rehearsal.
6. Run it again with `dry_run` off. It tags `vX.Y.Z`, creates the GitHub Release
   with the changelog section as its notes, and attaches both distributables as
   assets. (No PyPI publish — distribution is single-file via the hub.)

The workflow derives the version from `pyproject.toml`, so there's no tag to
create by hand; it refuses to run if `vX.Y.Z` already points at another commit.
Actions are pinned by commit SHA with the version in a trailing comment — update
both together.

## Publishing to the Open WebUI Community site

Both plugins are published to the [Open WebUI Community site](https://openwebui.com/)
so operators can discover them by keyword and import them in one click (imported
Tools land under **Workspace → Tools**, Functions under **Admin Panel → Functions**).

**Publish both, from the built single-file distributables** (not `src/`):

1. Build and sanity-check first: `python scripts/build.py`, `pytest tests/unit`,
   `ruff check src scripts tests`.
2. Sign in at [openwebui.com](https://openwebui.com/).
3. **Tool** — create a new Tool and paste the full contents of
   `open-webui/tools/tenki_code_execution.py`.
4. **Function** — create a new Function (Action) and paste the full contents of
   `open-webui/functions/tenki_run_code.py`.
5. Link both listings back to this repository, and keep the version in the
   listing in sync with the file's frontmatter `version:`.

### Discovery

Listings are found via keyword [search](https://openwebui.com/search). The
frontmatter `title` + `description` are the searchable text, so keep them
keyword-rich — both descriptions cover **code execution, code interpreter,
sandbox, python, shell, isolated, microVM**. Don't shorten the descriptions when
publishing.

### What to know before publishing

- **Listings are unaudited.** Being listed/featured on the community site is not
  an endorsement — reviewers are expected to read the source before importing. So
  keep the distributables readable and the `README` clear; that is what earns
  trust. (Ours: secrets only in Valves, never logged; fully `async` handlers;
  documented security posture — all in line with Open WebUI's sharing guidance.)
- **`requirements:` installs at load time.** Open WebUI pip-installs
  `luxor-ai[async]` on import. This requires that version to be published on
  PyPI. Note for operators: in multi-replica deployments, runtime installs can
  race across workers — they can set
  `ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS=False` and bake the dependency into
  their image instead. (Worth a line in the README's install notes.)

### Optional: docs PR

Consider opening a PR against [`open-webui/docs`](https://github.com/open-webui/docs)
adding a short tutorial that references this plugin, to index "Tenki" as a
code-execution backend for Open WebUI.
