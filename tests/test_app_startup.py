"""Exercise the real entry point, including the browser-session component.

Run after installing requirements.txt with Python 3.11. No real credentials or
network requests are used: the app stops at its sign-in form.
"""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Install application dependencies first')
class ApplicationStartupTests(unittest.TestCase):
    def test_login_and_persistent_session_component_start(self):
        from streamlit.testing.v1 import AppTest

        root = Path(__file__).resolve().parents[1]
        with patch.dict(os.environ, {
            'SUPABASE_URL': 'https://example.supabase.co',
            'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_startup_test',
        }):
            app = AppTest.from_file(str(root / 'app.py')).run(timeout=30)
        self.assertFalse(app.exception, str(app.exception))
        self.assertIn('Correo electrónico', [field.label for field in app.text_input])
        self.assertIn('Contraseña', [field.label for field in app.text_input])
        self.assertIn('Iniciar sesión', [button.label for button in app.button])


if __name__ == '__main__':
    unittest.main()
