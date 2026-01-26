#!/usr/bin/env python3
"""
Shared utilities for Claude Code hooks.

This module contains common functions used across multiple hooks to avoid duplication.
"""
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


# Files/patterns excluded from version tracking (dirty calculation)
# These don't represent code changes requiring re-deployment
# IMPORTANT: Use both root and nested patterns for directories like .claude/
# because :(exclude).claude/ only matches at root, not nested paths
VERSION_TRACKING_EXCLUSIONS = [
    # Base path required for exclude patterns to work correctly
    ".",
    # .claude directory at any depth (checkpoint files, state files)
    ":(exclude).claude",
    ":(exclude).claude/*",
    ":(exclude)*/.claude",
    ":(exclude)*/.claude/*",
    # Lock files
    ":(exclude)*.lock",
    ":(exclude)package-lock.json",
    ":(exclude)yarn.lock",
    ":(exclude)pnpm-lock.yaml",
    ":(exclude)poetry.lock",
    ":(exclude)Pipfile.lock",
    ":(exclude)Cargo.lock",
    # Git metadata
    ":(exclude).gitmodules",
    # Python artifacts
    ":(exclude)*.pyc",
    ":(exclude)__pycache__",
    ":(exclude)*/__pycache__",
    # Environment and logs
    ":(exclude).env*",
    ":(exclude)*.log",
    # OS and editor artifacts
    ":(exclude).DS_Store",
    ":(exclude)*.swp",
    ":(exclude)*.swo",
    ":(exclude)*.orig",
    ":(exclude).idea",
    ":(exclude).idea/*",
    ":(exclude).vscode",
    ":(exclude).vscode/*",
]

# Debug log location - shared across all hooks
DEBUG_LOG = Path(tempfile.gettempdir()) / "claude-hooks-debug.log"


def get_diff_hash(cwd: str = "") -> str:
    """
    Get hash of current git diff (excluding metadata files).

    Used to detect if THIS session made changes by comparing against
    the snapshot taken at session start.

    Excludes lock files, IDE config, .claude/, and other non-code files
    that shouldn't affect version tracking.

    Args:
        cwd: Working directory for git command

    Returns:
        12-character hash of the diff, or "unknown" on error
    """
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--"] + VERSION_TRACKING_EXCLUSIONS,
            capture_output=True, text=True, timeout=5,
            cwd=cwd or None,
        )
        return hashlib.sha1(result.stdout.encode()).hexdigest()[:12]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def get_code_version(cwd: str = "") -> str:
    """
    Get current code version (git HEAD + dirty state hash).

    Excludes metadata files (lock files, IDE config, .claude/, etc.) from
    dirty calculation. This prevents version-dependent checkpoint fields
    from becoming stale when only metadata changes (not actual code).

    Args:
        cwd: Working directory for git command

    Returns:
        Version string in format:
        - "abc1234" - clean commit
        - "abc1234-dirty-def5678" - commit with uncommitted code changes
        - "unknown" - not a git repo or error
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=cwd or None,
        )
        head_hash = head.stdout.strip()
        if not head_hash:
            return "unknown"

        diff = subprocess.run(
            ["git", "diff", "HEAD", "--"] + VERSION_TRACKING_EXCLUSIONS,
            capture_output=True, text=True, timeout=5,
            cwd=cwd or None,
        )
        if diff.stdout:
            dirty_hash = hashlib.sha1(diff.stdout.encode()).hexdigest()[:7]
            return f"{head_hash}-dirty-{dirty_hash}"

        return head_hash
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


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


def _check_state_file(cwd: str, filename: str) -> bool:
    """Check if a state file exists in .claude/ directory tree.

    Walks up the directory tree to find the state file,
    similar to how git finds the .git directory.

    Args:
        cwd: Current working directory path
        filename: Name of the state file (e.g., 'appfix-state.json')

    Returns:
        True if state file exists, False otherwise
    """
    if cwd:
        current = Path(cwd).resolve()
        # Walk up to filesystem root (max 20 levels to prevent infinite loops)
        for _ in range(20):
            state_file = current / ".claude" / filename
            if state_file.exists():
                return True
            parent = current.parent
            if parent == current:  # Reached filesystem root
                break
            current = parent
    return False


def is_appfix_active(cwd: str) -> bool:
    """Check if appfix mode is active via state file or env var.

    Args:
        cwd: Current working directory path

    Returns:
        True if appfix mode is active, False otherwise
    """
    if _check_state_file(cwd, "appfix-state.json"):
        return True

    # Fallback: Check environment variable
    if os.environ.get("APPFIX_ACTIVE", "").lower() in ("true", "1", "yes"):
        return True

    return False


def is_godo_active(cwd: str) -> bool:
    """Check if godo mode is active via state file or env var.

    Args:
        cwd: Current working directory path

    Returns:
        True if godo mode is active, False otherwise
    """
    if _check_state_file(cwd, "godo-state.json"):
        return True

    # Fallback: Check environment variable
    if os.environ.get("GODO_ACTIVE", "").lower() in ("true", "1", "yes"):
        return True

    return False


def is_autonomous_mode_active(cwd: str) -> bool:
    """Check if any autonomous execution mode is active (godo or appfix).

    This is the unified check for enabling auto-approval hooks.

    Args:
        cwd: Current working directory path

    Returns:
        True if godo OR appfix mode is active, False otherwise
    """
    return is_godo_active(cwd) or is_appfix_active(cwd)
