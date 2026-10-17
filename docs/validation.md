# LoveMachine FM inventory validation — 2026-10-12

Deployed and enabled **LoveMachine FM | 6'4 & 6'6 | Inventory**, watch ID
`d5d97674-a28e-4753-92e9-c2506e991c14`, with a ten-minute interval and the
existing configured ntfy destination. No new service, volume, or
package was added. The pricing helper was restarted to load its inventory route;
existing watch settings were captured before deployment and compared unchanged
afterward. The other concurrent implementation was consolidated after its chat
completed; unused draft files were preserved in ignored `.local/archive`.

Shopify's public collection endpoint returned four FM products. The matching
6'4 FM (`64-fm-copy`, price 1025.00) and 6'6 FM (`66-fm-19`, price 1285.00)
were both unavailable. Each product's `.js` endpoint independently agreed.
The collection's second page was empty. The deployed baseline was captured at
2026-10-12 14:48 America/Los_Angeles; two successful checks retained one CD
history snapshot, zero availability alerts, and no fetch error. Reapplying
inventory-only setup retained the same watch ID. The initial observation is a
silent baseline, including any boards already available at first setup.

All 34 offline regression tests passed, including 18 inventory simulations and
the existing pricing/availability tests. The full disposable CD integration
suite passed legacy jq, pricing, and inventory-through-production-HTTP-handler
checks. Inventory tests proved new available listings in both target sizes,
restocks, a second restock, unchanged availability, silent sellouts, ordering /
price / description / unrelated-size changes, empty/malformed responses,
request failure, and recovery without new history. Test notifications were muted;
production baseline/history was not replaced with fixtures. Each integration run
now owns a distinct disposable container to avoid concurrent test collisions.

A separate **LoveMachine FM — notification test** was sent using CD's normal
web session and notification test handler. ntfy's readback confirmed exactly one correctly labelled test message, explicitly
stating that it was not a stock alert. This verifies delivery to the topic,
not acknowledgment by a particular subscriber device. No synthetic stock alert
was sent. CD reported no notification error afterward.

Ten-minute polling and local uptime can miss brief restocks. Public Shopify
availability is not a checkout reservation. The monitor covers the FM collection
and recognized model/length notation; valid partial responses and a disappearance
without an observed sold-out flag can hide changes. See
[operating notes](lovemachine-inventory.md) for these boundaries and safe tests.

---

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

## Availability false-alert fix — October 13, 2026

The availability helper now compares normalized session dictionaries, excluding
natural expiration, before replacing its alert report. Unchanged collections
retain the last actual change report. Fresh observations, expired-session counts,
ordering, and clearing yesterday's change list cannot create alerts. Every
successful collection still saves current raw data, normalized inventory, and a
fresh `daily_report`; `report` is the durable alert payload. Existing saved state
migrates without replacing the CD baseline. Public-session visibility changes
still alert; returning IDs continue to use the existing NEW label.

Ten unit tests passed. The separate offline HTTP/history integration suite
(`bash tests/test-integration.sh tests/availability_integration.py`) passed ten
checks through the pinned changedetection engine: unchanged cached/fresh-day
collections, genuine decrease, unchanged day after a decrease, restart,
repeated equal-sized decrease, expiration only, status change, upstream failure,
and recovery. Delivery remained muted in the disposable container. Replaying
all three October 11–13 production snapshots reproduced their original reports.

Deployment recreated only the availability container to correct its stale
bind mount from the former `dsrt-surf-tracker` folder, preserving the existing
`dsrt-surf-tracker_availability-data` volume. The live watch check count advanced
from 9 to 11, its three history entries remained unchanged, notification count
stayed at 2, and fetch/notification errors were false. The URL, notification
destinations, mute setting, and 19:00–20:00 Pacific schedule were preserved.


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


## Remaining-change review — October 17, 2026

Reviewed the LoveMachine comparator, shared helper route, watch configuration,
setup scripts, fixtures, and availability report-stability changes before commit.
All 46 unit tests passed again. The dedicated disposable availability HTTP/history
suite passed all ten checks; the full pricing/inventory integration suite also
passed earlier in this session with the same runtime sources. Shell syntax,
JSON fixtures/configuration, and whitespace checks passed. Removed the private
notification destination from these public notes. No production state or
notification settings were changed during this review.


## Combined-commit and live verification — October 17, 2026

Verified the clean combined tree at 2a2c5cf and GitHub main matched. Source hashes
inside both running helpers matched the committed pricing, LoveMachine, and
availability files. All 46 unit tests and 24 normalization checks passed. Both
isolated HTTP/history suites passed against the final combined sources: pricing
and inventory, plus all ten availability checks. Simulated changes never touched
production baselines or sent notifications.

Two real checks of each active watch succeeded without fetch or notification
errors. Pricing advanced 63 to 65 checks with history 9 and notifications 7
unchanged. LoveMachine advanced 113 to 115 with history 3 and notifications 2
unchanged. Availability advanced 15 to 17: its first fresh collection detected
real availability changes and created one history entry and alert; the repeat
created neither. Watch identities, destinations, and active/unmuted state were
preserved. LoveMachine's live interval had drifted to 60 minutes; following user
confirmation it was restored to the committed 10 minutes, and another successful
unchanged check advanced its count to 116 without history or notification changes.

The audit also identified a scheduling edge: CD applies its minimum interval to
manual checks, so the availability watch's 12-hour interval could suppress a
7 PM check after an afternoon recheck. Changed the template and live minimum to
one hour, matching the 19:00–20:00 Pacific window. The existing helper still
collects only once per 19:00-to-19:00 period. All seven daily windows, history,
notification destinations, and cache boundary were preserved; live jitter was
zero and tonight's window was eligible after verification. The dedicated
availability pipeline suite passed again with the updated template. This verifies
configuration eligibility, not observation of the future 7 PM run; the Mac and
Docker must be awake then. No additional labeled delivery test was sent.


## Sequential three-month DSRT collection — October 17, 2026

Both DSRT helpers now request only the Pacific current month and the following
two months. Requests are sequential, with an independently drawn uniform 2–4
second sleep after each completed request except the last. A populated third
month never extends the scan. Overlap validation, effective-price comparisons,
slot references, daily caching, and atomic failure-safe baselines are retained.
An availability cache created under the older horizon refreshes once even within
the same daily slot. The helper still caches subsequent unchanged same-slot calls.

All 48 unit tests passed. Timing tests assert fetch/pause ordering, two random
draws with bounds 2 and 4, exactly three months across year rollover, and no
extension when the edge is populated. Tests also cover old-cache refresh and
third-month failures without baseline replacement. Separate tests using real
sleep and synthetic upstreams measured pricing gaps of 3.466 and 3.005 seconds,
and availability gaps of 3.849 and 2.855 seconds. Both disposable HTTP/history
integration suites passed; their waits are stubbed while unit and timing checks
verify throttling separately. Notifications remained muted in disposable tests.

Deployed by restarting only pricing and availability, preserving volumes and watch
settings. One live check each saved exactly 2026-10, 2026-11, and 2026-12; source
hashes in the containers matched the tested files. Pricing advanced 65 to 66 checks
without new history or notification. Availability advanced 17 to 18, producing one
real inventory-change alert (including availability 1 -> 0 and 2 -> 3), with expired
sessions excluded from bookings. Both fetch and notification errors were false.
The three-hour pricing interval, 7 PM availability window, ten-minute LoveMachine
interval, notification destinations, and active states were unchanged. Expected
successful scheduled DSRT traffic is now 27 requests/day rather than 117,
excluding manual checks and failures. No automatic scan beyond the third month
remains; DSRT's padded response dates can still overlap adjacent calendar months.
