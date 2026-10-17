#!/usr/bin/env bash
# Apply the user's ignored notification settings to all local active watches.
set -euo pipefail
cd "$(dirname "$0")/.."
pricing=${1:-.local/watch.json}
if [[ ! -f "$pricing" ]]; then
  echo 'Missing local notification configuration; supply the ignored pricing JSON.' >&2
  exit 1
fi
jq -e '.notification_muted == false and (.notification_urls | type == "array" and length > 0)' "$pricing" > /dev/null
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
jq --slurpfile pricing "$pricing" \
  '. + {notification_muted: false, notification_urls: $pricing[0].notification_urls}' \
  config/availability.json > "$tmp/availability.json"
# Keep local notification destinations, but always apply the current feed and message.
jq --slurpfile local "$pricing" \
  '. + {notification_muted: false, notification_urls: $local[0].notification_urls,
        time_between_check: $local[0].time_between_check}' \
  config/watch.json > "$tmp/pricing.json"
./scripts/setup-watch.sh "$tmp/pricing.json" none
./scripts/setup-watch.sh "$tmp/availability.json" none
jq --slurpfile pricing "$pricing" \
  '. + {notification_muted: false, notification_urls: $pricing[0].notification_urls}' \
  config/lovemachine.json > "$tmp/lovemachine.json"
bash scripts/setup-watch.sh "$tmp/lovemachine.json" none
