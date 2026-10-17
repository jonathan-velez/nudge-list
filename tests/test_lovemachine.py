"""Offline inventory simulations, using disposable persistent state."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lovemachine', ROOT/'pricing/lovemachine.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)

class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.rows = json.loads((ROOT/'tests/fixtures/lovemachine-products.json').read_text())['products']
        self.base = self.collect()

    def collect(self, rows=None):
        return inventory.collect(lambda page: {'products': copy.deepcopy(self.rows if rows is None else rows)}, self.state)

    def test_live_fixture_both_sizes_and_exclusions(self):
        boards = inventory.normalize(self.rows)
        self.assertEqual({b['size'] for b in boards.values()}, {"6'4", "6'6"})
        self.assertEqual(len(boards), 2)
        self.assertFalse(any(b['available'] for b in boards.values()))

    def test_size_notation_and_variant_override(self):
        for size in ["6’4”", '6′4″', '6 ft 4 in', '6 feet 4 inches', '6-4', "6' 4\""]:
            row = copy.deepcopy(self.rows[2]); row['title'] = size+' FM'
            self.assertEqual(next(iter(inventory.normalize([row]).values()))['size'], "6'4")
        for title in ["6'8 FM", "16'4 FM", "6'4 FMX", "6'4 Fish", "6'40 FM"]:
            row = copy.deepcopy(self.rows[2]); row['title'] = title
            self.assertEqual(inventory.normalize([row]), {})
        row = copy.deepcopy(self.rows[2]); row['variants'][0]['option1'] = "6'8"
        self.assertEqual(inventory.normalize([row]), {})
        row['variants'][0]['option1'] = "7'0"
        self.assertEqual(inventory.normalize([row]), {})
        row['title'] = 'FM'; row['variants'][0]['option1'] = "6'6"
        self.assertEqual(next(iter(inventory.normalize([row]).values()))['size'], "6'6")

    def test_two_restocks_soldout_silent_and_repeated_restock(self):
        rows = copy.deepcopy(self.rows)
        for i in [1, 2]: rows[i]['variants'][0]['available'] = True
        report = self.collect(rows)
        self.assertEqual(report.count('restock |'), 2)
        self.assertIn('1285.00', report)
        self.assertIn('/products/64-fm-copy?variant=', report)
        self.assertEqual(self.collect(rows), report)
        self.assertEqual(self.collect(), report)
        again = self.collect(rows)
        self.assertIn('Availability event #2', again)
        self.assertEqual(self.collect(rows), again)

    def test_new_available_and_soldout_listings(self):
        for n, size in enumerate(["6'4", "6'6"]):
            new = copy.deepcopy(self.rows[2]); new['id'] += 10
            new['id'] += n*100
            new['title'] = size+' FM'; new['variants'][0]['id'] += 10
            previous = json.loads((self.state/'latest.json').read_text())['report']
            self.assertEqual(self.collect(self.rows+[new]), previous)
            new['variants'][0]['available'] = True
            self.assertIn('restock |', self.collect(self.rows+[new]))
            new['id'] += 1; new['variants'][0]['id'] += 1
            report = self.collect(self.rows+[new])
            self.assertIn('new listing |', report)
            self.assertEqual(self.collect(self.rows+[new]), report)

    def test_unrelated_edits_ordering_and_missing_product_silent(self):
        rows = copy.deepcopy(self.rows); rows[2]['variants'][0]['available'] = True
        report = self.collect(rows)
        rows[2].update(title="6'4 FM new name", body_html='changed', images=[])
        rows[2]['variants'][0]['price'] = '1.00'
        rows[0]['variants'][0]['available'] = True
        self.assertEqual(self.collect(rows[::-1]), report)
        self.assertEqual(self.collect(rows[:2]), report)
        self.assertEqual(self.collect(rows), report)

    def test_errors_preserve_state_and_recovery(self):
        path = self.state/'latest.json'; baseline = path.read_bytes()
        invalid = [{}, {'products': []}, {'products': {}}, {'products': [None]}]
        for value in [None, 'false', 0]:
            rows = copy.deepcopy(self.rows); rows[2]['variants'][0]['available'] = value
            invalid.append({'products': rows})
        for payload in invalid:
            with self.assertRaises(ValueError):
                inventory.collect(lambda page: payload, self.state)
            self.assertEqual(path.read_bytes(), baseline)
        def failure(page): raise OSError('503 or request timeout')
        with self.assertRaises(OSError): inventory.collect(failure, self.state)
        def malformed(page): return json.loads('{bad')
        with self.assertRaises(ValueError): inventory.collect(malformed, self.state)
        self.assertEqual(path.read_bytes(), baseline)
        self.assertEqual(self.collect(), self.base)

    def test_pagination_and_later_page_failure(self):
        first = []
        for n in range(250):
            row = copy.deepcopy(self.rows[0]); row['id'] = n+1
            first.append(row)
        second = copy.deepcopy(self.rows[2]); second['variants'][0]['available'] = True
        calls = []
        def pages(page):
            calls.append(page); return {'products': first if page == 1 else [second]}
        self.assertIn('restock |', inventory.collect(pages, self.state))
        self.assertEqual(calls, [1, 2])
        baseline = (self.state/'latest.json').read_bytes()
        def broken(page):
            if page == 2: raise OSError('second page failed')
            return {'products': first}
        with self.assertRaises(OSError): inventory.collect(broken, self.state)
        self.assertEqual((self.state/'latest.json').read_bytes(), baseline)

    def test_restart(self):
        rows = copy.deepcopy(self.rows); rows[1]['variants'][0]['available'] = True
        report = self.collect(rows)
        reloaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(reloaded)
        self.assertEqual(reloaded.collect(lambda page: {'products': rows}, self.state), report)

if __name__ == '__main__': unittest.main()
