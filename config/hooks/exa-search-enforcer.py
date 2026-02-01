#!/usr/bin/env python3
"""
PreToolUse hook: block WebSearch, redirect to Exa MCP.

Hard enforcement: when WebSearch is invoked, blocks it with a deny decision
and instructs Claude to use Exa MCP tools instead.

Hook event: PreToolUse
Matcher: WebSearch

Exit codes:
  0 - Always (deny decision is in hookSpecificOutput, not exit code)
"""

from __future__ import annotations

import json
import sys

DENY_REASON = (
    "WebSearch is disabled. Use Exa MCP instead:\n"
    "- web_search_exa (general web search)\n"
    "- get_code_context_exa (code/GitHub/docs search)\n"
    "- company_research_exa (company/vendor info)\n\n"
    "If Exa tools aren't loaded, run: ToolSearch(query: 'exa')\n"
    "If ToolSearch returns nothing, Exa MCP is not configured — inform the user."
)


def main():
    sys.stdin.read()  # consume hook input

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": DENY_REASON,
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
