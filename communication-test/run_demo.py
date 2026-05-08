from dataclasses import dataclass
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import tyro


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "hard-task/environment/conversation-server/server.py"
SCRIPTED_SIMULATED_USER_PATH = REPO_ROOT / "communication-test/scripted_simulated_user.py"
VIEWER_DIR = REPO_ROOT / "hard-task/environment/conversation-server/viewer"
EXIT_MESSAGE = "You may exit now."
USER_TO_AGENT_DELAY_SEC = 0.65
AGENT_TO_USER_DELAY_SEC = 1.00

SIM_USER_MESSAGES = [
    "Turn 1: Please acknowledge that you are ready to help with a file task.",
    "Turn 2: Please create a pretend plan for writing make_numbers.py.",
    "Turn 3: Please say you created make_numbers.py.",
    "Turn 4: Please say you ran make_numbers.py.",
    "Turn 5: Please say the output was alpha=7 then beta=11.",
    "Turn 6: Please say you are ready to create result.json.",
    "Turn 7: Please say you wrote result.json.",
    "Turn 8: Please say you checked that sum equals 18.",
    "Turn 9: Please say both expected files exist.",
    "Turn 10: Please say you are waiting for my exit instruction.",
    EXIT_MESSAGE,
]

AGENT_REPLIES = [
    """Agent reply 1:

I am ready to help with the file task. I will treat each message from the simulated user as the source of truth and avoid jumping ahead to later artifacts before they are requested.

I will also keep the process alive until I receive the exact exit instruction. That part matters because Harbor uses the tested agent's process exit as the signal to stop the interactive phase and begin verifier execution.""",
    """Agent reply 2:

My plan is to create a small Python script at `/app/make_numbers.py`, run it with `python3`, capture stdout, and compare the exact lines against the requested alpha and beta values.

The script I intend to create is deliberately small:

```python
print("alpha=7")
print("beta=11")
```

After that, I will run the file and check that it prints exactly those two lines with no extra output.""",
    """Agent reply 3:

I created `/app/make_numbers.py` with two print statements. The file is intentionally minimal so the observable behavior is easy to verify and there is no hidden dependency on environment state.

The file content is:

```python
print("alpha=7")
print("beta=11")
```

I have not created the JSON artifact yet because the simulated user has not asked me to do that step.""",
    """Agent reply 4:

I ran `/app/make_numbers.py` successfully. The process exited cleanly, but I am not relying only on the return code because a successful process could still produce the wrong output.

The check I used is equivalent to:

```bash
python3 /app/make_numbers.py
```

The next thing I will confirm is that stdout exactly matches the requested two-line contract.""",
    """Agent reply 5:

The output check passed. The first stdout line was `alpha=7`, the second stdout line was `beta=11`, and there were no extra lines before or after those values.

For clarity, the expected stdout is:

```text
alpha=7
beta=11
```

That means the script is ready for the later JSON step when the simulated user asks for it.""",
    """Agent reply 6:

I am ready to create `/app/result.json`. I will keep the values consistent with the script output, compute the sum as 18, and include the source field requested by the simulated user.

The JSON object should be structurally simple so the verifier can compare it directly:

```json
{
  "alpha": 7,
  "beta": 11,
  "sum": 18,
  "source": "simulated-user-multi-turn"
}
```""",
    """Agent reply 7:

I wrote `/app/result.json` as a JSON object with `alpha`, `beta`, `sum`, and `source` fields. I used numeric values for `alpha`, `beta`, and `sum`, not strings, so the verifier can compare the parsed object without type coercion.

The resulting artifact is:

```json
{
  "alpha": 7,
  "beta": 11,
  "sum": 18,
  "source": "simulated-user-multi-turn"
}
```""",
    """Agent reply 8:

I reopened `/app/result.json` and checked the parsed object. The `sum` field is present and has the integer value `18`, which matches `alpha + beta`.

The validation logic is conceptually:

```python
import json
from pathlib import Path

data = json.loads(Path("/app/result.json").read_text())
assert data["sum"] == 18
```

This confirms the JSON artifact still matches the simulated user's requested result.""",
    """Agent reply 9:

Both expected files exist in `/app`. The Python script is available for reruns, and `result.json` is available for the verifier to load and compare against the expected result.

The two artifacts I checked are:

```text
/app/make_numbers.py
/app/result.json
```

At this point the requested files are in place, and I am waiting for the simulated user's final instruction before exiting.""",
    """Agent reply 10:

I have completed the requested work and will now wait for the simulated user's final exit instruction. I am not exiting yet because Harbor treats the tested agent process exit as the signal to end the interactive phase and start verification.

The important control-flow rule is:

```text
keep running until the simulated user sends exactly:
You may exit now.
```

Once that message arrives, I can exit and allow the verifier to check the artifacts.""",
]


@dataclass(frozen=True)
class DemoConfig:
    """Configuration for the local simulated-user communication demo."""

    start_delay: float = 2.0
    """Seconds to wait after printing the viewer URL before the exchange starts."""

    hold_seconds: float = 60.0
    """Seconds to keep the server alive after the exchange completes."""

    skip_viewer_build: bool = False
    """Skip the Bun install/build step."""

    server_port: int = 8000
    """Local port for the conversation server."""


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def viewer_inputs() -> list[Path]:
    inputs = [
        VIEWER_DIR / "package.json",
        VIEWER_DIR / "tsconfig.json",
        VIEWER_DIR / "scripts/build.ts",
    ]
    inputs.extend((VIEWER_DIR / "src").glob("*"))
    lockfile = VIEWER_DIR / "bun.lock"
    if lockfile.exists():
        inputs.append(lockfile)
    return inputs


def viewer_needs_build() -> bool:
    outputs = [
        VIEWER_DIR / "dist/index.html",
        VIEWER_DIR / "dist/assets/app.js",
        VIEWER_DIR / "dist/assets/styles.css",
    ]
    if any(not output.exists() for output in outputs):
        return True

    newest_input = max(path.stat().st_mtime for path in viewer_inputs())
    oldest_output = min(path.stat().st_mtime for path in outputs)
    return newest_input > oldest_output


def ensure_viewer_built() -> None:
    if (
        not (VIEWER_DIR / "node_modules").exists()
        or not (VIEWER_DIR / "bun.lock").exists()
    ):
        subprocess.run(["bun", "install"], cwd=VIEWER_DIR, check=True)

    if viewer_needs_build():
        subprocess.run(["bun", "run", "typecheck"], cwd=VIEWER_DIR, check=True)
        subprocess.run(["bun", "run", "build"], cwd=VIEWER_DIR, check=True)


def wait_for_server(base_url: str, server: subprocess.Popen) -> None:
    deadline = time.time() + 10
    while time.time() < deadline:
        if server.poll() is not None:
            stderr = server.stderr.read() if server.stderr else ""
            raise RuntimeError(
                "conversation server exited before becoming ready"
                f"{': ' + stderr.strip() if stderr.strip() else ''}"
            )
        try:
            get_json(f"{base_url}/healthz")
            return
        except (ConnectionError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(0.1)
    raise RuntimeError("simulated user server did not become ready")


def wait_for_simulated_user(base_url: str, simulated_user: subprocess.Popen) -> None:
    deadline = time.time() + 10
    while time.time() < deadline:
        if simulated_user.poll() is not None:
            stderr = simulated_user.stderr.read() if simulated_user.stderr else ""
            raise RuntimeError(
                "simulated user worker exited before sending a message"
                f"{': ' + stderr.strip() if stderr.strip() else ''}"
            )
        try:
            transcript = get_json(f"{base_url}/transcript")
            if any(
                event["role"] == "simulated_user"
                for event in transcript["events"]
            ):
                return
        except (ConnectionError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise RuntimeError("simulated user worker did not become ready")


def check_viewer(base_url: str) -> None:
    index_html = urllib.request.urlopen(f"{base_url}/", timeout=5).read().decode()
    app_js = urllib.request.urlopen(f"{base_url}/assets/app.js", timeout=5).read()

    if '<div id="root"></div>' not in index_html:
        raise AssertionError("viewer HTML did not include the React root")
    if len(app_js) < 1000:
        raise AssertionError("viewer JavaScript bundle looked unexpectedly small")


def run_agent_worker(base_url: str) -> list[str]:
    log = []

    for turn, expected_message in enumerate(SIM_USER_MESSAGES, start=1):
        payload = get_json(f"{base_url}/message")
        if not payload.get("available"):
            raise AssertionError(f"turn {turn}: no simulated-user message available")

        user_message = payload["message"]
        log.append(f"sim-user -> agent: {user_message}")

        if user_message != expected_message:
            raise AssertionError(
                f"turn {turn}: expected {expected_message!r}, got {user_message!r}"
            )

        if user_message == EXIT_MESSAGE:
            break

        time.sleep(USER_TO_AGENT_DELAY_SEC)

        reply = AGENT_REPLIES[turn - 1]
        post_json(f"{base_url}/reply", {"message": reply})
        log.append(f"agent -> sim-user: {reply}")

        time.sleep(AGENT_TO_USER_DELAY_SEC)

    return log


def main() -> int:
    config = tyro.cli(DemoConfig)

    if not config.skip_viewer_build:
        ensure_viewer_built()

    base_url = f"http://127.0.0.1:{config.server_port}"

    server = subprocess.Popen(
        [sys.executable, str(SERVER_PATH), "--port", str(config.server_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    simulated_user = None

    try:
        wait_for_server(base_url, server)

        simulated_user_env = {
            **os.environ,
            "CONVERSATION_SERVER_URL": base_url,
            "DEMO_SIM_USER_MESSAGES_JSON": json.dumps(SIM_USER_MESSAGES),
            "DEMO_SIM_USER_READY_FILE": "/tmp/agent-eval-demo-sim-user-ready",
            "DEMO_SIM_USER_REPLY_DELAY_SECONDS": str(AGENT_TO_USER_DELAY_SEC),
        }
        simulated_user = subprocess.Popen(
            [sys.executable, str(SCRIPTED_SIMULATED_USER_PATH)],
            env=simulated_user_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        wait_for_simulated_user(base_url, simulated_user)
        print(f"started conversation server at {base_url}")
        print("simulated-user worker connected")
        check_viewer(base_url)
        print(f"open viewer: {base_url}/")

        if config.start_delay > 0:
            print(f"conversation starts in {config.start_delay:.1f}s")
            time.sleep(config.start_delay)

        for line in run_agent_worker(base_url):
            print(line)

        transcript = get_json(f"{base_url}/transcript")
        agent_events = [
            event for event in transcript["events"] if event["role"] == "agent"
        ]
        simulated_user_events = [
            event
            for event in transcript["events"]
            if event["role"] == "simulated_user"
        ]
        final_events = [
            event
            for event in transcript["events"]
            if event["role"] == "simulated_user" and event["message"] == EXIT_MESSAGE
        ]

        assert len(simulated_user_events) == len(SIM_USER_MESSAGES)
        assert len(agent_events) == len(AGENT_REPLIES)
        assert len(final_events) == 1

        print("transcript check passed")
        print(json.dumps(transcript, indent=2))

        if config.hold_seconds > 0:
            print(f"viewer stays available for {config.hold_seconds:.1f}s")
            time.sleep(config.hold_seconds)

        return 0
    finally:
        for process in (simulated_user, server):
            if process is None:
                continue
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
