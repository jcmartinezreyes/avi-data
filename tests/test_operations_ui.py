"""Render every operational workflow using a synthetic scoped client, no network."""
import importlib.util
import unittest
from textwrap import dedent

HARNESS = '''
import streamlit as st
from types import SimpleNamespace
from datetime import date
from operations_ui import render_operations
box={'id':2,'lote_id':1,'nombre_box':'Box de prueba','aves_hembra_inicial':10,'aves_macho_inicial':10}
lot={'id':1,'codigo_lote':'SINTETICO-UI','activo':True,'fecha_encaste':'2026-11-24',
     'tipo_produccion':'reproductoras','linea_genetica':'Referencia sintética','aves_totales':20,'aves_hembra':10,'aves_macho':10,
     'is_synthetic':True,'galpon_boxes':[box], 'galpones':{'id':1,'nombre':'Galpón de prueba','granjas':{'id':1,'nombre':'Granja sintética'}}}
class Query:
 def __init__(self, table):self.name=table
 def __getattr__(self,name):return lambda *args,**kwargs:self
 def execute(self):
  data={'galpon_boxes':[box],'organizations':[{'id':'org','name':'Organización sintética'}],
        'granjas':[{'id':1,'nombre':'Granja sintética'}], 'organization_memberships':[{'user_id':'user','role':'owner'}],
        'registros_diarios':[], 'metricas_produccion':[]}.get(self.name,[])
  return SimpleNamespace(data=data)
class Client:
 def table(self,name):return Query(name)
 def rpc(self,*args,**kwargs):raise AssertionError('A read-only page must not write')
render_operations(Client(),'org','user',ROLE,[lot],date(2026,11,25),initial_section=SECTION)
'''


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Install app dependencies')
class OperationsUITests(unittest.TestCase):
    def render(self, section, role='owner'):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string(HARNESS.replace('ROLE', repr(role)).replace('SECTION', repr(section))).run(timeout=20)
        self.assertFalse(app.exception, str(app.exception))
        self.assertFalse(app.error, str([e.value for e in app.error]))
        return app

    def test_all_workspaces_load_without_writes(self):
        from operations_ui import SECTIONS
        for section in SECTIONS:
            with self.subTest(section=section):
                self.render(section)

    def test_every_trace_tool_loads(self):
        app = self.render('Trazabilidad y análisis')
        for mode in app.selectbox(key='op_trace_mode').options:
            with self.subTest(mode=mode):
                app.selectbox(key='op_trace_mode').select(mode).run()
                self.assertFalse(app.exception, str(app.exception))
                self.assertFalse(app.error, str([e.value for e in app.error]))

    def test_each_productive_event_loads(self):
        app = self.render('Eventos productivos')
        for kind in app.selectbox(key='op_event_kind').options:
            with self.subTest(event=kind):
                app.selectbox(key='op_event_kind').select(kind).run()
                self.assertFalse(app.exception, str(app.exception))
                self.assertFalse(app.error, str([e.value for e in app.error]))

    def test_form_keeps_original_version_when_server_changes_during_edit(self):
        from streamlit.testing.v1 import AppTest
        code = HARNESS.replace('ROLE', repr('owner')).replace('SECTION', repr('Jornada'))
        code = code.replace("'registros_diarios':[], 'metricas_produccion':[]", """'daily_captures':[{'id':'capture','lote_id':1,'fecha':'2026-11-25','status':'submitted','source':'manual','version':st.session_state.get('server_version',1),'payload':[{'box_id':2,'mortalidad_hembra':0,'mortalidad_macho':0,'descarte_hembra':0,'descarte_macho':0,'consumo_alimento_kg':1.0,'consumo_agua_litros':2.0}]}], 'registros_diarios':[], 'metricas_produccion':[]""")
        code = code.replace("def rpc(self,*args,**kwargs):raise AssertionError('A read-only page must not write')", """def rpc(self,name,payload):
  st.session_state['sent_payload']=payload
  def execute():raise RuntimeError('40001 version conflict')
  return SimpleNamespace(execute=execute)""")
        app=AppTest.from_string(code).run()
        app.session_state['server_version']=2
        app.checkbox(key='op_daily_confirm').check().run()
        self.assertTrue(any('más reciente' in item.value for item in app.warning))
        app.button(key='op_daily_submit').click().run()
        self.assertEqual(app.session_state['sent_payload']['p_expected_version'],1)
        self.assertTrue(any('Otra persona' in error.value for error in app.error))

    def test_analyst_has_no_daily_submission_or_management_controls(self):
        app = self.render('Jornada', 'analyst')
        keys = [b.key for b in app.button]
        for key in ['op_daily_save','op_daily_submit','op_review','op_period_close','op_period_reopen']:
            self.assertNotIn(key, keys)


if __name__ == '__main__':
    unittest.main()
