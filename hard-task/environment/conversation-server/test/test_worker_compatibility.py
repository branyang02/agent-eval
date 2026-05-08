"""
uv run pytest hard-task/environment/conversation-server/test/test_worker_compatibility.py -v
"""

import copy
import importlib.util
import json
import sys
from pathlib import Path
from threading import Thread
import urllib.request

import pytest


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def conversation_server(tmp_path):
    server_path = Path(__file__).resolve().parents[1] / "server.py"
    server_module = load_module("conversation_server_compat", server_path)

    viewer_dist = tmp_path / "viewer" / "dist"
    viewer_dist.mkdir(parents=True)
    (viewer_dist / "index.html").write_text('<div id="root"></div>')

    server = server_module.ConversationServer(server_module.Config(port=0))
    server.viewer_dist = viewer_dist
    server.long_poll_seconds = 0.1

    thread = Thread(target=server.serve_forever)
    thread.start()

    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.loads(response.read())


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read())


def test_worker_loop_is_compatible_with_live_server(conversation_server, monkeypatch):
    worker_path = (
        Path(__file__).resolve().parents[2] / "simulated-user" / "worker.py"
    )
    worker = load_module("simulated_user_worker_compat", worker_path)

    config = worker.Config(server_url=conversation_server, model="test-model")
    simulated_user_messages = [
        "Please create make_numbers.py.",
        "Please write result.json.",
        "You may exit now.",
    ]
    history_seen_by_llm = []
    ready_writes = []
    worker_errors = []

    def fake_ask_openrouter(config_arg, instruction, history):
        assert config_arg == config
        assert instruction == "integration instruction"
        history_seen_by_llm.append(copy.deepcopy(history))
        return simulated_user_messages.pop(0)

    class FakePath:
        def __init__(self, value):
            self.value = value

        def write_text(self, text):
            ready_writes.append((self.value, text))

    def run_worker():
        try:
            worker.main(config)
        except BaseException as exc:
            worker_errors.append(exc)

    monkeypatch.setattr(
        worker,
        "get_simulated_user_instruction",
        lambda: "integration instruction",
    )
    monkeypatch.setattr(worker, "ask_openrouter", fake_ask_openrouter)
    monkeypatch.setattr(worker, "Path", FakePath)

    worker_thread = Thread(target=run_worker, daemon=True)
    worker_thread.start()

    first_message = get_json(f"{conversation_server}/message")
    assert first_message["available"] is True
    assert first_message["message"] == "Please create make_numbers.py."
    assert first_message["event"]["role"] == "simulated_user"

    first_reply = post_json(
        f"{conversation_server}/reply",
        {"message": "Created make_numbers.py."},
    )
    assert first_reply["event"]["role"] == "agent"

    second_message = get_json(f"{conversation_server}/message")
    assert second_message["available"] is True
    assert second_message["message"] == "Please write result.json."

    post_json(
        f"{conversation_server}/reply",
        {"message": "Wrote result.json."},
    )

    exit_message = get_json(f"{conversation_server}/message")
    assert exit_message["available"] is True
    assert exit_message["message"] == "You may exit now."

    worker_thread.join(timeout=2)
    assert not worker_thread.is_alive()
    assert not worker_errors

    transcript = get_json(f"{conversation_server}/transcript")
    assert [
        (event["role"], event["message"])
        for event in transcript["events"]
    ] == [
        ("simulated_user", "Please create make_numbers.py."),
        ("agent", "Created make_numbers.py."),
        ("simulated_user", "Please write result.json."),
        ("agent", "Wrote result.json."),
        ("simulated_user", "You may exit now."),
    ]
    assert ready_writes == [("/tmp/sim-user-ready", "ready\n")]
    assert history_seen_by_llm == [
        [],
        [
            {"role": "simulated_user", "message": "Please create make_numbers.py."},
            {"role": "agent", "message": "Created make_numbers.py."},
        ],
        [
            {"role": "simulated_user", "message": "Please create make_numbers.py."},
            {"role": "agent", "message": "Created make_numbers.py."},
            {"role": "simulated_user", "message": "Please write result.json."},
            {"role": "agent", "message": "Wrote result.json."},
        ],
    ]
