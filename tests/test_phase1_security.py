"""Local Phase 1 checks, without real credentials or network connections.

Run with python3 -m unittest discover -s tests -p 'test_phase1_security.py'.
Database authorization checks are in phase1_rls_permissions.sql.
"""
import ast
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class StreamlitStop(Exception):
    pass


class StreamlitStub:
    def __init__(self):
        self.errors = []
        self.secrets = {}

    def error(self, message):
        self.errors.append(message)

    def stop(self):
        raise StreamlitStop()


class PhaseOneSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / 'app.py').read_text()
        tree = ast.parse(source)

        def assigns(node, name):
            return isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )

        start = next(i for i, node in enumerate(tree.body) if assigns(node, 'URL'))
        end = next(i for i, node in enumerate(tree.body) if assigns(node, 'supabase'))
        helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'configuracion']
        config = ast.Module(body=helpers + tree.body[start:end + 1], type_ignores=[])
        cls.config_code = compile(ast.fix_missing_locations(config), 'app.py', 'exec')

    def run_config(self, environment):
        calls = []
        streamlit = StreamlitStub()
        stopped = False
        namespace = {
            'os': os,
            'st': streamlit,
            'ClientOptions': lambda **kwargs: SimpleNamespace(**kwargs),
            'create_client': lambda *args, **kwargs: calls.append(args),
        }
        with patch.dict(os.environ, environment, clear=True):
            try:
                exec(self.config_code, namespace)
            except StreamlitStop:
                stopped = True
        return calls, streamlit.errors, stopped

    def test_missing_or_blank_configuration_stops_before_connection(self):
        for environment in (
            {},
            {'SUPABASE_URL': 'https://example.supabase.co'},
            {'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_example'},
            {'SUPABASE_URL': ' ', 'SUPABASE_PUBLISHABLE_KEY': '\t'},
        ):
            with self.subTest(environment=environment):
                calls, errors, stopped = self.run_config(environment)
                self.assertTrue(stopped)
                self.assertEqual(calls, [])
                self.assertEqual(len(errors), 1)

    def test_valid_environment_is_used_without_fallback(self):
        calls, errors, stopped = self.run_config({
            'SUPABASE_URL': ' https://example.supabase.co ',
            'SUPABASE_PUBLISHABLE_KEY': ' sb_publishable_example ',
        })
        self.assertFalse(stopped)
        self.assertEqual(errors, [])
        self.assertEqual(calls, [('https://example.supabase.co', 'sb_publishable_example')])

    def test_devcontainer_does_not_override_security(self):
        text = (ROOT / '.devcontainer/devcontainer.json').read_text()
        config = json.loads(re.sub(r'^\s*//.*$', '', text, flags=re.M))
        self.assertEqual(config['postAttachCommand']['server'], 'streamlit run app.py')

    def test_streamlit_security_is_explicit(self):
        text = (ROOT / '.streamlit/config.toml').read_text()
        self.assertRegex(text, r'(?m)^\[server\]$')
        for setting in ('enableCORS = true', 'enableXsrfProtection = true', 'maxUploadSize = 10'):
            self.assertIn(setting, text.split('[server]', 1)[1].split('[', 1)[0])

    def test_environment_template_contains_placeholders(self):
        entries = dict(
            line.split('=', 1) for line in (ROOT / '.env.example').read_text().splitlines()
            if line and not line.startswith('#')
        )
        self.assertEqual(entries['SUPABASE_URL'], 'https://tu-proyecto.supabase.co')
        self.assertEqual(entries['SUPABASE_PUBLISHABLE_KEY'], 'sb_publishable_tu_clave_publica_aqui')

    def test_local_secrets_are_ignored(self):
        lines = (ROOT / '.gitignore').read_text().splitlines()
        for rule in ('.env', '.env.*', '!.env.example', '.streamlit/secrets.toml'):
            self.assertIn(rule, lines)


if __name__ == '__main__':
    unittest.main()
