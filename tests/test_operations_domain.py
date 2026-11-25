import json
import unittest
from avilab_domain import (sample_statistics, weighted_sample_mean, water_consumption,
    bird_balance, egg_reconciliation, hatchery_indicators, feed_inventory,
    metric_coverage, forecast_baseline, chronological_backtest, cycle_snapshot, snapshot_csv)


class DomainTests(unittest.TestCase):
    def test_coverage_zero_is_visible_when_no_lot_has_a_measurement(self):
        result = metric_coverage([{'lote_id':1,'dia_vida':2,'peso':None}], ['peso'])
        self.assertEqual(result[0]['n_lots'], 0)
        self.assertIsNone(result[0]['median'])
        self.assertIsNone(result[0]['p25'])

    def test_sample_weights_not_population_weights(self):
        summary = weighted_sample_mean([{'mean_g': 100, 'sample_n': 1}, {'mean_g': 200, 'sample_n': 3}])
        self.assertEqual(summary['mean_g'], 175)
        self.assertIsNone(summary['cv_pct'])
        result = sample_statistics([100, 100, 200, 200])
        self.assertEqual(result['n'], 4)
        self.assertAlmostEqual(result['sd_g'], 57.7350269189)
        self.assertEqual(result['uniformity_pct'], 0)
        self.assertEqual(sample_statistics(frequency=[(100, 2), (200, 2)]),
                         dict(result, method='exact_frequency_sample'))
        self.assertIsNone(sample_statistics([100])['cv_pct'])

    def test_water_replacement_does_not_discard_old_counter_use(self):
        self.assertEqual(water_consumption(900, 80, reset=True, previous_end=950, new_start=10), 120)
        with self.assertRaises(ValueError):
            water_consumption(900, 80)
        with self.assertRaises(ValueError):
            water_consumption(900, 80, reset=True)

    def test_live_balance_sales_and_deaths_are_different(self):
        result = bird_balance({'hembra': 100}, [
            {'kind': 'sale', 'sex': 'hembra', 'count': 30},
            {'kind': 'death', 'sex': 'hembra', 'count': 2}])
        self.assertEqual(result['live'], 68)
        self.assertEqual(result['deaths'], 2)
        with self.assertRaises(ValueError):
            bird_balance({'hembra': 10}, [{'kind': 'sale', 'sex': 'hembra', 'count': 11}])

    def test_eggs_and_sample_fertility_denominators(self):
        self.assertTrue(egg_reconciliation(100, {'A': 80, 'B': 15}, losses=5)['balanced'])
        self.assertFalse(egg_reconciliation(100, {'A': 100, 'B': 10})['balanced'])
        result = hatchery_indicators(1000, 800, sample_examined=100, sample_fertile=90)
        self.assertEqual(result['sample_fertility_pct'], 90)
        self.assertEqual(result['hatch_of_set_pct'], 80)
        self.assertIsNone(result['hatch_of_fertile_pct'])

    def test_feed_stock_and_incomplete_window(self):
        result = feed_inventory(100, [{'kind': 'receipt', 'kg': 20}, {'kind': 'consumption', 'kg': 30}],
                                [{'fecha': '2026-01-01', 'kg': 10}, {'fecha': '2026-01-02', 'kg': 20}])
        self.assertEqual(result['closing_kg'], 90)
        self.assertEqual(result['coverage_days'], 6)
        result = feed_inventory(100, [], [{'fecha': '2026-01-01', 'kg': 10}, {'fecha': '2026-01-03', 'kg': 20}])
        self.assertIsNone(result['coverage_days'])
        with self.assertRaises(ValueError):
            feed_inventory(10, [{'kind': 'consumption', 'kg': 11}], [])

    def test_coverage_counts_valid_lots_per_metric(self):
        rows = [{'lote_id': i, 'dia_vida': 1, 'peso': weight, 'mortality': i} for i, weight in [(1, 10), (2, 20), (3, None)]]
        result = {r['metric']: r for r in metric_coverage(rows, ['peso', 'mortality'])}
        self.assertEqual(result['peso']['n_lots'], 2)
        self.assertEqual(result['mortality']['n_lots'], 3)
        self.assertEqual(result['peso']['median'], 15)
        with self.assertRaises(ValueError):
            metric_coverage(rows + [rows[0]], ['peso'])

    def test_forecast_cutoff_and_real_chronological_holdout(self):
        rows = [{'fecha': f'2026-01-{i:02}', 'value': i} for i in range(1, 11)]
        result = forecast_baseline(rows, 2, cutoff='2026-01-05')
        self.assertEqual([r['value'] for r in result['points']], [5, 5])
        self.assertEqual(result['points'][0]['fecha'], '2026-01-06')
        result = chronological_backtest([
            {'id': 1, 'estado': 'cerrado', 'is_synthetic': True, 'history': rows},
            {'id': 2, 'estado': 'cerrado', 'is_synthetic': False, 'history': rows},
            {'id': 3, 'estado': 'cerrado', 'is_synthetic': False, 'history': rows}], horizon=2)
        self.assertEqual(result['n_cycles'], 2)
        self.assertEqual(result['mae'], 1.5)
        self.assertEqual(result['folds'][0]['cutoff'], '2026-01-08')
        self.assertFalse(result['validated_for_real_use'])

    def test_snapshot_deterministic_anonymous_and_csv_safe(self):
        context = {'organization': 'Private Client', 'nombre': 'Someone', 'tipo_produccion': 'engorde'}
        events = [{'kind': 'health', 'notes': 'Private Client', 'value': 1, 'payload': {'client': 'Private Client', 'count': 1}}]
        first = cycle_snapshot(context, events, [], 'v1')
        self.assertNotIn('Private Client', first['content'])
        self.assertEqual(first, cycle_snapshot(context, list(reversed(events)), [], 'v1'))
        self.assertNotEqual(first['sha256'], cycle_snapshot(context, events, [], 'v2')['sha256'])
        raw = cycle_snapshot({}, [{'notes': '=CMD()'}], [], 'v1', anonymize=False)
        self.assertIn("'=CMD()", snapshot_csv(raw))


if __name__ == '__main__':
    unittest.main()
