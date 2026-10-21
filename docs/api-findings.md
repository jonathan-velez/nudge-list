# Live API inspection — 2026-10-11 (America/Los_Angeles)

Ordinary unauthenticated HTTPS GETs succeeded for both endpoints. No browser was needed.

## Schedule

Source: https://ep.dsrtsurf.com/api/sessions/with/2026-10?upcoming=true

The initial inspection at approximately 07:59 returned 837 records; 675 public, non-private reef sessions; 173 normalized groups. After 08:00, two sessions expired, yielding 835 records and 172 groups. The deployed baseline matches this later response. Observed fields include `_id`, `sessiontype`, `date`, `dateid`, `starttime`, `direction`, `price`, `basePrice`, `currentPrice`, `demandMultiplier`, `sessionlimit`, `available`, `incart`, `category`, `waveCode`, `waveClass`, `durationMin`, `endTime`, `audience`, `bookingMode`, `effectiveMax`, `effectiveAvailable`, and `lagoonSide`. Some records additionally have `blocked`, `blockReason`, `privateSession`, `bayOffering`, or `segmentSpan`.

All 837 records had equal price/basePrice/currentPrice; all demandMultiplier values were 1. This snapshot provides no evidence of active demand multipliers; it does not guarantee future equality. Names and wave codes are available but names are mutable and waveCode may be absent (e.g. private sessions); neither is assumed to be a unique stable identity. Catalog IDs also have collisions.

Both reef/bay and bookable/request-only values were observed. All audience values were `public`, including eight records with `privateSession=true`, `blocked=true`, and request-only mode. Thus audience alone is insufficient. Seventeen records had `available=0`. The initial blocked records were private and therefore excluded; the filter/tests retain blocked non-private public sessions.

Weekday/weekend and time differences exist. Advanced Turns ranged from 200/210 on weekdays to 220/230 on weekends. On Sunday October 18, Left sessions were 220 at 11:00 and 230 at 17:00. There were 76 session/date/direction combinations with multiple times and differing prices. No price differences were observed between directions sharing the same session/date/time; differing directions are nevertheless preserved as distinct prices by the filter.

## Month/query behavior (tested, not assumed)

| Parameter | Count | Earliest date | Latest date |
| --- | ---: | --- | --- |
| 2026-09 (no upcoming) | 505 | 2026-08-25 | 2026-10-07 |
| 2026-09?upcoming=true | 0 | — | — |
| 2026-10 (no upcoming) | 1288 | 2026-09-24 | 2026-11-07 |
| 2026-10?upcoming=false | 1288 | 2026-09-24 | 2026-11-07 |
| 2026-10?upcoming=true | 837 | 2026-10-11 | 2026-11-07 |
| 2026-11 (no upcoming) | 751 | 2026-10-25 | 2026-11-18 |
| 2026-11?upcoming=true | 751 | 2026-10-25 | 2026-11-18 |
| 2026-12?upcoming=true | 0 | — | — |
| 2000-01?upcoming=true | HTTP 400 | — | — |

The month selects a padded calendar window. Earliest/latest returned dates depend on published inventory; exact server boundary rules cannot be inferred from populated records alone. `upcoming=true` removes past sessions, including already-started same-day sessions, rather than returning all future inventory irrespective of the month. The 08:00 Left/Right pair disappeared after 08:00 during testing, removing the last representative of one group. Upcoming does not guarantee purchasable inventory. The monitor advances the month using changedetection.io's native timezone-aware date template, validated in the running watch.

## Catalog

Source: https://ep.dsrtsurf.com/api/sessions/types

34 definitions with `id`, `name`, `price`, `waveClass`, `waveCode`, `skill`, `skillLevels`, plus optional descriptions, gear, lessons, board types, and locals rates. Repeated IDs/names occur for Bay Beginner Lesson, Critical Carving, Critical Carving & Turns, and Critical Turns. Team Surf templates were priced at 50; Turns to Barrel was 0. These definitions do not establish bookable inventory or public minimum prices.

## Audience omission — 2026-10-21

The October and November `upcoming=true` calendar responses included three
distinct Air Camp reef sessions (October 30, November 6, and November 13) with
no `audience` field. One also lacked `incart`. Treating audience as mandatory
for every returned offering caused both helpers to reject otherwise usable
public calendars with HTTP 502. The helpers now exclude missing/null audiences
instead of inferring public status. Invalid audience types and malformed public
sessions still fail validation, and no eligible upcoming sessions still preserves
the previous baseline as an error.

## Implementation references

- [Official Compose example](https://github.com/dgtlmoon/changedetection.io/blob/master/docker-compose.yml)
- [REST API implementation](https://github.com/dgtlmoon/changedetection.io/blob/master/changedetectionio/api/Watch.py)
- [JSON/jq processing](https://github.com/dgtlmoon/changedetection.io/blob/master/changedetectionio/html_tools.py)

Implementation was checked against the deployed image, not only current upstream files. Raw inspection responses are local ignored files; a small derived schedule fixture is version controlled.
