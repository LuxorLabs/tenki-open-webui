"""Shared constants for the Tenki code-execution plugin.

Filesystem paths are **relative to the sandbox workdir** (the Tenki SDK restricts
``sb.fs`` reads/writes to the workdir, e.g. ``/home/tenki``), so a bare
directory name resolves inside the workdir regardless of the sandbox image.
"""

# Per-run output directory (workdir-relative). Images the code writes here — and,
# for Python, any auto-captured matplotlib figures — are collected after the run.
OUTPUT_DIR = "owui_tenki_out"

# Files written into the sandbox for Python runs.
CODE_FILENAME = "main.py"
RUNNER_FILENAME = "_owui_runner.py"

# Where the Python runner writes the repr of the last top-level expression, if any
# (REPL/notebook-style echo). Collected into ExecutionResult.result. Workdir-relative.
RESULT_FILENAME = "owui_tenki_result.txt"

# Extension -> MIME type for building inline base64 data: URIs.
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# Upper bound on the total base64 image payload returned from a single run, so a
# run that writes many/large images cannot balloon the response.
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Extra lifetime (seconds) granted to the sandbox beyond the execution timeout,
# as a backstop so an abandoned run cannot leak past teardown.
SANDBOX_LIFETIME_BUFFER = 30
