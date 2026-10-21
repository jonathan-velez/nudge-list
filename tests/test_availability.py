import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('availability',Path(__file__).parents[1]/'availability/server.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
NOW=dt.datetime(2026,10,11,22,tzinfo=m.TZ)
RAW={'_id':'a','dateid':'2026-10-20','starttime':'10:00','sessiontype':'Turns','direction':'Left','waveClass':'reef','audience':'public','sessionlimit':10,'available':8,'effectiveMax':10,'effectiveAvailable':8,'incart':0,'blocked':False,'bookingMode':'bookable'}

def snapshot(raw):
    return {'captured_at':NOW.isoformat(),'months':{'2026-10':[raw]},'sessions':m.normalize({'2026-10':[raw]},NOW)}

class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        pause = patch.object(m,"sleep")
        pause.start()
        self.addCleanup(pause.stop)
    def test_three_month_limit_sequential_pauses_and_cached_repeat(self):
        now=dt.datetime(2026,12,15,22,tzinfo=m.TZ)
        row=dict(RAW,dateid='2027-01-20')
        events=[]
        def fetch(month):
            events.append(('fetch',month))
            return [row]
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(m,'sleep',side_effect=lambda seconds: events.append(('pause',seconds))), \
             patch.object(m,'uniform',side_effect=[2,4]) as delay:
            state=Path(folder)
            report=m.collect(now,fetch,state)
            self.assertEqual(events,[('fetch','2026-12'),('pause',2),('fetch','2027-01'),
                                     ('pause',4),('fetch','2027-02')])
            self.assertEqual(delay.call_count,2)
            delay.assert_called_with(2,4)
            self.assertEqual(report,m.collect(now+dt.timedelta(minutes=5),fetch,state))
            self.assertEqual(len(events),5)
            self.assertEqual(list(json.loads((state/'latest.json').read_text())['months']),
                             ['2026-12','2027-01','2027-02'])

    def test_cached_old_horizon_refreshes_without_new_alert_and_failure_preserves_state(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)
            m.collect(NOW,lambda month:[RAW],state)
            path=state/'latest.json'; old=json.loads(path.read_text())
            old['months']['2027-01']=[]
            path.write_text(json.dumps(old))
            calls=[]
            def fetch(month):
                calls.append(month)
                return [RAW]
            self.assertEqual(old['report'],m.collect(NOW,fetch,state))
            self.assertEqual(calls,['2026-10','2026-11','2026-12'])
            saved=path.read_bytes()
            def invalid(month):
                return {} if month=='2026-12' else [RAW]
            with self.assertRaises(ValueError):
                m.collect(NOW+dt.timedelta(days=1),invalid,state)
            self.assertEqual(path.read_bytes(),saved)

    def test_decrease_and_capacity_exclusion(self):
        old=snapshot(RAW); changed=dict(RAW,available=5,effectiveAvailable=5)
        self.assertIn('Possible net booked spots: 3',m.report(old,snapshot(changed),NOW))
        changed.update(sessionlimit=12,effectiveMax=12)
        self.assertIn('Possible net booked spots: 0',m.report(old,snapshot(changed),NOW))
    def test_cart_bay_exclusions(self):
        for extra in ({'incart':1},{'waveClass':'bay'},{'blocked':True}):
            changed=dict(RAW,available=5,effectiveAvailable=5,**extra)
            self.assertIn('Possible net booked spots: 0',m.report(snapshot(RAW),snapshot(changed),NOW))
    def test_overlap_conflict(self):
        self.assertEqual(1,len(m.normalize({'a':[RAW],'b':[RAW]},NOW)))
        with self.assertRaises(ValueError):
            m.normalize({'a':[RAW],'b':[dict(RAW,available=7)]},NOW)
    def test_expiration_not_booking(self):
        old=snapshot(RAW); new=snapshot(dict(RAW,_id='b',dateid='2026-10-22'))
        text=m.report(old,new,dt.datetime(2026,10,21,22,tzinfo=m.TZ))
        self.assertIn('expired sessions: 1',text)
        self.assertNotIn('REMOVED/MISSING',text)
        self.assertIn('Possible net booked spots: 0',text)
    def test_collection_cache_gaps_and_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder); calls=[]
            def fetch(month):
                calls.append(month)
                return [RAW] if month=='2026-10' else []
            body=m.collect(NOW,fetch,state)
            self.assertEqual(3,len(calls))
            self.assertEqual(calls,['2026-10','2026-11','2026-12'])
            self.assertEqual(body,m.collect(NOW+dt.timedelta(minutes=5),fetch,state))
            self.assertEqual(3,len(calls))
            prior=(state/'latest.json').read_bytes()
            def fail(month): raise ValueError('upstream failure')
            with self.assertRaises(ValueError): m.collect(NOW+dt.timedelta(days=1),fail,state)
            self.assertEqual(prior,(state/'latest.json').read_bytes())
    def test_malformed_empty_preserves_baseline(self):
        with self.assertRaises(ValueError): m.normalize({'a':[]},NOW)
        with self.assertRaises(ValueError): m.normalize({'a':[dict(RAW,available=None)]},NOW)

    def test_unclassified_offerings_excluded_and_failure_preserves_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)
            baseline=m.collect(NOW,lambda month:[RAW],state)
            path=state/'latest.json'
            for audience in ('missing',None):
                row=dict(RAW,_id='air-camp',sessiontype='Air Camp',available=1)
                row.pop('incart')  # Observed unclassified offerings may lack this too.
                if audience=='missing': row.pop('audience')
                else: row['audience']=audience
                now=NOW+dt.timedelta(days=1)
                self.assertEqual(m.collect(now,lambda month:[RAW,row],state),baseline)
                self.assertNotIn('air-camp',json.loads(path.read_text())['sessions'])
                saved=path.read_bytes()
                with self.assertRaises(ValueError):
                    m.collect(now+dt.timedelta(days=1),lambda month:[row],state)
                self.assertEqual(path.read_bytes(),saved)
            for audience in ('',False,123):
                with self.assertRaises(ValueError):
                    m.collect(now+dt.timedelta(days=1),lambda month:[RAW,dict(RAW,audience=audience)],state)
                self.assertEqual(path.read_bytes(),saved)

    def test_stable_alert_payload_and_daily_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder); rows=[dict(RAW)]
            def fetch(month): return rows if month=='2026-10' else []
            baseline=m.collect(NOW,fetch,state)
            self.assertEqual(baseline,m.collect(NOW+dt.timedelta(days=1),fetch,state))
            saved=json.loads((state/'latest.json').read_text())
            self.assertIn('No upcoming availability changes.',saved['daily_report'])
            self.assertNotEqual(saved['daily_report'],saved['report'])
            rows[0].update(available=5,effectiveAvailable=5)
            changed=m.collect(NOW+dt.timedelta(days=2),fetch,state)
            self.assertIn('Possible net booked spots: 3',changed)
            self.assertNotEqual(baseline,changed)
            # Restart has no in-memory dependency; next day's empty diff stays silent.
            self.assertEqual(changed,m.collect(NOW+dt.timedelta(days=3),fetch,state))
            rows[0].update(available=2,effectiveAvailable=2)
            again=m.collect(NOW+dt.timedelta(days=4),fetch,state)
            self.assertNotEqual(changed,again)
            self.assertIn('availability 5 -> 2',again)

    def test_expiration_only_and_order_are_silent(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)
            rows=[dict(RAW),dict(RAW,_id='b',dateid='2026-11-02')]
            def fetch(month): return rows if month=='2026-10' else []
            baseline=m.collect(NOW,fetch,state)
            rows.reverse()
            self.assertEqual(baseline,m.collect(NOW+dt.timedelta(days=1),fetch,state))
            self.assertEqual(baseline,m.collect(NOW+dt.timedelta(days=10),fetch,state))
            saved=json.loads((state/'latest.json').read_text())
            self.assertEqual(['b'],list(saved['sessions']))
            self.assertIn('expired sessions: 1',saved['daily_report'])

    def test_inventory_fields_still_alert(self):
        old=snapshot(RAW)
        for extra in ({'available':7,'effectiveAvailable':7},{'incart':1},
                      {'blocked':True},{'sessionlimit':12,'effectiveMax':12},
                      {'bookingMode':'closed'},{'starttime':'11:00'},
                      {'_id':'new'}):
            self.assertTrue(m.inventory_changed(old,snapshot(dict(RAW,**extra)),NOW),extra)

    def test_migration_preserves_existing_report(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder); previous=snapshot(RAW)
            previous.update(slot='2026-10-10',report='Existing CD baseline\n')
            (state/'latest.json').write_text(json.dumps(previous))
            self.assertEqual(previous['report'],m.collect(NOW,lambda month:[RAW] if month=='2026-10' else [],state))

if __name__=='__main__': unittest.main()
