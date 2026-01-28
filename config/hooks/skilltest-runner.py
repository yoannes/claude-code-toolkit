#!/usr/bin/env python3
"""
Skill Test Runner - Execute Claude Code skill tests in isolated tmux sandboxes.

This runner creates isolated environments using git worktrees and tmux sessions,
executes skill tests via Claude CLI headless mode, and validates results against
expected outcomes.

Usage:
    python3 skilltest-runner.py run [--test NAME] [--pattern GLOB] [--parallel N]
    python3 skilltest-runner.py list
    python3 skilltest-runner.py validate
    python3 skilltest-runner.py cleanup

Environment:
    SKILLTEST_DIR: Directory containing test JSON files (default: .claude/skill-tests)
    SKILLTEST_PARALLEL: Max parallel tests (default: 3)
    SKILLTEST_TIMEOUT: Default timeout in seconds (default: 300)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_TIMEOUT = 300  # 5 minutes
DEFAULT_PARALLEL = 3
WORKTREE_BASE = Path(tempfile.gettempdir()) / "claude-skilltest-worktrees"
TMUX_SESSION_PREFIX = "skilltest"

# Default safe tools for tests (no network, no destructive ops)
DEFAULT_ALLOWED_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash(python:*)",
    "Bash(python3:*)",
    "Bash(pytest:*)",
    "Bash(ruff:*)",
    "Bash(git:*)",
    "Bash(ls:*)",
    "Bash(cat:*)",
    "Bash(mkdir:*)",
    "Bash(touch:*)",
    "Bash(echo:*)",
]

# Tools that should NEVER be auto-approved in tests
FORBIDDEN_TOOLS = [
    "Bash(rm -rf:*)",
    "Bash(curl:*)",
    "Bash(wget:*)",
    "Bash(az:*)",
    "Bash(gh:*)",
    "Bash(aws:*)",
    "Bash(gcloud:*)",
]


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class TestCase:
    """A skill test case definition."""

    name: str
    skill: str
    description: str
    prompt: str
    setup_files: dict[str, str] = field(default_factory=dict)
    setup_commands: list[str] = field(default_factory=list)
    expected_checkpoint: dict[str, Any] = field(default_factory=dict)
    expected_files_modified: list[str] = field(default_factory=list)
    expected_files_contain: dict[str, str] = field(default_factory=dict)
    expected_output_contains: str | None = None
    expected_exit_code: int = 0
    expected_state_file_exists: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT
    allowed_tools: list[str] = field(
        default_factory=lambda: DEFAULT_ALLOWED_TOOLS.copy()
    )
    inject_input: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict, name: str) -> "TestCase":
        """Parse a test case from JSON."""
        return cls(
            name=name,
            skill=data.get("skill", "unknown"),
            description=data.get("description", ""),
            prompt=data.get("prompt", ""),
            setup_files=data.get("setup", {}).get("files", {}),
            setup_commands=data.get("setup", {}).get("commands", []),
            expected_checkpoint=data.get("expected", {}).get("checkpoint", {}),
            expected_files_modified=data.get("expected", {}).get("files_modified", []),
            expected_files_contain=data.get("expected", {}).get("files_contain", {}),
            expected_output_contains=data.get("expected", {}).get("output_contains"),
            expected_exit_code=data.get("expected", {}).get("exit_code", 0),
            expected_state_file_exists=data.get("expected", {}).get(
                "state_file_exists"
            ),
            timeout_seconds=data.get("timeout_seconds", DEFAULT_TIMEOUT),
            allowed_tools=data.get("allowed_tools", DEFAULT_ALLOWED_TOOLS.copy()),
            inject_input=data.get("inject_input", []),
        )


@dataclass
class TestResult:
    """Result of a single test execution."""

    name: str
    status: str  # PASSED, FAILED, TIMEOUT, ERROR
    duration_seconds: float
    failure_reason: str | None = None
    checkpoint_valid: bool = False
    checkpoint_data: dict | None = None
    output_log: str = ""
    worktree_path: str | None = None


# ============================================================================
# tmux Utilities
# ============================================================================


def tmux_session_exists(session_name: str) -> bool:
    """Check if a tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
        timeout=5,
    )
    return result.returncode == 0


def tmux_create_session(session_name: str, working_dir: str) -> bool:
    """Create a new detached tmux session."""
    try:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "-c", working_dir],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def tmux_send_keys(session_name: str, keys: str, enter: bool = True) -> bool:
    """Send keys to a tmux session."""
    try:
        cmd = ["tmux", "send-keys", "-t", session_name, keys]
        if enter:
            cmd.append("Enter")
        subprocess.run(cmd, check=True, capture_output=True, timeout=5)
        return True
    except subprocess.CalledProcessError:
        return False


def tmux_capture_pane(session_name: str, lines: int = 1000) -> str:
    """Capture the content of a tmux pane."""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p", "-S", f"-{lines}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


def tmux_kill_session(session_name: str) -> bool:
    """Kill a tmux session."""
    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
            timeout=10,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


# ============================================================================
# Worktree Utilities
# ============================================================================


def create_test_worktree(test_name: str, base_repo: str | None = None) -> Path | None:
    """Create an isolated git worktree for a test."""
    if base_repo is None:
        base_repo = os.getcwd()

    worktree_path = WORKTREE_BASE / test_name
    branch_name = f"skilltest/{test_name}"

    # Clean up existing
    if worktree_path.exists():
        cleanup_test_worktree(test_name, base_repo)

    WORKTREE_BASE.mkdir(parents=True, exist_ok=True)

    try:
        # Get current HEAD
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=base_repo,
            timeout=10,
        )
        head_commit = head.stdout.strip()

        # Delete branch if exists
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            capture_output=True,
            cwd=base_repo,
            timeout=10,
        )

        # Create branch
        subprocess.run(
            ["git", "branch", branch_name, head_commit],
            capture_output=True,
            check=True,
            cwd=base_repo,
            timeout=10,
        )

        # Create worktree
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            capture_output=True,
            check=True,
            cwd=base_repo,
            timeout=30,
        )

        # Create .claude directory
        (worktree_path / ".claude").mkdir(parents=True, exist_ok=True)

        return worktree_path

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Error creating worktree for {test_name}: {e}", file=sys.stderr)
        return None


def cleanup_test_worktree(test_name: str, base_repo: str | None = None) -> bool:
    """Clean up a test worktree."""
    if base_repo is None:
        base_repo = os.getcwd()

    worktree_path = WORKTREE_BASE / test_name
    branch_name = f"skilltest/{test_name}"

    # Remove worktree
    if worktree_path.exists():
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                capture_output=True,
                cwd=base_repo,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        # Force remove if still exists
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

    # Delete branch
    try:
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            capture_output=True,
            cwd=base_repo,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    return True


# ============================================================================
# Test Execution
# ============================================================================


def setup_test_environment(test: TestCase, worktree_path: Path) -> bool:
    """Set up the test environment in the worktree."""
    try:
        # Create setup files
        for file_path, content in test.setup_files.items():
            full_path = worktree_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        # Run setup commands
        for cmd in test.setup_commands:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(worktree_path),
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                print(f"Setup command failed: {cmd}", file=sys.stderr)
                print(f"stderr: {result.stderr.decode()}", file=sys.stderr)
                return False

        return True

    except Exception as e:
        print(f"Error setting up test environment: {e}", file=sys.stderr)
        return False


def build_claude_command(test: TestCase, worktree_path: Path) -> str:
    """Build the Claude CLI command for a test."""
    # Filter out forbidden tools
    safe_tools = [t for t in test.allowed_tools if t not in FORBIDDEN_TOOLS]
    tools_arg = " ".join(f'"{t}"' for t in safe_tools)

    # Build command
    cmd_parts = [
        "claude",
        "-p",
        f'"{test.prompt}"',
        f"--allowedTools {tools_arg}",
        "--output-format stream-json",
        "--dangerously-skip-permissions",  # Safe in isolated worktree
    ]

    return " ".join(cmd_parts)


def monitor_test_execution(
    test: TestCase,
    session_name: str,
    worktree_path: Path,
    start_time: float,
) -> tuple[bool, str]:
    """Monitor test execution, inject input if needed, check for completion."""

    input_index = 0
    last_output = ""

    while True:
        elapsed = time.time() - start_time

        # Check timeout
        if elapsed > test.timeout_seconds:
            # Send Ctrl+C
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "C-c"],
                capture_output=True,
                timeout=5,
            )
            time.sleep(2)
            tmux_capture_pane(session_name)
            return False, "TIMEOUT"

        # Capture current output
        current_output = tmux_capture_pane(session_name)

        # Check for completion markers
        if "Claude Code session ended" in current_output:
            return True, "COMPLETED"

        # Check for shell prompt returning (Claude CLI finished)
        if current_output != last_output:
            # Look for shell prompt at end indicating Claude finished
            lines = current_output.strip().split("\n")
            if lines and lines[-1].endswith("$ "):
                return True, "COMPLETED"

        # Handle input injection
        if input_index < len(test.inject_input):
            inject = test.inject_input[input_index]
            wait_for = inject.get("wait_for", "")
            if wait_for and wait_for in current_output and wait_for not in last_output:
                send_text = inject.get("send", "")
                tmux_send_keys(session_name, send_text)
                input_index += 1

        last_output = current_output
        time.sleep(1)

    return False, "UNKNOWN"


def validate_test_results(
    test: TestCase,
    worktree_path: Path,
    output_log: str,
) -> tuple[bool, str | None, dict | None]:
    """Validate test results against expected outcomes."""

    # Load checkpoint if it exists
    checkpoint_path = worktree_path / ".claude" / "completion-checkpoint.json"
    checkpoint_data = None
    if checkpoint_path.exists():
        try:
            checkpoint_data = json.loads(checkpoint_path.read_text())
        except json.JSONDecodeError:
            pass

    # Validate state file exists
    if test.expected_state_file_exists:
        state_path = worktree_path / test.expected_state_file_exists
        if not state_path.exists():
            return (
                False,
                f"Expected state file not found: {test.expected_state_file_exists}",
                checkpoint_data,
            )

    # Validate checkpoint fields
    if test.expected_checkpoint and checkpoint_data:
        self_report = checkpoint_data.get("self_report", {})
        for key, expected_value in test.expected_checkpoint.items():
            actual_value = self_report.get(key)
            if actual_value != expected_value:
                return (
                    False,
                    f"Checkpoint {key}: expected {expected_value}, got {actual_value}",
                    checkpoint_data,
                )

    # Validate files modified
    if test.expected_files_modified:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(worktree_path),
                timeout=10,
            )
            modified_files = (
                result.stdout.strip().split("\n") if result.stdout.strip() else []
            )
            for expected_file in test.expected_files_modified:
                if expected_file not in modified_files:
                    return (
                        False,
                        f"Expected file not modified: {expected_file}",
                        checkpoint_data,
                    )
        except subprocess.TimeoutExpired:
            return False, "Failed to check git diff", checkpoint_data

    # Validate files contain
    for file_path, expected_content in test.expected_files_contain.items():
        full_path = worktree_path / file_path
        if not full_path.exists():
            return False, f"Expected file not found: {file_path}", checkpoint_data
        content = full_path.read_text()
        if expected_content not in content:
            return (
                False,
                f"File {file_path} does not contain expected content: {expected_content}",
                checkpoint_data,
            )

    # Validate output contains
    if test.expected_output_contains:
        if test.expected_output_contains not in output_log:
            return (
                False,
                f"Output does not contain expected: {test.expected_output_contains}",
                checkpoint_data,
            )

    return True, None, checkpoint_data


def run_single_test(test: TestCase, base_repo: str) -> TestResult:
    """Run a single skill test."""
    start_time = time.time()
    session_name = f"{TMUX_SESSION_PREFIX}-{test.name}"

    # Create worktree
    worktree_path = create_test_worktree(test.name, base_repo)
    if worktree_path is None:
        return TestResult(
            name=test.name,
            status="ERROR",
            duration_seconds=time.time() - start_time,
            failure_reason="Failed to create worktree",
        )

    try:
        # Set up test environment
        if not setup_test_environment(test, worktree_path):
            return TestResult(
                name=test.name,
                status="ERROR",
                duration_seconds=time.time() - start_time,
                failure_reason="Failed to set up test environment",
                worktree_path=str(worktree_path),
            )

        # Kill existing session if any
        tmux_kill_session(session_name)

        # Create tmux session
        if not tmux_create_session(session_name, str(worktree_path)):
            return TestResult(
                name=test.name,
                status="ERROR",
                duration_seconds=time.time() - start_time,
                failure_reason="Failed to create tmux session",
                worktree_path=str(worktree_path),
            )

        # Build and send Claude command
        claude_cmd = build_claude_command(test, worktree_path)
        time.sleep(0.5)  # Let tmux session initialize
        tmux_send_keys(session_name, claude_cmd)

        # Monitor execution
        completed, status = monitor_test_execution(
            test, session_name, worktree_path, start_time
        )

        # Capture final output
        output_log = tmux_capture_pane(session_name)

        # Validate results
        if status == "TIMEOUT":
            return TestResult(
                name=test.name,
                status="TIMEOUT",
                duration_seconds=time.time() - start_time,
                failure_reason=f"Test exceeded timeout of {test.timeout_seconds}s",
                output_log=output_log,
                worktree_path=str(worktree_path),
            )

        passed, failure_reason, checkpoint_data = validate_test_results(
            test, worktree_path, output_log
        )

        return TestResult(
            name=test.name,
            status="PASSED" if passed else "FAILED",
            duration_seconds=time.time() - start_time,
            failure_reason=failure_reason,
            checkpoint_valid=passed,
            checkpoint_data=checkpoint_data,
            output_log=output_log,
            worktree_path=str(worktree_path),
        )

    finally:
        # Cleanup tmux session
        tmux_kill_session(session_name)


# ============================================================================
# Test Discovery
# ============================================================================


def discover_tests(test_dir: Path, pattern: str = "*") -> list[TestCase]:
    """Discover test cases from JSON files."""
    tests = []

    if not test_dir.exists():
        return tests

    for json_file in test_dir.glob("*.json"):
        if json_file.name == "results.json":
            continue

        test_name = json_file.stem
        if not fnmatch.fnmatch(test_name, pattern):
            continue

        try:
            data = json.loads(json_file.read_text())
            test = TestCase.from_json(data, test_name)
            tests.append(test)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Invalid test file {json_file}: {e}", file=sys.stderr)

    return tests


def validate_test_case(data: dict) -> tuple[bool, list[str]]:
    """Validate a test case JSON structure."""
    errors = []

    required_fields = ["skill", "prompt"]
    for req_field in required_fields:
        if req_field not in data:
            errors.append(f"Missing required field: {req_field}")

    if "expected" in data:
        expected = data["expected"]
        if "checkpoint" in expected and not isinstance(expected["checkpoint"], dict):
            errors.append("expected.checkpoint must be an object")
        if "files_modified" in expected and not isinstance(
            expected["files_modified"], list
        ):
            errors.append("expected.files_modified must be an array")

    if "allowed_tools" in data:
        tools = data["allowed_tools"]
        for tool in tools:
            for forbidden in FORBIDDEN_TOOLS:
                if fnmatch.fnmatch(tool, forbidden):
                    errors.append(f"Forbidden tool in allowed_tools: {tool}")

    return len(errors) == 0, errors


# ============================================================================
# CLI Commands
# ============================================================================


def cmd_run(args):
    """Run skill tests."""
    test_dir = Path(args.test_dir)
    pattern = args.pattern or "*"

    if args.test:
        pattern = args.test

    # Discover tests
    tests = discover_tests(test_dir, pattern)
    if not tests:
        print(f"No tests found in {test_dir} matching '{pattern}'")
        return 1

    print(f"Found {len(tests)} test(s)")

    # Run tests
    base_repo = os.getcwd()
    results = []

    if args.parallel == 1:
        # Sequential execution
        for test in tests:
            print(f"\nRunning: {test.name}")
            result = run_single_test(test, base_repo)
            results.append(result)
            status_emoji = "[PASS]" if result.status == "PASSED" else "[FAIL]"
            print(f"  {status_emoji} {result.name} ({result.duration_seconds:.1f}s)")
            if result.failure_reason:
                print(f"    Reason: {result.failure_reason}")
    else:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(run_single_test, test, base_repo): test
                for test in tests
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                status_emoji = "[PASS]" if result.status == "PASSED" else "[FAIL]"
                print(f"{status_emoji} {result.name} ({result.duration_seconds:.1f}s)")
                if result.failure_reason:
                    print(f"  Reason: {result.failure_reason}")

    # Write results
    results_path = test_dir / "results.json"
    results_data = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": sum(1 for r in results if r.status == "PASSED"),
        "failed": sum(1 for r in results if r.status != "PASSED"),
        "tests": [
            {
                "name": r.name,
                "status": r.status,
                "duration_seconds": r.duration_seconds,
                "failure_reason": r.failure_reason,
                "checkpoint_valid": r.checkpoint_valid,
            }
            for r in results
        ],
    }
    test_dir.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results_data, indent=2))

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"RESULTS: {results_data['passed']}/{results_data['total']} passed")
    print(f"Results written to: {results_path}")

    # Cleanup worktrees unless --keep-worktrees
    if not args.keep_worktrees:
        print("\nCleaning up worktrees...")
        for test in tests:
            cleanup_test_worktree(test.name, base_repo)

    return 0 if results_data["failed"] == 0 else 1


def cmd_list(args):
    """List available tests."""
    test_dir = Path(args.test_dir)
    tests = discover_tests(test_dir)

    if not tests:
        print(f"No tests found in {test_dir}")
        return 0

    print(f"Available tests in {test_dir}:\n")
    for test in sorted(tests, key=lambda t: t.name):
        print(f"  {test.name}")
        print(f"    Skill: {test.skill}")
        print(f"    {test.description}")
        print()

    return 0


def cmd_validate(args):
    """Validate test case JSON files."""
    test_dir = Path(args.test_dir)

    if not test_dir.exists():
        print(f"Test directory not found: {test_dir}")
        return 1

    all_valid = True
    for json_file in test_dir.glob("*.json"):
        if json_file.name == "results.json":
            continue

        try:
            data = json.loads(json_file.read_text())
            valid, errors = validate_test_case(data)

            if valid:
                print(f"[OK] {json_file.name}")
            else:
                print(f"[INVALID] {json_file.name}")
                for error in errors:
                    print(f"  - {error}")
                all_valid = False

        except json.JSONDecodeError as e:
            print(f"[INVALID] {json_file.name}: JSON parse error: {e}")
            all_valid = False

    return 0 if all_valid else 1


def cmd_cleanup(args):
    """Clean up all test worktrees and tmux sessions."""
    base_repo = os.getcwd()

    # Kill all skilltest tmux sessions
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for session in result.stdout.strip().split("\n"):
            if session.startswith(TMUX_SESSION_PREFIX):
                print(f"Killing tmux session: {session}")
                tmux_kill_session(session)
    except subprocess.CalledProcessError:
        pass  # No sessions

    # Clean up worktrees
    if WORKTREE_BASE.exists():
        for worktree_dir in WORKTREE_BASE.iterdir():
            if worktree_dir.is_dir():
                print(f"Cleaning up worktree: {worktree_dir.name}")
                cleanup_test_worktree(worktree_dir.name, base_repo)

    print("Cleanup complete")
    return 0


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Skill Test Runner - Execute Claude Code skill tests"
    )
    parser.add_argument(
        "--test-dir",
        default=".claude/skill-tests",
        help="Directory containing test JSON files",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run skill tests")
    run_parser.add_argument("--test", "-t", help="Run specific test by name")
    run_parser.add_argument("--pattern", "-p", help="Run tests matching glob pattern")
    run_parser.add_argument(
        "--parallel",
        "-j",
        type=int,
        default=DEFAULT_PARALLEL,
        help=f"Max parallel tests (default: {DEFAULT_PARALLEL})",
    )
    run_parser.add_argument(
        "--keep-worktrees",
        action="store_true",
        help="Don't cleanup worktrees after tests",
    )
    run_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose output",
    )

    # list command
    subparsers.add_parser("list", help="List available tests")

    # validate command
    subparsers.add_parser("validate", help="Validate test case JSON files")

    # cleanup command
    subparsers.add_parser("cleanup", help="Clean up worktrees and tmux sessions")

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "cleanup":
        return cmd_cleanup(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
