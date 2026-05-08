"""
uv run pytest hard-task/environment/simulated-user/test/test_simulated_user.py -v
"""

import copy
import importlib.util
import os
import sys
from pathlib import Path

import pytest


def load_worker_module():
    worker_path = Path(__file__).resolve().parents[1] / "worker.py"
    spec = importlib.util.spec_from_file_location("simulated_user_worker", worker_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_loop_tracks_history_and_agent_event_ids(monkeypatch):
    worker = load_worker_module()

    config = worker.Config(
        server_url="http://conversation-server:8000", model="test-model"
    )
    llm_messages = [
        "Please create the file.",
        "Please verify the result.",
        "You may exit now.",
    ]
    agent_replies = [
        {"id": 10, "message": "Created the file."},
        {"id": 25, "message": "Verified the result."},
    ]
    history_seen_by_llm = []
    sent_messages = []
    waited_after_ids = []
    ready_writes = []

    def fake_read_json(url):
        assert url == "http://conversation-server:8000/healthz"
        return {"ok": True}

    def fake_ask_openrouter(config_arg, instruction, history):
        assert config_arg == config
        assert instruction == "simulated-user instruction"
        history_seen_by_llm.append(copy.deepcopy(history))
        return llm_messages.pop(0)

    def fake_send_message(config_arg, message):
        assert config_arg == config
        sent_messages.append(message)

    def fake_wait_for_agent_reply(config_arg, after_id):
        assert config_arg == config
        waited_after_ids.append(after_id)
        return agent_replies.pop(0)

    class FakePath:
        def __init__(self, value):
            self.value = value

        def write_text(self, text):
            ready_writes.append((self.value, text))

    monkeypatch.setattr(
        worker,
        "get_simulated_user_instruction",
        lambda: "simulated-user instruction",
    )
    monkeypatch.setattr(worker, "read_json", fake_read_json)
    monkeypatch.setattr(worker, "ask_openrouter", fake_ask_openrouter)
    monkeypatch.setattr(worker, "send_message", fake_send_message)
    monkeypatch.setattr(worker, "wait_for_agent_reply", fake_wait_for_agent_reply)
    monkeypatch.setattr(worker, "Path", FakePath)

    worker.main(config)

    assert sent_messages == [
        "Please create the file.",
        "Please verify the result.",
        "You may exit now.",
    ]
    assert waited_after_ids == [0, 10]
    assert ready_writes == [("/tmp/sim-user-ready", "ready\n")]
    assert history_seen_by_llm == [
        [],
        [
            {"role": "simulated_user", "message": "Please create the file."},
            {"role": "agent", "message": "Created the file."},
        ],
        [
            {"role": "simulated_user", "message": "Please create the file."},
            {"role": "agent", "message": "Created the file."},
            {"role": "simulated_user", "message": "Please verify the result."},
            {"role": "agent", "message": "Verified the result."},
        ],
    ]


@pytest.mark.skipif(
    "OPENROUTER_API_KEY" not in os.environ,
    reason="OPENROUTER_API_KEY is not set",
)
def test_ask_openrouter_returns_string_and_uses_history():
    worker = load_worker_module()
    marker = "HISTORY_MARKER_7C9F"
    instruction = (
        "This is an integration test for a simulated user. "
        f"If the latest agent message contains {marker}, reply with exactly: "
        f"saw {marker}. Do not say the exit message."
    )
    history = [
        {"role": "simulated_user", "message": "Please inspect the marker."},
        {
            "role": "agent",
            "message": f"The latest agent message contains {marker}.",
        },
    ]

    message = worker.ask_openrouter(worker.Config(), instruction, history)

    assert isinstance(message, str)
    assert message.strip()
    assert marker in message
