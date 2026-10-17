"""Offline price-baseline regression tests; production state is never touched."""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pricing', Path(__file__).resolve().parents[1]/'pricing/server.py')
pricing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pricing)

class PricingTests(unittest.TestCase):
    def setUp(self):
        pause = patch.object(pricing, "sleep")
        pause.start()
        self.addCleanup(pause.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.now = dt.datetime(2026, 10, 10, 12, tzinfo=pricing.TZ)
        self.rows = json.loads((Path(__file__).parent/'fixtures/sessions.json').read_text())
        self.base = self.collect()

    def collect(self, rows=None, now=None):
        return pricing.collect(now=now or self.now, fetch=lambda month: copy.deepcopy(self.rows if rows is None else rows), state=self.state)

    def test_expiry_and_removal_are_silent(self):
        self.assertEqual(self.collect(self.rows[:2]), self.base)
        self.assertEqual(self.collect(), self.base)

    def test_new_day_lower_price_alerts_without_existing_price_edits(self):
        new = copy.deepcopy(self.rows[0])
        new.update(_id='new-day', dateid='2026-10-26', currentPrice=99)
        rows = self.rows + [new]
        report = self.collect(rows)
        self.assertIn('NEW LOWER PRICE | 2026-10-26', report)
        self.assertIn('price 99', report)
        self.assertIn('Monday 08:00 reference 220 -> 99', report)
        self.assertNotIn(' | price 220 -> 99', report)
        self.assertEqual(self.collect(rows[::-1]), report)
        self.assertEqual(self.collect(), report)
        self.assertEqual(self.collect(rows), report)
        reloaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(reloaded)
        reloaded.sleep = lambda seconds: None
        self.assertEqual(reloaded.collect(self.now, lambda month: rows, self.state), report)
        rows[-1]['currentPrice'] = 90
        self.assertIn('price 99 -> 90', self.collect(rows))

    def test_normal_higher_and_unknown_new_sessions_are_silent(self):
        for price in [220, 250]:
            new = copy.deepcopy(self.rows[0])
            new.update(_id=f'new-{price}', dateid='2026-10-26', currentPrice=price)
            self.assertEqual(self.collect(self.rows + [new]), self.base)
        for field, value in [('sessiontype', 'New type'), ('dateid', '2026-10-20'),
                             ('starttime', '09:00'), ('direction', 'Unknown')]:
            new = copy.deepcopy(self.rows[0])
            new.update(_id='unknown-'+field, currentPrice=99)
            new[field] = value
            self.assertEqual(self.collect(self.rows+[new]), self.base)

    def test_reference_survives_expiration_restart_and_legacy_state(self):
        path = self.state/'latest.json'
        legacy = json.loads(path.read_text())
        del legacy['reference_prices']
        path.write_text(json.dumps(legacy))
        # All original Mondays expire while a different slot keeps the calendar valid.
        now = dt.datetime(2026,10,20,12,tzinfo=pricing.TZ)
        other = copy.deepcopy(self.rows[0])
        other.update(_id='other-slot', dateid='2026-10-21', starttime='12:00')
        self.assertEqual(self.collect([other],now), self.base)
        new = copy.deepcopy(self.rows[0])
        new.update(_id='new-monday', dateid='2026-10-26', currentPrice=200)
        reloaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(reloaded)
        reloaded.sleep = lambda seconds: None
        report = reloaded.collect(now, lambda month: [other,new], self.state)
        self.assertIn('Monday 08:00 reference 220 -> 200', report)
        self.assertEqual(reloaded.collect(now, lambda month: [other,new], self.state),report)

    def test_lowest_reference_and_same_collection_order_independence(self):
        rows = copy.deepcopy(self.rows)
        rows[2]['currentPrice'] = 200
        self.collect(rows)
        new = copy.deepcopy(rows[2])
        new.update(_id='new-monday', dateid='2026-10-26', currentPrice=210)
        unchanged = self.collect(rows)
        self.assertEqual(self.collect(rows+[new]), unchanged)
        new2 = copy.deepcopy(new)
        new2.update(_id='new-cheaper-monday', dateid='2026-11-02', currentPrice=180)
        report = self.collect([new2]+rows+[new])
        self.assertIn('reference 200 -> 180', report)
        self.assertNotIn('reference 210 -> 180', report)
        self.assertEqual(report.count('NEW LOWER PRICE'),1)

    def test_user_example_advanced_turns_monday_11am(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            row.update(sessiontype='Advanced Turns', starttime='11:00', currentPrice=200)
        # A separate fresh baseline, followed by the exact requested case.
        fresh = self.state/'example'
        pricing.collect(self.now, lambda month: rows, fresh)
        new = copy.deepcopy(rows[2])
        new.update(_id='new-monday', dateid='2026-10-26', currentPrice=180)
        report = pricing.collect(self.now, lambda month: rows+[new], fresh)
        self.assertIn('Advanced Turns',report)
        self.assertIn('Monday 11:00 reference 200 -> 180 (20 lower)', report)
        new2 = copy.deepcopy(new)
        new2.update(_id='next-monday', dateid='2026-11-02')
        self.assertEqual(pricing.collect(self.now,lambda month: rows+[new,new2],fresh),report)

    def test_increase_decrease_and_updated_baseline(self):
        rows = copy.deepcopy(self.rows); rows[0]['currentPrice'] = 200
        first = self.collect(rows)
        self.assertIn('price 220 -> 200', first)
        self.assertEqual(self.collect(rows), first)
        rows[0]['currentPrice'] = 210
        second = self.collect(rows)
        self.assertIn('price 200 -> 210', second)
        self.assertIn('Price change #2', second)
        self.assertEqual(self.collect(rows), second)
        self.assertIn('price 210 -> 220', self.collect())

    def test_missing_session_reappears_with_price_change(self):
        self.collect(self.rows[1:])
        rows = copy.deepcopy(self.rows); rows[0]['currentPrice'] = 205
        self.assertIn('price 220 -> 205', self.collect(rows))

    def test_expired_session_is_not_compared(self):
        rows = copy.deepcopy(self.rows); rows[0]['currentPrice'] = 1
        self.assertEqual(self.collect(rows, self.now+dt.timedelta(days=2)), self.base)
        stored = json.loads((self.state/'latest.json').read_text())
        self.assertEqual(set(stored['sessions']), {'fixture-next-monday'})

    def test_nonprice_edits_are_silent(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            row.update(sessiontype='Renamed', direction='Right', available=0, sessionlimit=99, blocked=True)
            row['currentPrice'] = 220.0
        self.assertEqual(self.collect(rows[::-1]), self.base)
        for row in rows:
            del row['currentPrice']
        self.assertEqual(self.collect(rows), self.base)

    def test_private_and_bay_excluded(self):
        rows = copy.deepcopy(self.rows)
        for key, value in [('privateSession', True), ('waveClass', 'bay')]:
            new = copy.deepcopy(rows[0]); new.update(_id='excluded', currentPrice=999); new[key] = value
            self.assertEqual(self.collect(rows+[new]), self.base)

    def test_failures_preserve_baseline_and_recovery(self):
        path = self.state/'latest.json'
        baseline = path.read_bytes()
        invalid = [[], {}, [{'waveClass': 'reef'}]]
        for field, value in [('currentPrice', 'bad'), ('currentPrice', -1), ('currentPrice', float('nan')), ('currentPrice', True), ('dateid', '2026-02-30'), ('starttime', '8:00'), ('_id', ''), ('privateSession', 'true')]:
            rows = copy.deepcopy(self.rows); rows[0][field] = value; invalid.append(rows)
        for rows in invalid:
            with self.subTest(rows=rows):
                with self.assertRaises((ValueError, TypeError)):
                    self.collect(rows)
                self.assertEqual(path.read_bytes(), baseline)
        def unavailable(month):
            raise OSError('network unavailable')
        with self.assertRaises(OSError):
            pricing.collect(self.now, unavailable, self.state)
        self.assertEqual(path.read_bytes(), baseline)
        self.assertEqual(self.collect(), self.base)

    def test_conflicting_duplicates_fail(self):
        duplicate = copy.deepcopy(self.rows[0]); duplicate['currentPrice'] = 100
        with self.assertRaises(ValueError):
            self.collect(self.rows+[duplicate])
        self.assertEqual(self.collect(self.rows+[self.rows[0]]), self.base)

    def test_restart_reads_durable_baseline_and_payload(self):
        rows = copy.deepcopy(self.rows); rows[1]['currentPrice'] = 225
        report = self.collect(rows)
        reloaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(reloaded)
        reloaded.sleep = lambda seconds: None
        self.assertEqual(reloaded.collect(self.now, lambda month: rows, self.state), report)
        self.assertIn('price 225 -> 220', self.collect())

    def test_month_year_rollover_normal_prices_are_silent(self):
        for now in [dt.datetime(2026,11,1,tzinfo=pricing.TZ), dt.datetime(2027,1,1,tzinfo=pricing.TZ)]:
            rows = copy.deepcopy(self.rows[:1]); rows[0].update(_id=now.strftime('%Y-%m'), dateid=now.strftime('%Y-%m-02'))
            months = []
            def fetch(month):
                months.append(month); return rows
            report = pricing.collect(now, fetch, self.state)
            self.assertEqual(report, self.base)
            self.assertEqual(set(months), {pricing.month_at(now,i) for i in range(3)})
            self.assertEqual(pricing.collect(now, fetch, self.state), report)

    def test_future_month_after_empty_gap_and_overlap(self):
        new = copy.deepcopy(self.rows[0])
        new.update(_id='farther-day', dateid='2026-12-21', currentPrice=99)
        def fetch(month):
            return {'2026-10': self.rows, '2026-12': [new], '2027-01': [new]}.get(month, [])
        report = pricing.collect(self.now, fetch, self.state)
        self.assertIn('NEW LOWER PRICE | 2026-12-21', report)
        self.assertEqual(report.count('NEW LOWER PRICE'), 1)
        state = json.loads((self.state/'latest.json').read_text())
        self.assertEqual(len(state['months']), 3)
        self.assertTrue(state['horizon_limited'])

    def test_later_month_failure_and_conflicting_overlap_preserve_baseline(self):
        path = self.state/'latest.json'
        baseline = path.read_bytes()
        for failure in ['network', 'schema', 'conflict']:
            def fetch(month):
                if month != '2026-12': return self.rows
                if failure == 'network': raise OSError('upstream failed')
                if failure == 'schema': return {}
                rows = copy.deepcopy(self.rows); rows[0]['currentPrice'] = 99
                return rows
            with self.subTest(failure=failure), self.assertRaises((OSError, ValueError)):
                pricing.collect(self.now, fetch, self.state)
            self.assertEqual(path.read_bytes(), baseline)

    def test_three_months_sequential_with_random_pauses_and_no_extension(self):
        events = []
        now = dt.datetime(2026,12,1,tzinfo=pricing.TZ)
        def fetch(month):
            events.append(('fetch',month))
            return self.rows
        with patch.object(pricing,'sleep',side_effect=lambda seconds: events.append(('pause',seconds))), \
             patch.object(pricing,'uniform',side_effect=[2,4]) as random_delay:
            rows, queried, limited = pricing.fetch_calendar(now,fetch)
        self.assertEqual(queried,['2026-12','2027-01','2027-02'])
        self.assertEqual(events,[('fetch','2026-12'),('pause',2),('fetch','2027-01'),
                                 ('pause',4),('fetch','2027-02')])
        self.assertEqual(random_delay.call_count,2)
        random_delay.assert_called_with(2,4)
        self.assertTrue(limited)

if __name__ == '__main__':
    unittest.main()
