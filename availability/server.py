"""Internal CD feed: multi-month availability and one cached report per 19:00 slot."""
from random import uniform
from time import sleep
import datetime as dt
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Los_Angeles')
STATE = Path(os.environ.get('STATE_DIR', '/state'))
FIELDS = ('_id', 'dateid', 'starttime', 'sessiontype', 'direction', 'waveClass',
          'sessionlimit', 'available', 'effectiveMax', 'effectiveAvailable',
          'incart', 'blocked', 'bookingMode', 'bayOffering', 'segmentSpan')

def month_at(now, offset):
    n = now.year * 12 + now.month - 1 + offset
    return f'{n // 12:04d}-{n % 12 + 1:02d}'

def fetch_month(month):
    url = f'https://ep.dsrtsurf.com/api/sessions/with/{month}?upcoming=true'
    with urllib.request.urlopen(url, timeout=12) as response:
        rows = json.load(response)
    if not isinstance(rows, list):
        raise ValueError(f'{month}: expected session array')
    return rows

def starts(row):
    return dt.datetime.fromisoformat(row['dateid'] + 'T' + row['starttime']).replace(tzinfo=TZ)

def normalize(months, now):
    sessions = {}
    for rows in months.values():
        for raw in rows:
            if not isinstance(raw, dict) or not all(isinstance(raw.get(k), str) and raw[k] for k in ('_id','dateid','starttime','sessiontype','waveClass')):
                raise ValueError('Invalid session identity/schema')
            # Missing/null audience is an unclassified offering, not evidence
            # that it is public. Exclude it before validating public inventory.
            audience = raw.get('audience')
            if audience is not None and (not isinstance(audience, str) or not audience):
                raise ValueError('Invalid session audience')
            if audience != 'public' or raw.get('privateSession'):
                continue
            row = {k: raw.get(k) for k in FIELDS}
            if starts(row) <= now:
                continue
            for key in ('sessionlimit', 'available', 'incart'):
                if type(row[key]) not in (int, float) or row[key] < 0:
                    raise ValueError(f'Invalid {key} for {row["_id"]}')
            for key in ('effectiveMax', 'effectiveAvailable'):
                if row[key] is not None and (type(row[key]) not in (int,float) or row[key] < 0):
                    raise ValueError(f'Invalid {key}')
            if row['_id'] in sessions and sessions[row['_id']] != row:
                raise ValueError(f'Conflicting duplicate {row["_id"]}; retry later')
            sessions[row['_id']] = row
    if not sessions:
        raise ValueError('No upcoming public sessions; preserve baseline pending verification')
    return sessions

def label(row):
    return f'{row["dateid"]} {row["starttime"]} | {row["sessiontype"]} | {row["direction"]} | {row["_id"]}'

def available(row):
    return row['effectiveAvailable'] if row['effectiveAvailable'] is not None else row['available']

def clean(a, b):
    # Reef only for inference: bay offerings can share the same inventory.
    return all(r['waveClass']=='reef' and not r['blocked'] and r['bookingMode']=='bookable'
               and r['incart']==0 and r['available']<=r['sessionlimit']
               and r['effectiveAvailable'] in (None,r['available'])
               and r['effectiveMax'] in (None,r['sessionlimit']) for r in (a,b)) and all(a[k]==b[k] for k in
        ('dateid','starttime','sessiontype','direction','sessionlimit','effectiveMax','waveClass','bayOffering','segmentSpan')) and ((a['effectiveAvailable'] is None)==(b['effectiveAvailable'] is None))

def inventory_changed(previous, current, now):
    # Compare normalized session data, excluding the natural passage of time.
    # Retain an expired ID if it has been rescheduled into the future.
    old = {key: row for key, row in previous['sessions'].items()
           if starts(row) > now or key in current['sessions']}
    return old != current['sessions']

def report(previous, current, now):
    rows = current['sessions']
    lines = ['DSRT — Daily upcoming availability', f'Observed: {current["captured_at"]}',
        f'Queried months: {min(current["months"])} through {max(current["months"])}',
        f'Upcoming public sessions: {len(rows)}; dates {min(r["dateid"] for r in rows.values())} through {max(r["dateid"] for r in rows.values())}',
        'Counts are net availability changes, not confirmed bookings. Cart/capacity/status changes and shared bay inventory are excluded from inferred totals.']
    if current.get('horizon_limited'):
        lines.append('Coverage limit: final queried month is populated; farther inventory may exist.')
    if previous:
        old = previous['sessions']
        lines.append(f'Compared with: {previous["captured_at"]}')
        changes=[]; decreases=increases=expired=0
        for key in sorted(set(old)|set(rows)):
            a,b=old.get(key),rows.get(key)
            if a and starts(a)<=now and b is None:
                expired+=1
                continue
            if a is None:
                changes.append('NEW | '+label(b)+f' | available {available(b)} (not counted as new bookings)')
            elif b is None:
                changes.append('REMOVED/MISSING | '+label(a)+' (not counted as bookings)')
            elif a!=b:
                delta=available(b)-available(a)
                if clean(a,b):
                    decreases+=max(0,-delta); increases+=max(0,delta)
                    tag='POSSIBLE NET BOOKINGS' if delta<0 else 'AVAILABILITY INCREASE' if delta>0 else 'DETAIL CHANGE'
                else:
                    tag='CHANGE — EXCLUDED FROM BOOKING TOTALS'
                details=', '.join(f'{k}: {a[k]} -> {b[k]}' for k in FIELDS if a[k]!=b[k])
                status=' | NOW SOLD OUT' if clean(a,b) and available(a)>0 and available(b)==0 else ' | REOPENED' if clean(a,b) and available(a)==0 and available(b)>0 else ''
                changes.append(f'{tag} | {label(b)} | availability {available(a)} -> {available(b)} ({delta:+g}){status} | {details}')
        lines += [f'Possible net booked spots: {decreases}; released spots: {increases}; expired sessions: {expired}.',
                  'Expired sessions are not counted as bookings; bookings and cancellations between snapshots can offset each other.', '', 'CHANGES'] + (changes or ['No upcoming availability changes.'])
    else:
        lines.append('Initial baseline. Changes will appear after the next daily collection.')
    lines += ['', 'UPCOMING INVENTORY']
    for row in sorted(rows.values(),key=lambda r:(r['dateid'],r['starttime'],str(r['direction']),r['_id'])):
        lines.append(label(row)+f' | available={available(row)} capacity={row["effectiveMax"] if row["effectiveMax"] is not None else row["sessionlimit"]} cart={row["incart"]} blocked={row["blocked"]} mode={row["bookingMode"]}')
    return '\n'.join(lines)+'\n'

def collect(now=None, fetch=fetch_month, state=STATE):
    now=now or dt.datetime.now(TZ)
    slot=(now-dt.timedelta(hours=19)).date().isoformat()
    state.mkdir(parents=True,exist_ok=True)
    path=state/'latest.json'
    previous=json.loads(path.read_text()) if path.exists() else None
    months=[month_at(now,i) for i in range(3)]
    if previous and previous['slot']==slot and list(previous['months'])==months:
        return previous['report']
    data={}
    for index, month in enumerate(months):
        if index:
            sleep(uniform(2,4))
        data[month]=fetch(month)
        if not isinstance(data[month],list):
            raise ValueError(f'{month}: expected session array; preserve baseline')
    current={'slot':slot,'captured_at':now.isoformat(),'months':data,
             'sessions':normalize(data,now),'horizon_limited':bool(data[months[-1]])}
    current['daily_report']=report(previous,current,now)
    # CD sees the last actual change report. Advancing dates, expiration totals,
    # and clearing yesterday's CHANGES must not create a notification.
    current['report']=(current['daily_report'] if previous is None or
                       inventory_changed(previous,current,now) else previous['report'])
    payload=json.dumps(current,indent=2)+'\n'
    # Failure before this point leaves the last valid baseline intact.
    (state/(now.strftime('%Y-%m-%dT%H%M%S%z')+'.json')).write_text(payload)
    tmp=state/'latest.tmp'; tmp.write_text(payload); tmp.replace(path)
    return current['report']

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!='/report':
            self.send_error(404); return
        try:
            body=collect().encode()
            self.send_response(200)
            self.send_header('Content-Type','text/plain; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers(); self.wfile.write(body)
        except Exception as exc:
            self.send_error(502,str(exc))

if __name__=='__main__':
    HTTPServer(('0.0.0.0',8080),Handler).serve_forever()
