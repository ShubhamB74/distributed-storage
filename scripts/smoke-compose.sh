#!/usr/bin/env bash
# Compose smoke test: liveness, readiness, readiness failure when PostgreSQL stops,
# and recovery when it returns. Requires `docker compose up -d` to have been run.
set -euo pipefail
cd "$(dirname "$0")/.."

base="${API_URL:-http://127.0.0.1:8000}"

status() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$base$1" || true; }

wait_for() { # wait_for <path> <expected-status> <timeout-seconds>
  local path="$1" expected="$2" timeout="$3" code=""
  for _ in $(seq 1 "$timeout"); do
    code="$(status "$path")"
    [[ "$code" == "$expected" ]] && return 0
    sleep 1
  done
  echo "FAIL: $path returned '$code', expected $expected after ${timeout}s" >&2
  return 1
}

echo "1. liveness and readiness come up"
wait_for /healthz 200 120
wait_for /readyz 200 120

echo "2. readiness fails (503) while PostgreSQL is stopped; liveness stays 200"
docker compose stop postgres
wait_for /readyz 503 30
wait_for /healthz 200 5

echo "3. readiness recovers after PostgreSQL restarts"
docker compose start postgres
wait_for /readyz 200 90

echo "Smoke test passed."
