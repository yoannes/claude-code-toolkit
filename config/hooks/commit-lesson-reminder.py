#!/usr/bin/env python3
"""PreToolUse hook: Remind model about memory-worthy commit messages.

Fires before git commit commands to encourage LESSON: prefixes and
memory citation in commit messages.
"""

import json
import re
import sys

GIT_COMMIT_PATTERNS = [
    r"\bgit\s+commit\b",
]


def main():
    input_data = json.loads(sys.stdin.read())
    tool_name = input_data.get("tool_name", "")

    if tool_name != "Bash":
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Check if this is a git commit
    is_commit = any(re.search(p, command, re.IGNORECASE) for p in GIT_COMMIT_PATTERNS)
    if not is_commit:
        sys.exit(0)

    reminder = (
        "[memory] Commit auto-captured to memory. "
        "Include LESSON: prefix for reusable insights. "
        "If m1-mN helped, mention for citation credit."
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "approve",
            "additionalContext": reminder,
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
