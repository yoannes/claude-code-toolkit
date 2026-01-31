#!/usr/bin/env python3
"""
PostToolUse hook that tracks context gathering for /go mode Read-gate.

When /go is active and context_gathered is False, this hook flips it to True
after Read, Grep, or Glob tools are used. This unlocks the Read-gate in
plan-mode-enforcer.py, allowing Edit/Write to proceed.

Only fires on iteration 1 (first task in session). Subsequent tasks also
need to re-read before editing (context_gathered resets per task).

Hook event: PostToolUse
Matcher: Read, Grep, Glob
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import log_debug
from _state import is_go_active, load_state_file, update_state_file


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    cwd = input_data.get("cwd", "") or os.getcwd()

    if tool_name not in ("Read", "Grep", "Glob"):
        sys.exit(0)

    if not is_go_active(cwd):
        sys.exit(0)

    state = load_state_file(cwd, "go-state.json")
    if not state:
        sys.exit(0)

    # Only track on first iteration and when not already gathered
    if state.get("context_gathered", True):
        sys.exit(0)

    # Flip context_gathered to True
    update_state_file(cwd, "go-state.json", {"context_gathered": True})

    log_debug(
        f"Context gathered via {tool_name} - Read-gate unlocked",
        hook_name="go-context-tracker",
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
