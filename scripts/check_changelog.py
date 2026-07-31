#!/usr/bin/env python3
"""Assert the declared version is documented in CHANGELOG.md.

Usage:
    python scripts/check_changelog.py

Exits non-zero when `pyproject.toml` declares a version that `CHANGELOG.md` does
not document.

This asserts a standing invariant — whatever version is declared right now is
documented right now — rather than diffing the branch against a base ref to
detect a bump. The diff approach needs `fetch-depth: 0`, breaks on force-pushes,
and false-fires on a change that reverts a bump; the invariant gives the same
protection with none of that. It stays green while the version is untouched and
goes red the moment the version is bumped without an entry.

Accepted heading forms (level-2, optionally bracketed and/or `v`-prefixed, with
an optional trailing date or label):

    ## 0.1.0
    ## v0.1.0
    ## [0.1.0] - 2026-01-31
    ## 0.1.0 — unreleased

Matching is anchored to a heading, so a passing mention of the version in prose
does not satisfy it. Known limit: this checks that a section *exists*, not that
it says anything useful — a heading with nothing under it passes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"


def pyproject_version() -> str:
    """The version declared in pyproject.toml."""
    text = (ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        sys.exit("could not find version in pyproject.toml")
    return match.group(1)


def heading_pattern(version: str) -> re.Pattern[str]:
    """Match the level-2 changelog heading that opens ``version``'s section.

    The version must end the heading or be followed by whitespace, so looking up
    0.1.1 never matches a "## 0.1.10" heading. Shared with
    ``changelog_notes.py`` so both agree on what counts as a section.
    """
    return re.compile(rf"^##\s+\[?v?{re.escape(version)}\]?(?:\s.*)?$", re.MULTILINE)


def _documents(text: str, version: str) -> bool:
    return heading_pattern(version).search(text) is not None


def main() -> None:
    version = pyproject_version()

    if not CHANGELOG.exists():
        sys.exit("CHANGELOG.md is missing; every released version must be documented")

    if not _documents(CHANGELOG.read_text(), version):
        sys.exit(
            f"pyproject.toml is at {version} but CHANGELOG.md has no entry for it\n\n"
            "Add a section to CHANGELOG.md before releasing:\n\n"
            f"  ## {version} — <YYYY-MM-DD>\n"
        )

    print(f"changelog OK: {version} is documented")


if __name__ == "__main__":
    main()
