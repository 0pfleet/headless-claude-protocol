#!/usr/bin/env python3
"""
Linear Backlog Worker

Pulls issues from Linear, sends them to Claude-in-a-Box, posts results.

Usage:
    ./linear_worker.py                    # Process one issue
    ./linear_worker.py --daemon           # Keep running, process queue
    ./linear_worker.py --dry-run          # Show what would be processed
    ./linear_worker.py --label "claude"   # Only process issues with this label

Environment:
    LINEAR_API_KEY      - Linear API key
    CLAUDE_BOX_SERVER   - Server URL (default: http://localhost:8080)
    LINEAR_TEAM_ID      - Team ID to filter issues (optional)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

import httpx

LINEAR_API = "https://api.linear.app/graphql"
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
CLAUDE_SERVER = os.environ.get("CLAUDE_BOX_SERVER", "http://localhost:8080")
TEAM_ID = os.environ.get("LINEAR_TEAM_ID", "")


def linear_query(query: str, variables: dict = None) -> dict:
    """Execute a Linear GraphQL query."""
    response = httpx.post(
        LINEAR_API,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": LINEAR_API_KEY},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        raise Exception(f"Linear API error: {data['errors']}")
    return data.get("data", {})


def get_pending_issues(label: str = None, limit: int = 10) -> list[dict]:
    """Fetch issues ready for Claude to work on."""
    # Filter: Backlog or Todo state, optionally with specific label
    query = """
    query PendingIssues($first: Int, $filter: IssueFilter) {
        issues(first: $first, filter: $filter, orderBy: priority) {
            nodes {
                id
                identifier
                title
                description
                priority
                state { name }
                labels { nodes { name } }
                url
            }
        }
    }
    """

    filter_obj = {
        "state": {"type": {"in": ["backlog", "unstarted"]}},
    }

    if TEAM_ID:
        filter_obj["team"] = {"id": {"eq": TEAM_ID}}

    if label:
        filter_obj["labels"] = {"name": {"eq": label}}

    data = linear_query(query, {"first": limit, "filter": filter_obj})
    return data.get("issues", {}).get("nodes", [])


def update_issue_state(issue_id: str, state_name: str):
    """Update issue state (In Progress, Done, etc.)."""
    # First, find the state ID
    query = """
    query States($filter: WorkflowStateFilter) {
        workflowStates(filter: $filter) {
            nodes { id name }
        }
    }
    """
    states = linear_query(query, {"filter": {"name": {"eq": state_name}}})
    state_nodes = states.get("workflowStates", {}).get("nodes", [])

    if not state_nodes:
        print(f"Warning: State '{state_name}' not found")
        return

    state_id = state_nodes[0]["id"]

    mutation = """
    mutation UpdateIssue($id: String!, $stateId: String!) {
        issueUpdate(id: $id, input: { stateId: $stateId }) {
            success
        }
    }
    """
    linear_query(mutation, {"id": issue_id, "stateId": state_id})


def add_comment(issue_id: str, body: str):
    """Add a comment to an issue."""
    mutation = """
    mutation AddComment($issueId: String!, $body: String!) {
        commentCreate(input: { issueId: $issueId, body: $body }) {
            success
        }
    }
    """
    linear_query(mutation, {"issueId": issue_id, "body": body})


def build_prompt(issue: dict) -> str:
    """Build a prompt from a Linear issue."""
    return f"""You are working on issue {issue['identifier']}: {issue['title']}

Description:
{issue.get('description') or '(no description)'}

Instructions:
1. Analyze this issue and understand what needs to be done
2. Look at the relevant code in the workspace
3. Make the necessary changes to fix/implement this
4. Run any relevant tests
5. Summarize what you did

If you cannot complete this task, explain why and what additional information you need.
"""


def process_issue(issue: dict, dry_run: bool = False) -> bool:
    """Process a single issue with Claude."""
    print(f"\n{'='*60}")
    print(f"Processing: {issue['identifier']} - {issue['title']}")
    print(f"URL: {issue['url']}")
    print(f"Priority: {issue.get('priority', 'none')}")
    print(f"State: {issue.get('state', {}).get('name', '?')}")
    print("="*60)

    if dry_run:
        print("[DRY RUN] Would process this issue")
        return True

    prompt = build_prompt(issue)

    # Mark as In Progress
    try:
        update_issue_state(issue["id"], "In Progress")
    except Exception as e:
        print(f"Warning: Could not update state: {e}")

    # Send to Claude
    output_lines = []
    success = False

    try:
        with httpx.stream(
            "POST",
            f"{CLAUDE_SERVER}/task",
            json={"prompt": prompt},
            timeout=None,
        ) as response:
            if response.status_code == 409:
                print("Error: Claude is busy")
                return False

            if response.status_code != 200:
                print(f"Error: {response.status_code}")
                return False

            event_type = None
            for line in response.iter_lines():
                line = line.strip()

                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue

                    if event_type == "output":
                        output_lines.append(data.get("line", ""))
                        # Try to extract text for display
                        try:
                            parsed = json.loads(data.get("line", ""))
                            if parsed.get("type") == "assistant":
                                for block in parsed.get("message", {}).get("content", []):
                                    if block.get("type") == "text":
                                        print(block.get("text", ""), end="", flush=True)
                        except:
                            pass

                    elif event_type == "done":
                        success = data.get("exit_code") == 0
                        print(f"\n[{'SUCCESS' if success else 'FAILED'}]")

    except Exception as e:
        print(f"Error communicating with Claude: {e}")
        return False

    # Build result comment
    result_comment = f"""## Claude's Analysis

**Status:** {'Completed' if success else 'Failed/Needs Review'}
**Processed at:** {datetime.now().isoformat()}

### Output Summary

```
{chr(10).join(output_lines[-50:])}
```

---
*Processed by Claude-in-a-Box*
"""

    # Post comment and update state
    try:
        add_comment(issue["id"], result_comment)

        if success:
            update_issue_state(issue["id"], "In Review")
        else:
            update_issue_state(issue["id"], "Todo")  # Back to queue
    except Exception as e:
        print(f"Warning: Could not update Linear: {e}")

    return success


def daemon_loop(label: str = None, interval: int = 60):
    """Keep running and process issues as they appear."""
    print(f"Starting daemon mode (poll every {interval}s)")
    print(f"Label filter: {label or 'none'}")
    print("Press Ctrl+C to stop")

    while True:
        try:
            issues = get_pending_issues(label=label, limit=1)

            if issues:
                issue = issues[0]
                process_issue(issue)
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No pending issues")

            time.sleep(interval)

        except KeyboardInterrupt:
            print("\nStopping daemon")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Linear Backlog Worker")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run continuously")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually process")
    parser.add_argument("--label", "-l", help="Only process issues with this label")
    parser.add_argument("--interval", "-i", type=int, default=60, help="Daemon poll interval (seconds)")
    parser.add_argument("--limit", "-n", type=int, default=5, help="Max issues to show/process")
    args = parser.parse_args()

    if not LINEAR_API_KEY:
        print("Error: LINEAR_API_KEY not set")
        print("Get your API key from: https://linear.app/settings/api")
        sys.exit(1)

    if args.daemon:
        daemon_loop(label=args.label, interval=args.interval)
    else:
        issues = get_pending_issues(label=args.label, limit=args.limit)

        if not issues:
            print("No pending issues found")
            return

        print(f"Found {len(issues)} pending issues:")
        for issue in issues:
            labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]
            print(f"  {issue['identifier']}: {issue['title'][:50]} [{', '.join(labels)}]")

        if args.dry_run:
            print("\n[DRY RUN] Would process first issue")
        else:
            print()
            process_issue(issues[0], dry_run=args.dry_run)


if __name__ == "__main__":
    main()
