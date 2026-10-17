"""Persistent session-price comparator; CD schedules checks and sends alerts."""
import datetime as dt
from random import uniform
from time import sleep
import json
import math
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Los_Angeles')
STATE = Path(os.environ.get('STATE_DIR', '/state'))

def month_at(now, offset):
    n = now.year * 12 + now.month - 1 + offset
    return f'{n // 12:04d}-{n % 12 + 1:02d}'

def fetch_month(month):
    url = f'https://ep.dsrtsurf.com/api/sessions/with/{month}?upcoming=true'
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)

def fetch_calendar(now, fetch):
    months = [month_at(now, i) for i in range(3)]
    rows = []
    last_rows = []
    for index, month in enumerate(months):
        if index:
            sleep(uniform(2, 4))
        last_rows = fetch(month)
        if not isinstance(last_rows, list):
            raise ValueError(f'{month}: expected session array; preserve baseline')
        rows.extend(last_rows)
    return rows, months, bool(last_rows)

def starts(row):
    return dt.datetime.fromisoformat(row['dateid']+'T'+row['starttime']).replace(tzinfo=TZ)

def reference_key(row):
    # JSON encoding avoids collisions in names and separates each exact weekday,
    # local start time, and direction. Unknown directions are not comparable.
    if not isinstance(row['direction'], str) or not row['direction']:
        return None
    return json.dumps([row['sessiontype'], starts(row).weekday(),
                       row['starttime'], row['direction']], ensure_ascii=False)

def reference_prices(sessions):
    prices = {}
    for row in sessions.values():
        key = reference_key(row)
        if key is not None:
            prices[key] = min(prices.get(key, row['price']), row['price'])
    return prices

def normalize(rows, now):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Expected nonempty session array; preserve baseline')
    sessions = {}
    for raw in rows:
        if not isinstance(raw, dict) or not all(isinstance(raw.get(k), str) and raw[k] for k in ('waveClass', 'audience')):
            raise ValueError('Invalid session classification')
        if raw.get('privateSession') is not None and type(raw['privateSession']) is not bool:
            raise ValueError('Invalid privateSession flag')
        if raw['waveClass'] != 'reef' or raw['audience'] != 'public' or raw.get('privateSession'):
            continue
        if not all(isinstance(raw.get(k), str) and raw[k] for k in ('_id', 'sessiontype', 'dateid', 'starttime')):
            raise ValueError('Invalid session identity/date/time')
        row = {k: raw.get(k) for k in ('_id', 'dateid', 'starttime', 'sessiontype', 'direction')}
        instant = starts(row)
        if instant.strftime('%Y-%m-%d') != row['dateid'] or instant.strftime('%H:%M') != row['starttime']:
            raise ValueError('Invalid date/time format')
        price = raw.get('currentPrice')
        if price is None:
            price = raw.get('price')
        if type(price) not in (int, float) or not math.isfinite(price) or price < 0:
            raise ValueError('Invalid effective price')
        row['price'] = price
        if instant <= now:
            continue
        uid = row['_id']
        if uid in sessions and sessions[uid] != row:
            raise ValueError(f'Conflicting duplicate session {uid}')
        sessions[uid] = row
    if not sessions:
        raise ValueError('No upcoming public reef sessions; preserve baseline')
    return sessions

def collect(now=None, fetch=fetch_month, state=STATE):
    now = now or dt.datetime.now(TZ)
    # Validate the complete response before touching durable state.
    rows, months, horizon_limited = fetch_calendar(now, fetch)
    sessions = normalize(rows, now)
    state.mkdir(parents=True, exist_ok=True)
    path = state/'latest.json'
    previous = json.loads(path.read_text()) if path.exists() else None
    old = previous['sessions'] if previous else {}
    # Upgrade older state from its stored observations. Keep reference prices
    # after individual IDs expire; never learn a new row before comparing it.
    references = dict(previous.get('reference_prices', reference_prices(old))) if previous else {}
    # Retain missing future sessions, so a temporary removal cannot reset a price.
    baseline = {uid: row for uid, row in old.items() if starts(row) > now}
    changes = []
    for uid, row in sorted(sessions.items()):
        prior = baseline.get(uid)
        if prior is not None and prior['price'] != row['price']:
            changes.append(f'{row["dateid"]} {row["starttime"]} | {row["sessiontype"]} | {row["direction"]} | {uid} | price {prior["price"]:g} -> {row["price"]:g}')
        elif prior is None and previous is not None:
            reference = references.get(reference_key(row))
            if reference is not None and row['price'] < reference:
                weekday = starts(row).strftime('%A')
                changes.append(f'NEW LOWER PRICE | {row["dateid"]} {row["starttime"]} | {row["sessiontype"]} | {row["direction"]} | {uid} | price {row["price"]:g} | {weekday} {row["starttime"]} reference {reference:g} -> {row["price"]:g} ({reference-row["price"]:g} lower)')
        baseline[uid] = row
    # With multiple prices for an exact slot, use its lowest stored future
    # price, including temporarily missing IDs. Absent slots retain references.
    references.update(reference_prices(baseline))
    revision = previous['revision'] if previous else 0
    report = previous['report'] if previous else 'DSRT — Published Session Pricing\nInitial price baseline stored. Waiting for actual price changes.\n'
    if changes:
        revision += 1
        report = '\n'.join(['DSRT — Published Session Pricing', f'Price change #{revision} | observed {now.isoformat()}',
                            f'Calendar coverage: {months[0]} through {months[-1]}',
                            *(['Coverage limit: final queried month is populated; farther sessions may exist.'] if horizon_limited else []),
                            *changes])+'\n'
    current = {'captured_at': now.isoformat(), 'month': now.strftime('%Y-%m'),
               'months': months, 'horizon_limited': horizon_limited,
               'reference_prices': references,
               'sessions': baseline, 'revision': revision, 'report': report}
    # One atomic file couples the updated prices and alert payload. No-change
    # checks keep the payload identical, including after a service restart.
    tmp = state/'latest.tmp'
    tmp.write_text(json.dumps(current, indent=2, allow_nan=False)+'\n')
    tmp.replace(path)
    return report

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/report', '/lovemachine/report'):
            self.send_error(404)
            return
        try:
            if self.path == '/lovemachine/report':
                import lovemachine
                body = lovemachine.collect(state=STATE/'lovemachine').encode()
            else:
                body = collect().encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_error(502, str(exc))

if __name__ == '__main__':
    HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
