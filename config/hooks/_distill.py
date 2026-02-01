#!/usr/bin/env python3
"""
Distillation utilities for raw transcript processing.

Provides manifest management for tracking processed/unprocessed transcripts,
and digest extraction from JSONL transcripts for Sonnet distillation.

Used by:
- distill-trigger.py (SessionStart: detect unprocessed + extract digests)
- distill-create-event.py (CLI: mark transcripts as processed)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from _common import log_debug

DISTILL_MANIFEST_NAME = ".distilled-manifest.json"
MAX_DIGEST_CHARS = 15000
MAX_TRANSCRIPTS_PER_SESSION = 3
IN_PROGRESS_TIMEOUT_SECONDS = 1800  # 30 minutes


# ============================================================================
# Manifest Management
# ============================================================================


def get_distill_manifest(raw_dir: Path) -> dict:
    """Read the distillation manifest. Returns empty dict structure if missing."""
    manifest_path = raw_dir / DISTILL_MANIFEST_NAME
    try:
        if manifest_path.exists():
            return json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {"transcripts": {}}


def save_distill_manifest(raw_dir: Path, manifest: dict) -> None:
    """Write manifest atomically."""
    from _memory import atomic_write_json

    manifest_path = raw_dir / DISTILL_MANIFEST_NAME
    atomic_write_json(manifest_path, manifest)


def get_unprocessed_transcripts(raw_dir: Path, limit: int = MAX_TRANSCRIPTS_PER_SESSION) -> list[Path]:
    """Get transcripts not yet processed, oldest first.

    A transcript is unprocessed if:
    - Not in manifest at all
    - Status is 'failed' (eligible for retry)
    - Status is 'in-progress' but started_at > IN_PROGRESS_TIMEOUT_SECONDS ago

    Returns up to `limit` paths, sorted oldest first by mtime.
    """
    manifest = get_distill_manifest(raw_dir)
    transcripts = manifest.get("transcripts", {})

    candidates = []
    for f in raw_dir.glob("*.jsonl"):
        name = f.name
        entry = transcripts.get(name, {})
        status = entry.get("status", "")

        if status == "processed" or status == "skipped":
            continue

        if status == "in-progress":
            started = entry.get("started_at", "")
            try:
                started_time = datetime.fromisoformat(started.replace("Z", "+00:00"))
                age_seconds = (datetime.now(timezone.utc) - started_time).total_seconds()
                if age_seconds < IN_PROGRESS_TIMEOUT_SECONDS:
                    continue  # Still in progress, skip
            except (ValueError, TypeError):
                pass  # Can't parse timestamp, treat as stale

        try:
            mtime = f.stat().st_mtime
            candidates.append((mtime, f))
        except OSError:
            continue

    # Sort oldest first
    candidates.sort(key=lambda x: x[0])
    return [f for _, f in candidates[:limit]]


def mark_transcript_status(
    raw_dir: Path,
    filename: str,
    status: str,
    event_ids: list[str] | None = None,
    lesson_count: int = 0,
) -> None:
    """Update manifest entry for a transcript.

    status: 'in-progress' | 'processed' | 'skipped' | 'failed'
    """
    manifest = get_distill_manifest(raw_dir)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    entry: dict = {"status": status}
    if status == "in-progress":
        entry["started_at"] = now_str
    elif status == "processed":
        entry["processed_at"] = now_str
        entry["event_ids"] = event_ids or []
        entry["lesson_count"] = lesson_count
    elif status == "failed":
        entry["failed_at"] = now_str

    manifest.setdefault("transcripts", {})[filename] = entry
    save_distill_manifest(raw_dir, manifest)


def cleanup_distill_manifest(raw_dir: Path) -> int:
    """Prune manifest entries for transcripts that no longer exist on disk.

    Keeps 'processed' entries even if file is deleted (avoids re-processing).
    Only removes entries where: file is gone AND status is not 'processed'.
    """
    manifest = get_distill_manifest(raw_dir)
    transcripts = manifest.get("transcripts", {})
    if not transcripts:
        return 0

    existing = {f.name for f in raw_dir.glob("*.jsonl")}
    pruned = {}
    removed = 0

    for name, entry in transcripts.items():
        if name in existing or entry.get("status") == "processed":
            pruned[name] = entry
        else:
            removed += 1

    if removed:
        manifest["transcripts"] = pruned
        save_distill_manifest(raw_dir, manifest)
        log_debug(
            f"Pruned {removed} stale manifest entries",
            hook_name="distill",
        )

    return removed


# ============================================================================
# Digest Extraction
# ============================================================================


def _extract_user_text(msg: dict | str) -> str:
    """Extract text from user message, handling str and list formats."""
    if isinstance(msg, str):
        return msg[:1000]
    content = msg.get("content", "")
    if isinstance(content, str):
        return content[:1000]
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                c = item.get("content", "")
                if isinstance(c, str) and len(c) > 500:
                    texts.append(f"[tool result: {len(c)} chars]")
                elif isinstance(c, str):
                    texts.append(c[:500])
        return " ".join(texts)[:1000]
    return ""


def _extract_assistant_text(msg: dict) -> str:
    """Extract only text blocks from assistant message (skip tool_use)."""
    content = msg.get("content", [])
    if not isinstance(content, list):
        return ""
    texts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            texts.append(block.get("text", ""))
    return "\n".join(texts)[:2000]


def extract_digest(transcript_path: Path, max_chars: int = MAX_DIGEST_CHARS) -> str:
    """Extract human-readable digest from JSONL transcript.

    Parses each line as JSON, extracts USER/ASSISTANT text (skips tool_use,
    truncates large tool results). Uses head 60% + tail 40% truncation
    if over budget.

    Returns empty string for empty/corrupt transcripts.
    """
    parts: list[str] = []
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type", "")

                if entry_type == "user":
                    msg = entry.get("message", {})
                    text = _extract_user_text(msg)
                    if text and len(text.strip()) > 5:
                        parts.append(f"USER: {text.strip()}")

                elif entry_type == "assistant":
                    msg = entry.get("message", {})
                    text = _extract_assistant_text(msg)
                    if text and len(text.strip()) > 5:
                        parts.append(f"ASSISTANT: {text.strip()}")
    except (OSError, IOError):
        return ""

    if not parts:
        return ""

    full = "\n\n".join(parts)
    if len(full) <= max_chars:
        return full

    # Balanced truncation: keep head (60%) and tail (40%)
    head_budget = int(max_chars * 0.6)
    tail_budget = max_chars - head_budget - 30
    head = full[:head_budget]
    tail = full[-tail_budget:]
    return f"{head}\n\n[...truncated...]\n\n{tail}"
