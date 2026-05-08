import json
import mimetypes
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Condition
from urllib.parse import parse_qs, unquote, urlparse

import tyro


@dataclass(frozen=True)
class Config:
    port: int = 8000


@dataclass
class State:
    events: list[dict] = field(default_factory=list)
    condition: Condition = field(default_factory=Condition)
    next_event_id: int = 1

    def append(self, role: str, message: str) -> dict:
        event = {
            "id": self.next_event_id,
            "role": role,
            "turn": self.next_event_id,
            "message": message,
            "timestamp": round(time.time(), 3),
        }
        self.next_event_id += 1
        self.events.append(event)
        self.condition.notify_all()
        return event

    def role_events(self, role: str) -> list[dict]:
        return [event for event in self.events if event["role"] == role]

    def events_after(self, after_id: int) -> list[dict]:
        return [event for event in self.events if event["id"] > after_id]


class ConversationServer(ThreadingHTTPServer):
    def __init__(self, config: Config) -> None:
        super().__init__(("0.0.0.0", config.port), Handler)
        self.state = State()
        self.viewer_dist = Path(__file__).resolve().parent / "viewer" / "dist"
        self.long_poll_seconds = 30.0


class Handler(BaseHTTPRequestHandler):
    @property
    def state(self) -> State:
        return self.server.state

    @property
    def viewer_dist(self) -> Path:
        return self.server.viewer_dist

    @property
    def long_poll_seconds(self) -> float:
        return self.server.long_poll_seconds

    def log_message(self, format: str, *args) -> None:
        return

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text: str, status: int = 200) -> None:
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/healthz":
            self.send_json({"ok": True})
            return

        if parsed.path == "/transcript":
            with self.state.condition:
                self.send_json({"events": list(self.state.events)})
            return

        if parsed.path == "/transcript/updates":
            self.handle_transcript_updates_request(parsed.query)
            return

        if parsed.path == "/message":
            self.handle_agent_message_request()
            return

        if parsed.path == "/agent-reply":
            self.handle_simulated_user_reply_request(parsed.query)
            return

        self.send_static()

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/reply":
            self.handle_message_post("agent")
            return

        if path == "/simulated-user/message":
            self.handle_message_post("simulated_user")
            return

        self.send_json({"error": "not found"}, status=404)

    def handle_agent_message_request(self) -> None:
        deadline = time.time() + self.long_poll_seconds

        with self.state.condition:
            while True:
                user_events = self.state.role_events("simulated_user")
                agent_events = self.state.role_events("agent")

                if len(user_events) > len(agent_events):
                    event = user_events[len(agent_events)]
                    self.send_json(
                        {
                            "available": True,
                            "message": event["message"],
                            "event": event,
                        }
                    )
                    return

                remaining = deadline - time.time()
                if remaining <= 0:
                    self.send_json({"available": False, "message": None})
                    return

                self.state.condition.wait(timeout=remaining)

    def handle_transcript_updates_request(self, query_string: str) -> None:
        after_id = int(parse_qs(query_string).get("after_id", ["0"])[0])
        deadline = time.time() + self.long_poll_seconds

        with self.state.condition:
            while True:
                events = self.state.events_after(after_id)
                if events:
                    self.send_json({"events": events})
                    return

                remaining = deadline - time.time()
                if remaining <= 0:
                    self.send_json({"events": []})
                    return

                self.state.condition.wait(timeout=remaining)

    def handle_simulated_user_reply_request(self, query_string: str) -> None:
        after_id = int(parse_qs(query_string).get("after_id", ["0"])[0])
        deadline = time.time() + self.long_poll_seconds

        with self.state.condition:
            while True:
                for event in self.state.events:
                    if event["role"] == "agent" and event["id"] > after_id:
                        self.send_json({"available": True, "event": event})
                        return

                remaining = deadline - time.time()
                if remaining <= 0:
                    self.send_json({"available": False, "event": None})
                    return

                self.state.condition.wait(timeout=remaining)

    def handle_message_post(self, role: str) -> None:
        try:
            body = self.read_body()
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
            return

        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            self.send_json({"error": "message must be a non-empty string"}, status=400)
            return

        with self.state.condition:
            event = self.state.append(role, message)

        self.send_json({"ok": True, "event": event})

    def read_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        body = json.loads(raw_body or b"{}")
        if not isinstance(body, dict):
            raise ValueError("request body must be a JSON object")
        return body

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_text("viewer asset not found", status=404)
            return

        body = path.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def viewer_file(self) -> Path:
        request_path = unquote(urlparse(self.path).path)

        if request_path in ("", "/", "/index.html"):
            return self.viewer_dist / "index.html"

        if request_path.startswith("/assets/"):
            viewer_root = self.viewer_dist.resolve()
            requested = (self.viewer_dist / request_path.lstrip("/")).resolve()
            try:
                requested.relative_to(viewer_root)
            except ValueError:
                return self.viewer_dist / "__missing__"
            return requested

        return self.viewer_dist / "index.html"

    def send_static(self) -> None:
        index_path = self.viewer_dist / "index.html"
        if not index_path.exists():
            self.send_text(
                "conversation viewer is not built; run bun install and bun run build "
                "in hard-task/environment/conversation-server/viewer",
                status=404,
            )
            return

        self.send_file(self.viewer_file())


if __name__ == "__main__":
    ConversationServer(tyro.cli(Config)).serve_forever()
