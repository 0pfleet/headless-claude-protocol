#!/usr/bin/env python3
"""
Demo agent that uses the protocol.
Run this, then use respond.py to interact with it.
"""

import time
import subprocess
import os
from protocol import AgentProtocol

# Make all tools non-interactive
os.environ.setdefault("DEBIAN_FRONTEND", "noninteractive")
os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
os.environ.setdefault("PIP_NO_INPUT", "1")


def run_cmd(cmd: str, check: bool = True) -> tuple[int, str, str]:
    """Run a command non-interactively."""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        env={**os.environ, "TERM": "dumb"},
        timeout=300,
    )
    return result.returncode, result.stdout, result.stderr


def main():
    agent = AgentProtocol()
    agent.log("info", "Agent started")
    agent.set_status("idle", task="Waiting for task")

    print("Demo agent running. Use respond.py to interact.")
    print("Protocol files in current directory.")
    print()

    # Main loop
    while True:
        # Check for commands
        cmd = agent.check_commands()
        if cmd:
            cmd_type = cmd.get("type")
            agent.log("info", f"Received command: {cmd_type}", command=cmd)

            if cmd_type == "abort":
                agent.log("info", "Aborting")
                agent.set_status("stopped")
                break

            elif cmd_type == "stop":
                agent.log("info", "Stopping current task")
                agent.set_status("idle")

            elif cmd_type == "task":
                task = cmd.get("task", "")
                agent.log("info", f"Starting task: {task}")
                agent.set_status("working", task=task)

                # Demo: pretend to work on task
                handle_task(agent, task)

        time.sleep(1)


def handle_task(agent: AgentProtocol, task: str):
    """Handle a task - demo implementation."""

    # Simulate some work
    agent.set_status("working", task=task, detail="Analyzing task...")
    time.sleep(2)

    # Demo: ask for confirmation before "dangerous" operations
    if "delete" in task.lower() or "remove" in task.lower():
        if not agent.confirm(f"Task involves deletion. Proceed with: {task}?"):
            agent.log("info", "User cancelled deletion task")
            agent.set_status("idle", task="Cancelled")
            return

    # Demo: ask for choice
    approach = agent.choose(
        "How should I approach this task?",
        choices=["quick_and_dirty", "thorough", "minimal"],
        default="thorough",
    )
    agent.log("info", f"Using approach: {approach}")

    # Demo: ask for additional context if needed
    if "unclear" in task.lower():
        clarification = agent.ask("The task is unclear. Can you provide more details?")
        agent.log("info", f"Got clarification: {clarification}")
        task = f"{task} - Clarification: {clarification}"

    # Pretend to do work
    agent.set_status("working", task=task, detail=f"Working ({approach} mode)...")
    for i in range(5):
        agent.log("debug", f"Work step {i+1}/5")
        time.sleep(1)

    # Done
    agent.log("info", f"Task completed: {task}")
    agent.set_status("idle", task=f"Completed: {task}")


if __name__ == "__main__":
    main()
