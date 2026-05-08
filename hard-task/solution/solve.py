import json
import subprocess
import urllib.request
from pathlib import Path


CONVERSATION_SERVER_URL = "http://conversation-server:8000"
EXIT_MESSAGE = "You may exit now."
SCRIPT_PATH = Path("/app/make_numbers.py")
RESULT_PATH = Path("/app/result.json")


def get_message() -> str:
    while True:
        with urllib.request.urlopen(
            f"{CONVERSATION_SERVER_URL}/message", timeout=35
        ) as response:
            payload = json.loads(response.read())
        if payload.get("available"):
            return payload["message"]


def post_reply(message: str) -> None:
    request = urllib.request.Request(
        f"{CONVERSATION_SERVER_URL}/reply",
        data=json.dumps({"message": message}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        json.loads(response.read())


def run_script() -> list[str]:
    completed = subprocess.run(
        ["python3", str(SCRIPT_PATH)],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.splitlines()


def handle_message(message: str) -> str:
    if "create /app/make_numbers.py" in message:
        SCRIPT_PATH.write_text('print("alpha=7")\nprint("beta=11")\n')
        assert run_script() == ["alpha=7", "beta=11"]
        return "Created /app/make_numbers.py and verified its output."

    if "Run /app/make_numbers.py again" in message:
        assert run_script() == ["alpha=7", "beta=11"]
        return "Re-ran /app/make_numbers.py and confirmed its exact output."

    if "create /app/result.json" in message:
        RESULT_PATH.write_text(
            json.dumps(
                {
                    "alpha": 7,
                    "beta": 11,
                    "sum": 18,
                    "source": "simulated-user-multi-turn",
                },
                indent=2,
            )
            + "\n"
        )
        return "Created /app/result.json with the requested values."

    if "confirm that the sum field is 18" in message:
        data = json.loads(RESULT_PATH.read_text())
        assert data["sum"] == 18
        return "Confirmed that /app/result.json has sum equal to 18."

    if "Confirm that both /app/make_numbers.py and /app/result.json exist" in message:
        assert SCRIPT_PATH.exists()
        assert RESULT_PATH.exists()
        return "Confirmed both requested files exist."

    return "Acknowledged and completed the requested step."


while True:
    current_message = get_message()
    if current_message == EXIT_MESSAGE:
        break

    post_reply(handle_message(current_message))
