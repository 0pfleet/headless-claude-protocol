"""
Agent Control Protocol - Core module

File-based communication between agent and human controller.
"""

import json
import time
import uuid
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Literal
from datetime import datetime

# Protocol directory (configurable via env)
PROTOCOL_DIR = Path(os.environ.get("AGENT_PROTOCOL_DIR", "."))

# File paths
STATUS_FILE = PROTOCOL_DIR / "status.json"
REQUESTS_FILE = PROTOCOL_DIR / "requests.jsonl"
RESPONSES_FILE = PROTOCOL_DIR / "responses.jsonl"
LOG_FILE = PROTOCOL_DIR / "log.jsonl"
COMMANDS_FILE = PROTOCOL_DIR / "commands.jsonl"

# Polling config
POLL_INTERVAL = float(os.environ.get("AGENT_POLL_INTERVAL", "1.0"))
POLL_TIMEOUT = float(os.environ.get("AGENT_POLL_TIMEOUT", "3600"))  # 1 hour default


def _append_jsonl(path: Path, data: dict):
    """Append a JSON record to a JSONL file."""
    with open(path, "a") as f:
        f.write(json.dumps(data) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    """Read all records from a JSONL file."""
    if not path.exists():
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _write_json(path: Path, data: dict):
    """Write JSON to file atomically."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)


def _read_json(path: Path) -> Optional[dict]:
    """Read JSON file if it exists."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# === Agent-side API ===

class AgentProtocol:
    """Agent-side protocol handler."""

    def __init__(self, agent_id: str = None):
        self.agent_id = agent_id or f"agent_{uuid.uuid4().hex[:8]}"
        self._request_counter = 0
        self._processed_commands = set()
        self._init_files()

    def _init_files(self):
        """Ensure protocol files exist."""
        PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
        for f in [REQUESTS_FILE, RESPONSES_FILE, LOG_FILE, COMMANDS_FILE]:
            f.touch()
        self.set_status("idle")

    def _next_request_id(self) -> str:
        self._request_counter += 1
        return f"req_{self.agent_id}_{self._request_counter:04d}"

    def set_status(self, state: str, task: str = None, detail: str = None):
        """Update agent status."""
        _write_json(STATUS_FILE, {
            "agent_id": self.agent_id,
            "state": state,
            "task": task,
            "detail": detail,
            "updated_at": datetime.now().isoformat(),
        })

    def log(self, level: str, message: str, **extra):
        """Write to activity log."""
        _append_jsonl(LOG_FILE, {
            "timestamp": datetime.now().isoformat(),
            "agent_id": self.agent_id,
            "level": level,
            "message": message,
            **extra,
        })

    def request_input(
        self,
        prompt: str,
        request_type: Literal["confirm", "choice", "input", "file"] = "input",
        choices: list[str] = None,
        default: str = None,
    ) -> str:
        """
        Request input from human controller.
        Blocks until response received or timeout.
        """
        req_id = self._next_request_id()

        request = {
            "id": req_id,
            "timestamp": datetime.now().isoformat(),
            "type": request_type,
            "prompt": prompt,
        }
        if choices:
            request["choices"] = choices
        if default is not None:
            request["default"] = default

        _append_jsonl(REQUESTS_FILE, request)
        self.set_status("waiting_for_input", detail=prompt)
        self.log("info", f"Waiting for input: {prompt}", request_id=req_id)

        # Poll for response
        start = time.time()
        while time.time() - start < POLL_TIMEOUT:
            responses = _read_jsonl(RESPONSES_FILE)
            for resp in responses:
                if resp.get("id") == req_id:
                    self.log("info", f"Got response: {resp.get('answer')}", request_id=req_id)
                    return resp.get("answer", default)
            time.sleep(POLL_INTERVAL)

        # Timeout - use default or raise
        if default is not None:
            self.log("warn", f"Timeout, using default: {default}", request_id=req_id)
            return default
        raise TimeoutError(f"No response for request {req_id}")

    def confirm(self, prompt: str, default: bool = False) -> bool:
        """Ask yes/no confirmation."""
        answer = self.request_input(
            prompt,
            request_type="confirm",
            choices=["no", "yes"],
            default="yes" if default else "no",
        )
        return answer.lower() in ("yes", "y", "true", "1")

    def choose(self, prompt: str, choices: list[str], default: str = None) -> str:
        """Ask to pick from choices."""
        return self.request_input(
            prompt,
            request_type="choice",
            choices=choices,
            default=default or choices[0],
        )

    def ask(self, prompt: str, default: str = None) -> str:
        """Ask for free-form input."""
        return self.request_input(prompt, request_type="input", default=default)

    def check_commands(self) -> Optional[dict]:
        """Check for new commands from controller."""
        commands = _read_jsonl(COMMANDS_FILE)
        for cmd in commands:
            cmd_id = cmd.get("id")
            if cmd_id and cmd_id not in self._processed_commands:
                self._processed_commands.add(cmd_id)
                return cmd
        return None


# === Controller-side API ===

class ControllerProtocol:
    """Human controller-side protocol handler."""

    def __init__(self):
        PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
        self._command_counter = 0

    def _next_command_id(self) -> str:
        self._command_counter += 1
        return f"cmd_{self._command_counter:04d}"

    def get_status(self) -> Optional[dict]:
        """Get current agent status."""
        return _read_json(STATUS_FILE)

    def get_pending_requests(self) -> list[dict]:
        """Get requests that haven't been answered."""
        requests = _read_jsonl(REQUESTS_FILE)
        responses = _read_jsonl(RESPONSES_FILE)
        answered_ids = {r.get("id") for r in responses}
        return [r for r in requests if r.get("id") not in answered_ids]

    def respond(self, request_id: str, answer: str):
        """Send response to a request."""
        _append_jsonl(RESPONSES_FILE, {
            "id": request_id,
            "answer": answer,
            "timestamp": datetime.now().isoformat(),
        })

    def send_command(self, command_type: str, **params):
        """Send command to agent."""
        cmd_id = self._next_command_id()
        _append_jsonl(COMMANDS_FILE, {
            "id": cmd_id,
            "type": command_type,
            "timestamp": datetime.now().isoformat(),
            **params,
        })
        return cmd_id

    def send_task(self, task: str):
        """Send a new task to the agent."""
        return self.send_command("task", task=task)

    def send_stop(self):
        """Tell agent to stop current task."""
        return self.send_command("stop")

    def get_log(self, tail: int = None) -> list[dict]:
        """Get activity log, optionally last N entries."""
        logs = _read_jsonl(LOG_FILE)
        if tail:
            return logs[-tail:]
        return logs


# === CLI helpers ===

def print_status():
    """Print current status (for shell scripts)."""
    ctrl = ControllerProtocol()
    status = ctrl.get_status()
    if status:
        print(json.dumps(status, indent=2))
    else:
        print("No status file found")


def print_pending():
    """Print pending requests (for shell scripts)."""
    ctrl = ControllerProtocol()
    pending = ctrl.get_pending_requests()
    for req in pending:
        print(json.dumps(req))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            print_status()
        elif cmd == "pending":
            print_pending()
        else:
            print(f"Unknown command: {cmd}")
    else:
        print("Usage: python protocol.py [status|pending]")
