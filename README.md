# Hard Task

## Installation

```bash
uv tool install harbor
uv sync
export OPENROUTER_API_KEY=...
```

## Evaluation

```bash
harbor run -p hard-task -a opencode -m openrouter/anthropic/claude-opus-4.6
```

When eval is running, open browser and see a live conversation dashboard between the simulated agent and AI agent at `http://127.0.0.1:18080/` (by default).


Oracle evaluation:

```bash
harbor run -p hard-task -a oracle
```

To run full evaluation:
```bash
./run_all.sh
```

## Write Up
`/submission/submission.pdf`.
