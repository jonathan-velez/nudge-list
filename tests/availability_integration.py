"""Offline availability feed checks through the real CD history engine."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from http.server import HTTPServer
import requests

ROOT = Path('/work')
spec = importlib.util.spec_from_file_location('availability', ROOT/'availability/server.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
now = dt.datetime(2026,10,11,22,tzinfo=m.TZ)
rows = [{'_id':'a','dateid':'2026-10-20','starttime':'10:00','sessiontype':'Turns',
         'direction':'Left','waveClass':'reef','audience':'public','sessionlimit':10,
         'available':8,'effectiveMax':10,'effectiveAvailable':8,'incart':0,
         'blocked':False,'bookingMode':'bookable'},
        {'_id':'b','dateid':'2026-11-02','starttime':'10:00','sessiontype':'Turns',
         'direction':'Left','waveClass':'reef','audience':'public','sessionlimit':10,
         'available':8,'effectiveMax':10,'effectiveAvailable':8,'incart':0,
         'blocked':False,'bookingMode':'bookable'}]
state = tempfile.TemporaryDirectory()
original_collect = m.collect
failed = False
def upstream(month):
    if failed: raise OSError('simulated upstream failure')
    return rows if month=='2026-10' else []
m.collect = lambda: original_collect(now, upstream, Path(state.name))
server = HTTPServer(('127.0.0.1',8092),m.Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
base='http://127.0.0.1:5000/api/v1'
client=requests.Session()
for _ in range(60):
    try:
        settings=json.loads(Path('/datastore/changedetection.json').read_text())
        client.headers['x-api-key']=settings['settings']['application']['api_access_token']
        if client.get(base+'/watch',timeout=2).ok: break
    except (OSError,ValueError,requests.RequestException): pass
    time.sleep(1)
else: raise RuntimeError('CD startup timed out')
def api(method,path,**kwargs):
    response=client.request(method,base+path,timeout=10,**kwargs)
    response.raise_for_status()
    return response.json() if response.content else None
watch=json.loads((ROOT/'config/availability.json').read_text())
watch.update(url='http://127.0.0.1:8092/report',notification_muted=True,
             notification_urls=[],time_schedule_limit={'enabled':False})
uid=api('POST','/watch',json=watch)['uuid']; path='/watch/'+uid

def check(expected,name):
    before=api('GET',path); history=api('GET',path+'/history')
    time.sleep(1.1)
    api('GET',path+'?recheck=true')
    for _ in range(300):
        after=api('GET',path)
        if after['check_count']>before['check_count']: break
        time.sleep(.2)
    else: raise AssertionError(name+': timed out')
    saved=api('GET',path+'/history')
    assert after['notification_alert_count']==0,name
    if expected=='error':
        assert after['last_error'] and saved==history,name
    else:
        assert not after['last_error'],(name,after['last_error'])
        assert len(saved)==len(history)+(expected=='change'),(name,saved,history)
    print('PASS availability HTTP/history:',name,flush=True)
# CD may enqueue a newly created watch immediately.
api('GET',path+'?recheck=true')
for _ in range(300):
    if api('GET',path)['history_n']==1: break
    time.sleep(.2)
else: raise AssertionError('initial baseline missing')
check('same','same cached collection')
now+=dt.timedelta(days=1); check('same','fresh day without inventory changes')
rows[0].update(available=5,effectiveAvailable=5)
now+=dt.timedelta(days=1); check('change','three spots decrease')
now+=dt.timedelta(days=1); check('same','next day does not clear prior alert')
# Module reload exercises durable payload across restarts.
spec.loader.exec_module(m)
m.collect=lambda: original_collect(now,upstream,Path(state.name))
now+=dt.timedelta(days=1); check('same','restart retains last actual change')
rows[0].update(available=2,effectiveAvailable=2)
now+=dt.timedelta(days=1); check('change','another three spots decrease')
now+=dt.timedelta(days=6); check('same','expiration only')
rows[1]['blocked']=True
now+=dt.timedelta(days=1); check('change','status change still detected')
now+=dt.timedelta(days=1); failed=True; check('error','failure preserves baseline')
failed=False; check('same','recovery remains silent')
server.shutdown(); state.cleanup()
print('All availability tests passed; production untouched and delivery muted.',flush=True)
