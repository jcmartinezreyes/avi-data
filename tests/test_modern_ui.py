"""Behavioral UX regressions for capture progress and truthful measurements.

Uses the existing synthetic client fixture; never reaches production or a network.
"""
import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
fixture_tree = ast.parse((ROOT / 'tests/test_operations_ui.py').read_text())
HARNESS = ast.literal_eval(next(node.value for node in fixture_tree.body
    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'HARNESS'
                                          for target in node.targets)))


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Install application dependencies')
class ModernCaptureTests(unittest.TestCase):
    def render(self, harness=HARNESS):
        from streamlit.testing.v1 import AppTest
        code = harness.replace('ROLE', repr('owner')).replace('SECTION', repr('Jornada'))
        app = AppTest.from_string(code).run(timeout=20)
        self.assertFalse(app.exception, str(app.exception))
        self.assertFalse(app.error, str([error.value for error in app.error]))
        return app

    def test_draft_keeps_measured_zero_and_missing_consumption_distinct(self):
        code = HARNESS.replace("def rpc(self,*args,**kwargs):raise AssertionError('A read-only page must not write')", """def rpc(self,name,payload):
  st.session_state['last_command']=(name,payload)
  return SimpleNamespace(execute=lambda:SimpleNamespace(data=None))""")
        app = self.render(code)
        deaths = next(field for field in app.number_input if field.label == 'Muertas · hembras')
        deaths.set_value(0).run()
        app.button(key='op_daily_save').click().run()
        command, payload = app.session_state['last_command']
        self.assertEqual(command, 'save_daily_capture')
        self.assertEqual(payload['p_status'], 'draft')
        self.assertEqual(payload['p_boxes'][0]['mortalidad_hembra'], 0)
        self.assertIsNone(payload['p_boxes'][0]['consumo_alimento_kg'])
        self.assertEqual(payload['p_boxes'][0]['measurement_states']['mortalidad_hembra'], 'measured')
        self.assertEqual(payload['p_boxes'][0]['measurement_states']['consumo_alimento_kg'], 'not_measured')

    def test_review_checkbox_never_submits_incomplete_capture(self):
        app = self.render()
        app.checkbox(key='op_daily_confirm').check().run()
        self.assertTrue(app.button(key='op_daily_submit').disabled)
        self.assertNotIn('last_command', app.session_state)

    def test_received_sex_remains_visible_even_if_initial_count_was_zero(self):
        female_only = HARNESS.replace("'aves_macho_inicial':10", "'aves_macho_inicial':0")
        without_arrival = self.render(female_only)
        self.assertNotIn('Muertas · machos', [field.label for field in without_arrival.number_input])
        event = """'effective_operations_events':[{'id':'transfer','kind':'bird_movement','lote_id':99,'box_id':99,'observed_at':'2026-11-25T12:00:00-05:00','quantity_female':0,'quantity_male':5,'data':{'movement':'transfer','destination_box_id':2}}], 'registros_diarios':[], 'metricas_produccion':[]"""
        incoming = female_only.replace("'registros_diarios':[], 'metricas_produccion':[]", event)
        with_arrival = self.render(incoming)
        self.assertIn('Muertas · machos', [field.label for field in with_arrival.number_input])

    def test_first_incomplete_box_is_open_without_expanding_completed_boxes(self):
        code = HARNESS.replace("lot={'id':1", "box2=dict(box,id=3,nombre_box='Box pendiente')\nlot={'id':1")
        code = code.replace("'galpon_boxes':[box]", "'galpon_boxes':[box,box2]")
        code = code.replace("data={'galpon_boxes':[box]", "data={'galpon_boxes':[box,box2]")
        capture = """'daily_captures':[{'id':'capture','lote_id':1,'fecha':'2026-11-25','status':'draft','source':'manual','version':1,'payload':[{'box_id':2,'mortalidad_hembra':0,'mortalidad_macho':0,'descarte_hembra':0,'descarte_macho':0,'consumo_alimento_kg':1.0,'consumo_agua_litros':2.0},{'box_id':3}]}], 'registros_diarios':[], 'metricas_produccion':[]"""
        code = code.replace("'registros_diarios':[], 'metricas_produccion':[]", capture)
        app = self.render(code)
        complete = next(panel for panel in app.expander if panel.label.startswith('Box de prueba'))
        pending = next(panel for panel in app.expander if panel.label.startswith('Box pendiente'))
        self.assertFalse(complete.proto.expanded)
        self.assertTrue(pending.proto.expanded)


if __name__ == '__main__':
    unittest.main()
