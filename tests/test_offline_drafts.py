"""Offline files preserve version identity and never store auth credentials."""
from datetime import date, datetime, timezone
import json
import re
import unittest
from offline_drafts import offline_editor


class OfflineDraftTests(unittest.TestCase):
    def test_export_retains_nulls_zero_version_and_expiry(self):
        html = offline_editor('org', 'user', 1, date(2026, 11, 25),
                              [{'box_id': 2, 'mortalidad_hembra': 0, 'peso_promedio_hembra_g': None}],
                              7, now=datetime(2026, 11, 25, tzinfo=timezone.utc))
        data = json.loads(re.search(r'const draft=(.*?), fields=', html).group(1))
        self.assertEqual(data['version'], 7)
        self.assertEqual(data['expires_at'], '2026-12-02T00:00:00+00:00')
        self.assertIsNone(data['boxes'][0]['peso_promedio_hembra_g'])
        self.assertEqual(data['boxes'][0]['mortalidad_hembra'], 0)
        self.assertEqual(data['format'], 'avidata-draft-v1')
        self.assertNotIn('access_token', html)
        self.assertIn("connect-src 'none'", html)

    def test_untrusted_text_cannot_escape_script(self):
        html = offline_editor('org', 'user', 1, '2026-11-25',
                              [{'box_id': 2, 'note': '</script><img src=x onerror=alert(1)>'}], 0)
        self.assertEqual(html.count('</script>'), 1)
        self.assertNotIn('<img src=x', html)
        self.assertIn('\\u003c/script\\u003e', html)


if __name__ == '__main__':
    unittest.main()
