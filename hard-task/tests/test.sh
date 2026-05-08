#!/bin/bash

# Use this file to install test dependencies and run the verifier.
# It will be copied to /tests/test.sh and run from the working directory.

apt-get update
apt-get install -y ca-certificates python3

mkdir -p /logs/verifier

python3 /tests/static_checks.py 2>&1 | tee /logs/verifier/static_checks_stdout.txt
static_checks_status=${PIPESTATUS[0]}

python3 /tests/llm_judge.py 2>&1 | tee /logs/verifier/llm_judge_stdout.txt
llm_judge_status=${PIPESTATUS[0]}

if [ "$llm_judge_status" -ne 0 ]; then
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

score=$(python3 - <<'PY'
import json

with open("/logs/verifier/llm_judge.json", "r", encoding="utf-8") as handle:
    judgment = json.load(handle)

score = judgment.get("score", 0.0)
try:
    score = float(score)
except (TypeError, ValueError):
    score = 0.0

score = max(0.0, min(1.0, score))
print(score)
PY
)

if [ -n "$score" ]; then
  if [ "$static_checks_status" -ne 0 ]; then
    score=$(SCORE="$score" python3 - <<'PY'
import os

score = float(os.environ["SCORE"])
print(min(score, 0.5))
PY
)
  fi
  echo "$score" > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
