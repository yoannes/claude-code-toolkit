---
status: working
updated: 2026-01-12T12:06:15+00:00
task: Fix UnicodeDecodeError in finalize-status-v5.py
---

## Summary
Hook failing with UnicodeDecodeError when git diff contains non-UTF-8 bytes. Need to add errors="replace" to subprocess call.
