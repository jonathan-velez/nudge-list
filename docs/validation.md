# Pricing baseline validation — 2026-10-12

The active **DSRT Surf — Published Session Pricing** watch now fetches
`http://pricing:8080/report`. The helper stores prices by session ID in the
`dsrt-surf-tracker_pricing-data` Docker volume and emits a changed report only
for an observed session's numeric price increase or decrease. New sessions,
removals, expiration, and calendar rollover are silent.

Ten offline baseline tests passed, covering last-group removal, new sessions,
updated-price comparisons, missing/reappearing sessions, expired-session pruning,
nonprice edits, exclusions, validation/network failures, conflicting duplicates,
restart persistence, and month/year rollover. The 24 legacy jq normalization
checks and six availability regression tests also passed.

The disposable Docker integration suite passed both its legacy jq checks and
the new helper-through-CD pipeline. It confirmed that schedule removals and new
discounted sessions leave CD history unchanged; a 220-to-200 decrease and a
200-to-210 increase add history; subsequent unchanged checks and helper restart
are silent. Empty calendars/upstream failures preserve the valid baseline and
CD history, and recovery does not add a spurious change. Test notifications
remained muted; no live delivery test was sent.

Production migration preserved pricing watch ID
`1b83eac3-52f7-4a20-a542-cbf10d9d10b4` and existing history. Its new baseline
contains 645 session prices. The one-time format transition was muted, then the
previous enabled notifications and three-hour polling interval were restored.
A live unchanged recheck passed with no new history entry or notification;
notification alert count remained six. No fetch error was reported. Local
`.env` retains the pre-rename Compose project name so existing volumes remain
attached. The availability and catalog watches were not reconfigured.

The baseline starts at migration; legacy grouped pricing history cannot supply
per-session IDs. Pricing coverage remains the Pacific current month's padded
calendar. A replacement session with a new ID establishes its baseline silently.

The entries below describe earlier deployment snapshots and are historical.
Their old pricing behavior and notification status do not describe the current
pricing watch.

---

# Deployment validation — 2026-10-11

## Local restoration after GitHub trial

The original Compose containers and named history volumes were restored without
deleting or resetting watches. The dashboard returned HTTP 200 at
`http://localhost:5050`. Pricing remains active every three hours; availability
remains active in the 22:00–23:00 Los Angeles window. Both use the existing ntfy
destination with notifications enabled; catalog remains paused/muted. Both active
watches initially reported no fetch errors. `bash scripts/setup-local.sh` reapplies
the ignored pricing notification settings to both active watches.

Manual rechecks of both active watches completed successfully with no fetch or
notification errors. Pricing retained its prior snapshots and added the current
observation; availability reused its existing daily cache and retained its history.

GitHub Actions monitoring was disabled, and its workflow/batch implementation was
removed from the current source. `monitor-data` retains GitHub observations; a
current-tree export is also saved in ignored
`.local/archive/github-monitor-data-2026-10-11.tar.gz`. Those observations are not
imported into changedetection.io history. The full-history hybrid proposal was
moved to `.local/archive/hybrid-dashboard-plan.md` for later reference.

The existing 24 normalization checks and six availability tests pass.

Environment: macOS Apple Silicon, Docker Desktop, official ARM64 changedetection.io 0.60.8 image pinned by digest in Compose. The official image contains jq bindings; no custom image or installed dependency was needed.

## Production instance

- Running at http://localhost:5050, bound to `127.0.0.1:5050` only.
- Live unauthenticated DSRT fetches succeed through `html_requests`.
- **DSRT Surf — Published Session Pricing** is active, every three hours, notifications muted.
- Stored normalized snapshot has 172 groups and matches jq output from a fresh live API response exactly (after JSON key ordering).
- Repeated successful live checks retained one history snapshot and zero notifications.
- Setup was run repeatedly; only one pricing watch was created.
- Container restart preserved the exact history index, interval, active state, mute setting, and templated URL.
- **DSRT Surf — Session Catalog** successfully collected one baseline with the standalone catalog filter; it is now paused and muted.
- Dashboard HTTP response contains both watch names. No browser automation was necessary.

## Automated tests

`tests/test-normalization.sh` passes 24 checks: availability, capacity, direction availability, order, redundant expiry, blocked sessions, fallback, private/bay exclusions, weekday/weekend decreases, increases, extra tiers, renames, new types, direction price differences, last-tier expiry, empty/wrong-shape/missing-price/bad-price/invalid-date/no-reef responses, and invalid JSON.

`tests/test-integration.sh` exercises the deployed image's actual HTTP fetcher, jq selector, change engine, REST API, and history persistence against a loopback fixture server inside an isolated disposable container. Tests verify unchanged checks, synthetic changes, malformed/empty JSON, HTTP 503, connection refusal, and recovery without baseline corruption. Test watches remain muted and alert counts stay zero. It also tests native month/year URL rendering and ntfy URL parsing without sending anything.

The test container has no external network, no published ports, tmpfs state, and a read-only repository mount. Bundled example watches start paused so their external requests cannot delay tests. The harness waits for `check_count` to advance: `last_checked` is set at fetch start, before processing completes.

## Important boundaries

No actual notification delivery was tested or configured. ntfy URL parsing is verified; delivery requires the user's chosen topic/server and a later send test.

The three-hour interval is configured and persists, but this initial validation used manual rechecks rather than waiting three hours. Month/year boundaries were simulated using the application's native renderer; a real future calendar rollover has not yet occurred.

The initial 07:59 API inspection contained 173 groups. Started 08:00 sessions disappeared during deployment, leaving 172. This confirms the documented last-representative expiry limitation, rather than a normalization mismatch. No price-drop-only behavior is claimed.

## Matching-slot price references — October 17, 2026

New sessions now compare with saved prices for the same session type, weekday,
local start time, and direction. Only a price below that reference emits
`NEW LOWER PRICE`; normal/higher prices and unknown slots establish baselines
silently. Existing-ID price increases/decreases still alert. References survive
expiration and restart; the lowest stored future price is used when a slot has
multiple prices, with the last reference retained when that slot disappears.
All new IDs in one collection compare before references update. Old state
initializes references from its stored sessions without replacing its report.
This supersedes both the earlier rule ignoring all new IDs and the brief rule
alerting on every new ID. That earlier notification/history entry is preserved.

The price scan now covers the current month and next 12 months, including empty
gaps, extending to 24 months ahead when its edge is populated. Overlapping IDs
are deduplicated and conflicting/failed month responses preserve the baseline.

All 46 unit tests passed, including 18 price tests. The exact Advanced Turns
Monday 11 AM $200-reference/$180-new-session scenario passed, as did silent
normal prices, matching-slot isolation, expiration, legacy state, restart,
minimum-price references, month gaps, overlapping calendars, and failed fetches.
The full disposable HTTP/history integration suite passed, including cheaper
new dates, silent ordinary additions, repeat checks, missing/returning IDs,
existing price edits, restart, month rollover, failure recovery, and inventory
regressions. Disposable notifications remained muted.

A live-data preview against a copy of the original 511-session baseline found
239 additional sessions through November 18 and no lower matching-slot prices.
After deployment, two live rechecks advanced check_count from 61 to 63 while
history remained at 9 and notification_alert_count at 7. Fetch and notification
errors were false. The watch identity, destinations, unmuted/active state, and
three-hour interval were retained. The saved live state has 750 sessions and
184 slot references, including Advanced Turns Monday 11 AM at $200 in both
directions. The running source checksum matches the local tested source.
No additional delivery test was sent during this correction; the earlier
separate labeled test was accepted by the configured notification service.
