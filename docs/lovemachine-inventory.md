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

## Apply settings

```sh
docker compose restart pricing
bash scripts/setup-lovemachine.sh
```

The inventory-only setup reads the enabled pricing watch's current notification
destinations and updates only the exact inventory title. It refuses ambiguous
pricing titles or missing active destinations. `bash scripts/setup-local.sh`
applies ignored `.local/watch.json` notification settings to all active watches.
The committed watch template is muted until one of these setup scripts supplies
the installation's notification destinations.

## Test safely

```sh
python3 tests/test_lovemachine.py -v
python3 tests/test_inventory.py -v
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
