"""Presentation changes must keep data entry safe and navigation side-effect free."""
import unittest
from unittest.mock import patch

from ui_design import context_card, workflow_steps


class PresentationSafetyTests(unittest.TestCase):
    def test_customer_text_is_escaped_in_context_and_step_labels(self):
        with patch('streamlit.markdown') as render:
            context_card('<img src=x>', '<script>alert(1)</script>', status='<b>Pending</b>', tone='" onclick="x')
            markup = render.call_args.args[0]
            self.assertNotIn('<img src=x>', markup)
            self.assertNotIn('<script>', markup)
            self.assertIn('&lt;script&gt;', markup)
            self.assertNotIn('onclick=', markup)
            workflow_steps(['<svg>', 'Revisar'], current=1)
            markup = render.call_args.args[0]
            self.assertNotIn('<svg>', markup)
            self.assertEqual(markup.count('aria-current="step"'), 1)


class WorkspaceBehaviorTests(unittest.TestCase):
    def harness(self):
        from tests.test_operations_ui import HARNESS
        return HARNESS.replace('ROLE', repr('owner')).replace('SECTION', 'None')

    def test_visible_navigation_renders_only_selected_workspace(self):
        from streamlit.testing.v1 import AppTest
        code = self.harness().replace('class Client:', "st.session_state['queried_tables']=[]\nclass Client:")
        code = code.replace('def table(self,name):return Query(name)', "def table(self,name):\n  st.session_state['queried_tables'].append(name)\n  return Query(name)")
        app = AppTest.from_string(code).run()
        self.assertFalse(app.exception)
        self.assertIn('daily_captures', app.session_state['queried_tables'])
        navigation = app.get('button_group')[0]
        self.assertEqual(len(navigation.options), 7)
        navigation.set_value('Importar planillas').run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.session_state['queried_tables'], [])
        self.assertFalse(any(button.key == 'op_daily_save' for button in app.button))

    def test_grouped_import_preserves_mapping_units_and_confirmation(self):
        from streamlit.testing.v1 import AppTest
        code = self.harness().replace('initial_section=None', "initial_section='Importar planillas'")
        code = code.replace("render_operations(Client()", """from unittest.mock import patch
from io import BytesIO
upload=BytesIO(b'lote_id,box_id,fecha,mortalidad_hembra,consumo_alimento_kg\\n1,2,2026-11-25,0,1000\\n')
upload.name='sintetico.csv'
patcher=patch('streamlit.file_uploader',return_value=upload)
with patcher:
 render_operations(Client()""")
        app = AppTest.from_string(code).run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertFalse(app.error, str([error.value for error in app.error]))
        self.assertEqual(app.selectbox(key='op_import_map_consumo_alimento_kg').value, 'consumo_alimento_kg')
        app.selectbox(key='op_import_unit_consumo_alimento_kg').select('g').run()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key='op_import_save').disabled)
        self.assertIn('Pesos opcionales', [panel.label for panel in app.expander])

    def test_reload_discards_local_edits_even_when_server_version_is_unchanged(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string(self.harness()).run()
        next(field for field in app.number_input if field.label == 'Muertas · hembras').set_value(5).run()
        app.button(key='op_daily_reload').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertIsNone(next(field for field in app.number_input if field.label == 'Muertas · hembras').value)

    def test_success_feedback_survives_save_rerun(self):
        from streamlit.testing.v1 import AppTest
        code = self.harness().replace("def rpc(self,*args,**kwargs):raise AssertionError('A read-only page must not write')", """def rpc(self,name,payload):
  return SimpleNamespace(execute=lambda:SimpleNamespace(data={'id':'capture','version':1,'status':'draft'}))""")
        app = AppTest.from_string(code).run()
        app.button(key='op_daily_save').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Borrador guardado' in notice.value for notice in app.success))


if __name__ == '__main__':
    unittest.main()
