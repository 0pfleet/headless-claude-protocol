#!/usr/bin/env python3
"""
Headless Claude Code wrapper.

Runs Claude Code in print mode, controlled via files:
- commands.jsonl: Send tasks here
- output.jsonl: Claude's responses appear here
- log.jsonl: Activity log

Usage:
    ./claude_wrapper.py                    # Start watching for tasks
    ./claude_wrapper.py --once "prompt"    # Run single prompt
"""

import subprocess
import json
import time
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

# Protocol files
PROTOCOL_DIR = Path(os.environ.get("AGENT_PROTOCOL_DIR", "."))
COMMANDS_FILE = PROTOCOL_DIR / "commands.jsonl"
OUTPUT_FILE = PROTOCOL_DIR / "output.jsonl"
LOG_FILE = PROTOCOL_DIR / "log.jsonl"
STATUS_FILE = PROTOCOL_DIR / "status.json"

# Track processed commands
PROCESSED_FILE = PROTOCOL_DIR / ".processed_commands"


def log(level: str, msg: str, **extra):
    """Write to log file and print."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": msg,
        **extra,
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[{level.upper()}] {msg}")


def set_status(state: str, task: str = None, detail: str = None):
    """Update status file."""
    with open(STATUS_FILE, "w") as f:
        json.dump({
            "state": state,
            "task": task,
            "detail": detail,
            "updated_at": datetime.now().isoformat(),
        }, f, indent=2)


def get_processed_ids() -> set:
    """Get set of already-processed command IDs."""
    if not PROCESSED_FILE.exists():
        return set()
    return set(PROCESSED_FILE.read_text().strip().split("\n"))


def mark_processed(cmd_id: str):
    """Mark a command as processed."""
    with open(PROCESSED_FILE, "a") as f:
        f.write(cmd_id + "\n")


def get_pending_commands() -> list[dict]:
    """Get unprocessed commands."""
    if not COMMANDS_FILE.exists():
        return []

    processed = get_processed_ids()
    pending = []

    with open(COMMANDS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                cmd = json.loads(line)
                if cmd.get("id") not in processed:
                    pending.append(cmd)

    return pending


def run_claude(prompt: str, workdir: str = None) -> tuple[int, str]:
    """
    Run Claude Code in print mode.
    Returns (exit_code, output).
    """
    cmd = [
        "claude",
        "--print",  # Non-interactive, just print response
        "--dangerously-skip-permissions",  # Auto-approve everything
        "--verbose",  # More output
    ]

    log("info", f"Running claude with prompt: {prompt[:100]}...")

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=workdir or os.getcwd(),
            timeout=600,  # 10 min timeout
            env={
                **os.environ,
                "TERM": "dumb",
                "NO_COLOR": "1",
            },
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"

        return result.returncode, output

    except subprocess.TimeoutExpired:
        return -1, "ERROR: Claude timed out after 10 minutes"
    except FileNotFoundError:
        return -1, "ERROR: 'claude' command not found. Is Claude Code installed?"
    except Exception as e:
        return -1, f"ERROR: {e}"


def write_output(cmd_id: str, prompt: str, response: str, exit_code: int):
    """Write response to output file."""
    entry = {
        "id": cmd_id,
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt,
        "response": response,
        "exit_code": exit_code,
    }
    with open(OUTPUT_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def handle_command(cmd: dict):
    """Process a single command."""
    cmd_id = cmd.get("id", "unknown")
    cmd_type = cmd.get("type", "task")

    if cmd_type == "abort":
        log("info", "Received abort command")
        set_status("stopped")
        sys.exit(0)

    if cmd_type == "task":
        prompt = cmd.get("task") or cmd.get("prompt", "")
        workdir = cmd.get("workdir")

        set_status("working", task=prompt[:50])
        log("info", f"Processing task: {prompt[:100]}")

        exit_code, output = run_claude(prompt, workdir)

        write_output(cmd_id, prompt, output, exit_code)
        mark_processed(cmd_id)

        if exit_code == 0:
            log("info", f"Task completed: {cmd_id}")
        else:
            log("error", f"Task failed (exit {exit_code}): {cmd_id}")

        set_status("idle")


def watch_loop(poll_interval: float = 2.0):
    """Main loop - watch for commands and process them."""
    log("info", "Claude wrapper started, watching for commands...")
    set_status("idle", detail="Waiting for tasks")

    # Ensure files exist
    COMMANDS_FILE.touch()
    OUTPUT_FILE.touch()

    print(f"\nProtocol directory: {PROTOCOL_DIR.absolute()}")
    print(f"Send tasks to: {COMMANDS_FILE}")
    print(f"Read output from: {OUTPUT_FILE}")
    print()

    while True:
        try:
            pending = get_pending_commands()
            for cmd in pending:
                handle_command(cmd)
        except KeyboardInterrupt:
            log("info", "Interrupted")
            set_status("stopped")
            break
        except Exception as e:
            log("error", f"Error processing commands: {e}")

        time.sleep(poll_interval)


def run_once(prompt: str, workdir: str = None):
    """Run a single prompt and exit."""
    log("info", f"Single-shot mode: {prompt[:100]}")
    set_status("working", task=prompt[:50])

    exit_code, output = run_claude(prompt, workdir)

    print("\n" + "="*60)
    print("RESPONSE:")
    print("="*60)
    print(output)
    print("="*60)
    print(f"\nExit code: {exit_code}")

    set_status("idle")
    return exit_code


def main():
    parser = argparse.ArgumentParser(description="Headless Claude Code wrapper")
    parser.add_argument("--once", "-o", metavar="PROMPT", help="Run single prompt and exit")
    parser.add_argument("--workdir", "-w", help="Working directory for Claude")
    parser.add_argument("--interval", "-i", type=float, default=2.0, help="Poll interval in seconds")
    args = parser.parse_args()

    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)

    if args.once:
        sys.exit(run_once(args.once, args.workdir))
    else:
        watch_loop(args.interval)


if __name__ == "__main__":
    main()
