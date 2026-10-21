"""Disposable, offline tests for legacy jq and persistent pricing/inventory feeds."""
import copy
import sys
sys.path.insert(0, "/app")
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import requests
import jq
import arrow
from unittest.mock import patch
from changedetectionio.jinja2_custom import render
from apprise import Apprise

ROOT = Path('/work')
BASE = 'http://127.0.0.1:5000/api/v1'
url_template = "https://ep.dsrtsurf.com/api/sessions/with/{% now 'America/Los_Angeles', '%Y-%m' %}?upcoming=true"
for instant, month in [('2026-10-31T23:59:59-07:00', '2026-10'), ('2026-11-01T00:00:00-07:00', '2026-11'), ('2027-01-01T00:00:00-08:00', '2027-01')]:
    with patch('arrow.now', return_value=arrow.get(instant)):
        assert render(url_template) == f'https://ep.dsrtsurf.com/api/sessions/with/{month}?upcoming=true'
print('PASS date templates: month and year rollover', flush=True)
for notification_url in ['ntfy://your-unguessable-topic', 'ntfys://ntfy.example.com/your-topic']:
    assert Apprise().add(notification_url)
print('PASS ntfy URL parsing (no delivery attempted)', flush=True)
for _ in range(60):
    try:
        state = json.loads(Path('/datastore/changedetection.json').read_text())
        client = requests.Session()
        client.headers['x-api-key'] = state['settings']['application']['api_access_token']
        if client.get(BASE + '/watch', timeout=2).ok:
            break
    except (OSError, ValueError, requests.RequestException):
        pass
    time.sleep(1)
else:
    raise RuntimeError('changedetection startup timed out')

def api(method, path, **kwargs):
    response = client.request(method, BASE + path, timeout=10, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else None

# Only disposable default watches are removed.
for uid in api('GET', '/watch'):
    api('DELETE', '/watch/' + uid)
fixture = json.loads((ROOT / 'tests/fixtures/sessions.json').read_text())
body, status = json.dumps(fixture).encode(), 200
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
server = HTTPServer(('127.0.0.1', 8088), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
expression = ' '.join(line for line in (ROOT / 'filters/sessions.jq').read_text().splitlines() if not line.startswith('#'))
watch = json.loads((ROOT / 'config/watch.json').read_text())
watch.update(url='http://127.0.0.1:8088/sessions', include_filters=['jq:' + expression], paused=False)
uid = api('POST', '/watch', json=watch)['uuid']
path = '/watch/' + uid
api('GET', path + '?recheck=true')

def fetch(data, expected, name, code=200):
    global body, status
    before = api('GET', path)
    previous_history = api('GET', path + '/history')
    # Snapshot keys and last_checked use whole seconds.
    time.sleep(1.1)
    body = data if isinstance(data, bytes) else json.dumps(data).encode()
    status = code
    api('GET', path + '?recheck=true')
    for _ in range(600):
        after = api('GET', path)
        if after['check_count'] > before['check_count']:
            break
        time.sleep(.2)
    else:
        raise AssertionError(name + ': check timed out')
    history = api('GET', path + '/history')
    if expected == 'error':
        assert after['last_error'], (name, after)
        assert history == previous_history, (name, 'error overwrote baseline')
    else:
        assert not after['last_error'], (name, after['last_error'])
        assert len(history) == len(previous_history) + (expected == 'change'), (name, history, previous_history)
    assert after['notification_alert_count'] == 0, name
    print('PASS integration:', name, flush=True)

for _ in range(600):
    initial = api('GET', path)
    if initial['history_n'] == 1:
        break
    time.sleep(.2)
else:
    raise AssertionError(('initial baseline failed', initial))
print('PASS integration: initial baseline', flush=True)
fetch(fixture, 'same', 'unchanged repeat')
for name, expression, expected in [
    ('availability', 'map(.available=0 | .effectiveAvailable=0 | .incart=9)', 'same'),
    ('capacity', 'map(.sessionlimit=99 | .effectiveMax=99)', 'same'),
    ('direction availability', '.[1].available=0', 'same'),
    ('ordering', 'reverse', 'same'),
    ('session expires but tier remains', 'del(.[3])', 'same'),
    ('blocked sold-out retained', 'map(.blocked=true | .available=0)', 'same'),
    ('fallback numeric formatting', 'map(del(.currentPrice))', 'same'),
    ('private excluded', '. + [.[0] | .privateSession=true | .currentPrice=12500]', 'same'),
    ('weekday decrease', '.[2].currentPrice-=10', 'change'),
    ('weekend decrease', '.[0].currentPrice-=10', 'change'),
    ('increase', '.[0].currentPrice+=10', 'change'),
    ('new discounted tier', '. + [.[0] | .currentPrice-=20]', 'change'),
    ('rename', 'map(.sessiontype="Renamed")', 'change'),
    ('new type', '. + [.[0] | .sessiontype="New type"]', 'change'),
    ('different direction price', '.[1].currentPrice+=15', 'change'),
    ('last tier expires', 'del(.[2:4])', 'change'),
]:
    data = jq.compile(expression).input_value(copy.deepcopy(fixture)).first()
    fetch(data, expected, name)
    if expected == 'change':
        fetch(fixture, 'change', name + ' restore')
for name, data, code in [
    ('invalid JSON', b'{invalid', 200),
    ('empty response', [], 200),
    ('wrong shape', {}, 200),
    ('invalid effective price', jq.compile('map(.currentPrice="bad")').input_value(fixture).first(), 200),
    ('API unavailable 503', b'service unavailable', 503),
]:
    fetch(data, 'error', name, code)
fetch(fixture, 'same', 'recovery preserves baseline')
# Connection refusal as well as HTTP errors must preserve history.
api('PUT', path, json={'url':'http://127.0.0.1:8089/unavailable'})
fetch(fixture, 'error', 'connection refused')
api('PUT', path, json={'url':'http://127.0.0.1:8088/sessions'})
fetch(fixture, 'same', 'connection recovery')
print('All HTTP/jq/history integration tests passed; notifications stayed muted.', flush=True)

# Exercise the actual comparator through CD's HTTP fetcher and history engine.
import datetime as dt
import importlib.util
import tempfile
spec = importlib.util.spec_from_file_location('pricing', ROOT/'pricing/server.py')
pricing = importlib.util.module_from_spec(spec); spec.loader.exec_module(pricing)
pricing.sleep = lambda seconds: None
price_rows = copy.deepcopy(fixture)
price_now = dt.datetime(2026,10,10,12,tzinfo=pricing.TZ)
price_tmp = tempfile.TemporaryDirectory()
class PricingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if price_rows == 'network error':
                raise OSError('upstream unavailable')
            result = pricing.collect(price_now, lambda month: price_rows, Path(price_tmp.name))
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers(); self.wfile.write(result.encode())
        except Exception as exc:
            self.send_error(502, str(exc))
    def log_message(self, *args):
        pass
price_server = HTTPServer(('127.0.0.1',8090), PricingHandler)
threading.Thread(target=price_server.serve_forever, daemon=True).start()
watch = json.loads((ROOT/'config/watch.json').read_text())
watch.update(url='http://127.0.0.1:8090/report', include_filters=[], notification_muted=True)
uid = api('POST','/watch',json=watch)['uuid']; path='/watch/'+uid
api('GET',path+'?recheck=true')
for _ in range(600):
    initial=api('GET',path)
    if initial['history_n']==1:
        break
    time.sleep(.2)
else:
    raise AssertionError(('price feed baseline failed', initial))
print('PASS pricing feed: durable initial baseline', flush=True)
def price_check(rows, expected, name):
    global price_rows
    price_rows = copy.deepcopy(rows)
    fetch({}, expected, 'pricing feed: '+name)
price_check(fixture[:2], 'same', 'last weekday group removed')
price_check(fixture, 'same', 'missing sessions restored')
new = copy.deepcopy(fixture[0]); new.update(_id='new-session',dateid='2026-10-26',currentPrice=99)
price_check(fixture+[new], 'change', 'new day at lower price with existing days unchanged')
latest = max(api('GET',path+'/history'), key=int)
snapshot = client.get(BASE+path+'/history/'+latest).text
assert 'NEW LOWER PRICE | 2026-10-26' in snapshot and 'price 99' in snapshot, snapshot
price_check(fixture+[new], 'same', 'new day does not repeat alert')
price_check(fixture, 'same', 'new day temporarily disappears')
price_check(fixture+[new], 'same', 'new day returns without duplicate alert')
standard = copy.deepcopy(new); standard.update(_id='new-standard-session',currentPrice=220)
price_check(fixture+[new,standard], 'same', 'normal-priced new session stays silent')
changed = copy.deepcopy(fixture); changed[0]['currentPrice']=200
price_check(changed, 'change', 'real decrease 220 to 200')
price_check(changed, 'same', 'unchanged after decrease')
price_check(changed[:2], 'same', 'removal after decrease')
# Reloading the module emulates a process restart; durable prices/report survive.
pricing = importlib.util.module_from_spec(spec); spec.loader.exec_module(pricing)
pricing.sleep = lambda seconds: None
price_check(changed, 'same', 'restart preserves payload')
changed[0]['currentPrice']=210
price_check(changed, 'change', 'increase uses updated 200 baseline')
price_check([], 'error', 'empty calendar fails closed')
price_check('network error', 'error', 'upstream failure fails closed')
price_check(changed, 'same', 'recovery preserves latest report')
price_now=dt.datetime(2026,11,1,tzinfo=pricing.TZ)
next_month=copy.deepcopy(fixture[:1]); next_month[0].update(_id='november',dateid='2026-11-02')
price_check(next_month,'same','normal-priced new sessions at month rollover stay silent')
price_check(next_month,'same','unchanged month after rollover')
price_server.shutdown(); price_tmp.cleanup()
print('All persistent pricing HTTP/history tests passed; notifications stayed muted.',flush=True)

# Use the production HTTP handler with a mocked Shopify upstream. Inventory
# and CD datastore are both disposable; alert delivery remains muted.
sys.path.insert(0, str(ROOT/'pricing'))
import lovemachine as inventory
inventory_rows = json.loads((ROOT/'tests/fixtures/lovemachine-products.json').read_text())
inventory_original_collect = inventory.collect
inventory_tmp = tempfile.TemporaryDirectory()
pricing.STATE = Path(inventory_tmp.name)
def inventory_fetch(page):
    if inventory_rows == 'network error':
        raise OSError('upstream unavailable')
    return inventory_rows
inventory.collect = lambda state: inventory_original_collect(fetch=inventory_fetch, state=state)
inventory_server = HTTPServer(('127.0.0.1',8091), pricing.Handler)
threading.Thread(target=inventory_server.serve_forever, daemon=True).start()
watch = json.loads((ROOT/'config/lovemachine.json').read_text())
watch.update(url='http://127.0.0.1:8091/lovemachine/report', notification_muted=True)
uid = api('POST','/watch',json=watch)['uuid']; path='/watch/'+uid
api('GET',path+'?recheck=true')
for _ in range(600):
    initial=api('GET',path)
    if initial['history_n']==1:
        break
    time.sleep(.2)
else:
    raise AssertionError(('inventory feed baseline failed', initial))
print('PASS inventory feed: production route and initial baseline',flush=True)
def inventory_check(rows, expected, name):
    global inventory_rows
    inventory_rows = copy.deepcopy(rows)
    fetch({}, expected, 'inventory feed: '+name)
boards = copy.deepcopy(inventory_rows)
restock = copy.deepcopy(boards); restock['products'][1]['variants'][0]['available'] = True
inventory_check(restock, 'change', '6-6 restock')
inventory_check(restock, 'same', 'unchanged availability')
inventory_check(boards, 'same', 'sellout suppressed')
inventory_check(restock, 'change', 'second restock')
new_boards = copy.deepcopy(restock)
for index in (1, 2):
    new = copy.deepcopy(boards['products'][index]); new['id'] += 1
    new['variants'][0].update(id=new['variants'][0]['id']+1, available=True)
    new_boards['products'].append(new)
inventory_check(new_boards, 'change', 'new 6-4 and 6-6 listings')
metadata = copy.deepcopy(new_boards)
metadata['products'].reverse()
for product in metadata['products']:
    product['variants'][0]['price'] = '999.00'
    product['body_html'] = 'edited'
    if "7'0" in product['title']:
        product['variants'][0]['available'] = True
inventory_check(metadata, 'same', 'prices ordering descriptions unrelated inventory')
inventory_check({'products': []}, 'error', 'empty collection fails closed')
inventory_check({'products': [{}]}, 'error', 'malformed schema fails closed')
inventory_check('network error', 'error', 'request failure fails closed')
inventory_check(metadata, 'same', 'recovery does not alert')
inventory_server.shutdown(); inventory_tmp.cleanup()
print('All inventory HTTP/history tests passed; notifications stayed muted.',flush=True)

# Exercise Daydream through its production HTTP route and CD history.
inventory.collect = inventory_original_collect
import daydream
daydream_original_collect = daydream.collect
inventory_rows = json.loads((ROOT/'tests/fixtures/daydream-products.json').read_text())
inventory_tmp = tempfile.TemporaryDirectory()
pricing.STATE = Path(inventory_tmp.name)
daydream.collect = lambda state: daydream_original_collect(fetch=inventory_fetch, state=state)
inventory_server = HTTPServer(('127.0.0.1',8092), pricing.Handler)
threading.Thread(target=inventory_server.serve_forever, daemon=True).start()
watch = json.loads((ROOT/'config/daydream.json').read_text())
watch.update(url='http://127.0.0.1:8092/daydream/report', notification_muted=True)
uid = api('POST','/watch',json=watch)['uuid']; path='/watch/'+uid
api('GET',path+'?recheck=true')
for _ in range(600):
    initial=api('GET',path)
    if initial['history_n']==1:
        break
    time.sleep(.2)
else:
    raise AssertionError(('Daydream baseline failed', initial))
boards = copy.deepcopy(inventory_rows)
restock = copy.deepcopy(boards)
linked = next(r for r in restock['products'] if r['handle'] == '6-6-lovemachine-fm')
linked['variants'][0]['available'] = True
inventory_check(restock, 'change', 'Daydream linked 6-6 restock')
inventory_check(restock, 'same', 'Daydream unchanged stock')
inventory_check(boards, 'same', 'Daydream silent sellout')
inventory_check('network error', 'error', 'Daydream upstream failure')
inventory_check(boards, 'same', 'Daydream recovery')
inventory_server.shutdown(); inventory_tmp.cleanup()
print('All Daydream HTTP/history tests passed; notifications stayed muted.',flush=True)
