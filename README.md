# Headless Claude Code Protocol

A file-based protocol for controlling Claude Code without terminal access. Designed for headless environments, CI pipelines, and remote agent control.

## The Problem

Claude Code (and most interactive tools) expect stdin for user input. When running in containers, CI, or remotely, there's no terminal to type into. Blocking on stdin causes deadlocks.

## The Solution

Replace stdin/stdout with append-only files:
- **You write** → `commands.jsonl`
- **Claude responds** → `output.jsonl`
- Agent polls files instead of blocking on stdin

## Quick Start

**Terminal 1 - Start the wrapper:**
```bash
./claude_wrapper.py
```

**Terminal 2 - Send tasks and watch output:**
```bash
./send_task.py "Create a Python function that calculates fibonacci numbers"
./watch_output.py
```

## Scripts

| Script | Purpose |
|--------|---------|
| `claude_wrapper.py` | Main wrapper - runs Claude Code headlessly |
| `send_task.py` | Send tasks to the wrapper |
| `watch_output.py` | Watch Claude's responses |
| `protocol.py` | Core protocol library |
| `respond.py` | Interactive responder (for demo agent) |

## Usage

### Start the Wrapper

```bash
# Foreground (see logs)
./claude_wrapper.py

# Background
nohup ./claude_wrapper.py > wrapper.log 2>&1 &

# One-shot mode (single prompt, then exit)
./claude_wrapper.py --once "What files are in this directory?"
```

### Send Tasks

```bash
# Simple task
./send_task.py "Fix the bug in main.py"

# With working directory
./send_task.py --workdir /path/to/project "Run the tests"

# From stdin (useful for long prompts)
cat prompt.txt | ./send_task.py --stdin

# Stop the wrapper
./send_task.py --abort
```

### Watch Output

```bash
# Live watch (like tail -f)
./watch_output.py

# Last N responses
./watch_output.py --last 3

# Specific response by ID
./watch_output.py --id cmd_abc123

# Just show status
./watch_output.py --status
```

### Raw File Access

```bash
# Send task directly
echo '{"id":"t1","type":"task","task":"List files"}' >> commands.jsonl

# Read latest response
tail -1 output.jsonl | jq -r '.response'

# Watch status
watch -n1 cat status.json
```

## Protocol Files

| File | Direction | Purpose |
|------|-----------|---------|
| `commands.jsonl` | You → Agent | Tasks and commands |
| `output.jsonl` | Agent → You | Claude's responses |
| `status.json` | Agent → You | Current state (idle/working) |
| `log.jsonl` | Agent → You | Activity log |

### Command Format

```json
{"id": "cmd_001", "type": "task", "task": "Your prompt here", "workdir": "/optional/path"}
{"id": "cmd_002", "type": "abort"}
```

### Output Format

```json
{
  "id": "cmd_001",
  "timestamp": "2024-01-15T10:30:00",
  "prompt": "Your prompt",
  "response": "Claude's response...",
  "exit_code": 0
}
```

### Status Format

```json
{
  "state": "working",
  "task": "Fix the bug...",
  "detail": null,
  "updated_at": "2024-01-15T10:30:00"
}
```

## Headless / CI Usage

```bash
# In CI script
cd /workspace
nohup ./claude_wrapper.py &
sleep 2

# Send task
./send_task.py "Run tests and fix any failures"

# Wait for completion (poll status)
while [ "$(jq -r .state status.json)" = "working" ]; do
  sleep 5
done

# Get result
RESPONSE=$(tail -1 output.jsonl | jq -r '.response')
EXIT_CODE=$(tail -1 output.jsonl | jq -r '.exit_code')

echo "$RESPONSE"
exit $EXIT_CODE
```

## How It Works

1. **Non-interactive by default**: The wrapper sets environment variables that disable prompts:
   - `DEBIAN_FRONTEND=noninteractive`
   - `GIT_TERMINAL_PROMPT=0`
   - `PIP_NO_INPUT=1`

2. **Auto-approve permissions**: Uses `--dangerously-skip-permissions` so Claude can run commands and edit files without asking.

3. **Poll, don't block**: Wrapper loops checking `commands.jsonl` every 2 seconds instead of blocking on stdin.

4. **Atomic writes**: Status updates use write-to-temp + rename for crash safety.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_PROTOCOL_DIR` | `.` | Directory for protocol files |
| `AGENT_POLL_INTERVAL` | `1.0` | Seconds between polls |
| `AGENT_POLL_TIMEOUT` | `3600` | Max seconds to wait for response |

## Demo Agents

Two demo agents are included that use the lower-level protocol (for building custom agents):

- `demo_agent.py` - Simple demo showing request/response flow
- `coding_agent.py` - More realistic agent with git/file operations

These use `protocol.py` directly and support interactive confirmation via `requests.jsonl`/`responses.jsonl`.

## Limitations

- **No conversation memory**: Each task is independent. Claude doesn't remember previous tasks.
- **No streaming**: You get the full response when done, not incrementally.
- **Trust required**: `--dangerously-skip-permissions` means Claude can do anything.

## Future Ideas

- [ ] Session persistence (conversation memory across tasks)
- [ ] Webhook notifications when tasks complete
- [ ] Rate limiting / queue management
- [ ] Response streaming via chunked files
- [ ] Docker container for full sandboxing
