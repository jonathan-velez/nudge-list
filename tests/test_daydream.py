"""Daydream fixture transitions use isolated state and no network."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'pricing'))
import daydream


class DaydreamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.rows = json.loads((ROOT/'tests/fixtures/daydream-products.json').read_text())

    def collect(self):
        return daydream.collect(lambda page: copy.deepcopy(self.rows), self.state)

    def test_discovery_restock_and_silent_edits(self):
        baseline = self.collect()
        saved = json.loads((self.state/'latest.json').read_text())
        self.assertEqual(len(saved['observed']), 2)
        self.assertTrue(all(r['size'] == "6'6" and not r['available'] for r in saved['observed'].values()))
        linked = next(r for r in self.rows['products'] if r['handle'] == '6-6-lovemachine-fm')
        linked['variants'][0]['available'] = True
        report = self.collect()
        self.assertNotEqual(baseline, report)
        self.assertIn('restock |', report)
        self.assertIn('https://daydreamsurfshop.com/products/6-6-lovemachine-fm?variant=', report)
        self.assertIn('1100.00', report)
        linked['variants'][0]['price'] = '1000.00'
        self.rows['products'].reverse()
        self.assertEqual(self.collect(), report)
        linked['variants'][0]['available'] = False
        self.assertEqual(self.collect(), report)
        linked['variants'][0]['available'] = True
        self.assertIn('Availability event #2', self.collect())

    def test_new_listing_brand_filter_and_failure_recovery(self):
        baseline = self.collect()
        new = copy.deepcopy(self.rows['products'][-1])
        new.update(id=12345, title="6'6 Another Brand FM", vendor='Another Brand', handle='new-fm')
        new['variants'][0].update(id=54321, available=True)
        self.rows['products'].append(new)
        self.assertEqual(self.collect(), baseline)
        new['title'] = "6'6 Love Machine FM"
        report = self.collect()
        self.assertIn('new listing |', report)
        self.assertIn('/products/new-fm?variant=54321', report)
        before = (self.state/'latest.json').read_bytes()
        def fail(page):
            raise OSError('upstream failed')
        with self.assertRaises(OSError):
            daydream.collect(fail, self.state)
        self.assertEqual((self.state/'latest.json').read_bytes(), before)
        self.assertEqual(self.collect(), report)
        before = (self.state/'latest.json').read_bytes()
        with self.assertRaises(ValueError):
            daydream.collect(lambda page: {'products': []}, self.state)
        self.assertEqual((self.state/'latest.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
