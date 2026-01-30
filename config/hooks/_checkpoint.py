#!/usr/bin/env python3
"""
Checkpoint operations for Claude Code hooks.

Handles loading, saving, and version-based invalidation of
completion checkpoint files.
"""

from __future__ import annotations

import json
from pathlib import Path


# Code file extensions that trigger checkpoint invalidation
CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb", ".php",
    ".vue", ".svelte",
    ".tf", ".tfvars", ".bicep",
    ".yaml", ".yml",
    ".sql", ".sh", ".bash",
}

# Fields invalidated when code changes (in dependency order)
# When a field is invalidated, all fields that depend on it are also invalidated
FIELD_DEPENDENCIES = {
    "linters_pass": [],
    "deployed": ["linters_pass"],
    "web_testing_done": ["deployed"],
}

# All version-dependent fields
VERSION_DEPENDENT_FIELDS = list(FIELD_DEPENDENCIES.keys())


# ============================================================================
# Checkpoint File Operations
# ============================================================================


def load_checkpoint(cwd: str) -> dict | None:
    """Load completion checkpoint file from .claude directory.

    Args:
        cwd: Working directory containing .claude/

    Returns:
        Parsed checkpoint dict if exists and valid, None otherwise
    """
    if not cwd:
        return None

    checkpoint_path = Path(cwd) / ".claude" / "completion-checkpoint.json"
    if checkpoint_path.exists():
        try:
            return json.loads(checkpoint_path.read_text())
        except (json.JSONDecodeError, IOError):
            return None

    return None


def save_checkpoint(cwd: str, checkpoint: dict) -> bool:
    """Save checkpoint file to .claude directory.

    Args:
        cwd: Working directory containing .claude/
        checkpoint: Checkpoint dict to save

    Returns:
        True if save succeeded, False otherwise
    """
    if not cwd:
        return False
    checkpoint_path = Path(cwd) / ".claude" / "completion-checkpoint.json"
    try:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2))
        return True
    except IOError:
        return False


# ============================================================================
# Checkpoint Invalidation
# ============================================================================


def is_code_file(file_path: str) -> bool:
    """Check if file is a code file based on extension."""
    return Path(file_path).suffix.lower() in CODE_EXTENSIONS


def get_fields_to_invalidate(primary_field: str) -> set[str]:
    """Get all fields that should be invalidated when primary_field changes.

    Uses dependency graph to cascade invalidations.
    """
    to_invalidate = {primary_field}
    changed = True
    while changed:
        changed = False
        for field, deps in FIELD_DEPENDENCIES.items():
            if field not in to_invalidate:
                if any(dep in to_invalidate for dep in deps):
                    to_invalidate.add(field)
                    changed = True
    return to_invalidate


def normalize_version(version: str) -> str:
    """Normalize version by stripping the -dirty suffix.

    Prevents invalidation loops where "abc1234" and "abc1234-dirty"
    are treated as different versions.
    """
    if version.endswith("-dirty"):
        return version[:-6]
    return version


def invalidate_stale_fields(
    checkpoint: dict, current_version: str
) -> tuple[dict, list[str]]:
    """Check all version-dependent fields and invalidate stale ones.

    Versions are normalized before comparison to prevent loops.

    Returns (modified_checkpoint, list_of_invalidated_fields).
    """
    report = checkpoint.get("self_report", {})
    invalidated = []

    current_normalized = normalize_version(current_version)

    for field in VERSION_DEPENDENT_FIELDS:
        if report.get(field, False):
            field_version = report.get(f"{field}_at_version", "")
            if field_version:
                field_normalized = normalize_version(field_version)
                if field_normalized != current_normalized:
                    fields_to_reset = get_fields_to_invalidate(field)
                    for f in fields_to_reset:
                        if report.get(f, False):
                            report[f] = False
                            report[f"{f}_at_version"] = ""
                            if f not in invalidated:
                                invalidated.append(f)

    return checkpoint, invalidated
