"""Git provenance shared by model metadata and decision records.

One helper so a model artifact and the decision rows it produces report the
same commit. CI exports ``GITHUB_SHA``; a workstation falls back to ``git
rev-parse``. Returns None rather than raising when neither is available (a
tarball export, a container without .git).
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache


@lru_cache(maxsize=1)
def current_git_sha() -> str | None:
    """Resolve the current commit SHA, or None when it cannot be determined."""
    env = os.environ.get("GIT_SHA") or os.environ.get("GITHUB_SHA")
    if env:
        return env.strip()[:40]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.strip()[:40]
    return sha or None
