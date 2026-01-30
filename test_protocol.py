#!/usr/bin/env python3
"""
Test the protocol without running full agents.
Shows the basic flow works.
"""

import os
import tempfile
import threading
import time

# Use temp dir for test
TEST_DIR = tempfile.mkdtemp(prefix="protocol_test_")
os.environ["AGENT_PROTOCOL_DIR"] = TEST_DIR
os.environ["AGENT_POLL_INTERVAL"] = "0.1"  # Fast polling for test

from protocol import AgentProtocol, ControllerProtocol

print(f"Test directory: {TEST_DIR}")


def test_basic_flow():
    """Test basic request/response flow."""
    print("\n=== Test: Basic Flow ===")

    agent = AgentProtocol("test_agent")
    ctrl = ControllerProtocol()

    # Agent sends request in background
    result = {"answer": None}

    def agent_ask():
        result["answer"] = agent.confirm("Deploy to production?", default=False)

    t = threading.Thread(target=agent_ask)
    t.start()

    # Wait for request to appear
    time.sleep(0.2)

    # Controller responds
    pending = ctrl.get_pending_requests()
    assert len(pending) == 1, f"Expected 1 pending, got {len(pending)}"
    print(f"Pending request: {pending[0]}")

    ctrl.respond(pending[0]["id"], "yes")
    print("Sent response: yes")

    # Wait for agent to receive
    t.join(timeout=2)
    assert result["answer"] == True, f"Expected True, got {result['answer']}"
    print(f"Agent received: {result['answer']}")
    print("PASS")


def test_commands():
    """Test command sending."""
    print("\n=== Test: Commands ===")

    agent = AgentProtocol("test_agent2")
    ctrl = ControllerProtocol()

    # Send a task
    ctrl.send_task("Fix the bug in auth.py")
    print("Sent task")

    # Agent receives
    cmd = agent.check_commands()
    assert cmd is not None, "Expected command"
    assert cmd["type"] == "task"
    assert cmd["task"] == "Fix the bug in auth.py"
    print(f"Agent received: {cmd}")
    print("PASS")


def test_status():
    """Test status updates."""
    print("\n=== Test: Status ===")

    agent = AgentProtocol("test_agent3")
    ctrl = ControllerProtocol()

    agent.set_status("working", task="Writing tests", detail="test_foo.py")

    status = ctrl.get_status()
    assert status["state"] == "working"
    assert status["task"] == "Writing tests"
    print(f"Status: {status}")
    print("PASS")


def test_logging():
    """Test activity logging."""
    print("\n=== Test: Logging ===")

    agent = AgentProtocol("test_agent4")
    ctrl = ControllerProtocol()

    agent.log("info", "Starting task")
    agent.log("debug", "Reading file", file="foo.py")
    agent.log("error", "File not found")

    logs = ctrl.get_log()
    assert len(logs) >= 3
    print(f"Logs: {len(logs)} entries")
    for log in logs[-3:]:
        print(f"  [{log['level']}] {log['message']}")
    print("PASS")


if __name__ == "__main__":
    test_basic_flow()
    test_commands()
    test_status()
    test_logging()
    print("\n=== All tests passed! ===")
