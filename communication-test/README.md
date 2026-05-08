# Communication Test

This folder contains a local sanity check for the simulated-user HTTP protocol.
It starts the real `hard-task/environment/conversation-server/server.py` code on
a local port, launches the separate simulated-user worker, and runs a fixed
agent worker against the shared conversation server.

Run:

```bash
uv run communication-test/run_demo.py
```

The demo adds short delays between turns so the transcript looks like a slow
agent/user exchange without needing Harbor or an LLM. The simulated-user worker
and the fixed agent worker use explicit string lists for this local test.

The script prints a local viewer URL such as `http://127.0.0.1:45001/`.
The same Python simulated-user server serves both the transcript API and the
built React viewer.
