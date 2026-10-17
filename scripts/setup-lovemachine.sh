#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/api.sh
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# Read the active pricing watch, rather than inventing a notification destination.
api "$API_URL/watch" > "$tmp/watches.json"
id=$(jq -er '[to_entries[] | select(.value.title == "DSRT Surf — Published Session Pricing") | .key] | if length == 1 then .[0] else error("Expected exactly one pricing watch") end' "$tmp/watches.json")
api "$API_URL/watch/$id" > "$tmp/pricing.json"
jq -e '.notification_muted == false and (.notification_urls | type == "array" and length > 0)' "$tmp/pricing.json" > /dev/null
jq --slurpfile pricing "$tmp/pricing.json" '. + {notification_muted: false, notification_urls: $pricing[0].notification_urls}' config/lovemachine.json > "$tmp/watch.json"
bash scripts/setup-watch.sh "$tmp/watch.json" none
