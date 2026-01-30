# Claude-in-a-Box

Run Claude Code in a sandboxed container, controlled via HTTP with SSE streaming. Designed for autonomous backlog processing, bug triage, and CI pipelines.

## The Problem

Claude Code expects a terminal. You want to:
- Run it in a container (sandboxed, reproducible)
- Send it tasks from your backlog (Linear, GitHub Issues)
- Watch progress in real-time
- Let it work autonomously while you sleep

## The Solution

```
┌─────────────────────────────────────────────────────────┐
│  Docker Container                                       │
│  ┌───────────────┐    ┌──────────────┐                 │
│  │ Claude Code   │◄──►│ Task Server  │◄── HTTP :8080   │
│  │ (sandboxed)   │    │ (SSE stream) │                 │
│  └───────────────┘    └──────────────┘                 │
│         │                                               │
│         ▼                                               │
│    /workspace (your code, mounted read-write)          │
└─────────────────────────────────────────────────────────┘
         ▲
         │
   ┌─────┴─────┐
   │  Linear   │  ◄── Worker pulls issues, posts results
   └───────────┘
```

## Quick Start

### 1. Run Locally (no Docker)

```bash
# Install dependencies
pip install aiohttp aiofiles httpx

# Start server
export ANTHROPIC_API_KEY="sk-..."
./server.py

# In another terminal, send a task
./client.py "List all Python files and summarize what they do"
```

### 2. Run with Docker

```bash
# Build and run
export ANTHROPIC_API_KEY="sk-..."
export WORKSPACE_PATH="/path/to/your/codebase"
docker compose up

# Send tasks
./client.py "Fix the failing tests"
```

### 3. With Linear Integration

```bash
# Set up
export LINEAR_API_KEY="lin_api_..."
export ANTHROPIC_API_KEY="sk-..."
export WORKSPACE_PATH="/path/to/your/codebase"

# Start with Linear worker
docker compose --profile with-linear up

# Or run worker manually
./linear_worker.py --daemon --label claude
```

## API

### POST /task
Submit a task and receive SSE stream of progress.

```bash
curl -N -X POST http://localhost:8080/task \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Fix the bug in auth.py"}'
```

**SSE Events:**
```
event: start
data: {"task_id": "task_abc123", "prompt": "..."}

event: output
data: {"line": "Looking at auth.py..."}

event: done
data: {"task_id": "task_abc123", "exit_code": 0, "state": "completed"}
```

### GET /status
Current agent status.

```bash
curl http://localhost:8080/status
# {"state": "running", "task_id": "...", "prompt": "..."}
```

### POST /stop
Stop the current task.

```bash
curl -X POST http://localhost:8080/stop
```

### GET /history
Recent task history.

```bash
curl http://localhost:8080/history?limit=10
```

## CLI Client

```bash
# Send a task (streams output to terminal)
./client.py "Refactor the database module"

# Check status
./client.py status

# Stop current task
./client.py stop

# View history
./client.py history

# Connect to remote server
./client.py --server http://my-server:8080 "Run tests"
```

## Linear Integration

The `linear_worker.py` pulls issues from your Linear backlog and sends them to Claude.

```bash
# Show pending issues
./linear_worker.py --dry-run

# Process one issue
./linear_worker.py

# Process issues with specific label
./linear_worker.py --label "claude-ready"

# Run as daemon (continuous processing)
./linear_worker.py --daemon --interval 120
```

**Workflow:**
1. Worker finds issues in Backlog/Todo state
2. Moves issue to "In Progress"
3. Sends issue to Claude with context
4. Posts Claude's response as comment
5. Moves to "In Review" (success) or back to "Todo" (failed)

**Recommended Labels:**
- `claude` or `claude-ready` - Issues Claude should pick up
- Use `--label` flag to filter

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `LINEAR_API_KEY` | For Linear | Linear API key |
| `WORKSPACE_DIR` | No | Workspace path (default: /workspace) |
| `AGENT_PORT` | No | Server port (default: 8080) |
| `AGENT_HOST` | No | Server host (default: 0.0.0.0) |
| `LINEAR_TEAM_ID` | No | Filter Linear issues by team |

### Docker Compose

```bash
# Just the server
docker compose up claude-box

# Server + Linear worker
docker compose --profile with-linear up

# Custom workspace
WORKSPACE_PATH=/my/code docker compose up
```

## Files

| File | Purpose |
|------|---------|
| `server.py` | HTTP server with SSE streaming |
| `client.py` | CLI client |
| `linear_worker.py` | Linear backlog integration |
| `Dockerfile` | Container image |
| `docker-compose.yml` | Easy deployment |
| `protocol.py` | Low-level file-based protocol (for custom agents) |

## Safety Notes

⚠️ **This runs with `--dangerously-skip-permissions`** - Claude can execute any command and modify any file in the workspace.

Mitigations:
- Run in Docker (isolated from host)
- Mount workspace read-only if you just want analysis: `-v /code:/workspace:ro`
- Set resource limits in docker-compose
- Review Claude's output before merging changes

## Limitations

- **No conversation memory** - Each task is independent
- **Single task at a time** - Queue your own tasks
- **No auth** - Add a reverse proxy for production

## Future Ideas

- [ ] Session persistence (memory across tasks)
- [ ] Task queue with priorities
- [ ] GitHub Issues integration
- [ ] Web dashboard
- [ ] Webhooks for task completion
- [ ] Read-only mode for analysis tasks
