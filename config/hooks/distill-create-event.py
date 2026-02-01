#!/usr/bin/env python3
"""
CLI Script: Create memory events from distilled transcript lessons.

Called by Sonnet agent via Bash after analyzing a session digest.
Reads JSON from stdin with extracted lessons and creates structured
memory events via _memory.append_event().

Usage:
  echo '{"cwd": "/path", "transcript": "session_*.jsonl", "lessons": [...]}' | \
    python3 ~/.claude/hooks/distill-create-event.py

Input schema:
  {
    "cwd": "/path/to/project",
    "transcript": "session_20260201T120000_abc123.jsonl",
    "lessons": [
      {
        "content": "LESSON: insight\\nCONTEXT: detail",
        "entities": ["file.py", "concept-keyword"],
        "category": "pattern"
      }
    ]
  }

Part of the Compound Memory System's distillation daemon.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add hooks directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent))

VALID_CATEGORIES = frozenset({
    "bugfix", "pattern", "config", "architecture",
    "tooling", "session", "gotcha", "refactor",
})


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        print("ERROR: Invalid JSON input", file=sys.stderr)
        sys.exit(1)

    cwd = input_data.get("cwd", "")
    transcript = input_data.get("transcript", "")
    lessons = input_data.get("lessons", [])

    if not cwd or not transcript:
        print("ERROR: Missing cwd or transcript", file=sys.stderr)
        sys.exit(1)

    from _memory import append_event, get_raw_dir
    from _distill import mark_transcript_status

    raw_dir = get_raw_dir(cwd)
    event_ids: list[str] = []

    if not lessons:
        mark_transcript_status(
            raw_dir, transcript, "processed",
            event_ids=[], lesson_count=0,
        )
        print(f"No learnings in {transcript}. Marked as processed.")
        sys.exit(0)

    for lesson in lessons:
        content = lesson.get("content", "").strip()
        entities = lesson.get("entities", [])
        category = lesson.get("category", "session")

        # Validate content
        if not content or len(content) < 20:
            continue
        if not content.startswith("LESSON:"):
            content = f"LESSON: {content}"

        # Validate entities
        if not isinstance(entities, list) or len(entities) < 1:
            continue
        entities = [
            str(e).strip().lower()
            for e in entities
            if e and len(str(e).strip()) >= 2
        ][:10]
        if not entities:
            continue

        # Validate category
        if category not in VALID_CATEGORIES:
            category = "session"

        result = append_event(
            cwd=cwd,
            content=content,
            entities=entities,
            event_type="distilled",
            source="distill-daemon",
            category=category,
            meta={
                "source_transcript": transcript,
                "quality": "distilled",
            },
        )
        if result:
            event_ids.append(result.stem)
            print(f"Created event: {result.stem}")

    mark_transcript_status(
        raw_dir, transcript, "processed",
        event_ids=event_ids, lesson_count=len(event_ids),
    )
    print(f"Distilled {len(event_ids)} lesson(s) from {transcript}.")
    sys.exit(0)


if __name__ == "__main__":
    main()
