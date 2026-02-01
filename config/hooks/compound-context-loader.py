#!/usr/bin/env python3
"""
Compound Context Loader - SessionStart Hook

Injects relevant memory events at session start. Reads from the
append-only event store at ~/.claude/memory/{project-hash}/events/.

Hybrid Selection: Haiku-based semantic selection with deterministic fallback.
When Haiku is available, it selects memories based on git context understanding.
Falls back to 4-signal deterministic scoring if Haiku fails or is unavailable.

Scoring (fallback): entity overlap 35%, recency 30%, content quality 20%,
source quality 15%. Entity matching: multi-tier set lookups.

Part of the Compound Memory System that enables cross-session learning.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Add hooks directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent))

from _common import log_debug

MAX_EVENTS = 10
MAX_CHARS = 8000
MIN_SCORE = 0.12  # Below this: zero entity overlap + low recency = noise

# Budget tiers: higher-scoring events get more space
BUDGET_HIGH = 600     # score >= 0.6
BUDGET_MEDIUM = 350   # score >= 0.35
BUDGET_LOW = 200      # score < 0.35

# Bootstrap sources to filter out (commit-message-level, near-zero learning value)
BOOTSTRAP_SOURCES = frozenset({"async-task-bootstrap", "bootstrap"})


# ============================================================================
# File Context
# ============================================================================


def _get_changed_files(cwd: str) -> set[str]:
    """Get files changed in recent commits + uncommitted changes."""
    files = set()
    try:
        # Uncommitted changes
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                files.add(line.strip())

        # Last 5 commits
        result = subprocess.run(
            ["git", "log", "--name-only", "--format=", "-5"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                files.add(line.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return files


def _build_file_components(changed_files: set[str]) -> tuple[set, set, set]:
    """Pre-compute file component sets for O(1) entity matching."""
    basenames = set()
    stems = set()
    dirs = set()
    for f in changed_files:
        parts = f.split("/")
        basename = parts[-1]
        basenames.add(basename)
        stem = basename.rsplit(".", 1)[0] if "." in basename else basename
        stems.add(stem)
        dirs.update(p for p in parts[:-1] if p)
    return basenames, stems, dirs


# ============================================================================
# Scoring
# ============================================================================


def _recency_score(event: dict) -> float:
    """Exponential decay with half-life 7 days, freshness boost for <24h."""
    ts = event.get("ts", "")
    try:
        event_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - event_time).total_seconds() / 86400
        if age_days < 1:
            return 1.0  # freshness boost
        return 0.5 ** (age_days / 7.0)  # half-life 7 days
    except (ValueError, TypeError):
        return 0.3


def _entity_overlap_score(
    event: dict, basenames: set, stems: set, dirs: set,
) -> float:
    """Score entity overlap using multi-tier matching. Uses max() not average().

    Tiers:
    - Exact basename match (1.0): "stop-validator.py" in basenames
    - Stem match (0.6): "stop-validator" in stems
    - Concept match (0.5): concept keyword found in stems or dirs
    - Directory match (0.3): "hooks" in dirs

    One strong match is decisive — avoids penalizing entity-rich events.
    Concept entities (from search_terms) don't contain "/" or "." — they
    match against stems and directory names for cross-cutting relevance.
    """
    entities = event.get("entities", [])
    if not entities or not (basenames or stems or dirs):
        return 0.0
    best = 0.0
    for e in entities:
        is_file_entity = "/" in e or "." in e
        if is_file_entity:
            # File-path entity: exact basename or stem match
            e_base = e.split("/")[-1]
            if e_base in basenames:
                best = max(best, 1.0)
            elif (e_base.rsplit(".", 1)[0] if "." in e_base else e_base) in stems:
                best = max(best, 0.6)
            elif e in dirs or e_base in dirs:
                best = max(best, 0.3)
        else:
            # Concept entity (from search_terms): match against stems and dirs
            e_lower = e.lower()
            if e_lower in stems or e_lower in dirs:
                best = max(best, 0.5)
            # Also check if concept appears as a substring of any stem/dir
            # (e.g., "maestro" matches stem "maestro-mcp-contract")
            elif any(e_lower in s.lower() for s in stems) or any(e_lower in d.lower() for d in dirs):
                best = max(best, 0.35)

        if best >= 1.0:
            break  # Can't do better
    return best


def _content_quality_score(event: dict) -> float:
    """Score based on content richness: has lesson + has concept entities.

    Events with structured LESSON content and sufficient entity tags
    are more valuable than raw "DONE:" dumps.
    """
    content = event.get("content", "")
    entities = event.get("entities", [])

    has_lesson = content.startswith("LESSON:") and len(content.split("\n")[0]) > 35
    has_terms = len(entities) >= 3

    if has_lesson and has_terms:
        return 1.0
    if has_lesson:
        return 0.6
    if has_terms:
        return 0.4
    return 0.2


def _score_event(
    event: dict, basenames: set, stems: set, dirs: set,
) -> float:
    """Score event: entity overlap (35%) + recency (30%) + quality (20%) + source (15%)."""
    entity_score = _entity_overlap_score(event, basenames, stems, dirs)
    recency = _recency_score(event)
    quality = _content_quality_score(event)

    source = event.get("source", "")
    source_score = 1.0 if source == "compound" else 0.7 if source == "auto-capture" else 0.2

    return 0.35 * entity_score + 0.30 * recency + 0.20 * quality + 0.15 * source_score


# ============================================================================
# Haiku-based Semantic Selection (with caching and fallback)
# ============================================================================

HAIKU_MODEL = "claude-3-5-haiku-20241022"
HAIKU_TIMEOUT = 120  # seconds - user accepts 1-3 minute wait
HAIKU_MAX_TOKENS = 300
CACHE_TTL_SECONDS = 3600  # 1 hour


def _gather_git_context(cwd: str) -> dict:
    """Gather git context for Haiku selection."""
    context = {
        "branch": "unknown",
        "commit_subjects": [],
        "changed_files": [],
        "project_name": Path(cwd).name,
    }

    try:
        # Current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if result.returncode == 0:
            context["branch"] = result.stdout.strip()

        # Recent commit subjects
        result = subprocess.run(
            ["git", "log", "--format=%s", "-5"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if result.returncode == 0:
            context["commit_subjects"] = [
                line.strip() for line in result.stdout.strip().split("\n")
                if line.strip()
            ][:5]

        # Changed files (already available from _get_changed_files)
        # Will be passed in separately

        # Project name from remote
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip()
            name = url.split("/")[-1].replace(".git", "")
            context["project_name"] = name

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return context


def _compute_cache_key(events: list[dict], changed_files: set[str]) -> str:
    """Generate cache key from memory IDs + git state."""
    # Component 1: Event IDs (detect new memories)
    event_ids = sorted(e.get("id", "") for e in events)
    events_hash = hashlib.sha256("|".join(event_ids).encode()).hexdigest()[:8]

    # Component 2: Changed file basenames
    basenames = sorted(set(f.split("/")[-1] for f in changed_files))
    files_hash = hashlib.sha256("|".join(basenames).encode()).hexdigest()[:8]

    return f"{events_hash}_{files_hash}"


def _get_selection_cache(cwd: str, cache_key: str) -> list[str] | None:
    """Get cached Haiku selection if fresh (<1h)."""
    try:
        from _memory import get_memory_dir
        cache_path = get_memory_dir(cwd).parent / "haiku-cache.json"
        if not cache_path.exists():
            return None

        cache = json.loads(cache_path.read_text())
        entry = cache.get(cache_key)
        if not entry:
            return None

        # Check TTL
        cached_at = entry.get("cached_at", 0)
        if time.time() - cached_at > CACHE_TTL_SECONDS:
            return None

        return entry.get("selected_ids")
    except (json.JSONDecodeError, IOError, OSError, ImportError):
        return None


def _save_selection_cache(cwd: str, cache_key: str, selected_ids: list[str]) -> None:
    """Save Haiku selection to cache."""
    try:
        from _memory import get_memory_dir, atomic_write_json
        cache_path = get_memory_dir(cwd).parent / "haiku-cache.json"

        cache = {}
        if cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text())
            except json.JSONDecodeError:
                cache = {}

        # LRU-style cleanup: keep only last 10 entries
        if len(cache) > 10:
            sorted_entries = sorted(
                cache.items(),
                key=lambda x: x[1].get("cached_at", 0)
            )
            for k, _ in sorted_entries[:len(cache) - 10]:
                del cache[k]

        cache[cache_key] = {
            "selected_ids": selected_ids,
            "cached_at": time.time(),
        }

        atomic_write_json(cache_path, cache)
    except (IOError, OSError, ImportError):
        pass


def _build_haiku_prompt(events: list[dict], git_context: dict, changed_files: set[str]) -> str:
    """Build prompt for Haiku memory selection."""
    now = datetime.now(timezone.utc)

    # Build memory summaries
    memory_lines = []
    for i, event in enumerate(events[:30]):
        content = event.get("content", "")[:150].replace("\n", " ")
        age = _human_age(event.get("ts", ""), now)
        cat = event.get("category", "session")
        entities = event.get("entities", [])[:4]
        memory_lines.append(
            f"[m{i+1}] age={age} cat={cat} entities={entities} | {content}"
        )

    files_list = list(changed_files)[:15]

    return f"""Select memories relevant to the upcoming coding session.

GIT CONTEXT:
- Branch: {git_context.get('branch', 'unknown')}
- Recent commits: {', '.join(git_context.get('commit_subjects', [])[:3])}
- Changed files: {', '.join(files_list)}
- Project: {git_context.get('project_name', 'unknown')}

MEMORIES ({len(events)}):
{chr(10).join(memory_lines)}

Select 8-12 most relevant memories. Semantic relevance > exact keyword match.
Return ONLY valid JSON: {{"selected": ["m1", "m3", ...]}}"""


def _parse_haiku_response(text: str, events: list[dict]) -> list[str] | None:
    """Parse Haiku's JSON response to extract selected event IDs."""
    # Try to extract JSON from response (may have markdown wrapping)
    json_match = re.search(r'\{[^}]+\}', text)
    if not json_match:
        return None

    try:
        result = json.loads(json_match.group())
        selected_refs = result.get("selected", [])
        if not isinstance(selected_refs, list):
            return None

        # Convert m1, m2, ... back to event IDs
        event_ids = []
        for ref in selected_refs:
            if isinstance(ref, str) and ref.startswith("m"):
                try:
                    idx = int(ref.replace("m", "")) - 1
                    if 0 <= idx < len(events):
                        event_id = events[idx].get("id")
                        if event_id:
                            event_ids.append(event_id)
                except ValueError:
                    continue

        return event_ids if event_ids else None
    except json.JSONDecodeError:
        return None


def _call_haiku_sdk(api_key: str, prompt: str, events: list[dict]) -> list[str] | None:
    """Call Haiku via anthropic SDK."""
    try:
        import anthropic

        client = anthropic.Anthropic(
            api_key=api_key,
            max_retries=1,
            timeout=HAIKU_TIMEOUT,
        )

        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=HAIKU_MAX_TOKENS,
            system="You are a memory relevance selector. Output ONLY valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )

        return _parse_haiku_response(response.content[0].text, events)

    except Exception as e:
        log_debug(f"Haiku SDK error: {e}", hook_name="compound-context-loader")
        return None


def _call_haiku_urllib(api_key: str, prompt: str, events: list[dict]) -> list[str] | None:
    """Call Haiku via stdlib urllib (fallback when SDK not installed)."""
    payload = {
        "model": HAIKU_MODEL,
        "max_tokens": HAIKU_MAX_TOKENS,
        "system": "You are a memory relevance selector. Output ONLY valid JSON.",
        "messages": [{"role": "user", "content": prompt}],
    }

    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=HAIKU_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
            text = result.get("content", [{}])[0].get("text", "")
            return _parse_haiku_response(text, events)
    except urllib.error.HTTPError as e:
        log_debug(f"Haiku HTTP {e.code}", hook_name="compound-context-loader")
        return None
    except urllib.error.URLError as e:
        log_debug(f"Haiku network error: {e}", hook_name="compound-context-loader")
        return None
    except (json.JSONDecodeError, KeyError, IndexError, TimeoutError) as e:
        log_debug(f"Haiku parse error: {e}", hook_name="compound-context-loader")
        return None


def _call_haiku_selection(
    events: list[dict],
    git_context: dict,
    changed_files: set[str],
) -> list[str] | None:
    """Use Haiku to select relevant memories. Returns event IDs or None on failure."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log_debug("No ANTHROPIC_API_KEY, using deterministic fallback",
                  hook_name="compound-context-loader")
        return None

    prompt = _build_haiku_prompt(events, git_context, changed_files)

    # Try SDK first, fall back to urllib
    try:
        import anthropic  # noqa: F401
        return _call_haiku_sdk(api_key, prompt, events)
    except ImportError:
        return _call_haiku_urllib(api_key, prompt, events)


# ============================================================================
# Injection Formatting
# ============================================================================


def _human_age(ts: str, now: datetime) -> str:
    """Convert ISO timestamp to human-readable relative age."""
    try:
        event_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        delta = now - event_time
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return "<1h"
        if hours < 24:
            return f"{int(hours)}h"
        days = delta.days
        if days < 7:
            return f"{days}d"
        if days < 30:
            return f"{days // 7}w"
        return f"{days // 30}mo"
    except (ValueError, TypeError):
        return "?"


def _budget_for_score(score: float) -> int:
    """Return character budget based on event score tier."""
    if score >= 0.6:
        return BUDGET_HIGH
    if score >= 0.35:
        return BUDGET_MEDIUM
    return BUDGET_LOW


def _truncate_content(content: str, max_len: int) -> str:
    """Truncate at sentence boundary if possible, preserving LESSON prefix."""
    if len(content) <= max_len:
        return content
    trunc = content[:max_len]
    # Try to cut at sentence boundary
    last_period = trunc.rfind(". ")
    last_newline = trunc.rfind("\n")
    cut_point = max(last_period, last_newline)
    if cut_point > max_len * 0.6:
        return trunc[:cut_point + 1].rstrip()
    return trunc.rstrip() + "..."


def _format_injection(scored_events: list[tuple[dict, float]]) -> str:
    """Format scored events as structured XML with metadata attributes.

    Score-tiered budget: high-score events get more space for richer content.
    Shows concept tags alongside file names for retrieval transparency.
    """
    now = datetime.now(timezone.utc)
    event_count = 0
    parts = []

    for event, score in scored_events:
        content = event.get("content", "").strip()
        if not content:
            continue

        budget = _budget_for_score(score)
        content = _truncate_content(content, budget)

        entities = event.get("entities", [])

        # Separate file entities and concept entities
        file_entities = [
            e.split("/")[-1] for e in entities
            if "." in e.split("/")[-1]
        ][:3]
        concept_entities = [
            e for e in entities
            if "/" not in e and "." not in e
        ][:5]

        files_attr = ", ".join(file_entities) if file_entities else ""
        tags_attr = ", ".join(concept_entities) if concept_entities else ""

        age_str = _human_age(event.get("ts", ""), now)
        # Category: top-level first, fall back to meta for backward compatibility
        cat = event.get("category", "") or event.get("meta", {}).get("category", "session")

        event_id = event.get("id", "")
        # Dual-ID: ref="m1" for easy citation, id="evt_..." for utility tracking
        ref_id = f"m{event_count + 1}"
        attrs = f'ref="{ref_id}" id="{event_id}" files="{files_attr}" age="{age_str}" cat="{cat}"'
        if tags_attr:
            attrs += f' tags="{tags_attr}"'
        parts.append(f"<m {attrs}>\n{content}\n</m>")
        event_count += 1

    if not parts:
        return ""

    header = (
        f'<memories count="{event_count}">\n'
        f"BEFORE starting: scan m1-m{event_count} for applicable lessons.\n"
        "At stop: list any that helped in memory_that_helped (e.g., [\"m1\", \"m3\"]).\n"
    )
    body = "\n\n".join(parts)
    footer = "\n</memories>"

    return header + "\n" + body + footer


# ============================================================================
# Main
# ============================================================================


def main():
    input_data = json.loads(sys.stdin.read() or "{}")
    cwd = input_data.get("cwd", "")

    if not cwd:
        sys.exit(0)

    # Import memory primitives
    try:
        from _memory import get_recent_events, cleanup_old_events
    except ImportError:
        log_debug(
            "Cannot import _memory module",
            hook_name="compound-context-loader",
        )
        sys.exit(0)

    # Cleanup old events at session start
    try:
        removed = cleanup_old_events(cwd)
        if removed:
            log_debug(
                f"Cleaned up {removed} old events",
                hook_name="compound-context-loader",
            )
    except Exception:
        pass

    # Load recent events (manifest fast-path)
    events = get_recent_events(cwd, limit=30)
    if not events:
        log_debug(
            "No memory events found",
            hook_name="compound-context-loader",
        )
        sys.exit(0)

    # Filter bootstrap events (commit-message-level noise)
    events = [e for e in events if e.get("source") not in BOOTSTRAP_SOURCES]
    if not events:
        log_debug(
            "No non-bootstrap events found",
            hook_name="compound-context-loader",
        )
        sys.exit(0)

    # Get changed files for context
    changed_files = _get_changed_files(cwd)

    # Try Haiku-based semantic selection (with caching)
    haiku_selected_ids = None
    haiku_used = False
    cache_hit = False

    # Check cache first
    cache_key = _compute_cache_key(events, changed_files)
    haiku_selected_ids = _get_selection_cache(cwd, cache_key)

    if haiku_selected_ids is not None:
        cache_hit = True
        haiku_used = True
        log_debug(
            f"Haiku cache hit: {len(haiku_selected_ids)} memories",
            hook_name="compound-context-loader",
        )
    else:
        # Cache miss: call Haiku
        git_context = _gather_git_context(cwd)
        git_context["changed_files"] = list(changed_files)[:20]

        log_debug(
            "Calling Haiku for memory selection...",
            hook_name="compound-context-loader",
        )
        haiku_selected_ids = _call_haiku_selection(events, git_context, changed_files)

        if haiku_selected_ids:
            haiku_used = True
            _save_selection_cache(cwd, cache_key, haiku_selected_ids)
            log_debug(
                f"Haiku selected {len(haiku_selected_ids)} memories",
                hook_name="compound-context-loader",
            )

    # Build final selection
    if haiku_used and haiku_selected_ids:
        # Use Haiku's selection - preserve order, assign high scores
        selected_id_set = set(haiku_selected_ids)
        id_to_event = {e.get("id"): e for e in events}
        top_events = []
        for i, eid in enumerate(haiku_selected_ids[:MAX_EVENTS]):
            event = id_to_event.get(eid)
            if event:
                # Assign descending scores for Haiku-selected memories
                score = 0.95 - (i * 0.05)
                top_events.append((event, max(score, 0.5)))
        demoted_count = 0
        filtered_count = 0
        min_score = MIN_SCORE
    else:
        # Fallback: deterministic 4-signal scoring
        log_debug(
            "Using deterministic fallback",
            hook_name="compound-context-loader",
        )
        basenames, stems, dirs = _build_file_components(changed_files)
        scored = [(event, _score_event(event, basenames, stems, dirs)) for event in events]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Apply per-event demotion from utility tracking (feedback loop)
        demoted_count = 0
        try:
            from _memory import get_event_demotion
            for i, (event, score) in enumerate(scored):
                demotion = get_event_demotion(cwd, event.get("id", ""))
                if demotion > 0:
                    scored[i] = (event, score * (1.0 - demotion))
                    demoted_count += 1
            scored.sort(key=lambda x: x[1], reverse=True)
        except (ImportError, Exception):
            pass

        # Apply minimum score threshold (auto-tuned from utility data)
        try:
            from _memory import get_tuned_min_score
            min_score = get_tuned_min_score(cwd, default=MIN_SCORE)
        except (ImportError, Exception):
            min_score = MIN_SCORE
        pre_filter_count = len(scored)
        scored = [(e, s) for e, s in scored if s >= min_score]
        filtered_count = pre_filter_count - len(scored)

        # Take top N
        top_events = scored[:MAX_EVENTS]

    # Format as structured XML
    output = _format_injection(top_events)
    if not output:
        sys.exit(0)

    # Enforce total budget
    if len(output) > MAX_CHARS:
        output = output[:MAX_CHARS - 15] + "\n</memories>"

    log_debug(
        "Injecting memory context",
        hook_name="compound-context-loader",
        parsed_data={"events_count": len(top_events), "output_chars": len(output)},
    )

    print(output)

    # Write injection log for feedback loop (read by stop-validator)
    try:
        session_id = ""
        snap_path = Path(cwd) / ".claude" / "session-snapshot.json"
        if snap_path.exists():
            session_id = json.loads(snap_path.read_text()).get("session_id", "")
        log_path = Path(cwd) / ".claude" / "injection-log.json"
        log_data = {
            "session_id": session_id,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "events": [
                {"ref": f"m{i+1}", "id": e.get("id", ""), "score": round(s, 3)}
                for i, (e, s) in enumerate(top_events) if e.get("id")
            ],
        }
        log_path.write_text(json.dumps(log_data, indent=2))
    except Exception:
        pass

    # Write health injection metrics sidecar (read by _health.py)
    try:
        metrics_path = Path(cwd) / ".claude" / "health-injection-metrics.json"
        metrics = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_candidates": len(events),
            "demoted_count": demoted_count,
            "filtered_by_min_score": filtered_count,
            "min_score_used": round(min_score, 3),
            "injected_count": len(top_events),
            "scores": [round(s, 3) for _, s in top_events],
            "haiku_used": haiku_used,
            "haiku_cache_hit": cache_hit,
        }
        metrics_path.write_text(json.dumps(metrics, indent=2))
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
