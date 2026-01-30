#!/usr/bin/env python3
"""
Claude-in-a-Box Task Server

HTTP server with SSE streaming for controlling Claude Code.

Endpoints:
    POST /task          Submit a task, get SSE stream of progress
    GET  /status        Current agent status
    GET  /health        Health check
    POST /stop          Stop current task
    GET  /history       Recent task history
"""

import asyncio
import json
import os
import sys
import uuid
import subprocess
from datetime import datetime
from typing import AsyncGenerator, Optional
from dataclasses import dataclass, asdict, field

from aiohttp import web

# Config
HOST = os.environ.get("AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("AGENT_PORT", "8080"))
WORKSPACE = os.environ.get("WORKSPACE_DIR", "/workspace")
MAX_HISTORY = 100


@dataclass
class TaskStatus:
    id: str
    state: str  # pending, running, completed, failed, cancelled
    prompt: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    output_lines: list[str] = field(default_factory=list)
    error: Optional[str] = None


class ClaudeAgent:
    """Manages Claude Code process and streaming output."""

    def __init__(self):
        self.current_task: Optional[TaskStatus] = None
        self.process: Optional[asyncio.subprocess.Process] = None
        self.history: list[TaskStatus] = []
        self._cancel_requested = False

    @property
    def status(self) -> dict:
        if self.current_task:
            return asdict(self.current_task)
        return {"state": "idle"}

    async def run_task(self, prompt: str, workdir: str = None) -> AsyncGenerator[str, None]:
        """
        Run a task and yield SSE events as Claude produces output.
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        self.current_task = TaskStatus(
            id=task_id,
            state="running",
            prompt=prompt,
            started_at=datetime.now().isoformat(),
        )
        self._cancel_requested = False

        yield self._sse_event("start", {"task_id": task_id, "prompt": prompt})

        cmd = [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "--output-format", "stream-json",
        ]

        env = {
            **os.environ,
            "TERM": "dumb",
            "NO_COLOR": "1",
            "DEBIAN_FRONTEND": "noninteractive",
            "GIT_TERMINAL_PROMPT": "0",
            "PIP_NO_INPUT": "1",
        }

        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=workdir or WORKSPACE,
                env=env,
            )

            # Send prompt
            self.process.stdin.write(prompt.encode() + b"\n")
            await self.process.stdin.drain()
            self.process.stdin.close()

            # Stream output
            buffer = ""
            while True:
                if self._cancel_requested:
                    self.process.terminate()
                    yield self._sse_event("cancelled", {"task_id": task_id})
                    self.current_task.state = "cancelled"
                    break

                try:
                    chunk = await asyncio.wait_for(
                        self.process.stdout.read(1024),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
                    continue

                if not chunk:
                    break

                text = chunk.decode("utf-8", errors="replace")
                buffer += text

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        self.current_task.output_lines.append(line)
                        yield self._sse_event("output", {"line": line})

            # Wait for process to finish
            await self.process.wait()
            exit_code = self.process.returncode

            self.current_task.exit_code = exit_code
            self.current_task.finished_at = datetime.now().isoformat()

            if self.current_task.state != "cancelled":
                self.current_task.state = "completed" if exit_code == 0 else "failed"

            yield self._sse_event("done", {
                "task_id": task_id,
                "exit_code": exit_code,
                "state": self.current_task.state,
            })

        except Exception as e:
            self.current_task.state = "failed"
            self.current_task.error = str(e)
            self.current_task.finished_at = datetime.now().isoformat()
            yield self._sse_event("error", {"error": str(e)})

        finally:
            # Save to history
            self.history.append(self.current_task)
            if len(self.history) > MAX_HISTORY:
                self.history = self.history[-MAX_HISTORY:]
            self.current_task = None
            self.process = None

    def stop(self):
        """Request cancellation of current task."""
        if self.process and self.current_task:
            self._cancel_requested = True
            return True
        return False

    def _sse_event(self, event: str, data: dict) -> str:
        """Format an SSE event."""
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# Global agent instance
agent = ClaudeAgent()


# === HTTP Handlers ===

async def handle_task(request: web.Request) -> web.StreamResponse:
    """POST /task - Submit task and stream results via SSE."""
    if agent.current_task:
        return web.json_response(
            {"error": "Agent is busy", "current_task": agent.current_task.id},
            status=409
        )

    try:
        body = await request.json()
        prompt = body.get("prompt") or body.get("task")
        workdir = body.get("workdir")

        if not prompt:
            return web.json_response({"error": "Missing 'prompt' field"}, status=400)

    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    # Set up SSE response
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
    await response.prepare(request)

    # Stream task output
    try:
        async for event in agent.run_task(prompt, workdir):
            await response.write(event.encode())
            await response.drain()
    except ConnectionResetError:
        # Client disconnected
        agent.stop()

    return response


async def handle_status(request: web.Request) -> web.Response:
    """GET /status - Current agent status."""
    return web.json_response(agent.status)


async def handle_health(request: web.Request) -> web.Response:
    """GET /health - Health check."""
    return web.json_response({"status": "ok", "agent": agent.status.get("state", "idle")})


async def handle_stop(request: web.Request) -> web.Response:
    """POST /stop - Stop current task."""
    if agent.stop():
        return web.json_response({"status": "stopping"})
    return web.json_response({"status": "no task running"}, status=404)


async def handle_history(request: web.Request) -> web.Response:
    """GET /history - Recent task history."""
    limit = int(request.query.get("limit", "10"))
    history = [asdict(t) for t in agent.history[-limit:]]
    return web.json_response({"history": history})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/task", handle_task)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/stop", handle_stop)
    app.router.add_get("/history", handle_history)
    return app


def main():
    print(f"Claude-in-a-Box server starting on {HOST}:{PORT}")
    print(f"Workspace: {WORKSPACE}")
    print()
    print("Endpoints:")
    print(f"  POST http://localhost:{PORT}/task     - Submit task (SSE stream)")
    print(f"  GET  http://localhost:{PORT}/status   - Current status")
    print(f"  POST http://localhost:{PORT}/stop     - Stop current task")
    print(f"  GET  http://localhost:{PORT}/history  - Task history")
    print()

    app = create_app()
    web.run_app(app, host=HOST, port=PORT, print=None)


if __name__ == "__main__":
    main()
