import copy
import json
import unittest
from cycle_report import build_frozen_report


class FrozenReportTests(unittest.TestCase):
    def sample(self):
        return {'rules_version':'avilab-2026-11','lote':{'id':1,'codigo_lote':'PRIVATE-CLIENT',
            'fecha_encaste':'2026-11-25','aves_hembra':100,'aves_macho':0,'aves_totales':100,
            'tipo_produccion':'engorde','is_synthetic':True},'boxes':[], 'daily_details':[],
            'daily_records':[{'id':3,'lote_id':1,'fecha':'2026-11-25','dia_vida':1,
            'mortalidad_hembra':2,'mortalidad_macho':0,'descarte_hembra':0,'descarte_macho':0,
            'consumo_alimento_kg':10,'consumo_agua_litros':20,'peso_promedio_hembra_g':1000,
            'peso_promedio_macho_g':None,'peso_promedio_mixto_g':1000}], 'events':[],
            'incidents':[{'title':'PRIVATE-CLIENT incident'}]}

    def test_frozen_legacy_production_preserves_indicators_and_anonymity(self):
        content = self.sample()
        report = build_frozen_report(content, 1)
        data = json.loads(report['content'])
        self.assertNotIn('PRIVATE-CLIENT', report['content'])
        self.assertEqual(report['indicators'][0]['aves_vivas'],98)
        self.assertAlmostEqual(report['indicators'][0]['fcr_acumulado'],10/98)
        observed = next(e for e in data['events'] if e['kind']=='daily_observed')
        self.assertEqual(observed['payload']['consumo_alimento_kg'],10)
        self.assertIsNone(observed['payload']['peso_promedio_macho_g'])
        self.assertEqual(report['sha256'],build_frozen_report(copy.deepcopy(content),1)['sha256'])
        self.assertTrue(all('denominator' in r for r in data['rules']))

    def test_new_version_retains_prior_and_complete_export_evidence(self):
        content = self.sample()
        before = build_frozen_report(content,1)
        changed = copy.deepcopy(content)
        changed['daily_records'][0]['consumo_alimento_kg']=12
        after = build_frozen_report(changed,2)
        self.assertNotEqual(before['sha256'],after['sha256'])
        self.assertEqual(before['sha256'],build_frozen_report(content,1)['sha256'])
        internal = build_frozen_report(content,1,anonymize=False)
        self.assertIn('evidence',json.loads(internal['content']))
        self.assertIn('PRIVATE-CLIENT',internal['content'])


if __name__=='__main__': unittest.main()
