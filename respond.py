#!/usr/bin/env python3
"""
Controller CLI for interacting with the agent.

Usage:
    python respond.py              # Interactive mode
    python respond.py status       # Show status
    python respond.py pending      # Show pending requests
    python respond.py log [N]      # Show last N log entries
    python respond.py task "..."   # Send a task
    python respond.py stop         # Stop current task
    python respond.py abort        # Kill agent
"""

import sys
import json
from protocol import ControllerProtocol


def interactive_respond(ctrl: ControllerProtocol):
    """Interactively respond to pending requests."""
    pending = ctrl.get_pending_requests()

    if not pending:
        print("No pending requests.")
        return

    for req in pending:
        req_id = req["id"]
        req_type = req["type"]
        prompt = req["prompt"]
        choices = req.get("choices", [])
        default = req.get("default", "")

        print(f"\n{'='*50}")
        print(f"Request ID: {req_id}")
        print(f"Type: {req_type}")
        print(f"Prompt: {prompt}")

        if choices:
            print(f"Choices: {', '.join(choices)}")
        if default:
            print(f"Default: {default}")

        print()

        # Get response based on type
        if req_type == "confirm":
            while True:
                answer = input("Answer [yes/no]: ").strip().lower()
                if answer in ("", "yes", "y", "no", "n"):
                    if answer == "":
                        answer = default
                    elif answer == "y":
                        answer = "yes"
                    elif answer == "n":
                        answer = "no"
                    break
                print("Please enter 'yes' or 'no'")

        elif req_type == "choice":
            while True:
                answer = input(f"Answer [{'/'.join(choices)}]: ").strip()
                if answer == "":
                    answer = default
                    break
                if answer in choices:
                    break
                print(f"Please choose from: {choices}")

        else:  # input or file
            answer = input("Answer: ").strip()
            if answer == "" and default:
                answer = default

        ctrl.respond(req_id, answer)
        print(f"Sent response: {answer}")


def show_status(ctrl: ControllerProtocol):
    """Show current agent status."""
    status = ctrl.get_status()
    if status:
        print(json.dumps(status, indent=2))
    else:
        print("No agent running (no status file)")


def show_pending(ctrl: ControllerProtocol):
    """Show pending requests."""
    pending = ctrl.get_pending_requests()
    if not pending:
        print("No pending requests")
    else:
        for req in pending:
            print(json.dumps(req, indent=2))


def show_log(ctrl: ControllerProtocol, tail: int = 20):
    """Show recent log entries."""
    logs = ctrl.get_log(tail=tail)
    for entry in logs:
        ts = entry.get("timestamp", "")[:19]
        level = entry.get("level", "?").upper()
        msg = entry.get("message", "")
        print(f"[{ts}] {level}: {msg}")


def send_task(ctrl: ControllerProtocol, task: str):
    """Send a task to the agent."""
    cmd_id = ctrl.send_task(task)
    print(f"Sent task (cmd_id={cmd_id}): {task}")


def main():
    ctrl = ControllerProtocol()

    if len(sys.argv) < 2:
        # Interactive mode
        interactive_respond(ctrl)
        return

    cmd = sys.argv[1]

    if cmd == "status":
        show_status(ctrl)

    elif cmd == "pending":
        show_pending(ctrl)

    elif cmd == "log":
        tail = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        show_log(ctrl, tail)

    elif cmd == "task":
        if len(sys.argv) < 3:
            print("Usage: respond.py task 'task description'")
            sys.exit(1)
        send_task(ctrl, sys.argv[2])

    elif cmd == "stop":
        ctrl.send_stop()
        print("Sent stop command")

    elif cmd == "abort":
        ctrl.send_command("abort")
        print("Sent abort command")

    elif cmd == "watch":
        # Simple watch mode
        import time
        while True:
            print("\033[2J\033[H")  # Clear screen
            print("=== Status ===")
            show_status(ctrl)
            print("\n=== Pending Requests ===")
            show_pending(ctrl)
            print("\n=== Recent Log ===")
            show_log(ctrl, 10)
            time.sleep(2)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
