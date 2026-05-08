import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from urllib.parse import urlencode


@dataclass(frozen=True)
class DemoSimulatedUserConfig:
    server_url: str
    messages: tuple[str, ...]
    ready_file: Path
    reply_delay_seconds: float
    request_timeout_seconds: float = 35.0

    @classmethod
    def from_env(cls) -> "DemoSimulatedUserConfig":
        raw_messages = os.environ.get("DEMO_SIM_USER_MESSAGES_JSON")
        if not raw_messages:
            raise ValueError("DEMO_SIM_USER_MESSAGES_JSON must be set")

        messages = json.loads(raw_messages)
        if not isinstance(messages, list) or not messages:
            raise ValueError("demo simulated-user messages must be a non-empty list")
        if not all(isinstance(message, str) and message for message in messages):
            raise ValueError("demo simulated-user messages must be non-empty strings")

        return cls(
            server_url=os.environ["CONVERSATION_SERVER_URL"].rstrip("/"),
            messages=tuple(messages),
            ready_file=Path(
                os.environ.get(
                    "DEMO_SIM_USER_READY_FILE",
                    "/tmp/agent-eval-demo-sim-user-ready",
                )
            ),
            reply_delay_seconds=float(
                os.environ.get("DEMO_SIM_USER_REPLY_DELAY_SECONDS", "0")
            ),
        )


@dataclass(frozen=True)
class ConversationClient:
    config: DemoSimulatedUserConfig

    def get_json(self, path: str) -> dict:
        with urllib.request.urlopen(
            f"{self.config.server_url}{path}",
            timeout=self.config.request_timeout_seconds,
        ) as response:
            return json.loads(response.read())

    def post_json(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.config.server_url}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(
            request,
            timeout=self.config.request_timeout_seconds,
        ) as response:
            return json.loads(response.read())

    def send_message(self, message: str) -> None:
        self.post_json("/simulated-user/message", {"message": message})

    def wait_for_agent_reply(self, after_id: int) -> int:
        query = urlencode({"after_id": after_id})
        while True:
            response = self.get_json(f"/agent-reply?{query}")
            if response.get("available"):
                return int(response["event"]["id"])


def mark_ready(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ready\n")


def run_demo_simulated_user(config: DemoSimulatedUserConfig) -> None:
    client = ConversationClient(config)
    client.get_json("/healthz")
    mark_ready(config.ready_file)

    last_agent_event_id = 0
    for index, message in enumerate(config.messages):
        if index > 0:
            last_agent_event_id = client.wait_for_agent_reply(last_agent_event_id)
            if config.reply_delay_seconds > 0:
                time.sleep(config.reply_delay_seconds)

        client.send_message(message)


def main() -> None:
    run_demo_simulated_user(DemoSimulatedUserConfig.from_env())
    Event().wait()


if __name__ == "__main__":
    main()
