#!/usr/bin/env python3
"""
Watch Claude output in real-time.

Usage:
    ./watch_output.py           # Watch all output
    ./watch_output.py --last 5  # Show last 5 responses
    ./watch_output.py --id cmd_abc123  # Show specific response
"""

import json
import sys
import time
import argparse
import os
from pathlib import Path

PROTOCOL_DIR = Path(os.environ.get("AGENT_PROTOCOL_DIR", "."))
OUTPUT_FILE = PROTOCOL_DIR / "output.jsonl"
STATUS_FILE = PROTOCOL_DIR / "status.json"


def read_outputs() -> list[dict]:
    if not OUTPUT_FILE.exists():
        return []
    outputs = []
    with open(OUTPUT_FILE) as f:
        for line in f:
            if line.strip():
                outputs.append(json.loads(line))
    return outputs


def read_status() -> dict:
    if not STATUS_FILE.exists():
        return {}
    with open(STATUS_FILE) as f:
        return json.load(f)


def print_response(resp: dict, verbose: bool = False):
    """Pretty print a response."""
    print(f"\n{'='*60}")
    print(f"ID: {resp.get('id')} | Exit: {resp.get('exit_code')} | {resp.get('timestamp', '')[:19]}")
    if verbose:
        print(f"Prompt: {resp.get('prompt', '')[:200]}")
    print("-"*60)
    print(resp.get("response", "(no response)"))
    print("="*60)


def watch_mode():
    """Watch for new outputs in real-time."""
    print(f"Watching {OUTPUT_FILE} for output...")
    print("Press Ctrl+C to stop\n")

    seen_ids = set()
    last_status = None

    while True:
        # Check status
        status = read_status()
        status_str = f"{status.get('state', '?')} - {status.get('task', '')}"
        if status_str != last_status:
            print(f"[STATUS] {status_str}")
            last_status = status_str

        # Check for new outputs
        for output in read_outputs():
            oid = output.get("id")
            if oid and oid not in seen_ids:
                seen_ids.add(oid)
                print_response(output)

        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Watch Claude output")
    parser.add_argument("--last", "-n", type=int, help="Show last N responses")
    parser.add_argument("--id", help="Show specific response by ID")
    parser.add_argument("--status", "-s", action="store_true", help="Show status only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show prompts too")
    args = parser.parse_args()

    if args.status:
        status = read_status()
        print(json.dumps(status, indent=2))
        return

    if args.id:
        for output in read_outputs():
            if output.get("id") == args.id:
                print_response(output, args.verbose)
                return
        print(f"No output found for ID: {args.id}")
        return

    if args.last:
        outputs = read_outputs()[-args.last:]
        for output in outputs:
            print_response(output, args.verbose)
        return

    # Default: watch mode
    try:
        watch_mode()
    except KeyboardInterrupt:
        print("\nStopped watching")


if __name__ == "__main__":
    main()
