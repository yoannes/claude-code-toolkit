# Solution Schema Reference

Controlled vocabulary for `/compound` solution documents.

## Problem Types

Maps to directory structure in `docs/solutions/`.

| problem_type | Directory | Use When |
|--------------|-----------|----------|
| `build_error` | build-errors/ | Compilation, bundling, or build tool failures |
| `test_failure` | test-failures/ | Unit, integration, or E2E test failures |
| `runtime_error` | runtime-errors/ | Crashes, exceptions, or errors during execution |
| `performance_issue` | performance/ | Slow queries, memory leaks, rendering lag |
| `config_error` | config-errors/ | Wrong config, missing env vars, bad settings |
| `dependency_issue` | dependencies/ | Version conflicts, missing packages, incompatibilities |
| `integration_issue` | integrations/ | API mismatches, service communication failures |
| `logic_error` | logic-errors/ | Wrong behavior, incorrect calculations, bad state |
| `design_flaw` | design-flaws/ | Architectural issues, poor abstractions |
| `infrastructure_issue` | infrastructure/ | Deployment, CI/CD, hosting, network issues |
| `security_issue` | security/ | Vulnerabilities, auth problems, data exposure |

## Root Causes

The underlying reason the problem occurred.

| root_cause | Description |
|------------|-------------|
| `missing_config` | Required configuration not present |
| `wrong_api_usage` | API called incorrectly or with wrong parameters |
| `race_condition` | Timing-dependent bug, concurrent access issue |
| `state_management` | State not properly initialized, updated, or cleaned |
| `missing_validation` | Input not validated, edge case not handled |
| `missing_dependency` | Package, library, or service not available |
| `wrong_assumption` | Code assumes something that isn't true |
| `incomplete_migration` | Migration partially applied or missing steps |
| `environment_mismatch` | Works in one environment, fails in another |
| `logic_error` | Algorithm or calculation is simply wrong |
| `type_error` | Type mismatch, null/undefined access |
| `schema_mismatch` | Data shape doesn't match expected schema |
| `memory_issue` | Memory leak, buffer overflow, stack overflow |
| `timeout` | Operation took too long, deadline exceeded |
| `permission_error` | Missing access rights, auth failure |
| `platform_difference` | Behavior differs between OS, browser, or runtime |

## Resolution Types

How the problem was fixed.

| resolution_type | Description |
|-----------------|-------------|
| `code_fix` | Modified code to fix the bug |
| `config_change` | Changed configuration or environment variables |
| `dependency_update` | Updated, added, or removed a dependency |
| `architecture_change` | Restructured code or system design |
| `test_fix` | Fixed the test, not the code (test was wrong) |
| `environment_fix` | Fixed deployment, CI, or infrastructure |
| `workaround` | Applied a temporary fix, not root cause |
| `documentation` | Clarified docs, no code change needed |
| `rollback` | Reverted to previous working state |
| `deletion` | Removed problematic code entirely |

## Severity Levels

| severity | Description | Example |
|----------|-------------|---------|
| `critical` | Production outage, data loss, security breach | Auth bypass, database corruption |
| `high` | Major feature broken, significant user impact | Checkout fails, can't save data |
| `medium` | Feature degraded, workaround exists | Slow load, minor UI glitch |
| `low` | Cosmetic, minor inconvenience | Typo, styling issue |

## Tags

Free-form keywords for search. Guidelines:

- **3-7 tags** per solution
- **Lowercase** with hyphens for multi-word (`state-management`)
- Include:
  - Affected module/component (`hooks`, `api`, `auth`)
  - Technology involved (`react`, `postgres`, `redis`)
  - Symptom keywords (`timeout`, `crash`, `silent-failure`)
  - Platform if relevant (`macos`, `linux`, `ios`)

## Example Frontmatter

```yaml
---
title: "Redis rate limiter race condition on multi-pod deployment"
date: 2026-01-15
problem_type: runtime_error
component: "src/middleware/rateLimiter.ts"
root_cause: race_condition
resolution_type: code_fix
severity: high
symptoms:
  - "Rate limits not enforced consistently"
  - "Some requests bypass limits entirely"
  - "Works in single-pod, fails in multi-pod"
tags: [redis, rate-limit, race-condition, kubernetes, multi-pod]
---
```

## Validation

When creating a solution, verify:

- [ ] `problem_type` is one of the 11 defined types
- [ ] `root_cause` is one of the 16 defined causes
- [ ] `resolution_type` is one of the 10 defined types
- [ ] `severity` is critical, high, medium, or low
- [ ] `tags` has 3-7 entries
- [ ] `date` is YYYY-MM-DD format
- [ ] `title` is concise (<80 chars)
- [ ] `component` identifies the affected file or module
