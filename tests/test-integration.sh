#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Each run owns its disposable container, avoiding parallel-test collisions.
compose=(docker compose -p "nudge-monitor-test-$$" -f tests/compose.yaml)
cleanup() {
  result=$?
  if [[ $result != 0 ]]; then "${compose[@]}" logs --tail=25; fi
  "${compose[@]}" down >/dev/null
  exit "$result"
}
trap cleanup EXIT
"${compose[@]}" up -d
"${compose[@]}" exec -T integration python "/work/${1:-tests/integration.py}"
