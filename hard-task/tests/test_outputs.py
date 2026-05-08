import json
import subprocess
import urllib.request
from pathlib import Path


SCRIPT_PATH = Path("/app/make_numbers.py")
RESULT_PATH = Path("/app/result.json")

EXPECTED_OUTPUT = ["alpha=7", "beta=11"]
EXPECTED_RESULT = {
    "alpha": 7,
    "beta": 11,
    "sum": 18,
    "source": "simulated-user-multi-turn",
}
EXIT_MESSAGE = "You may exit now."


def test_python_file_exists_and_runs() -> None:
    assert SCRIPT_PATH.exists(), "make_numbers.py artifact does not exist"

    completed = subprocess.run(
        ["python3", str(SCRIPT_PATH)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.splitlines() == EXPECTED_OUTPUT


def test_result_file_contents() -> None:
    assert RESULT_PATH.exists(), "result.json artifact does not exist"

    data = json.loads(RESULT_PATH.read_text())

    assert data == EXPECTED_RESULT


def test_simulated_user_reached_exit() -> None:
    with urllib.request.urlopen(
        "http://conversation-server:8000/transcript",
        timeout=5,
    ) as response:
        transcript = json.loads(response.read())

    agent_replies = [
        event for event in transcript["events"] if event["role"] == "agent"
    ]
    final_exit_messages = [
        event
        for event in transcript["events"]
        if event["role"] == "simulated_user" and event["message"] == EXIT_MESSAGE
    ]

    assert agent_replies
    assert final_exit_messages
