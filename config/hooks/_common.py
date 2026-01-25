#!/usr/bin/env python3
"""
Shared utilities for Claude Code hooks.

This module contains common functions used across multiple hooks to avoid duplication.
"""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

# Debug log location - shared across all hooks
DEBUG_LOG = Path(tempfile.gettempdir()) / "claude-hooks-debug.log"


def log_debug(
    message: str,
    hook_name: str = "unknown",
    raw_input: str = "",
    parsed_data: dict | None = None,
    error: Exception | None = None,
) -> None:
    """Log diagnostic info for debugging hook issues.

    Args:
        message: Description of what happened
        hook_name: Name of the calling hook
        raw_input: Raw stdin content (optional)
        parsed_data: Parsed JSON data (optional)
        error: Exception that occurred (optional)
    """
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Hook: {hook_name}\n")
            f.write(f"Message: {message}\n")
            if error:
                f.write(f"Error: {type(error).__name__}: {error}\n")
            if raw_input:
                f.write(f"Raw stdin ({len(raw_input)} bytes): {repr(raw_input[:500])}\n")
            if parsed_data is not None:
                f.write(f"Parsed data: {json.dumps(parsed_data, indent=2)}\n")
            f.write(f"{'='*60}\n")
    except Exception:
        pass  # Never fail on logging


def is_appfix_active(cwd: str) -> bool:
    """Check if appfix mode is active via state file or env var.

    Walks up the directory tree to find .claude/appfix-state.json,
    similar to how git finds the .git directory.

    Args:
        cwd: Current working directory path

    Returns:
        True if appfix mode is active, False otherwise
    """
    # Primary: Walk up directory tree looking for state file
    if cwd:
        current = Path(cwd).resolve()
        # Walk up to filesystem root (max 20 levels to prevent infinite loops)
        for _ in range(20):
            state_file = current / ".claude" / "appfix-state.json"
            if state_file.exists():
                return True
            parent = current.parent
            if parent == current:  # Reached filesystem root
                break
            current = parent

    # Fallback: Check environment variable
    if os.environ.get("APPFIX_ACTIVE", "").lower() in ("true", "1", "yes"):
        return True

    return False
