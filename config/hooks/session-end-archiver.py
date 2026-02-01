#!/usr/bin/env python3
"""
SessionEnd Hook - Raw Transcript Safety Net

Archives the raw transcript on ANY session exit (clean stop, Ctrl+C,
crash, context exhaustion). This ensures no session data is lost even
when the Stop hook doesn't fire.

Part of the Compound Memory System that enables cross-session learning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add hooks directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent))

from _common import log_debug


def main():
    input_data = json.loads(sys.stdin.read() or "{}")
    cwd = input_data.get("cwd", "")

    if not cwd:
        sys.exit(0)

    try:
        from _memory import archive_raw_transcript

        archive_raw_transcript(cwd)
        log_debug(
            "Raw transcript archived at SessionEnd",
            hook_name="session-end-archiver",
        )
    except ImportError:
        log_debug(
            "Cannot import _memory module",
            hook_name="session-end-archiver",
        )
    except Exception:
        pass  # SessionEnd hooks must not fail

    sys.exit(0)


if __name__ == "__main__":
    main()
