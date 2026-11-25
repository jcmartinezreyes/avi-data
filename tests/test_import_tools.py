import io
import unittest
import zipfile
from import_tools import inspect_upload, preview_import


class ImportTests(unittest.TestCase):
    def preview(self, body, **kwargs):
        return preview_import(body.encode(), 'source.csv', {'lote_id': 'lot', 'fecha': 'date', 'kg': 'feed'},
                              units={'kg': 'g'}, **kwargs)

    def test_units_zero_missing_and_duplicate_identity(self):
        result = self.preview('lot,date,feed\nA,2026-01-01,1000\nA,2026-01-02,0\nA,2026-01-03,\nA,2026-01-01,2000\n')
        self.assertEqual([r['kg'] for r in result['valid']], [1, 0])
        self.assertEqual(len(result['pending']), 1)
        self.assertEqual(len(result['duplicates']), 1)
        key = result['valid'][0]['_key']
        retry = self.preview('lot,date,feed\nA,2026-01-01,1000', existing_keys=[key])
        self.assertEqual(len(retry['duplicates']), 1)

    def test_formula_weekly_and_ambiguous_date_do_not_become_events(self):
        self.assertEqual(len(self.preview('lot,date,feed\nA,2026-01-01,=SUM(A1:A3)')['pending']), 1)
        self.assertEqual(len(self.preview('lot,date,feed\nA,2026-01-01,100', period='weekly')['pending']), 1)
        self.assertEqual(len(self.preview('lot,date,feed\nA,01/02/2026,100')['invalid']), 1)
        self.assertEqual(self.preview('lot,date,feed\nA,01/02/2026,100', date_format='%d/%m/%Y')['valid'][0]['fecha'], '2026-02-01')

    def test_reject_invalid_units_without_leaking_private_values(self):
        result = preview_import(b'lot,date,feed\nPrivateName,2026-01-01,100', 'private.csv',
                                {'lote_id': 'lot', 'fecha': 'date', 'kg': 'feed'}, units={'kg': 'lbs'})
        self.assertEqual(len(result['invalid']), 1)
        self.assertNotIn('PrivateName', str(result['invalid']))

    def test_csv_limits_fail_safely_and_anonymously(self):
        with self.assertRaisesRegex(ValueError, 'CSV no válido'):
            inspect_upload(('header\n' + 'x' * 140000).encode(), 'private.csv')
        with self.assertRaisesRegex(ValueError, 'Demasiadas filas'):
            inspect_upload(('header\n' + 'row\n' * 10001).encode(), 'private.csv')

    def test_xlsx_formula_macro_external_links_and_zip_bomb(self):
        def book(extra=None, cell='<c r="A2"><v>5</v></c>'):
            target = io.BytesIO()
            with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as out:
                out.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
                out.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>test</t></is></c></row><row>' + cell + '</row></sheetData></worksheet>')
                if extra:
                    out.writestr(*extra)
            return target.getvalue()
        result = inspect_upload(book(cell='<c r="A2"><f>1+1</f><v>2</v></c>'), 'sample.xlsx')
        self.assertEqual(result['formula_cells'], 1)
        for name in ('xl/vbaProject.bin', 'xl/externalLinks/externalLink1.xml', '../outside.xml'):
            with self.assertRaises(ValueError):
                inspect_upload(book((name, '')), 'sample.xlsx')
        with self.assertRaises(ValueError):
            inspect_upload(book(('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="x" Target="https://example.com" TargetMode="External"/></Relationships>')), 'sample.xlsx')
        with self.assertRaises(ValueError):
            inspect_upload(book(('xxe.rels', '<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>')), 'sample.xlsx')
        with self.assertRaises(ValueError):
            inspect_upload(b'not a workbook', 'sample.xlsm')


if __name__ == '__main__':
    unittest.main()
