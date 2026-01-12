#!/usr/bin/env python3
"""
Stop hook (phase 2) - Finalize status.v5 with Sonnet AI analysis.

This hook runs during the stop flow after the validator has run once.
It invokes headless Sonnet to analyze git diff and fill semantic fields:
- impact_level: trivial|minor|moderate|major
- broadcast_level: silent|mention|highlight
- doc_drift_risk: low|medium|high
- summary, technical notes

Exit codes:
  0 - Allow stop (finalization complete)
  2 - Block stop (stderr shown to Claude)
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# Path to JSON schema for Sonnet output
SCHEMA_PATH = Path.home() / ".claude" / "commander" / "schemas" / "finalize_status.json"

# Maximum time to wait for Sonnet
SONNET_TIMEOUT_SECONDS = 60


def get_git_diff_summary() -> str:
    """Get a summary of git changes for Sonnet to analyze."""
    try:
        # Get staged + unstaged diff
        # Use encoding with errors="replace" to handle non-UTF-8 bytes in diffs
        staged = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        unstaged = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )

        # Get diff content (limited to avoid token overload)
        diff_content = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if not diff_content.stdout:
            diff_content = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )

        # Limit diff content to ~8000 chars to stay within context
        diff_text = diff_content.stdout[:8000]
        if len(diff_content.stdout) > 8000:
            diff_text += "\n... (diff truncated)"

        return f"""## Staged Changes:
{staged.stdout or "(none)"}

## Unstaged Changes:
{unstaged.stdout or "(none)"}

## Diff Content:
{diff_text or "(no changes)"}
"""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(git diff unavailable)"


def get_head_commit() -> str | None:
    """Get the current HEAD commit after changes."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def invoke_sonnet(git_diff: str, status_content: str) -> dict | None:
    """
    Invoke headless Sonnet to analyze changes and fill semantic fields.

    Returns parsed JSON result or None if invocation fails.
    """
    if not SCHEMA_PATH.exists():
        # Schema not installed yet, skip AI analysis
        return None

    prompt = f"""Analyze this Claude Code session and provide semantic classification.

## Current Status File:
{status_content}

## Git Changes:
{git_diff}

Based on the changes, determine:
1. impact_level: How significant are these changes?
   - trivial: typos, comments, formatting
   - minor: small bug fixes, config tweaks
   - moderate: new features, refactoring
   - major: breaking changes, architecture shifts

2. broadcast_level: Who needs to know?
   - silent: no notification needed
   - mention: team should be aware
   - highlight: requires immediate attention

3. doc_drift_risk: Risk that documentation is now outdated?
   - low: changes don't affect docs
   - medium: some docs may need updates
   - high: docs definitely need updates

4. summary: One paragraph summary of what was accomplished

5. technical_notes: Key decisions, gotchas, or things to note

6. files_touched: List of significant files changed
7. docs_touched: List of documentation files that may need updates
8. blockers: Any known blockers or issues
9. next_steps: Recommended follow-up tasks

Output JSON matching the schema."""

    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--model", "sonnet",
                "--output-format", "json",
                "--json-schema", f"@{SCHEMA_PATH}",
                "--max-turns", "1",
                "--disallowedTools", "Bash,Edit,Write,TodoWrite",
            ],
            capture_output=True,
            text=True,
            timeout=SONNET_TIMEOUT_SECONDS,
        )

        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Sonnet invocation failed: {e}", file=sys.stderr)

    return None


def update_status_file(status_path: Path, analysis: dict, head_commit: str | None) -> None:
    """Update the status.v5 file with Sonnet's analysis."""
    content = status_path.read_text()
    lines = content.split('\n')

    # Update frontmatter fields
    updated_lines = []
    in_frontmatter = False
    frontmatter_done = False

    for line in lines:
        if line.strip() == '---':
            if not in_frontmatter:
                in_frontmatter = True
                updated_lines.append(line)
                continue
            else:
                # End of frontmatter - add ended_at
                in_frontmatter = False
                frontmatter_done = True
                updated_lines.append(line)
                continue

        if in_frontmatter:
            # Update specific fields
            if line.startswith('status:'):
                updated_lines.append(f"status: completed")
            elif line.startswith('ended_at:'):
                updated_lines.append(f"ended_at: {datetime.now(timezone.utc).isoformat()}")
            elif line.startswith('impact_level:'):
                updated_lines.append(f"impact_level: {analysis.get('impact_level', 'minor')}")
            elif line.startswith('broadcast_level:'):
                updated_lines.append(f"broadcast_level: {analysis.get('broadcast_level', 'silent')}")
            elif line.startswith('doc_drift_risk:'):
                updated_lines.append(f"doc_drift_risk: {analysis.get('doc_drift_risk', 'low')}")
            elif line.startswith('head_commit:'):
                updated_lines.append(f"head_commit: {head_commit or ''}")
            elif line.startswith('blockers:'):
                blockers = analysis.get('blockers', [])
                if blockers:
                    updated_lines.append(f"blockers:")
                    for b in blockers:
                        updated_lines.append(f"  - {b}")
                else:
                    updated_lines.append("blockers: []")
            elif line.startswith('next_steps:'):
                next_steps = analysis.get('next_steps', [])
                if next_steps:
                    updated_lines.append(f"next_steps:")
                    for n in next_steps:
                        updated_lines.append(f"  - {n}")
                else:
                    updated_lines.append("next_steps: []")
            elif line.startswith('docs_touched:'):
                docs = analysis.get('docs_touched', [])
                if docs:
                    updated_lines.append(f"docs_touched:")
                    for d in docs:
                        updated_lines.append(f"  - {d}")
                else:
                    updated_lines.append("docs_touched: []")
            elif line.startswith('files_touched:'):
                files = analysis.get('files_touched', [])
                if files:
                    updated_lines.append(f"files_touched:")
                    for f in files:
                        updated_lines.append(f"  - {f}")
                else:
                    updated_lines.append("files_touched: []")
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    # Replace markdown body with Sonnet's analysis
    new_content = '\n'.join(updated_lines)

    # Find where markdown body starts (after second ---)
    parts = new_content.split('---', 2)
    if len(parts) >= 3:
        frontmatter = parts[0] + '---' + parts[1] + '---'
        markdown_body = f"""
# Briefing

## Summary
{analysis.get('summary', 'Session completed.')}

## Technical Notes
{analysis.get('technical_notes', 'No notes.')}
"""
        new_content = frontmatter + markdown_body

    status_path.write_text(new_content)


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    cwd = input_data.get("cwd", "")
    session_id = input_data.get("session_id", "")
    stop_hook_active = input_data.get("stop_hook_active", False)

    if not cwd or not session_id:
        sys.exit(0)

    # Only run on second stop (when stop_hook_active is True)
    # This means the validator already ran and we're in finalization phase
    if not stop_hook_active:
        sys.exit(0)

    # Find status.v5 file
    claude_dir = Path(cwd) / ".claude"
    status_path = claude_dir / f"status.v5.{session_id}.md"

    if not status_path.exists():
        # No v5 status file, skip finalization
        sys.exit(0)

    # Check if already finalized (has ended_at set)
    content = status_path.read_text()
    if "ended_at: 20" in content:  # Already has timestamp
        sys.exit(0)

    # Get git context
    git_diff = get_git_diff_summary()
    head_commit = get_head_commit()

    # Invoke Sonnet for analysis
    analysis = invoke_sonnet(git_diff, content)

    if analysis:
        # Update status file with Sonnet's analysis
        update_status_file(status_path, analysis, head_commit)
        print(f"<system-reminder>", file=sys.stderr)
        print(f"Fleet Commander: Status finalized with AI analysis", file=sys.stderr)
        print(f"Impact: {analysis.get('impact_level', 'unknown')}", file=sys.stderr)
        print(f"</system-reminder>", file=sys.stderr)
    else:
        # Fallback: just update timestamps without AI analysis
        simple_analysis = {
            "impact_level": "minor",
            "broadcast_level": "silent",
            "doc_drift_risk": "low",
            "summary": "Session completed.",
            "technical_notes": "AI analysis unavailable.",
            "files_touched": [],
            "docs_touched": [],
            "blockers": [],
            "next_steps": [],
        }
        update_status_file(status_path, simple_analysis, head_commit)

    sys.exit(0)


if __name__ == "__main__":
    main()
