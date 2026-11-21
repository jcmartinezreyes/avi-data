"""Check the real app save block with a fake RPC client and no network access."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SaveStopped(Exception):
    pass


class PhaseTwoSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((ROOT / 'app.py').read_text())
        cls.save_code = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            for i, statement in enumerate(node.body):
                if not isinstance(statement, ast.Try):
                    continue
                if not any(
                    isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == 'rpc' and call.args
                    and isinstance(call.args[0], ast.Constant)
                    and call.args[0].value == 'save_lote_with_boxes'
                    for call in ast.walk(statement)
                ):
                    continue
                assignment = node.body[i - 1]
                cls.save_code = compile(ast.fix_missing_locations(ast.Module(
                    body=[assignment, statement], type_ignores=[],
                )), 'app.py', 'exec')
        if cls.save_code is None:
            raise AssertionError('Could not find the atomic save entry point')

    def run_save(self, edit, fail=False):
        calls, errors = [], []

        def stop():
            raise SaveStopped()

        def rpc(name, payload):
            calls.append((name, payload))

            def execute():
                if fail:
                    raise RuntimeError('Simulated database rollback')
                return SimpleNamespace(data=123)

            return SimpleNamespace(execute=execute)

        namespace = {
            'datos_boxes_inputs': [
                {'id': 41 if edit else None, 'nombre_box': 'Original box name', 'hembras': 3, 'machos': 2},
                {'id': None, 'nombre_box': 'New box', 'hembras': 2, 'machos': 3},
            ],
            'datos_lote': {'codigo_lote': 'TEST'},
            'lote_edit': {'id': 9} if edit else None,
            'es_edicion': edit,
            'supabase': SimpleNamespace(rpc=rpc),
            'st': SimpleNamespace(error=errors.append, stop=stop),
        }
        if fail:
            with self.assertRaises(SaveStopped):
                exec(self.save_code, namespace)
        else:
            exec(self.save_code, namespace)
        return calls, errors

    def test_edit_sends_existing_ids_and_names_in_one_transaction(self):
        calls, errors = self.run_save(edit=True)
        self.assertEqual(len(calls), 1)
        name, payload = calls[0]
        self.assertEqual(name, 'save_lote_with_boxes')
        self.assertEqual(payload['p_lote_id'], 9)
        self.assertEqual(payload['p_boxes'][0], {
            'id': 41, 'nombre_box': 'Original box name',
            'aves_hembra_inicial': 3, 'aves_macho_inicial': 2,
        })
        self.assertIsNone(payload['p_boxes'][1]['id'])
        self.assertEqual(errors, [])

    def test_new_lot_uses_null_id(self):
        calls, errors = self.run_save(edit=False)
        self.assertIsNone(calls[0][1]['p_lote_id'])
        self.assertTrue(all(box['id'] is None for box in calls[0][1]['p_boxes']))
        self.assertEqual(errors, [])

    def test_rpc_failure_stops_without_fallback_writes(self):
        calls, errors = self.run_save(edit=True, fail=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn('historial', errors[0])


if __name__ == '__main__':
    unittest.main()
