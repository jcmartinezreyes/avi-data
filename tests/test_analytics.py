import unittest
from analytics import build_production_series


class ProductionAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.lot = {'id': 1, 'codigo_lote': 'A', 'fecha_encaste': '2026-11-01',
                    'aves_hembra': 90, 'aves_macho': 10, 'aves_totales': 100, 'tipo_produccion': 'engorde'}
        self.boxes = [
            {'id': 11, 'lote_id': 1, 'aves_hembra_inicial': 80, 'aves_macho_inicial': 0},
            {'id': 12, 'lote_id': 1, 'aves_hembra_inicial': 10, 'aves_macho_inicial': 10},
        ]

    def daily(self, identity, day, **values):
        row = {'id': identity, 'lote_id': 1, 'fecha': f'2026-11-{day:02d}', 'dia_vida': day,
               'mortalidad_hembra': 0, 'mortalidad_macho': 0, 'descarte_hembra': 0,
               'descarte_macho': 0, 'consumo_alimento_kg': 10, 'consumo_agua_litros': 20}
        row.update(values)
        return row

    def detail(self, daily_id, box_id, **values):
        row = self.daily(999, 1)
        row.update(registro_diario_id=daily_id, box_id=box_id)
        row.update(values)
        return row

    def test_weights_are_population_weighted_across_boxes_and_sexes(self):
        rows = build_production_series([self.daily(1, 1)], [self.lot], self.boxes, [
            self.detail(1, 11, peso_promedio_hembra_g=100),
            self.detail(1, 12, peso_promedio_hembra_g=200, peso_promedio_macho_g=400),
        ])
        self.assertAlmostEqual(rows[0]['peso_promedio_hembra_g'], 10000 / 90)
        self.assertEqual(rows[0]['peso_promedio_mixto_g'], 140)
        self.assertAlmostEqual(rows[0]['fcr_acumulado'], 20 / 14)

    def test_current_and_prior_losses_reduce_box_weight(self):
        details = []
        for day in (1, 2):
            details.extend([
                self.detail(day, 11, mortalidad_hembra=10, peso_promedio_hembra_g=100),
                self.detail(day, 12, peso_promedio_hembra_g=200, peso_promedio_macho_g=400),
            ])
        rows = build_production_series([self.daily(1, 1), self.daily(2, 2)], [self.lot], self.boxes, details)
        self.assertEqual(rows[1]['aves_vivas'], 80)
        self.assertEqual(rows[1]['peso_promedio_mixto_g'], 150)
        self.assertEqual(rows[1]['mortalidad_pct'], 20)
        self.assertAlmostEqual(rows[1]['consumo_g_ave'], 20000 / 85)

    def test_unmeasured_live_sex_does_not_become_zero_or_disappear(self):
        row = build_production_series([self.daily(1, 1)], [self.lot], self.boxes, [
            self.detail(1, 11, peso_promedio_hembra_g=100),
            self.detail(1, 12, peso_promedio_hembra_g=200, peso_promedio_macho_g=0),
        ])[0]
        self.assertIsNone(row['peso_promedio_mixto_g'])
        self.assertIsNone(row['fcr_acumulado'])

    def test_single_sex_ignores_zero_population_sex(self):
        lot = dict(self.lot, aves_hembra=100, aves_macho=0)
        box = {'id': 11, 'lote_id': 1, 'aves_hembra_inicial': 100, 'aves_macho_inicial': 0}
        row = build_production_series([self.daily(1, 1)], [lot], [box], [self.detail(1, 11, peso_promedio_hembra_g=200)])[0]
        self.assertEqual(row['peso_promedio_mixto_g'], 200)
        self.assertIsNone(row['peso_promedio_macho_g'])

    def test_legacy_weight_and_no_double_count(self):
        row = build_production_series([self.daily(1, 1, peso_promedio_mixto_g=1000)], [self.lot], [], [])[0]
        self.assertEqual(row['fcr_acumulado'], 0.1)
        self.assertEqual(row['ratio_agua_alimento'], 2)
        self.assertEqual(row['viabilidad_pct'], 100)
        self.assertIsNone(row['gmd_g'])
        self.assertAlmostEqual(row['epef'], 100000)

    def test_gaps_disable_cumulative_kpis_and_gmd_uses_elapsed_days(self):
        rows = build_production_series([
            self.daily(1, 1, peso_promedio_mixto_g=100),
            self.daily(2, 3, peso_promedio_mixto_g=300),
        ], [self.lot], [], [])
        self.assertEqual(rows[1]['gmd_g'], 100)
        self.assertFalse(rows[1]['cobertura_completa'])
        self.assertIsNone(rows[1]['fcr_acumulado'])
        self.assertIsNone(rows[1]['mortalidad_pct'])

    def test_missing_consumption_and_zero_ratios_remain_undefined(self):
        row = build_production_series([self.daily(1, 1, consumo_alimento_kg=None)], [self.lot], [], [])[0]
        self.assertIsNone(row['alimento_acum_kg'])
        self.assertIsNone(row['consumo_g_ave'])
        self.assertIsNone(row['ratio_agua_alimento'])
        row = build_production_series([self.daily(1, 1, consumo_alimento_kg=0, peso_promedio_mixto_g=1000)], [self.lot], [], [])[0]
        self.assertEqual(row['fcr_acumulado'], 0)
        self.assertIsNone(row['epef'])
        self.assertIsNone(row['ratio_agua_alimento'])

    def test_non_broiler_has_no_broiler_fcr_or_epef(self):
        row = build_production_series([self.daily(1, 1, peso_promedio_mixto_g=1000)], [dict(self.lot, tipo_produccion='postura')], [], [])[0]
        self.assertIsNone(row['fcr_acumulado'])
        self.assertIsNone(row['epef'])

    def test_partial_box_capture_disables_accumulated_consumption(self):
        row = build_production_series([self.daily(1, 1)], [self.lot], self.boxes, [
            self.detail(1, 11, peso_promedio_hembra_g=100),
        ])[0]
        self.assertFalse(row['cobertura_completa'])
        self.assertIsNone(row['alimento_acum_kg'])
        self.assertIsNone(row['peso_promedio_mixto_g'])

    def test_draft_does_not_contribute_or_conflict_with_submitted_day(self):
        rows = build_production_series([
            self.daily(1, 1, status='draft', consumo_alimento_kg=999),
            self.daily(2, 1, status='submitted', peso_promedio_mixto_g=1000),
        ], [self.lot], [], [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['alimento_acum_kg'], 10)

    def test_sale_reduces_live_but_is_not_mortality_and_fcr_requires_biomass(self):
        rows = build_production_series([self.daily(1, 1)], [self.lot], self.boxes, [
            self.detail(1, 11, peso_promedio_hembra_g=100),
            self.detail(1, 12, peso_promedio_hembra_g=200, peso_promedio_macho_g=400),
        ], movements=[{'lote_id': 1, 'box_id': 11, 'fecha': '2026-11-01',
                       'sex': 'hembra', 'kind': 'sale', 'count': 20}])
        row = rows[0]
        self.assertEqual(row['aves_vivas'], 80)
        self.assertEqual(row['mortalidad_pct'], 0)
        self.assertEqual(row['viabilidad_pct'], 100)
        self.assertEqual(row['peso_promedio_mixto_g'], 150)
        self.assertIsNone(row['fcr_acumulado'])
        self.assertEqual(row['fcr_metodo'], 'unavailable_departure_biomass')

    def test_arrival_updates_weight_denominator_and_sex_population(self):
        row = build_production_series([self.daily(1, 1)], [self.lot], self.boxes, [
            self.detail(1, 11, peso_promedio_hembra_g=100),
            self.detail(1, 12, peso_promedio_hembra_g=200, peso_promedio_macho_g=400),
        ], movements=[{'lote_id': 1, 'box_id': 11, 'fecha': '2026-11-01',
                       'sex': 'hembra', 'kind': 'arrival', 'count': 100}])[0]
        self.assertEqual(row['aves_vivas'], 200)
        self.assertEqual(row['aves_vivas_hembra'], 190)
        self.assertEqual(row['peso_promedio_mixto_g'], 120)
        self.assertEqual(row['denominador_aves_expuestas'], 200)

    def test_internal_box_transfer_preserves_exposure_and_fcr(self):
        row = build_production_series([self.daily(1, 1)], [self.lot], self.boxes, [
            self.detail(1, 11, peso_promedio_hembra_g=100),
            self.detail(1, 12, peso_promedio_hembra_g=200, peso_promedio_macho_g=400),
        ], movements=[
            {'event_id': 'same', 'lote_id': 1, 'box_id': 11, 'fecha': '2026-11-01',
             'sex': 'hembra', 'kind': 'transfer_out', 'count': 20},
            {'event_id': 'same', 'lote_id': 1, 'box_id': 12, 'fecha': '2026-11-01',
             'sex': 'hembra', 'kind': 'transfer_in', 'count': 20}])[0]
        self.assertEqual(row['aves_vivas'], 100)
        self.assertEqual(row['denominador_aves_expuestas'], 100)
        self.assertEqual(row['peso_promedio_mixto_g'], 160)
        self.assertIsNotNone(row['fcr_acumulado'])

    def test_duplicate_day_rejected(self):
        with self.assertRaises(ValueError):
            build_production_series([self.daily(1, 1), self.daily(2, 1)], [self.lot], [], [])


if __name__ == '__main__':
    unittest.main()
