"""Offline FM inventory tests; no production state or notifications touched."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inventory', ROOT/'pricing/lovemachine.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.fixture = json.loads((ROOT/'tests/fixtures/lovemachine-products.json').read_text())
        self.base = self.collect()

    def collect(self, payload=None):
        return inventory.collect(fetch=lambda page: copy.deepcopy(self.fixture if payload is None else payload), state=self.state)

    def saved(self):
        return json.loads((self.state/'latest.json').read_text())

    def available(self, index=1):
        payload = copy.deepcopy(self.fixture)
        payload['products'][index]['variants'][0]['available'] = True
        return payload

    def test_real_fixture_both_target_sizes_soldout_other_sizes_excluded(self):
        rows = list(self.saved()['boards'].values())
        self.assertEqual({r['size'] for r in rows}, {"6'4", "6'6"})
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not r['available'] for r in rows))

    def test_size_variations(self):
        for name in ["6'4\" FM", '6’4” FM', '6′4″ FM', '6 ft 4 in FM', '6 feet 4 inches FM', '6-4 FM', "6' 04 FM"]:
            with self.subTest(name=name):
                self.assertEqual(inventory.sizes(name), {"6'4"})
        for name in ["6'6 FM", '6’6” FM', '6′6″ FM', '6 ft 6 in FM', '6-6 FM']:
            self.assertEqual(inventory.sizes(name), {"6'6"})
        for name in ['64 FM', '6.4 FM', "6'40 FM", "7'4 FM", "6'8 FM"]:
            self.assertEqual(inventory.sizes(name) & {"6'4", "6'6"}, set())

    def test_restock_sellout_repeat_restart_and_second_restock(self):
        payload = self.available()
        first = self.collect(payload)
        self.assertIn('restock', first)
        self.assertIn('6\'6 FM', first)
        self.assertIn('1285.00', first)
        self.assertIn('/products/66-fm-19?variant=', first)
        self.assertEqual(self.collect(payload), first)
        reloaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(reloaded)
        self.assertEqual(reloaded.collect(fetch=lambda page: payload, state=self.state), first)
        self.assertEqual(self.collect(), first)  # sellout updates state silently
        second = self.collect(payload)
        self.assertNotEqual(second, first)
        self.assertIn('Availability event #2', second)

    def test_new_listings_both_sizes_and_multiple_boards(self):
        payload = copy.deepcopy(self.fixture)
        for index in (1, 2):
            new = copy.deepcopy(payload['products'][index])
            new.update(id=new['id']+1, handle='new-'+new['handle'])
            new['variants'][0].update(id=new['variants'][0]['id']+1, available=True)
            payload['products'].append(new)
        report = self.collect(payload)
        self.assertEqual(report.count('new listing'), 2)
        self.assertIn("size 6'4", report)
        self.assertIn("size 6'6", report)
        self.assertEqual(self.collect(payload), report)
        payload['products'][-1]['variants'][0]['available'] = False
        self.assertEqual(self.collect(payload), report)

    def test_new_soldout_listing_then_restock(self):
        payload = copy.deepcopy(self.fixture)
        new = copy.deepcopy(payload['products'][1]); new['id'] += 1
        new['variants'][0]['id'] += 1
        payload['products'].append(new)
        self.assertEqual(self.collect(payload), self.base)
        new['variants'][0]['available'] = True
        self.assertIn('restock', self.collect(payload))

    def test_order_metadata_and_unrelated_models_sizes_silent(self):
        payload = self.available()
        report = self.collect(payload)
        payload['products'].reverse()
        for row in payload['products']:
            row['variants'][0]['price'] = '999.00'
            row.update(body_html='Edited', images=['changed'], title=row['title']+' custom')
        new = copy.deepcopy(payload['products'][2]); new['id'] += 100
        new['variants'][0]['id'] += 100
        new['title'] = "6'6 FML"; new['variants'][0]['available'] = True
        payload['products'].append(new)
        for row in payload['products']:
            if "7'0" in row['title']:
                row['variants'][0]['available'] = True
        self.assertEqual(self.collect(payload), report)

    def test_variant_length_matching_and_override(self):
        payload = copy.deepcopy(self.fixture)
        product = payload['products'][1]
        product['title'] = 'FM'
        product['variants'][0].update(title='6’4” / Red', option1='6’4”', available=True)
        report = self.collect(payload)
        self.assertIn("size 6'4", report)
        product['title'] = "6'6 FM"
        product['variants'][0].update(title="6'8", option1="6'8")
        self.assertEqual(self.collect(payload), report)

    def test_missing_listing_does_not_manufacture_restock(self):
        payload = self.available()
        report = self.collect(payload)
        removed = copy.deepcopy(payload); del removed['products'][1]
        self.assertEqual(self.collect(removed), report)
        self.assertEqual(self.collect(payload), report)

    def test_invalid_and_failed_requests_preserve_state(self):
        before = (self.state/'latest.json').read_bytes()
        invalid = [{}, {'products': None}, {'products': []}, {'products': [{}]}]
        for field, value in [('available', None), ('available', 'true'), ('id', ''), ('price', 'NaN')]:
            payload = copy.deepcopy(self.fixture)
            payload['products'][1]['variants'][0][field] = value
            invalid.append(payload)
        payload = copy.deepcopy(self.fixture); payload['products'].append(payload['products'][0])
        invalid.append(payload)
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.collect(payload)
                self.assertEqual((self.state/'latest.json').read_bytes(), before)
        def failure(page):
            raise OSError('request failed')
        with self.assertRaises(OSError):
            inventory.collect(fetch=failure, state=self.state)
        self.assertEqual((self.state/'latest.json').read_bytes(), before)
        self.assertEqual(self.collect(), self.base)

    def test_pagination_complete_before_commit_and_safety_limit(self):
        original = inventory.LIMIT
        inventory.LIMIT = 2
        self.addCleanup(setattr, inventory, 'LIMIT', original)
        calls = []
        def fetch(page):
            calls.append(page)
            return {'products': self.fixture['products'][(page-1)*2:page*2]}
        self.assertEqual(inventory.collect(fetch=fetch, state=self.state), self.base)
        self.assertEqual(calls, [1, 2, 3])
        before = (self.state/'latest.json').read_bytes()
        def partial(page):
            if page == 2:
                raise OSError('second page failed')
            return fetch(page)
        with self.assertRaises(OSError):
            inventory.collect(fetch=partial, state=self.state)
        self.assertEqual((self.state/'latest.json').read_bytes(), before)
        with self.assertRaises(ValueError):
            inventory.collect(fetch=lambda page: {'products': self.fixture['products'][:2]}, state=self.state)
        self.assertEqual((self.state/'latest.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
