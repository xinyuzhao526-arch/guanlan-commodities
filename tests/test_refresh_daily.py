"""Publication boundary tests: bad source data must never replace the last good close."""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts/refresh_daily.py'
spec = importlib.util.spec_from_file_location('refresh_daily', MODULE)
daily = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily)


def snapshot(day='2026-10-23'):
    markets = []
    for ex in sorted(daily.EXCHANGES):
        bar = {'date': day, 'contract': ex.lower() + '2701', 'close': 100}
        history = ([{**bar, 'date':'2026-10-23'}] if day>'2026-10-23' else []) + [dict(bar)]
        markets.append({'code': ex.lower(), 'exchange': ex, 'main': bar,
                        'history': history, 'ranks': [], 'analysis': {},
                        'quoteSource': {'date': day, 'url': 'https://example.com/public'}})
    return {'schema': 'domestic-v1', 'asOf': day, 'markets': markets,
            'exchangeSources': [{'date': day, 'exchange': ex} for ex in sorted(daily.EXCHANGES)]}


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'dist').mkdir()
        self.published = self.root / 'dist/data.json'
        self.original = json.dumps(snapshot()).encode()
        self.published.write_bytes(self.original)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, stage, day, start):
        candidate = snapshot(day)
        (stage / 'dist/data.json').write_text(json.dumps(candidate), encoding='utf-8')
        (stage / 'data/shfe-base.json').write_text('{}', encoding='utf-8')
        return candidate

    def refresh(self, **kwargs):
        return daily.refresh(self.root, '2026-10-26', '2026-07-01',
                             preflight=lambda *_: True, **kwargs)

    def test_success_promotes_common_date(self):
        with patch.object(daily, 'run_script'):
            result = self.refresh(builder=self.build)
        self.assertTrue(result['changed'])
        self.assertEqual(json.loads(self.published.read_bytes())['asOf'], '2026-10-26')

    def test_partial_source_failure_keeps_exact_old_bytes(self):
        def fail(stage, *_):
            (stage / 'dist/data.json').write_text('partially overwritten')
            raise RuntimeError('CZCE unavailable')
        with self.assertRaisesRegex(RuntimeError, 'CZCE'):
            self.refresh(builder=fail)
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_export_failure_keeps_exact_old_bytes(self):
        with patch.object(daily, 'run_script', side_effect=RuntimeError('export failed')):
            with self.assertRaisesRegex(RuntimeError, 'export failed'):
                self.refresh(builder=self.build)
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_history_download_loss_keeps_published_snapshot(self):
        def lose_history(*args):
            candidate = self.build(*args)
            candidate['markets'][0]['history'] = candidate['markets'][0]['history'][-1:]
            return candidate
        with self.assertRaisesRegex(ValueError, 'previously validated'):
            self.refresh(builder=lose_history)
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_mixed_exchange_dates_are_rejected(self):
        def wrong_date(*args):
            candidate = self.build(*args)
            candidate['markets'][0]['quoteSource']['date'] = '2026-10-23'
            return candidate
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.refresh(builder=wrong_date)
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_unpublished_report_skips_without_claiming_holiday(self):
        result = daily.refresh(self.root, '2026-10-26', '2026-07-01',
                               preflight=lambda *_: False,
                               builder=lambda *_: self.fail('must not build'))
        self.assertEqual(result['status'], 'no-published-report')
        self.assertEqual(result['asOf'], '2026-10-23')
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_old_target_cannot_roll_back_publication(self):
        result = daily.refresh(self.root, '2026-10-22', '2026-07-01',
                               preflight=lambda *_: self.fail('must not fetch'))
        self.assertEqual(result['status'], 'up-to-date')
        self.assertEqual(self.published.read_bytes(), self.original)

    def test_invalid_data_and_coverage_regression(self):
        good = snapshot()
        mutations = [lambda x: x['markets'].pop(),
                     lambda x: x['markets'][0]['history'][0].update(contract='other2701'),
                     lambda x: x['markets'][0]['history'][0].update(date='2027-01-01'),
                     lambda x: x['markets'][0]['main'].update(close=float('nan'))]
        for mutate in mutations:
            value = copy.deepcopy(good)
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                daily.validate_snapshot(value, value['asOf'], good)
        prior = copy.deepcopy(good)
        prior['markets'].extend([dict(good['markets'][0])] * 4)
        with self.assertRaisesRegex(ValueError, 'coverage fell'):
            daily.validate_snapshot(good, good['asOf'], prior)

    def test_shanghai_date_selection_and_future_guard(self):
        friday = dt.datetime(2026, 10, 23, 14, tzinfo=daily.SHANGHAI)
        self.assertEqual(daily.target_day(friday).isoformat(), '2026-10-22')
        sunday = dt.datetime(2026, 10, 25, 20, tzinfo=daily.SHANGHAI)
        self.assertEqual(daily.target_day(sunday).isoformat(), '2026-10-23')
        with self.assertRaises(ValueError):
            daily.target_day(friday, '2026-10-23')


if __name__ == '__main__':
    unittest.main()
