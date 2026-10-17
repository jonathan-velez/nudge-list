# Nudge List

A personal monitoring list powered by changedetection.io at
[localhost:5050](http://localhost:5050). It monitors DSRT's published public reef
pricing every three hours, DSRT upcoming availability daily, and LoveMachine
FM inventory every ten minutes, with an optional paused catalog watch. Small
internal Python helpers store comparison baselines and combine calendars.

The monitor runs locally in Docker. All active watches use the configured ntfy
destination; the optional catalog remains paused.

## Start / stop

Prerequisites: Docker Desktop running on macOS (Apple Silicon supported), Docker Compose, Bash, curl, and jq (`brew install jq` if needed).

```sh
docker compose up -d
# Wait for the dashboard to load, then:
# Configure notifications and create or update the active watches:
bash scripts/setup-local.sh
# Fresh setup without notifications: ./scripts/setup-watch.sh
```

Open http://localhost:5050. The official image is pinned to a
changedetection.io 0.60.8 digest and includes Python jq. The web port binds
only to `127.0.0.1`, with timezone `America/Los_Angeles`. State and history
live in the named Docker volume.

```sh
docker compose stop        # stop, retain container and history
docker compose start       # resume
docker compose down        # remove container, retain volume
# Do NOT add -v unless you intend to delete all settings and history.
```

Docker Desktop and the Mac must remain awake for checks. Restart policy is `unless-stopped`; enable Docker Desktop login startup if desired. Missed observations while asleep/offline cannot be reconstructed.

## What it measures

`pricing/server.py` selects `waveClass=reef`, `audience=public`, and excludes
`privateSession=true`. It stores each upcoming session's effective price by
DSRT session ID in the persistent `pricing-data` Docker volume. The effective
price is numeric `currentPrice`, with `price` fallback only when currentPrice
is absent/null. Integer/decimal formatting is equivalent.

An increase or decrease for an already observed session ID triggers an alert.
For a new ID, the monitor compares its price with a saved reference matching
**session type, weekday, local start time, and direction**. A lower price triggers
**NEW LOWER PRICE**, with its date, time, direction, ID, reference price, new price,
and savings. For example, a new Monday 11 AM Advanced Turns Left session at $180
alerts against a matching $200 reference. A normal-priced or higher-priced new
session stays silent. A slot with no matching reference establishes one silently.

Reference prices survive individual session expiration and restarts. When an exact
slot has multiple stored future prices, the lowest is the reference, so an already
available cheaper tier does not create a false reduction. All comparisons use the
previous saved references before learning the current collection. After a successful
collection, references update to the lowest stored future price for each slot;
slots with no remaining future sessions retain their last reference. Older state
initializes these references from its saved sessions without clearing history.

The initial installation baseline is silent. Removals, expiration, names,
directions, availability, capacity, and calendar rollover alone do not trigger
alerts. Missing future sessions retain their last observed price until their start
time, so temporary disappearance/reappearance does not reset a baseline or repeat
an alert. Expired session IDs are pruned; their slot references are retained.
Replacement IDs use the same comparison rule as new IDs. Confirmed price edits
include the old/new price; new lower prices are comparisons against the matching
slot reference, rather than claims that the new ID previously had a higher price.

The last price-change report stays identical through subsequent no-change checks
and restarts; there is no alert when the report returns to an empty state.
Prices and report are saved together with an atomic file replacement. CD retains
its usual history and sends notifications. `filters/sessions.jq` remains available
for legacy normalization tests; the active watch uses the helper without jq.

- **Published pricing:** prices attached to scheduled public reef sessions, even when unavailable.
- **Currently bookable pricing:** would additionally require availability, booking mode, blocking, and checkout validation; this monitor does not promise that a displayed price can be booked.
- **Catalog/template pricing:** secondary product definitions, potentially internal/unpublished. These are not price floors or booking offers.

Empty, malformed, wrong-schema, and failed HTTP responses produce watch errors and preserve the previous valid baseline. Partial but otherwise valid responses cannot reliably be recognized as incomplete.

## Dates and normal calendar changes

The internal feed at `http://pricing:8080/report` requests the Pacific current
month and next 12 months from DSRT with `upcoming=true` at each check, including
empty intervening months. If the final month is populated, it extends up to 24
months ahead and flags the limit if still populated. This is bounded discovery,
not a guarantee of unlimited coverage. Overlapping sessions are deduplicated by
ID; conflicting responses fail without replacing the baseline. No monthly script
or manual update is needed. The API returns a padded calendar window for each
month and removes started/past sessions. See [live API findings](docs/api-findings.md).
Removed/expired sessions and the passage of time are silent. New sessions
at month rollover alert only when cheaper than their matching saved slot reference.
Calendar expansion uses the same rule; ordinary additions stay silent.

For an existing deployment, migrate the watch once with:

```sh
docker compose up -d pricing
bash scripts/migrate-pricing.sh
```

The migration retains watch identity, settings, and history. It mutes the format
transition, verifies a successful new baseline, and restores the previous mute
and pause settings. Existing history remains available; the new per-session
baseline starts at migration because old grouped snapshots lack session IDs.
Local `.env` preserves the existing Docker project name `dsrt-surf-tracker` after
the repository rename, keeping its existing history volumes. Keep that value
when operating this installation.

## Settings and history

To configure notifications, edit ignored `.local/watch.json` and rerun
`bash scripts/setup-local.sh`. This applies its notification destination to pricing,
availability, and LoveMachine inventory watches. The current feed and message are taken from
`config/watch.json`; local notification destinations and polling interval are retained.
The setup script finds the exact title, creates or updates one watch, and refuses
ambiguous duplicate titles. Keep titles stable to retain identity/history.
Tracked `config/*.json` are muted templates: applying them directly will mute
the corresponding watch.

Change `time_between_check.hours` to adjust polling. Checks use the normal HTTP fetcher against the internal helper. Click the watch's **Diff/history** controls to inspect saved versions; the watch's human-facing link opens [DSRT's calendar](https://book.dsrtsurf.com/app.html#/calendar). Filter changes can themselves cause a historical diff.

The script reads the local instance's API key from its Docker volume without printing it. Alternatively set `CHANGEDETECTION_API_KEY` and `API_URL` in your environment. Do not commit credentials. Local web access is not password protected by this setup; an optional UI password is available in changedetection.io settings.

The image may create example watches on first startup. They can be deleted in
the dashboard; setup deliberately does not delete unrelated watches.

## Optional ntfy notifications

No provider or credentials are required. Once ready, use the watch's Notifications settings to add an Apprise URL, test delivery, and unmute. See [Apprise ntfy syntax](https://github.com/caronc/apprise/wiki/Notify_ntfy). Examples:

- Public ntfy: `ntfy://your-unguessable-topic`
- Your HTTPS ntfy server: `ntfys://ntfy.example.com/your-topic`

For repeatable local configuration, copy the JSON to an ignored file:

```sh
mkdir -p .local
cp config/watch.json .local/watch.json
# Edit .local/watch.json: notification_urls = [your Apprise URL],
# notification_muted = false. Keep credentials out of version control.
./scripts/setup-watch.sh .local/watch.json
```

The prepared message reports existing-session price changes or new sessions below
their matching slot reference, and links to the booking calendar. It includes the
latest pricing report rather than calendar schedule diffs. The configured ntfy destination is used by all local
active watches and kept out of version control.

## Optional catalog

```sh
./scripts/setup-watch.sh config/catalog.json filters/catalog.jq
```

This creates/updates **DSRT Surf — Session Catalog**, paused and muted. Unpause to collect informational history. The filter preserves ID, name, price, wave class/code, and skill fields, sorts deterministically, and removes exact duplicates. Conflicting definitions sharing an ID remain distinct. Missing optional fields become null; malformed required identity/price data errors out.

## Daily upcoming availability

`ALLOW_IANA_RESTRICTED_ADDRESSES=true` allows changedetection.io to fetch the
internal pricing and availability helpers. It permits private-network fetching for every
watch, so only add watches you trust. The UI remains bound to localhost.

The **DSRT Surf — Daily Upcoming Availability** watch runs in CD's
**19:00–20:00 America/Los_Angeles** window. Its one-hour minimum interval matches
the window, allowing a nightly check even after an afternoon manual recheck. The
helper caches one successful collection per 19:00-to-19:00 period; manual
rechecks reuse it. Setup creates a baseline immediately. Docker and the Mac
must be awake during the nightly window; missed days produce a comparison
spanning the gap.

```sh
docker compose up -d availability
bash scripts/setup-local.sh
python3 tests/test_availability.py
```

Open the watch's Preview for the most recent actual change report or Diff/history for saved changes. It fetches the current month and the next 12 months, including empty intervening months, deduplicates overlapping calendars by session ID, and tracks all public, non-private reef and bay sessions. If the final month is populated it extends the search, up to 24 months ahead, and flags that limit if still populated. This is bounded discovery, not a promise of unlimited future coverage.

The report lists availability decreases/increases, new and removed sessions, expired sessions, and the full upcoming inventory. Only clean reef availability decreases are totaled as **possible net bookings**. Capacity, cart, blocking, schedule, and shared bay inventory changes are excluded from those totals. Expired or missing sessions are never interpreted as bookings. The public API cannot establish gross sales or attendance, and bookings/cancellations between snapshots can offset each other.

Malformed responses, HTTP failures, conflicting overlap records, and an entirely
empty public calendar fail the watch without replacing the previous valid
baseline. A syntactically valid partial API response cannot always be detected.
Successful raw responses and reports persist in the `availability-data` Docker
volume; CD also retains its usual history in `changedetection-data`. The helper
has no host port and is reachable only on the Compose network at
`http://availability:8080/report`. It reuses the already-pinned image's Python
runtime, with no additional packages. Scheduling belongs to CD.

Alert detection compares normalized upcoming inventory, excluding sessions that
have simply expired. Timestamps, changing daily totals, ordering, and clearing
the previous day's changes cannot trigger alerts. The HTTP feed retains the
last actual change report across unchanged days and restarts; its observation
time is the time of that change. Real availability, capacity, cart, status,
schedule, and public-session additions/removals still trigger changes.
Each saved JSON includes a fresh `daily_report`, current `sessions`, and the
retained alert `report`, even on no-change days. To test the HTTP/history pipeline
without live delivery, run `bash tests/test-integration.sh tests/availability_integration.py`.
Notifications use the same ntfy
destination as pricing. Use `bash scripts/setup-local.sh` to apply this
configuration; the tracked availability JSON remains a muted template.

## Verification / troubleshooting

```sh
python3 tests/test_pricing.py -v
python3 tests/test_inventory.py -v
./tests/test-normalization.sh
./tests/test-integration.sh
docker compose ps
docker compose logs --tail=80 changedetection
```

Integration tests run the same pinned image in a disposable, network-isolated container, with synthetic JSON served on its internal loopback interface. Test state is tmpfs, the repository is mounted read-only, and no production history is modified. The tests cover both legacy jq normalization and the persistent pricing and inventory helpers through CD's actual fetcher and history engine. Synthetic price tests never modify production state or send notifications.

On API/network errors, inspect the watch's error and press Recheck after recovery. Do not clear history to hide failures. Check Docker is awake, internet/DNS works, and DSRT still exposes the expected schema. A sudden no-public-reef error may mean the calendar has no published sessions or the API changed. Do not relax validation without inspecting the response.

If setup returns an HTTP validation error, its body identifies the unsupported field. If connection is refused, wait for startup and confirm port 5050 is free. If the API returns 403, check the API key/security setting. Rerun setup after changing filters/settings; do not edit the application code or its datastore files.

To upgrade, update the image digest in both Compose files, run the tests, and recreate production with `docker compose up -d`. Back up the named volume before upgrades. See [validation results](docs/validation.md).

## LoveMachine FM inventory

**LoveMachine FM | 6'4 & 6'6 | Inventory** checks Shopify's public FM collection
JSON every **10 minutes**, discovers new products automatically, and reports
only newly available matching listings or restocks. Sold-outs and metadata edits
are silent. It shares the existing pricing helper container and storage, with
no new service or dependency. Notifications reuse the existing channels.

```sh
docker compose restart pricing
bash scripts/setup-lovemachine.sh
python3 tests/test_lovemachine.py -v
python3 tests/test_inventory.py -v
```

See [inventory implementation, setup, and limitations](docs/lovemachine-inventory.md).
