#!/usr/bin/env python3
"""PostToolUse hook: Remind model to cite memories when editing files.

Fires once per session on first Edit/Write to remind about memory citation.
Throttled via session_id marker to avoid spam.
"""

import json
import os
import sys
from pathlib import Path


def main():
    input_data = json.loads(sys.stdin.read())
    tool_name = input_data.get("tool_name", "")

    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    cwd = input_data.get("cwd", os.getcwd())
    project_claude = Path(cwd) / ".claude"

    # Check if memories were injected
    injection_log = project_claude / "injection-log.json"
    if not injection_log.exists():
        sys.exit(0)

    try:
        log_data = json.loads(injection_log.read_text())
        events = log_data.get("events", [])
        if not events:
            sys.exit(0)
    except Exception:
        sys.exit(0)

    # Throttle: only remind once per session
    reminded_marker = project_claude / "citation-reminded.json"
    session_id = log_data.get("session_id", "")

    if reminded_marker.exists():
        try:
            marker_data = json.loads(reminded_marker.read_text())
            if marker_data.get("session_id") == session_id:
                sys.exit(0)  # Already reminded this session
        except Exception:
            pass

    # Write marker
    reminded_marker.write_text(json.dumps({"session_id": session_id}))

    # Build reminder
    ref_count = len(events)
    reminder = (
        f"[memory] {ref_count} memories (m1-m{ref_count}) injected. "
        f"If any helped, include in memory_that_helped at stop."
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": reminder,
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
