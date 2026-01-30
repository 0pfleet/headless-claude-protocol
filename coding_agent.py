#!/usr/bin/env python3
"""
A more realistic coding agent example.

This agent can:
- Run shell commands (non-interactively)
- Read/write files
- Ask for confirmation on dangerous operations
- Request clarification when needed
"""

import os
import subprocess
import json
import time
from pathlib import Path
from protocol import AgentProtocol

# Force non-interactive mode for all tools
ENV_OVERRIDES = {
    "DEBIAN_FRONTEND": "noninteractive",
    "GIT_TERMINAL_PROMPT": "0",
    "PIP_NO_INPUT": "1",
    "NPM_CONFIG_YES": "true",
    "CI": "true",  # Many tools check this
    "TERM": "dumb",
}


class CodingAgent:
    def __init__(self, workdir: str = "."):
        self.protocol = AgentProtocol()
        self.workdir = Path(workdir).resolve()
        self.env = {**os.environ, **ENV_OVERRIDES}

    def log(self, msg: str, level: str = "info", **extra):
        self.protocol.log(level, msg, **extra)
        print(f"[{level.upper()}] {msg}")

    def status(self, state: str, task: str = None, detail: str = None):
        self.protocol.set_status(state, task, detail)

    def run_cmd(
        self,
        cmd: str,
        check: bool = True,
        timeout: int = 300,
        confirm_if_dangerous: bool = True,
    ) -> tuple[int, str, str]:
        """Run a shell command non-interactively."""

        # Check for dangerous commands
        dangerous_patterns = ["rm -rf", "rm -r", "git push -f", "drop table", "truncate"]
        if confirm_if_dangerous:
            for pattern in dangerous_patterns:
                if pattern in cmd.lower():
                    if not self.protocol.confirm(f"Run dangerous command?\n{cmd}"):
                        self.log(f"User cancelled dangerous command: {cmd}", "warn")
                        raise RuntimeError("User cancelled")

        self.log(f"Running: {cmd}")

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.workdir,
                env=self.env,
                timeout=timeout,
            )

            if result.returncode != 0:
                self.log(f"Command failed (exit {result.returncode}): {result.stderr}", "error")
                if check:
                    raise subprocess.CalledProcessError(
                        result.returncode, cmd, result.stdout, result.stderr
                    )

            return result.returncode, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            self.log(f"Command timed out after {timeout}s", "error")
            raise

    def read_file(self, path: str) -> str:
        """Read a file."""
        full_path = self.workdir / path
        self.log(f"Reading: {full_path}")
        return full_path.read_text()

    def write_file(self, path: str, content: str, confirm: bool = True):
        """Write a file, optionally confirming with user."""
        full_path = self.workdir / path

        if confirm and full_path.exists():
            if not self.protocol.confirm(f"Overwrite existing file?\n{full_path}"):
                self.log(f"User cancelled overwrite: {path}", "warn")
                return False

        self.log(f"Writing: {full_path}")
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return True

    def git_commit(self, message: str, add_all: bool = False):
        """Make a git commit."""
        if add_all:
            self.run_cmd("git add -A")

        # Show what will be committed
        _, diff, _ = self.run_cmd("git diff --cached --stat", check=False)
        if not diff.strip():
            self.log("Nothing to commit", "warn")
            return

        if self.protocol.confirm(f"Commit these changes?\n{diff}\n\nMessage: {message}"):
            self.run_cmd(f'git commit -m "{message}"')
            self.log("Committed changes")
        else:
            self.run_cmd("git reset HEAD", check=False)
            self.log("Commit cancelled, changes unstaged")

    def install_deps(self, package_manager: str = "auto"):
        """Install dependencies."""
        if package_manager == "auto":
            if (self.workdir / "package.json").exists():
                package_manager = "npm"
            elif (self.workdir / "requirements.txt").exists():
                package_manager = "pip"
            elif (self.workdir / "Cargo.toml").exists():
                package_manager = "cargo"
            else:
                package_manager = self.protocol.choose(
                    "Which package manager?",
                    choices=["npm", "pip", "cargo", "none"],
                )

        if package_manager == "npm":
            self.run_cmd("npm install --yes")
        elif package_manager == "pip":
            self.run_cmd("pip install -r requirements.txt --quiet")
        elif package_manager == "cargo":
            self.run_cmd("cargo build")


def main():
    agent = CodingAgent()
    agent.status("idle", "Waiting for commands")
    agent.log("Coding agent started")

    print("Coding agent running. Use respond.py to interact.")
    print()

    while True:
        cmd = agent.protocol.check_commands()
        if cmd:
            cmd_type = cmd.get("type")

            if cmd_type == "abort":
                agent.log("Aborting")
                break

            elif cmd_type == "task":
                task = cmd.get("task", "")
                agent.status("working", task)
                try:
                    execute_task(agent, task)
                except Exception as e:
                    agent.log(f"Task failed: {e}", "error")
                agent.status("idle")

        time.sleep(1)


def execute_task(agent: CodingAgent, task: str):
    """Execute a task - this is where your LLM integration would go."""
    agent.log(f"Executing task: {task}")

    # In a real implementation, this would:
    # 1. Send the task to an LLM
    # 2. Parse the LLM's response for tool calls
    # 3. Execute tools using this agent's methods
    # 4. Loop until task complete

    # Demo: simple command interpreter
    if task.startswith("run:"):
        cmd = task[4:].strip()
        agent.run_cmd(cmd)

    elif task.startswith("read:"):
        path = task[5:].strip()
        content = agent.read_file(path)
        agent.log(f"File content:\n{content[:500]}...")

    elif task.startswith("write:"):
        # Format: write:path:content
        parts = task[6:].split(":", 1)
        if len(parts) == 2:
            agent.write_file(parts[0].strip(), parts[1])

    elif task == "git status":
        agent.run_cmd("git status")

    elif task.startswith("commit:"):
        message = task[7:].strip()
        agent.git_commit(message, add_all=True)

    else:
        # Unknown task - ask for clarification
        clarified = agent.protocol.ask(
            f"I don't understand the task:\n{task}\n\nCan you rephrase or give me a specific command?"
        )
        execute_task(agent, clarified)


if __name__ == "__main__":
    main()
