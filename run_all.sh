#!/usr/bin/env bash

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT="${PROJECT:-hard-task}"
AGENT="${AGENT:-opencode}"
RUNS_PER_MODEL="${RUNS_PER_MODEL:-2}"
BASE_PORT="${BASE_PORT:-18080}"
JOBS_DIR="${JOBS_DIR:-$ROOT_DIR/.docker-writes/jobs}"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/.docker-writes/launch-logs}"

MODELS=(
  "opus46|openrouter/anthropic/claude-opus-4.6"
  "gpt54|openrouter/openai/gpt-5.4"
  "gemini31pro|openrouter/google/gemini-3.1-pro-preview"
)

if ! command -v harbor >/dev/null 2>&1; then
  echo "error: harbor is not installed or not on PATH" >&2
  exit 127
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "error: OPENROUTER_API_KEY is not set" >&2
  exit 1
fi

if ! [[ "$RUNS_PER_MODEL" =~ ^[0-9]+$ ]] || (( RUNS_PER_MODEL < 1 )); then
  echo "error: RUNS_PER_MODEL must be a positive integer" >&2
  exit 1
fi

if ! [[ "$BASE_PORT" =~ ^[0-9]+$ ]] || (( BASE_PORT < 1 || BASE_PORT > 65535 )); then
  echo "error: BASE_PORT must be a TCP port between 1 and 65535" >&2
  exit 1
fi

mkdir -p "$JOBS_DIR" "$LOG_DIR"

port_is_busy() {
  local port="$1"

  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn "sport = :$port" | grep -q .
    return
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi

  timeout 1 bash -c "</dev/tcp/127.0.0.1/$port" >/dev/null 2>&1
}

next_port="$BASE_PORT"
pids=()
job_names=()
ports=()
log_files=()

cleanup() {
  local pid

  echo
  echo "Stopping launched Harbor jobs..."
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup INT TERM

launch_run() {
  local label="$1"
  local model="$2"
  local run_number="$3"
  local port
  local job_name
  local log_file
  local pid

  shift 3

  while port_is_busy "$next_port"; do
    next_port=$((next_port + 1))
    if (( next_port > 65535 )); then
      echo "error: ran out of TCP ports while launching runs" >&2
      exit 1
    fi
  done

  port="$next_port"
  next_port=$((next_port + 1))
  job_name="${label}-run-${run_number}-${timestamp}"
  log_file="$LOG_DIR/${job_name}.log"

  (
    cd "$ROOT_DIR" || exit 1
    export CONVERSATION_HOST_PORT="$port"
    exec harbor run \
      -p "$PROJECT" \
      -a "$AGENT" \
      -m "$model" \
      --jobs-dir "$JOBS_DIR" \
      --job-name "$job_name" \
      --yes \
      "$@"
  ) >"$log_file" 2>&1 &

  pid="$!"
  pids+=("$pid")
  job_names+=("$job_name")
  ports+=("$port")
  log_files+=("$log_file")

  printf 'started %-34s pid=%-8s port=%-5s log=%s\n' \
    "$job_name" "$pid" "$port" "$log_file"
}

timestamp="$(date +%Y%m%d-%H%M%S)"

echo "Launching Harbor runs:"
echo "  project:       $PROJECT"
echo "  agent:         $AGENT"
echo "  runs/model:    $RUNS_PER_MODEL"
echo "  jobs dir:      $JOBS_DIR"
echo "  launch logs:   $LOG_DIR"
echo "  first port:    $BASE_PORT"
echo

for model_entry in "${MODELS[@]}"; do
  IFS='|' read -r label model <<< "$model_entry"

  for ((run_number = 1; run_number <= RUNS_PER_MODEL; run_number++)); do
    launch_run "$label" "$model" "$run_number" "$@"
  done
done

echo
echo "Conversation dashboards:"
for i in "${!job_names[@]}"; do
  printf '  %-34s http://127.0.0.1:%s/\n' "${job_names[$i]}" "${ports[$i]}"
done
echo
echo "Waiting for all runs to finish..."

failure=0
for i in "${!pids[@]}"; do
  if wait "${pids[$i]}"; then
    printf 'finished %-34s status=0\n' "${job_names[$i]}"
  else
    status="$?"
    failure=1
    printf 'failed   %-34s status=%s log=%s\n' \
      "${job_names[$i]}" "$status" "${log_files[$i]}"
  fi
done

trap - INT TERM
exit "$failure"
