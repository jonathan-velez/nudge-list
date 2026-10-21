# LoveMachine FM inventory

The watch **LoveMachine FM | 6'4 & 6'6 | Inventory** checks the entire
[FM collection](https://lovemachinesurfboards.com/collections/all-fm) every
10 minutes. Shopify's public collection JSON exposes boolean variant
`available` flags, titles, IDs, prices, and handles. A live product `.js`
cross-check agreed with the collection's sold-out status on October 12, 2026.

`pricing/lovemachine.py` runs through `/lovemachine/report` in the existing
pricing helper container. No new service, volume, package, browser, or retailer
credentials are required. CD owns scheduling, history, and notifications.
The watch fetches `http://pricing:8080/lovemachine/report`; its dashboard link
opens the public collection. Do not substitute the public URL for the feed.

Each successful check requests one collection page today. At 250 products it
follows additional pages, with a 20-page safety limit. The entire response is
validated before saving state. Empty collections, missing availability flags,
malformed JSON, failed HTTP requests, duplicate product IDs, pagination overflow,
and potentially truncated variant arrays return an HTTP 502 watch error and
preserve the last valid baseline. A well-formed but incomplete retailer response
cannot always be recognized.

Matching requires a standalone FM designation in the product title and a
6'4 or 6'6 length in its title or variant options. Smart quotes, spaces, feet
notation, and hyphens are accepted. An explicit variant length overrides the
product title. Ambiguous lengths are excluded; dimensions must be stated in a
recognized notation. Decimal lengths and bare numbers are deliberately excluded.

State lives in `pricing-data` at `/state/lovemachine/latest.json`, separately
from DSRT pricing. Product and variant IDs identify individual boards. The first
observation establishes a silent baseline. Subsequent new available identities
and false-to-true availability transitions create reports containing product
name, size, store price, a variant-specific product URL, and new-listing/restock
reason. Prices use the store's currency; the collection response does not
explicitly identify the currency.

Sold-out transitions update the stock baseline silently. Changes to prices,
names, images, descriptions, ordering, and nonmatching boards do not change the
alert report. The last event report remains identical across repeat checks and
process restarts. Missing identities retain their last known state, preventing
temporary omission/reappearance from manufacturing a restock. This can miss a
restock if an available board disappears, sells out, and returns available
without an observed false flag.

CD supports native additions-only diffs, but the comparator retains history to
distinguish new listings from restocks, include prices without price-only
alerts, and reliably handle simultaneous additions and removals.

## Daydream Surf Shop

**Daydream | LoveMachine FM | 6'6 | Inventory** checks the
[new surfboards collection](https://daydreamsurfshop.com/collections/new-surfboards)
every 10 minutes using the same validated Shopify comparator. It discovers all
6'6 LoveMachine FM listings, including the original
[linked board](https://daydreamsurfshop.com/products/6-6-lovemachine-fm), without
hardcoded product handles. A standalone FM model, LoveMachine brand in title or
vendor, and a recognized 6'6 length are required. Other brands and sizes are excluded.

The separate `/daydream/report` route, `/state/daydream/latest.json` state, and
CD watch keep the manufacturer's existing baseline and history intact. Restocks
and new available listings alert; initial observations, sellouts, price edits,
and metadata edits are silent. Failed fetches preserve the previous baseline.
The existing pricing helper, volume, and notification channel are reused.

On October 21, 2026, collection JSON contained two sold-out 6'6 FM listings at
$1,100 each, including the linked board. The same collection also listed an
available 6'4 FM; it is outside this Daydream watch's 6'6 scope. Retail stock can
change between checks. Collection removal can hide a subsequent restock, and
only listings in the configured new-board collection are discovered.

Deployed October 21, 2026 as watch `d02c5693-0988-4990-9fee-7bb008b91807`.
Live verification confirmed a successful baseline, an unchanged second check
with one history entry and zero alerts, no fetch error, enabled notifications,
and the same notification destination as DSRT pricing. All 52 unit tests and
the disposable HTTP/CD history integration suite passed, including Daydream
restock, silent sellout, upstream failure, and recovery. No live notification
was sent for this addition. No manual setup steps remain.

## Apply settings

```sh
docker compose restart pricing
bash scripts/setup-lovemachine.sh
```

Both inventory watches are applied by the commands above.
The inventory-only setup reads the enabled pricing watch's current notification
destinations and updates only the exact inventory titles. It refuses ambiguous
pricing titles or missing active destinations. `bash scripts/setup-local.sh`
applies ignored `.local/watch.json` notification settings to all active watches.
The committed watch template is muted until one of these setup scripts supplies
the installation's notification destinations.

## Test safely

```sh
python3 tests/test_lovemachine.py -v
python3 tests/test_inventory.py -v
python3 tests/test_daydream.py -v
./tests/test-integration.sh
```

Fixtures simulate both target sizes, excluded models and sizes, new listings,
restocks, sellouts, unchanged inventory, metadata edits, request failures,
pagination, and restarts. Integration tests use a disposable, network-isolated
CD instance and muted notifications. They never modify production inventory
history or send real stock alerts.

Ten-minute polling can miss inventory that appears and sells between checks.
The Mac and Docker must stay awake. Shopify's availability flag describes
storefront purchase availability rather than inventory quantity, reservation,
or a guarantee that checkout will succeed. Listings outside the FM collection,
unrecognized size/model notation, or Shopify endpoint/schema changes can require
adjustments. Watch errors are visible in CD; error notifications are disabled,
matching the existing project convention.

## Current deployment

Enabled on October 12, 2026, with a successful persisted CD baseline and a
successful unchanged recheck. Both target sizes were sold out at setup.
The existing ntfy channel received one explicitly labelled delivery test.
No manual setup steps remain. Keep Docker and the Mac awake for scheduled checks.
See [validation evidence](validation.md) for the watch ID and test results.
