"""Exercise actual app helpers/manager/overview with a relational API double.

AST isolation avoids logging in or reaching Supabase while preserving the real
entry-point code. The double applies query predicates to representative rows.
"""
import ast
import copy
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

import pandas as pd
from analytics import build_production_series

ROOT = Path(__file__).resolve().parents[1]


class Query:
    def __init__(self, client, name):
        self.client, self.name = client, name
        self.predicates = []
        self.inner_capture = False
        self.bounds = None
        self.sort = None

    def select(self, columns):
        self.inner_capture = 'daily_captures!inner' in columns
        return self

    @staticmethod
    def field(row, name):
        value = row
        for field in name.split('.'):
            if isinstance(value, list):
                return [item.get(field) for item in value]
            value = value.get(field) if isinstance(value, dict) else None
        return value

    def eq(self, name, value):
        self.predicates.append(lambda row: self.field(row, name) == value)
        return self

    def in_(self, name, values):
        def matches(row):
            value = self.field(row, name)
            return any(item in values for item in value) if isinstance(value, list) else value in values
        self.predicates.append(matches)
        return self

    def gte(self, name, value):
        self.predicates.append(lambda row: self.field(row, name) >= value)
        return self

    def order(self, field):
        self.sort = field
        return self

    def range(self, start, end):
        self.bounds = start, end
        return self

    def execute(self):
        rows = copy.deepcopy(self.client.rows.get(self.name, []))
        if self.inner_capture:
            rows = [r for r in rows if r.get('daily_captures')]
        rows = [row for row in rows if all(predicate(row) for predicate in self.predicates)]
        if self.sort:
            rows.sort(key=lambda row: row[self.sort])
        if self.bounds:
            start, end = self.bounds
            rows = rows[start:end + 1]
        return SimpleNamespace(data=rows)


class FakeClient:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return Query(self, name)


class NavigationRequested(Exception):
    pass


class UI:
    def __init__(self, choices=None):
        self.choices = choices or {}
        self.metrics = {}
        self.tables = []
        self.messages = []
        self.session_state = {}
        self.progress_value = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def columns(self, count):
        return [self] * (count if isinstance(count, int) else len(count))

    def button(self, label, **kwargs):
        return self.choices.get('click') == kwargs.get('key', label)

    def rerun(self):
        raise NavigationRequested()

    def progress(self, value, **kwargs):
        self.progress_value = value
        self.messages.append(kwargs.get('text', ''))

    def metric(self, title, value, *args, **kwargs):
        self.metrics[title] = value

    def selectbox(self, title, values, **kwargs):
        return self.choices.get(title, list(values)[0])

    def multiselect(self, title, values, **kwargs):
        return self.choices.get(title, kwargs.get('default', []))

    def checkbox(self, title, **kwargs):
        return kwargs.get('value', False)

    def expander(self, *args, **kwargs):
        return self

    def dataframe(self, data, **kwargs):
        self.tables.append(data)

    def caption(self, value):
        self.messages.append(value)

    subheader = caption
    info = caption

    def stop(self):
        raise AssertionError('App stopped unexpectedly')


class AppOperationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse((ROOT / 'app.py').read_text())
        names = {'listar_filas', 'consulta_lotes_organizacion', 'obtener_diarios',
                 'obtener_movimientos_aves', 'obtener_saldos_lotes', 'series_productivas'}
        nodes = [node for node in cls.tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        nodes += [node for node in cls.tree.body if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in ('CAMPOS_DIARIOS', 'CAMPOS_PESO') for target in node.targets)]
        cls.helper_code = compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'app.py', 'exec')

    def ns(self, rows, ui=None):
        namespace = {'supabase': FakeClient(rows), 'organization_id': 'org-a',
                     'datetime': datetime, 'timedelta': timedelta, 'ZoneInfo': ZoneInfo,
                     'pd': pd, 'build_production_series': build_production_series, 'st': ui or UI(), 'current_role': 'admin'}
        exec(self.helper_code, namespace)
        return namespace

    def run_view(self, text, namespace):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.If) and isinstance(node.test, (ast.Compare, ast.BoolOp)) and text in ast.unparse(node.test) and any(isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == 'opcion' and any(isinstance(op, ast.Eq) for op in test.ops) for test in ast.walk(node.test)):
                code = compile(ast.fix_missing_locations(ast.Module(body=node.body, type_ignores=[])), 'app.py', 'exec')
                exec(code, namespace)
                return
        raise AssertionError('App view not found')

    @staticmethod
    def lot(identity=1, active=True):
        return {'id': identity, 'activo': active, 'codigo_lote': 'SYNTHETIC-' + str(identity),
                'fecha_encaste': '2026-11-01', 'tipo_produccion': 'engorde', 'linea_genetica': 'Test',
                'aves_hembra': 90, 'aves_macho': 10, 'aves_totales': 100,
                'galpones': {'id': identity, 'granjas': {'id': 1, 'nombre': 'Synthetic farm', 'organization_id': 'org-a'}},
                'galpon_boxes': [{'id': identity * 10, 'aves_hembra_inicial': 90, 'aves_macho_inicial': 10}]}

    @staticmethod
    def daily(identity=1, lot=1, day=1, status='submitted', **values):
        row = {'id': identity, 'lote_id': lot, 'fecha': f'2026-11-{day:02d}', 'dia_vida': day,
               'mortalidad_hembra': 0, 'mortalidad_macho': 0, 'descarte_hembra': 0, 'descarte_macho': 0,
               'consumo_alimento_kg': 10, 'consumo_agua_litros': 20,
               'peso_promedio_hembra_g': 1000, 'peso_promedio_macho_g': 1200,
               'daily_captures': [{'status': status, 'source': 'manual', 'version': 1}], 'registros_diarios_box': []}
        row.update(values)
        return row

    def test_withdrawn_captures_do_not_reenter_analytics_and_pages_are_complete(self):
        rows = [self.daily(identity=i, status='submitted') for i in range(1, 1002)]
        rows += [self.daily(2001, status='draft', consumo_alimento_kg=9000),
                 self.daily(2002, status='reviewed'), self.daily(2003, status='closed'),
                 self.daily(2004, status='pending')]
        ns = self.ns({'registros_diarios': rows})
        actual = ns['obtener_diarios']([1])
        self.assertEqual(len(actual), 1003)
        self.assertNotIn(2001, {r['id'] for r in actual})
        self.assertNotIn(2004, {r['id'] for r in actual})
        self.assertEqual(sum(r['consumo_alimento_kg'] for r in actual), 10030)
        self.assertEqual(ns['obtener_diarios']([]), [])

    def test_transfer_normalization_uses_local_date_and_preserves_both_sides(self):
        events = [dict(id='transfer-one', organization_id='org-a', kind='bird_movement', lote_id=1,
                       box_id=10, observed_at='2026-11-02T02:00:00Z', quantity_female=20,
                       quantity_male=2, data={'movement': 'transfer', 'destination_box_id': 20}),
                  dict(id='receipt', organization_id='org-a', kind='arrival', lote_id=1,
                       box_id=10, observed_at='2026-11-02T02:00:00Z', quantity_female=100,
                       data={'movement': 'arrival'}),
                  dict(id='other-org', organization_id='org-b', kind='bird_movement', lote_id=1,
                       box_id=10, observed_at='2026-11-02T02:00:00Z', quantity_female=500,
                       data={'movement': 'sale'})]
        ns = self.ns({'effective_operations_events': events})
        result = ns['obtener_movimientos_aves']([self.lot(1), self.lot(2)])
        self.assertEqual(len(result), 4)
        self.assertEqual({m['fecha'] for m in result}, {'2026-11-01'})
        self.assertEqual({m['event_id'] for m in result}, {'transfer-one'})
        self.assertEqual(sum(m['count'] * (1 if m['kind'] == 'transfer_in' else -1) for m in result), 0)
        recipient_only = ns['obtener_movimientos_aves']([self.lot(2)])
        self.assertEqual(sum(m['count'] for m in recipient_only if m['lote_id'] == 2), 22)

    def test_series_forwards_sales_to_population_weight_and_fcr_safety(self):
        lot = self.lot()
        events = [dict(id='sale-one', organization_id='org-a', kind='bird_movement', lote_id=1,
                       box_id=10, observed_at='2026-11-01T10:00:00Z', quantity_female=20,
                       quantity_male=0, data={'movement': 'sale'})]
        ns = self.ns({'effective_operations_events': events})
        result = ns['series_productivas']([self.daily()], [lot])
        self.assertEqual(result.iloc[0]['aves_vivas'], 80)
        self.assertEqual(result.iloc[0]['mortalidad_pct'], 0)
        self.assertIsNone(result.iloc[0]['fcr_acumulado'])
        self.assertAlmostEqual(result.iloc[0]['peso_promedio_mixto_g'], 1025)

    def test_stage_boundary_is_local_and_manager_sex_filter_never_splits_feed(self):
        lots = [self.lot(1), self.lot(2, active=False)]
        records = [self.daily(i * 10 + day, lot=i, day=day) for i in (1, 2) for day in (1, 2)]
        stage_events = [dict(id='stage-' + str(i), organization_id='org-a', kind='stage', lote_id=i,
                            observed_at='2026-11-02T06:00:00Z', stage='produccion') for i in (1, 2)]
        ui = UI({'Población representada': 'Hembras', 'Etapa productiva observada': 'produccion'})
        ns = self.ns({'lotes': lots, 'registros_diarios': records, 'effective_operations_events': stage_events}, ui)
        captured = []
        ns['mostrar_lineas'] = lambda curves, metrics, *args: captured.append((curves, metrics))
        ns['mostrar_tabla'] = lambda *args: None
        self.run_view('📈 Análisis Gerencial', ns)
        curves, metrics = captured[0]
        self.assertEqual([m[0] for m in metrics], ['peso_promedio_hembra_g', 'mortalidad_hembra_pct'])
        self.assertTrue(all(set(frame['dia_vida']) == {2} for _, frame, _ in curves))
        self.assertTrue(all('fcr_acumulado' != m[0] for m in metrics))
        self.assertTrue(any('cada indicador' in text for text in ui.messages))

    def test_overview_shortcuts_open_capture_and_agenda_without_writing(self):
        for action, expected in [('avi_home_daily', '4. Ingreso Diario'), ('avi_home_agenda', 'Centro de operación')]:
            ui = UI({'click': action})
            ns = self.ns({'lotes': [self.lot()]}, ui)
            with self.assertRaises(NavigationRequested):
                self.run_view('📊 Overview General', ns)
            self.assertEqual(ui.session_state['opcion_nav'], expected)
            if action == 'avi_home_agenda':
                self.assertEqual(ui.session_state['op_workspace_section'], 'Agenda e incidencias')

    def test_overview_ignores_withdrawn_daily_and_accounts_sales(self):
        today = datetime.now(ZoneInfo('America/Bogota')).date()
        records = [self.daily(1, status='submitted', fecha=today.isoformat(), mortalidad_hembra=2),
                   self.daily(2, status='draft', fecha=today.isoformat(), mortalidad_hembra=50, consumo_alimento_kg=5000)]
        event = dict(id='sale', organization_id='org-a', kind='bird_movement', lote_id=1, box_id=10,
                     observed_at=today.isoformat() + 'T12:00:00Z', quantity_female=20,
                     quantity_male=0, data={'movement': 'sale'})
        ui = UI()
        ns = self.ns({'lotes': [self.lot()], 'registros_diarios': records, 'effective_operations_events': [event]}, ui)
        ns['mostrar_lineas'] = lambda *args: None
        ns['mostrar_tabla'] = lambda *args: None
        self.run_view('📊 Overview General', ns)
        self.assertEqual(ui.metrics['Aves vivas estimadas'], '78')
        self.assertEqual(ui.metrics['Mortalidad registrada'], '2')
        self.assertEqual(ui.metrics['Alimento registrado'], '10 kg')
        self.assertEqual(ui.progress_value, 1)
        self.assertTrue(any('1 de 1 lotes' in message for message in ui.messages))


if __name__ == '__main__':
    unittest.main()
