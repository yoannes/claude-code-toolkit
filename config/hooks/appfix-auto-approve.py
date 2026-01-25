#!/usr/bin/env python3
"""
PermissionRequest hook for ALL tools during appfix.

Auto-approves all tool permissions when appfix mode is detected,
enabling truly autonomous execution without permission prompts.

Detection: Checks for .claude/appfix-state.json in cwd or APPFIX_ACTIVE env var.

Hook event: PermissionRequest
Matcher: * (wildcard - matches all tools)

Exit codes:
  0 - Decision made (allow via hookSpecificOutput) or silent passthrough
"""
import json
import sys
from pathlib import Path

# Add hooks directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent))
from _common import is_appfix_active, log_debug


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        log_debug("Failed to parse JSON input", hook_name="appfix-auto-approve", error=e)
        sys.exit(0)

    cwd = input_data.get("cwd", "")

    # Only auto-approve if appfix is active
    if not is_appfix_active(cwd):
        sys.exit(0)  # Silent passthrough - normal approval flow

    # Auto-approve the tool (any tool)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": "allow"
            }
        }
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
