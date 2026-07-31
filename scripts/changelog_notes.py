#!/usr/bin/env python3
"""Print a version's CHANGELOG.md section, for use as GitHub release notes.

Usage:
    python scripts/changelog_notes.py              # the version in pyproject.toml
    python scripts/changelog_notes.py 0.1.0        # an explicit version

Writes the section body (everything under the version's heading, up to the next
level-2 heading) to stdout, so the release workflow can hand it to
``gh release create --notes-file``. That yields notes written for operators
instead of ``--generate-notes``' commit list.

Exits non-zero when the section is missing *or* empty. ``check_changelog.py``
only asserts a heading exists — a heading with nothing under it satisfies it —
so this closes that gap at the point where it actually costs something: an
empty section would otherwise publish a release with blank notes.
"""

from __future__ import annotations

import re
import sys

from check_changelog import CHANGELOG, heading_pattern, pyproject_version

NEXT_HEADING = re.compile(r"^##\s", re.MULTILINE)


def section(text: str, version: str) -> str:
    """The body of ``version``'s section, without its heading."""
    match = heading_pattern(version).search(text)
    if not match:
        sys.exit(f"CHANGELOG.md has no section for {version}")

    body = text[match.end() :]
    # Stop at the next version heading; the newest section runs to end of file.
    following = NEXT_HEADING.search(body)
    return (body[: following.start()] if following else body).strip()


def main() -> None:
    version = sys.argv[1].lstrip("v") if len(sys.argv) > 1 else pyproject_version()

    if not CHANGELOG.exists():
        sys.exit("CHANGELOG.md is missing")

    body = section(CHANGELOG.read_text(), version)
    if not body:
        sys.exit(f"CHANGELOG.md's {version} section is empty; release notes would be blank")

    print(body)


if __name__ == "__main__":
    main()
