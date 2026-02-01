#!/usr/bin/env python3
"""
PostToolUse Memory Recall - Topic-Shift Retrieval

Triggered after Read/Grep/Glob tool uses. Extracts file paths from
tool_input, matches against memory events, and injects relevant
memories not already in the session context.

Throttled: max 3 recalls per session, 60s cooldown between recalls.

Part of the Compound Memory System's mid-session retrieval layer.
"""

from __future__ import annotations

import fcntl
import json
import sys
import time
from pathlib import Path

# Add hooks directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent))

from _common import log_debug

# Throttle constants
MAX_RECALLS_PER_SESSION = 8
RECALL_COOLDOWN_SECONDS = 30
MAX_RECALL_EVENTS = 2
MAX_RECALL_CHARS = 1200


def _extract_file_paths(tool_input: dict) -> set[str]:
    """Extract file paths from tool_input for entity matching."""
    paths = set()

    # Read tool: file_path
    if "file_path" in tool_input:
        paths.add(tool_input["file_path"])

    # Grep tool: path
    if "path" in tool_input:
        paths.add(tool_input["path"])

    # Glob tool: pattern may contain path info, also check path
    if "pattern" in tool_input:
        pattern = tool_input["pattern"]
        if "/" in pattern:
            dir_parts = [p for p in pattern.split("/") if "*" not in p and "?" not in p]
            if dir_parts:
                paths.add("/".join(dir_parts))

    return paths


def _build_entity_set(paths: set[str]) -> tuple[set, set, set]:
    """Build basenames, stems, dirs from extracted paths."""
    basenames = set()
    stems = set()
    dirs = set()

    for p in paths:
        parts = p.split("/")
        basename = parts[-1]
        if basename and "." in basename:
            basenames.add(basename)
            stem = basename.rsplit(".", 1)[0]
            stems.add(stem)
        elif basename:
            stems.add(basename)

        for part in parts[:-1]:
            if part and part != ".":
                dirs.add(part)

    return basenames, stems, dirs


def _check_throttle(cwd: str) -> bool:
    """Check if recall is allowed (cooldown + session limit)."""
    log_path = Path(cwd) / ".claude" / "injection-log.json"
    try:
        if not log_path.exists():
            return True
        log_data = json.loads(log_path.read_text())
        recalled = log_data.get("recalled_events", [])

        # Check session limit (MAX_RECALLS * MAX_EVENTS per recall)
        posttool_recalls = [r for r in recalled if r.get("trigger") == "posttooluse"]
        if len(posttool_recalls) >= MAX_RECALLS_PER_SESSION * MAX_RECALL_EVENTS:
            return False

        # Check cooldown against last posttooluse recall
        if posttool_recalls:
            last_ts = posttool_recalls[-1].get("ts", 0)
            if isinstance(last_ts, (int, float)) and time.time() - last_ts < RECALL_COOLDOWN_SECONDS:
                return False

        return True
    except (json.JSONDecodeError, IOError):
        return True


def _get_injected_ids(cwd: str) -> set[str]:
    """Get all event IDs already injected or recalled in this session."""
    log_path = Path(cwd) / ".claude" / "injection-log.json"
    ids = set()
    try:
        if log_path.exists():
            log_data = json.loads(log_path.read_text())
            for entry in log_data.get("events", []):
                ids.add(entry.get("id", ""))
            for entry in log_data.get("recalled_events", []):
                ids.add(entry.get("id", ""))
    except (json.JSONDecodeError, IOError):
        pass
    return ids


def main():
    input_data = json.loads(sys.stdin.read() or "{}")
    cwd = input_data.get("cwd", "")
    tool_input = input_data.get("tool_input", {})

    if not cwd:
        sys.exit(0)

    # Throttle check
    if not _check_throttle(cwd):
        sys.exit(0)

    # Extract file paths from tool input
    paths = _extract_file_paths(tool_input)
    if not paths:
        sys.exit(0)

    basenames, stems, dirs = _build_entity_set(paths)
    if not (basenames or stems or dirs):
        sys.exit(0)

    # Load events
    try:
        from _memory import get_recent_events
    except ImportError:
        sys.exit(0)

    events = get_recent_events(cwd, limit=30)
    if not events:
        sys.exit(0)

    # Get already-injected IDs
    injected_ids = _get_injected_ids(cwd)

    # Score events against new entities
    scored = []
    for event in events:
        eid = event.get("id", "")
        if eid in injected_ids:
            continue
        if event.get("meta", {}).get("archived_by"):
            continue
        if event.get("source") in {"async-task-bootstrap", "bootstrap"}:
            continue

        entities = event.get("entities", [])
        best_match = 0.0
        for e in entities:
            is_file = "/" in e or "." in e
            if is_file:
                e_base = e.split("/")[-1]
                if e_base in basenames:
                    best_match = max(best_match, 1.0)
                elif (e_base.rsplit(".", 1)[0] if "." in e_base else e_base) in stems:
                    best_match = max(best_match, 0.6)
            else:
                e_lower = e.lower()
                if e_lower in stems or e_lower in dirs:
                    best_match = max(best_match, 0.5)
            if best_match >= 1.0:
                break

        content = event.get("content", "")
        has_lesson = content.startswith("LESSON:") or content.startswith("SCHEMA:")
        quality = 0.8 if has_lesson else 0.3

        score = 0.6 * best_match + 0.4 * quality
        if score > 0.5:
            scored.append((event, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:MAX_RECALL_EVENTS]

    if not top:
        sys.exit(0)

    # Format recalled memories
    parts = []
    total_chars = 0
    for event, _score in top:
        content = event.get("content", "").strip()
        if not content:
            continue
        if len(content) > 500:
            cut = content[:500].rfind(". ")
            if cut > 250:
                content = content[:cut + 1]
            else:
                content = content[:500] + "..."

        eid = event.get("id", "")
        entry = f'<recalled id="{eid}">\n{content}\n</recalled>'
        if total_chars + len(entry) > MAX_RECALL_CHARS:
            break
        parts.append(entry)
        total_chars += len(entry)

    if not parts:
        sys.exit(0)

    # Update injection log (with flock for concurrent safety)
    try:
        log_path = Path(cwd) / ".claude" / "injection-log.json"
        lock_path = Path(cwd) / ".claude" / ".injection-log.lock"
        with open(lock_path, "w") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError):
                pass  # Skip update if locked — recall is best-effort
            else:
                try:
                    log_data = {}
                    if log_path.exists():
                        log_data = json.loads(log_path.read_text())
                    recalled = log_data.get("recalled_events", [])
                    for event, score in top:
                        recalled.append({
                            "id": event.get("id", ""),
                            "score": round(score, 3),
                            "trigger": "posttooluse",
                            "ts": time.time(),
                        })
                    log_data["recalled_events"] = recalled
                    from _memory import atomic_write_json
                    atomic_write_json(log_path, log_data)
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass

    # Output via hookSpecificOutput
    context = "MEMORY RECALL (relevant to current exploration):\n" + "\n".join(parts)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }

    log_debug(
        f"Recalled {len(parts)} memories",
        hook_name="memory-recall",
        parsed_data={
            "event_ids": [e.get("id", "") for e, _ in top],
            "scores": [round(s, 3) for _, s in top],
        },
    )

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
