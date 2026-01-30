#!/usr/bin/env python3
"""
Claude-in-a-Box CLI Client

Send tasks to the server and watch streaming output.

Usage:
    ./client.py "Fix the bug in main.py"
    ./client.py --server http://localhost:8080 "Run tests"
    ./client.py status
    ./client.py stop
    ./client.py history
"""

import argparse
import json
import sys
import httpx
import os

DEFAULT_SERVER = os.environ.get("CLAUDE_BOX_SERVER", "http://localhost:8080")


def send_task(server: str, prompt: str, workdir: str = None):
    """Send task and stream SSE output."""
    print(f"Sending task to {server}...")
    print(f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print("-" * 60)

    payload = {"prompt": prompt}
    if workdir:
        payload["workdir"] = workdir

    with httpx.stream(
        "POST",
        f"{server}/task",
        json=payload,
        timeout=None,  # No timeout for streaming
    ) as response:
        if response.status_code == 409:
            data = response.json()
            print(f"Error: Agent is busy with task {data.get('current_task')}")
            sys.exit(1)

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text)
            sys.exit(1)

        # Parse SSE stream
        event_type = None
        data_buffer = ""

        for line in response.iter_lines():
            line = line.strip()

            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_buffer = line[5:].strip()

                try:
                    data = json.loads(data_buffer)
                except json.JSONDecodeError:
                    continue

                # Handle events
                if event_type == "start":
                    print(f"[STARTED] Task ID: {data.get('task_id')}")
                    print("-" * 60)

                elif event_type == "output":
                    line_text = data.get("line", "")
                    # Try to parse as JSON (Claude's stream-json format)
                    try:
                        parsed = json.loads(line_text)
                        if parsed.get("type") == "assistant":
                            content = parsed.get("message", {}).get("content", [])
                            for block in content:
                                if block.get("type") == "text":
                                    print(block.get("text", ""), end="", flush=True)
                                elif block.get("type") == "tool_use":
                                    print(f"\n[TOOL] {block.get('name')}: {block.get('input', {})}")
                        elif parsed.get("type") == "result":
                            print(f"\n[RESULT] Cost: ${parsed.get('cost_usd', 0):.4f}")
                    except json.JSONDecodeError:
                        # Plain text output
                        print(line_text)

                elif event_type == "done":
                    print("-" * 60)
                    state = data.get("state", "unknown")
                    exit_code = data.get("exit_code", -1)
                    print(f"[{state.upper()}] Exit code: {exit_code}")

                elif event_type == "error":
                    print(f"[ERROR] {data.get('error')}")

                elif event_type == "cancelled":
                    print("[CANCELLED] Task was stopped")

                data_buffer = ""
                event_type = None

            elif line.startswith(":"):
                # Comment/heartbeat, ignore
                pass


def get_status(server: str):
    """Get current agent status."""
    response = httpx.get(f"{server}/status")
    print(json.dumps(response.json(), indent=2))


def stop_task(server: str):
    """Stop current task."""
    response = httpx.post(f"{server}/stop")
    print(json.dumps(response.json(), indent=2))


def get_history(server: str, limit: int = 10):
    """Get task history."""
    response = httpx.get(f"{server}/history", params={"limit": limit})
    data = response.json()

    for task in data.get("history", []):
        state = task.get("state", "?")
        prompt = task.get("prompt", "")[:50]
        exit_code = task.get("exit_code", "?")
        print(f"[{state}] {task.get('id')} - {prompt}... (exit: {exit_code})")


def main():
    parser = argparse.ArgumentParser(description="Claude-in-a-Box CLI")
    parser.add_argument("command", nargs="?", help="Task prompt or command (status/stop/history)")
    parser.add_argument("--server", "-s", default=DEFAULT_SERVER, help="Server URL")
    parser.add_argument("--workdir", "-w", help="Working directory for task")
    parser.add_argument("--limit", "-n", type=int, default=10, help="History limit")
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "status":
        get_status(args.server)
    elif args.command == "stop":
        stop_task(args.server)
    elif args.command == "history":
        get_history(args.server, args.limit)
    else:
        # Treat as task prompt
        send_task(args.server, args.command, args.workdir)


if __name__ == "__main__":
    main()
