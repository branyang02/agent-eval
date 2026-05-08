import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
import tyro


@dataclass(frozen=True)
class Config:
    server_url: str = "http://conversation-server:8000"
    model: str = "openai/gpt-5.2"


def read_json(url: str, timeout: int = 35) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read())


def post_json(
    url: str,
    payload: dict,
    headers: dict | None = None,
    timeout: int = 35,
) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def get_simulated_user_instruction() -> str:
    path = Path(__file__).resolve().parent / "simulated_user_instruction.md"
    return path.read_text().strip()


def ask_openrouter(config: Config, instruction: str, history: list[dict]) -> str:
    api_key = os.environ["OPENROUTER_API_KEY"]
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": instruction},
            {
                "role": "system",
                "content": (
                    "You are the simulated user in an agent evaluation. "
                    "Given the conversation history, send exactly one next user "
                    "message. If the task is complete, return exactly this text "
                    "and nothing else: You may exit now."
                ),
            },
            {"role": "user", "content": json.dumps({"history": history})},
        ],
    }
    response = post_json(
        "https://openrouter.ai/api/v1/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    message = response["choices"][0]["message"]["content"]
    if not isinstance(message, str) or not message.strip():
        raise ValueError("OpenRouter response must be a non-empty message")
    return message.strip()


def send_message(config: Config, message: str) -> None:
    post_json(f"{config.server_url}/simulated-user/message", {"message": message})


def wait_for_agent_reply(config: Config, after_id: int) -> dict:
    while True:
        response = read_json(f"{config.server_url}/agent-reply?after_id={after_id}")
        if response.get("available"):
            return response["event"]


def main(config: Config) -> None:
    exit_message = "You may exit now."
    instruction = get_simulated_user_instruction()

    read_json(f"{config.server_url}/healthz")
    Path("/tmp/sim-user-ready").write_text("ready\n")

    history: list[dict] = []
    last_agent_event_id = 0
    while True:
        message = ask_openrouter(config, instruction, history)
        send_message(config, message)
        history.append({"role": "simulated_user", "message": message})

        if message == exit_message:
            return

        agent_event = wait_for_agent_reply(config, last_agent_event_id)
        last_agent_event_id = int(agent_event["id"])
        history.append({"role": "agent", "message": agent_event["message"]})


if __name__ == "__main__":
    main(tyro.cli(Config))
