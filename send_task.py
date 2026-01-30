#!/usr/bin/env python3
"""
Send a task to the Claude wrapper.

Usage:
    ./send_task.py "Fix the bug in main.py"
    ./send_task.py --workdir /path/to/project "Add tests"
    echo "Your task" | ./send_task.py --stdin
"""

import json
import sys
import argparse
import uuid
from pathlib import Path
from datetime import datetime
import os

PROTOCOL_DIR = Path(os.environ.get("AGENT_PROTOCOL_DIR", "."))
COMMANDS_FILE = PROTOCOL_DIR / "commands.jsonl"


def send_task(task: str, workdir: str = None) -> str:
    """Send a task and return the command ID."""
    cmd_id = f"cmd_{uuid.uuid4().hex[:8]}"

    command = {
        "id": cmd_id,
        "type": "task",
        "task": task,
        "timestamp": datetime.now().isoformat(),
    }
    if workdir:
        command["workdir"] = workdir

    COMMANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COMMANDS_FILE, "a") as f:
        f.write(json.dumps(command) + "\n")

    return cmd_id


def main():
    parser = argparse.ArgumentParser(description="Send task to Claude wrapper")
    parser.add_argument("task", nargs="?", help="Task to send")
    parser.add_argument("--workdir", "-w", help="Working directory for the task")
    parser.add_argument("--stdin", action="store_true", help="Read task from stdin")
    parser.add_argument("--abort", action="store_true", help="Send abort command")
    args = parser.parse_args()

    if args.abort:
        cmd_id = f"cmd_{uuid.uuid4().hex[:8]}"
        with open(COMMANDS_FILE, "a") as f:
            f.write(json.dumps({"id": cmd_id, "type": "abort"}) + "\n")
        print(f"Sent abort command: {cmd_id}")
        return

    if args.stdin:
        task = sys.stdin.read().strip()
    elif args.task:
        task = args.task
    else:
        parser.print_help()
        sys.exit(1)

    cmd_id = send_task(task, args.workdir)
    print(f"Task sent: {cmd_id}")
    print(f"Task: {task[:100]}{'...' if len(task) > 100 else ''}")
    print(f"\nWatch output: tail -f {PROTOCOL_DIR / 'output.jsonl'}")


if __name__ == "__main__":
    main()
