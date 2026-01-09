# Session Memories

## Architectural Decisions

### Status File Enforcement (2026-01-09, updated)
**Decision**: Status.md is checked as part of the compliance checklist, NOT as a separate early exit.

**Why**: When status was a separate early exit (before checklist), it set `stop_hook_active=True` on failure. This meant the second stop would bypass the entire compliance checklist. By moving status into the checklist as "item 0", users always see the full checklist on first stop.

**Implementation**:
- `status-working.py` (UserPromptSubmit) - reminds Claude to update status
- `stop-validator.py` (Stop) - shows status as item 0 in checklist if stale/missing
- `stop_hook_active` check is now FIRST (loop prevention), then full checklist shown
