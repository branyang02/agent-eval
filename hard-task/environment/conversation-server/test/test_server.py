"""
uv run pytest hard-task/environment/conversation-server/test/test_server.py -v
"""

import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
import urllib.request

import pytest


def load_server_module():
    server_path = Path(__file__).resolve().parents[1] / "server.py"
    spec = importlib.util.spec_from_file_location("conversation_server", server_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class RunningServer:
    base_url: str


def read_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=2) as response:
        return response.read()


def get_json(url: str) -> dict:
    return json.loads(read_url(url))


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.loads(response.read())


@pytest.fixture
def conversation_server(tmp_path):
    server_module = load_server_module()

    viewer_dist = tmp_path / "viewer" / "dist"
    (viewer_dist / "assets").mkdir(parents=True)
    (viewer_dist / "index.html").write_text('<div id="root"></div>')
    (viewer_dist / "assets" / "app.js").write_text("console.log('viewer');")

    server = server_module.ConversationServer(server_module.Config(port=0))
    server.viewer_dist = viewer_dist
    server.long_poll_seconds = 0.05

    thread = Thread(target=server.serve_forever)
    thread.start()

    try:
        port = server.server_address[1]
        yield RunningServer(base_url=f"http://127.0.0.1:{port}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_health_and_empty_transcript(conversation_server):
    assert get_json(f"{conversation_server.base_url}/healthz") == {"ok": True}
    assert get_json(f"{conversation_server.base_url}/transcript") == {"events": []}
    assert get_json(
        f"{conversation_server.base_url}/transcript/updates?after_id=0"
    ) == {"events": []}


def test_agent_receives_simulated_user_messages_in_turn_order(conversation_server):
    first = post_json(
        f"{conversation_server.base_url}/simulated-user/message",
        {"message": "first user request"},
    )
    second = post_json(
        f"{conversation_server.base_url}/simulated-user/message",
        {"message": "second user request"},
    )

    assert first["event"]["id"] == 1
    assert first["event"]["role"] == "simulated_user"
    assert second["event"]["id"] == 2

    message = get_json(f"{conversation_server.base_url}/message")
    assert message["available"] is True
    assert message["event"]["id"] == 1
    assert message["message"] == "first user request"

    repeated_message = get_json(f"{conversation_server.base_url}/message")
    assert repeated_message["event"]["id"] == 1

    reply = post_json(
        f"{conversation_server.base_url}/reply",
        {"message": "agent handled first request"},
    )
    assert reply["event"]["id"] == 3
    assert reply["event"]["role"] == "agent"

    next_message = get_json(f"{conversation_server.base_url}/message")
    assert next_message["available"] is True
    assert next_message["event"]["id"] == 2
    assert next_message["message"] == "second user request"

    transcript_updates = get_json(
        f"{conversation_server.base_url}/transcript/updates?after_id=2"
    )
    assert transcript_updates["events"] == [reply["event"]]


def test_simulated_user_receives_agent_replies_after_event_id(conversation_server):
    reply = post_json(
        f"{conversation_server.base_url}/reply",
        {"message": "agent reply"},
    )

    agent_reply = get_json(f"{conversation_server.base_url}/agent-reply?after_id=0")
    assert agent_reply["available"] is True
    assert agent_reply["event"] == reply["event"]

    timed_out = get_json(
        f"{conversation_server.base_url}/agent-reply?after_id={reply['event']['id']}"
    )
    assert timed_out == {"available": False, "event": None}


def test_transcript_updates_wait_for_new_events(conversation_server):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            get_json,
            f"{conversation_server.base_url}/transcript/updates?after_id=0",
        )
        reply = post_json(
            f"{conversation_server.base_url}/reply",
            {"message": "agent reply"},
        )

        assert future.result(timeout=2) == {"events": [reply["event"]]}


def test_empty_messages_are_rejected(conversation_server):
    with pytest.raises(HTTPError) as exc_info:
        post_json(f"{conversation_server.base_url}/reply", {"message": "  "})

    assert exc_info.value.code == 400


def test_static_viewer_files_are_served(conversation_server):
    index_html = read_url(f"{conversation_server.base_url}/").decode()
    nested_html = read_url(f"{conversation_server.base_url}/conversation/123").decode()
    app_js = read_url(f"{conversation_server.base_url}/assets/app.js").decode()

    assert index_html == '<div id="root"></div>'
    assert nested_html == '<div id="root"></div>'
    assert app_js == "console.log('viewer');"
