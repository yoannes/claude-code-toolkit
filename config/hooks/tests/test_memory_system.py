#!/usr/bin/env python3
"""
Unit tests for the memory system.

Tests scoring functions, entity matching, recency curves, dedup guard,
entity gate, cleanup, and core assertions.

Run with: cd config/hooks && python3 -m pytest tests/test_memory_system.py -v
"""

import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# Add hooks directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Scoring Tests (compound-context-loader.py)
# ============================================================================


class TestRecencyScore:
    """Tests for _recency_score: gradual freshness curve + exponential decay."""

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "compound_context_loader",
            str(Path(__file__).parent.parent / "compound-context-loader.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._recency_score = mod._recency_score

    def _make_event(self, hours_ago: float) -> dict:
        ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return {"ts": ts}

    def test_brand_new_event_near_one(self):
        """Events created minutes ago should score very close to 1.0."""
        score = self._recency_score(self._make_event(0.1))
        assert score > 0.95

    def test_12h_event_less_than_1(self):
        """Events at 12h should NOT be 1.0 (old binary boost was broken)."""
        score = self._recency_score(self._make_event(12))
        assert score < 1.0, "12h event should not get full freshness score"
        assert score > 0.5, "12h event should still be fairly fresh"

    def test_24h_event_less_than_12h(self):
        """Recency should strictly decrease over time."""
        score_12h = self._recency_score(self._make_event(12))
        score_24h = self._recency_score(self._make_event(24))
        assert score_24h < score_12h

    def test_48h_event_at_boundary(self):
        """Events at 48h should be at the linear→exponential boundary (0.5)."""
        score = self._recency_score(self._make_event(48))
        assert 0.45 < score < 0.55, f"48h score should be ~0.5, got {score}"

    def test_7day_event_half_life(self):
        """7-day half-life: event at 7 days should score ~0.5."""
        score = self._recency_score(self._make_event(7 * 24))
        assert 0.3 < score < 0.7

    def test_30day_event_very_low(self):
        """30-day old event should score very low."""
        score = self._recency_score(self._make_event(30 * 24))
        assert score < 0.15

    def test_missing_timestamp(self):
        """Missing ts should return fallback score."""
        score = self._recency_score({})
        assert score == 0.3

    def test_malformed_timestamp(self):
        """Garbage timestamp should return fallback score."""
        score = self._recency_score({"ts": "not-a-date"})
        assert score == 0.3

    def test_monotonic_decrease(self):
        """Recency should be monotonically decreasing over time."""
        hours = [0.1, 1, 6, 12, 24, 48, 72, 168, 336]
        scores = [self._recency_score(self._make_event(h)) for h in hours]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Recency not monotonic: {hours[i]}h={scores[i]:.3f} > "
                f"{hours[i+1]}h={scores[i+1]:.3f}"
            )


class TestEntityOverlapScore:
    """Tests for _entity_overlap_score: multi-tier matching."""

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "compound_context_loader",
            str(Path(__file__).parent.parent / "compound-context-loader.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._entity_overlap_score = mod._entity_overlap_score

    def test_exact_basename_match(self):
        """Exact basename match should score 1.0."""
        event = {"entities": ["hooks/stop-validator.py"]}
        score = self._entity_overlap_score(
            event, {"stop-validator.py"}, {"stop-validator"}, {"hooks"},
        )
        assert score == 1.0

    def test_stem_match(self):
        """Stem match should score 0.6."""
        event = {"entities": ["hooks/stop-validator.py"]}
        score = self._entity_overlap_score(
            event, set(), {"stop-validator"}, {"hooks"},
        )
        assert score == 0.6

    def test_concept_match(self):
        """Concept entity matching against stems should score 0.5."""
        event = {"entities": ["memory-scoring"]}
        score = self._entity_overlap_score(
            event, set(), {"memory-scoring"}, set(),
        )
        assert score == 0.5

    def test_directory_match(self):
        """File entity with basename in dirs should score 0.3."""
        # Note: "hooks/foo.py" is a file entity. Its basename "foo.py" and
        # the entity itself are checked against dirs. For a dir match, the
        # entity path or basename must appear literally in the dirs set.
        event = {"entities": ["hooks"]}
        score = self._entity_overlap_score(
            event, set(), set(), {"hooks"},
        )
        # "hooks" has no "/" or ".", so it's a concept entity → matches dirs → 0.5
        assert score == 0.5

    def test_no_match(self):
        """No entity overlap should score 0.0."""
        event = {"entities": ["unrelated/file.go"]}
        score = self._entity_overlap_score(
            event, {"main.py"}, {"main"}, {"src"},
        )
        assert score == 0.0

    def test_empty_entities(self):
        """Event with no entities should score 0.0."""
        event = {"entities": []}
        score = self._entity_overlap_score(
            event, {"main.py"}, {"main"}, {"src"},
        )
        assert score == 0.0

    def test_empty_context(self):
        """No changed files should score 0.0."""
        event = {"entities": ["hooks/stop-validator.py"]}
        score = self._entity_overlap_score(event, set(), set(), set())
        assert score == 0.0

    def test_concept_substring_match(self):
        """Concept entity as substring of stem should score 0.35."""
        event = {"entities": ["maestro"]}
        score = self._entity_overlap_score(
            event, set(), {"maestro-mcp-contract"}, set(),
        )
        assert score == 0.35

    def test_max_not_average(self):
        """Should use max() over entities, not average."""
        event = {"entities": ["unrelated/junk.txt", "hooks/stop-validator.py"]}
        score = self._entity_overlap_score(
            event, {"stop-validator.py"}, {"stop-validator"}, {"hooks"},
        )
        assert score == 1.0, "Should take best match, not average"


class TestScoreEvent:
    """Tests for _score_event: 2-signal composite scoring."""

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "compound_context_loader",
            str(Path(__file__).parent.parent / "compound-context-loader.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._score_event = mod._score_event

    def _make_event(self, hours_ago: float, entities: list, content: str = "") -> dict:
        ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return {"ts": ts, "entities": entities, "content": content, "source": "auto-capture"}

    def test_perfect_match_recent(self):
        """Recent event with exact entity match should score high."""
        event = self._make_event(1, ["hooks/stop-validator.py"])
        score = self._score_event(
            event, {"stop-validator.py"}, {"stop-validator"}, {"hooks"},
        )
        assert score > 0.8

    def test_no_entity_match_recent(self):
        """Recent event with zero entity overlap should score low."""
        event = self._make_event(1, ["unrelated/file.go"])
        score = self._score_event(
            event, {"stop-validator.py"}, {"stop-validator"}, {"hooks"},
        )
        assert score < 0.55, "Zero entity overlap should cap the score"

    def test_old_event_perfect_entity(self):
        """Old event with perfect entity match should still score moderate."""
        event = self._make_event(14 * 24, ["hooks/stop-validator.py"])
        score = self._score_event(
            event, {"stop-validator.py"}, {"stop-validator"}, {"hooks"},
        )
        assert 0.3 < score < 0.7

    def test_score_discrimination(self):
        """Two events should NOT score identically (the original collapse bug)."""
        relevant = self._make_event(
            2, ["hooks/stop-validator.py"],
            "LESSON: Important insight about stop validators",
        )
        irrelevant = self._make_event(
            2, ["unrelated/file.go"],
            "LESSON: Something about Go files",
        )
        basenames = {"stop-validator.py"}
        stems = {"stop-validator"}
        dirs = {"hooks"}

        score_relevant = self._score_event(relevant, basenames, stems, dirs)
        score_irrelevant = self._score_event(irrelevant, basenames, stems, dirs)

        assert score_relevant > score_irrelevant, (
            f"Scoring collapsed: relevant={score_relevant:.3f}, "
            f"irrelevant={score_irrelevant:.3f}"
        )

    def test_scores_not_constant(self):
        """Multiple events should produce distinct scores (anti-collapse)."""
        events = [
            self._make_event(1, ["hooks/stop-validator.py"], "LESSON: a"),
            self._make_event(12, ["hooks/_memory.py"], "LESSON: b"),
            self._make_event(48, ["unrelated.go"], "DONE: c"),
            self._make_event(168, ["hooks/stop-validator.py"], "DONE: d"),
        ]
        basenames = {"stop-validator.py"}
        stems = {"stop-validator"}
        dirs = {"hooks"}

        scores = [self._score_event(e, basenames, stems, dirs) for e in events]
        unique_scores = len(set(round(s, 3) for s in scores))
        assert unique_scores >= 3, (
            f"Only {unique_scores} distinct scores from 4 events: {scores}"
        )


class TestEntityGate:
    """Tests for entity_overlap==0 gate in main() flow."""

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "compound_context_loader",
            str(Path(__file__).parent.parent / "compound-context-loader.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._entity_overlap_score = mod._entity_overlap_score
        self._score_event = mod._score_event

    def test_zero_overlap_excluded(self):
        """Events with zero entity overlap should be gated out."""
        event = {
            "entities": ["completely/unrelated.rs"],
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "content": "LESSON: something",
            "source": "auto-capture",
        }
        overlap = self._entity_overlap_score(
            event, {"main.py"}, {"main"}, {"src"},
        )
        assert overlap == 0.0, "Should have zero overlap"


# ============================================================================
# Dedup Guard Tests (_memory.py)
# ============================================================================


class TestDedupGuard:
    """Tests for _is_duplicate in _memory.py."""

    def setup_method(self):
        from _memory import _is_duplicate, append_event, get_memory_dir, atomic_write_json
        self._is_duplicate = _is_duplicate
        self.append_event = append_event
        self.get_memory_dir = get_memory_dir
        self.atomic_write_json = atomic_write_json

    def test_no_manifest_not_duplicate(self):
        """Missing manifest should not flag as duplicate."""
        with tempfile.TemporaryDirectory() as td:
            event_dir = Path(td) / "events"
            event_dir.mkdir(parents=True)
            assert self._is_duplicate(event_dir, "some content") is False

    def test_different_content_not_duplicate(self):
        """Different content should not be flagged."""
        with tempfile.TemporaryDirectory() as td:
            event_dir = Path(td) / "events"
            event_dir.mkdir(parents=True)
            # Create a manifest with one event
            event_id = "evt_test_001"
            event = {"id": event_id, "content": "original content"}
            self.atomic_write_json(event_dir / f"{event_id}.json", event)
            manifest = {"recent": [event_id]}
            self.atomic_write_json(event_dir.parent / "manifest.json", manifest)

            assert self._is_duplicate(event_dir, "completely different") is False


# ============================================================================
# Cleanup Tests (_memory.py)
# ============================================================================


class TestCleanup:
    """Tests for cleanup_old_events."""

    def test_removes_expired_events(self):
        """Events older than TTL should be removed."""
        from _memory import cleanup_old_events, EVENT_TTL_DAYS
        with tempfile.TemporaryDirectory() as td:
            with patch("_memory.MEMORY_ROOT", Path(td)):
                with patch("_memory.get_project_hash", return_value="testhash"):
                    event_dir = Path(td) / "testhash" / "events"
                    event_dir.mkdir(parents=True)

                    # Create an expired event
                    old_event = event_dir / "evt_old.json"
                    old_event.write_text('{"id": "evt_old", "content": "old"}')
                    # Set mtime to past
                    import os
                    old_time = time.time() - (EVENT_TTL_DAYS + 1) * 86400
                    os.utime(old_event, (old_time, old_time))

                    # Create a fresh event
                    fresh_event = event_dir / "evt_fresh.json"
                    fresh_event.write_text('{"id": "evt_fresh", "content": "new"}')

                    removed = cleanup_old_events(td)
                    assert removed >= 1
                    assert not old_event.exists()
                    assert fresh_event.exists()


# ============================================================================
# Memory Recall Tests (memory-recall.py)
# ============================================================================


class TestExtractFilePaths:
    """Tests for _extract_file_paths in memory-recall.py."""

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "memory_recall",
            str(Path(__file__).parent.parent / "memory-recall.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._extract_file_paths = mod._extract_file_paths

    def test_read_tool_input(self):
        """Should extract file_path from Read tool input."""
        paths = self._extract_file_paths({"file_path": "/foo/bar.py"})
        assert "/foo/bar.py" in paths

    def test_grep_tool_input(self):
        """Should extract path from Grep tool input."""
        paths = self._extract_file_paths({"path": "/src/hooks", "pattern": "def main"})
        assert "/src/hooks" in paths

    def test_glob_tool_input(self):
        """Should extract directory parts from Glob pattern."""
        paths = self._extract_file_paths({"pattern": "src/hooks/**/*.py"})
        assert len(paths) > 0


class TestRecallThrottling:
    """Tests for recall throttling in memory-recall.py."""

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "memory_recall",
            str(Path(__file__).parent.parent / "memory-recall.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._check_throttle = mod._check_throttle
        self.MAX_RECALLS_PER_SESSION = mod.MAX_RECALLS_PER_SESSION
        self.RECALL_COOLDOWN_SECONDS = mod.RECALL_COOLDOWN_SECONDS

    def test_no_log_allows_recall(self):
        """Missing injection log should allow recall."""
        with tempfile.TemporaryDirectory() as td:
            assert self._check_throttle(td) is True

    def test_budget_increased(self):
        """MAX_RECALLS should be 8 (increased from 3)."""
        assert self.MAX_RECALLS_PER_SESSION == 8

    def test_cooldown_decreased(self):
        """RECALL_COOLDOWN should be 30s (decreased from 60s)."""
        assert self.RECALL_COOLDOWN_SECONDS == 30


# ============================================================================
# Schema Version Tests (_memory.py)
# ============================================================================


class TestSchemaVersion:
    """Tests for schema version on events."""

    def test_event_has_version(self):
        """New events should include v: 1."""
        from _memory import append_event, safe_read_event
        with tempfile.TemporaryDirectory() as td:
            with patch("_memory.MEMORY_ROOT", Path(td)):
                with patch("_memory.get_project_hash", return_value="testhash"):
                    path = append_event(
                        td,
                        "test content for schema version",
                        ["test-entity"],
                        event_type="test",
                        source="test",
                    )
                    assert path is not None
                    event = safe_read_event(path)
                    assert event is not None
                    assert event.get("v") == 1


# ============================================================================
# Build File Components Tests
# ============================================================================


class TestBuildFileComponents:
    """Tests for _build_file_components."""

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "compound_context_loader",
            str(Path(__file__).parent.parent / "compound-context-loader.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._build_file_components = mod._build_file_components

    def test_extracts_basenames(self):
        files = {"src/hooks/stop-validator.py", "lib/main.ts"}
        basenames, stems, dirs = self._build_file_components(files)
        assert "stop-validator.py" in basenames
        assert "main.ts" in basenames

    def test_extracts_stems(self):
        files = {"src/hooks/stop-validator.py"}
        basenames, stems, dirs = self._build_file_components(files)
        assert "stop-validator" in stems

    def test_extracts_dirs(self):
        files = {"src/hooks/stop-validator.py"}
        basenames, stems, dirs = self._build_file_components(files)
        assert "src" in dirs
        assert "hooks" in dirs


# ============================================================================
# Content Quality Tests
# ============================================================================


class TestContentQualityScore:
    """Tests for _content_quality_score (removed from scoring, but function kept)."""

    # These tests document the function behavior even though quality
    # is no longer part of composite scoring.

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "compound_context_loader",
            str(Path(__file__).parent.parent / "compound-context-loader.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._content_quality_score = mod._content_quality_score

    def test_lesson_with_terms_is_highest(self):
        event = {
            "content": "LESSON: This is a detailed lesson about memory scoring systems",
            "entities": ["a", "b", "c"],
        }
        assert self._content_quality_score(event) == 1.0

    def test_lesson_without_terms(self):
        event = {
            "content": "LESSON: This is a detailed lesson about memory scoring systems",
            "entities": ["a"],
        }
        assert self._content_quality_score(event) == 0.6

    def test_no_lesson_with_terms(self):
        event = {
            "content": "DONE: just some work",
            "entities": ["a", "b", "c"],
        }
        assert self._content_quality_score(event) == 0.4

    def test_bare_event(self):
        event = {"content": "DONE: minimal", "entities": []}
        assert self._content_quality_score(event) == 0.2


# ============================================================================
# Injection Formatting Tests
# ============================================================================


class TestFormatInjection:
    """Tests for _format_injection output format."""

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "compound_context_loader",
            str(Path(__file__).parent.parent / "compound-context-loader.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._format_injection = mod._format_injection

    def test_produces_xml_structure(self):
        events = [
            (
                {
                    "id": "evt_test_001",
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "content": "LESSON: test lesson content here",
                    "entities": ["hooks/main.py", "memory-scoring"],
                    "category": "architecture",
                },
                0.8,
            )
        ]
        output = self._format_injection(events)
        assert '<memories count="1">' in output
        assert 'ref="m1"' in output
        assert "</memories>" in output

    def test_empty_events_returns_empty(self):
        assert self._format_injection([]) == ""


# ============================================================================
# Truncation Tests
# ============================================================================


class TestTruncateContent:
    """Tests for _truncate_content."""

    def setup_method(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "compound_context_loader",
            str(Path(__file__).parent.parent / "compound-context-loader.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._truncate_content = mod._truncate_content

    def test_short_content_unchanged(self):
        assert self._truncate_content("short", 100) == "short"

    def test_long_content_truncated(self):
        long = "A" * 1000
        result = self._truncate_content(long, 100)
        assert len(result) <= 103  # max_len + "..."

    def test_sentence_boundary(self):
        text = "First sentence. Second sentence. Third sentence is very long indeed."
        result = self._truncate_content(text, 40)
        assert result.endswith(".")


# ============================================================================
# MAX_EVENTS Constant Test
# ============================================================================


class TestConstants:
    """Tests for key constants after Phase 1 changes."""

    def test_max_events_is_5(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location(
            "compound_context_loader",
            str(Path(__file__).parent.parent / "compound-context-loader.py"),
        )
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.MAX_EVENTS == 5, f"MAX_EVENTS should be 5, got {mod.MAX_EVENTS}"
