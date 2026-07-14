#!/usr/bin/env python3
"""Assert version consistency across pyproject and both distributable frontmatters.

Usage:
    python scripts/check_version.py            # all versions must match each other
    python scripts/check_version.py v0.1.0     # ...and must match this release tag

Exits non-zero on any mismatch. Used by the release workflow (against the tag) and
runnable locally before cutting a release.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISTRIBUTABLES = [
    ROOT / "open-webui" / "tools" / "tenki_code_execution.py",
    ROOT / "open-webui" / "functions" / "tenki_run_code.py",
]


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        sys.exit("could not find version in pyproject.toml")
    return match.group(1)


def _frontmatter_version(path: Path) -> str:
    match = re.search(r"^version:\s*(.+)$", path.read_text(), re.MULTILINE)
    if not match:
        sys.exit(f"could not find 'version:' frontmatter in {path.relative_to(ROOT)}")
    return match.group(1).strip()


def _dunder_version() -> str:
    path = ROOT / "src" / "open_webui_tenki" / "__init__.py"
    match = re.search(r'__version__\s*=\s*"([^"]+)"', path.read_text())
    if not match:
        sys.exit("could not find __version__ in src/open_webui_tenki/__init__.py")
    return match.group(1)


def main() -> None:
    expected_tag = sys.argv[1].lstrip("v") if len(sys.argv) > 1 else None

    versions = {
        "pyproject.toml": _pyproject_version(),
        "src/open_webui_tenki/__init__.py": _dunder_version(),
    }
    for path in DISTRIBUTABLES:
        versions[str(path.relative_to(ROOT))] = _frontmatter_version(path)

    unique = set(versions.values())
    if len(unique) != 1:
        lines = "\n".join(f"  {name}: {ver}" for name, ver in versions.items())
        sys.exit(f"version mismatch across files:\n{lines}")

    version = unique.pop()
    if expected_tag is not None and version != expected_tag:
        sys.exit(f"release tag {expected_tag!r} != declared version {version!r}")

    print(f"version OK: {version}" + (f" (matches tag {expected_tag})" if expected_tag else ""))


if __name__ == "__main__":
    main()
