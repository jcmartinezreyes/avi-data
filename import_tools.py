"""Read-only, bounded CSV/XLSX preview. Never executes spreadsheet code.

Only explicit daily rows can become daily candidates. Formula cells, macros,
external links and weekly summaries are rejected or held for human review.
No customer-specific headers/values are included in validation error messages.
"""
import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import PurePath
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from avilab_domain import number

MAX_BYTES = 10 * 1024 * 1024
MAX_XML_BYTES = 50 * 1024 * 1024
MAX_ROWS = 10000
MAX_COLUMNS = 200
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
FORMULA = object()
NUMERIC_FIELDS = {'value', 'count', 'kg', 'liters', 'mortalidad_hembra', 'mortalidad_macho',
                  'descarte_hembra', 'descarte_macho', 'consumo_alimento_kg', 'consumo_agua_litros',
                  'peso_promedio_hembra_g', 'peso_promedio_macho_g', 'sample_n', 'temperature_c', 'humidity_pct'}
INTEGER_FIELDS = {'count', 'sample_n', 'mortalidad_hembra', 'mortalidad_macho', 'descarte_hembra', 'descarte_macho'}
UNIT_TARGETS = {'kg': ('kg', {'kg': 1, 'g': .001, 't': 1000}),
                'consumo_alimento_kg': ('kg', {'kg': 1, 'g': .001, 't': 1000}),
                'liters': ('L', {'L': 1, 'l': 1, 'm3': 1000}),
                'consumo_agua_litros': ('L', {'L': 1, 'l': 1, 'm3': 1000}),
                'peso_promedio_hembra_g': ('g', {'g': 1, 'kg': 1000}),
                'peso_promedio_macho_g': ('g', {'g': 1, 'kg': 1000})}


def _column_index(reference):
    result = 0
    match = re.fullmatch(r'([A-Z]{1,3})[1-9][0-9]{0,6}', reference)
    if not match:
        raise ValueError('Referencia de celda no válida')
    for char in match.group(1):
        result = result * 26 + ord(char) - 64
    return result - 1


def _xlsx(data, sheet_index):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError('Archivo XLSX no válido') from exc
    with archive:
        names = archive.namelist()
        if any(PurePath(name).is_absolute() or '..' in PurePath(name).parts or '\\' in name for name in names):
            raise ValueError('Ruta interna de archivo no permitida')
        if any(info.file_size > 1024 * 1024 and info.file_size / max(info.compress_size, 1) > 1000 for info in archive.infolist()):
            raise ValueError('Compresión de archivo no permitida')
        if len(names) > 2000 or sum(info.file_size for info in archive.infolist()) > MAX_XML_BYTES:
            raise ValueError('Archivo expandido demasiado grande')
        if any('vbaproject' in n.lower() or 'externallinks/' in n.lower() for n in names):
            raise ValueError('No se admiten macros ni vínculos externos')
        def xml(name):
            raw = archive.read(name)
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                raise ValueError('XML con entidades no permitido')
            return ET.fromstring(raw)
        for rel_name in [n for n in names if n.endswith('.rels')]:
            if any(item.attrib.get('TargetMode', '').lower() == 'external' for item in xml(rel_name)):
                raise ValueError('No se admiten vínculos externos')
        sheets = sorted([n for n in names if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)],
                        key=lambda n: int(re.search(r'sheet(\d+)', n).group(1)))
        # Follow workbook relationships: sheet1.xml is not necessarily tab one.
        workbook = xml('xl/workbook.xml')
        if 'xl/_rels/workbook.xml.rels' in names:
            relationships = xml('xl/_rels/workbook.xml.rels')
            targets = {item.attrib.get('Id'): item.attrib.get('Target', '') for item in relationships}
            ordered_sheets = []
            relation_key = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
            for sheet in workbook.findall('s:sheets/s:sheet', NS):
                target = targets.get(sheet.attrib.get(relation_key), '')
                path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
                if path in sheets:
                    ordered_sheets.append(path)
            if ordered_sheets:
                sheets = ordered_sheets
        if isinstance(sheet_index, bool) or sheet_index < 0 or sheet_index >= len(sheets):
            raise ValueError('Hoja no disponible')
        shared = []
        if 'xl/sharedStrings.xml' in names:
            shared = [''.join(si.itertext()) for si in xml('xl/sharedStrings.xml').findall('s:si', NS)]
        date_styles = set()
        if 'xl/styles.xml' in names:
            styles = xml('xl/styles.xml')
            custom = {int(v.attrib['numFmtId']): v.attrib.get('formatCode', '') for v in styles.findall('s:numFmts/s:numFmt', NS)}
            for i, xf in enumerate(styles.findall('s:cellXfs/s:xf', NS)):
                fmt = int(xf.attrib.get('numFmtId', 0))
                pattern = re.sub(r'"[^"]*"|\[[^\]]*\]', '', custom.get(fmt, '')).lower()
                if 14 <= fmt <= 22 or (('d' in pattern or 'y' in pattern) and 'm' in pattern):
                    date_styles.add(i)
        props = workbook.find('s:workbookPr', NS)
        epoch = datetime(1904, 1, 1) if props is not None and props.attrib.get('date1904') in ('1', 'true') else datetime(1899, 12, 30)
        rows = []
        for source in xml(sheets[sheet_index]).findall('s:sheetData/s:row', NS):
            if len(rows) > MAX_ROWS:
                raise ValueError('Demasiadas filas')
            row = []
            for cell in source.findall('s:c', NS):
                col = _column_index(cell.attrib.get('r', 'A1'))
                if col >= MAX_COLUMNS:
                    raise ValueError('Demasiadas columnas')
                row.extend([None] * max(0, col + 1 - len(row)))
                node = cell.find('s:v', NS)
                raw = node.text if node is not None else None
                kind = cell.attrib.get('t')
                if cell.find('s:f', NS) is not None:
                    value = FORMULA
                elif kind == 's':
                    value = shared[int(raw)] if raw is not None else None
                elif kind == 'inlineStr':
                    value = ''.join(cell.find('s:is', NS).itertext())
                elif kind in ('str', 'd', 'e'):
                    value = raw
                elif kind == 'b':
                    value = raw == '1'
                elif raw is None:
                    value = None
                else:
                    value = float(raw)
                    if int(cell.attrib.get('s', 0)) in date_styles:
                        value = (epoch + timedelta(days=value)).date().isoformat()
                row[col] = value
            if any(v is not None for v in row):
                rows.append(row)
        return rows


def inspect_upload(data, filename, sheet_index=0):
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        raise ValueError('Archivo vacío o superior a 10 MB')
    suffix = PurePath(filename).suffix.lower()
    if suffix == '.xlsx':
        try:
            raw_rows = _xlsx(data, sheet_index)
        except (ET.ParseError, DefusedXmlException, KeyError, IndexError, OverflowError, TypeError, AttributeError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
            raise ValueError('Estructura XLSX no válida o no admitida') from exc
    elif suffix in ('.csv', '.tsv'):
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('Guarde el CSV como UTF-8') from exc
        delimiter = '\t' if suffix == '.tsv' else ','
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=',;\t').delimiter
        except csv.Error:
            pass
        raw_rows = []
        try:
            for row in csv.reader(io.StringIO(text), delimiter=delimiter):
                if len(raw_rows) >= MAX_ROWS + 1 or len(row) > MAX_COLUMNS:
                    raise ValueError('Demasiadas filas o columnas')
                raw_rows.append(row)
        except csv.Error as exc:
            raise ValueError('CSV no válido o con una celda demasiado grande') from exc
    else:
        raise ValueError('Use CSV, TSV o XLSX sin macros')
    if not raw_rows:
        raise ValueError('No hay filas')
    header = [str(v).strip() if v is not None and v is not FORMULA else '' for v in raw_rows[0]]
    if any(not v for v in header) or len(set(header)) != len(header):
        raise ValueError('Los encabezados deben ser únicos y no vacíos')
    rows = []
    formulas = 0
    for index, values in enumerate(raw_rows[1:], start=2):
        if not any(v not in (None, '') for v in values):
            continue
        formula_columns = []
        row = {}
        for col, name in enumerate(header):
            value = values[col] if col < len(values) else None
            if value is FORMULA or isinstance(value, str) and value.lstrip().startswith(('=', '+', '@')):
                formula_columns.append(name)
                value = None
                formulas += 1
            row[name] = value
        rows.append({'row_number': index, 'values': row, 'formula_columns': formula_columns})
    return {'columns': header, 'rows': rows, 'sha256': hashlib.sha256(data).hexdigest(),
            'warnings': ['Se omitieron celdas con fórmulas; requieren revisión'] if formulas else [],
            'formula_cells': formulas}


def _date(value, date_format):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise ValueError('Fecha no válida')
    value = value.strip()
    try:
        return datetime.strptime(value, date_format).date().isoformat() if date_format else date.fromisoformat(value).isoformat()
    except (ValueError, TypeError) as exc:
        raise ValueError('Fecha no válida; seleccione su formato explícito') from exc


def preview_import(data, filename, mapping, units=None, period='daily', date_format=None, existing_keys=(), sheet_index=0):
    """Map canonical target->source columns; return candidates, never write.

    _key is content-independent identity (lot,box,date,eventtype,source_event_id),
    while _content_sha256 distinguishes correction conflicts from exact retries.
    For repeated egg rounds supply source_event_id; never use total rows as rounds.
    Numeric blank is pending, zero is measured. Units must be explicitly mapped
    for feed/water/weight. Required lote_id and fecha are never inferred.
    """
    inspected = inspect_upload(data, filename, sheet_index)
    if not mapping or any(source not in inspected['columns'] for source in mapping.values()):
        raise ValueError('El mapeo contiene columnas ausentes')
    if not {'lote_id', 'fecha'}.issubset(mapping):
        raise ValueError('Asigne lote_id y fecha antes de importar')
    units = units or {}
    valid, invalid, pending, duplicates = [], [], [], []
    seen = set(existing_keys)
    for item in inspected['rows']:
        row_number, source = item['row_number'], item['values']
        if period != 'daily':
            pending.append({'row_number': row_number, 'errors': ['Resumen no diario: no se inventarán jornadas']})
            continue
        mapped = {target: source[column] for target, column in mapping.items()}
        errors, absent = [], []
        if any(mapping[target] in item['formula_columns'] for target in mapping):
            pending.append({'row_number': row_number, 'errors': ['La fila contiene fórmulas mapeadas; revise el origen']})
            continue
        if not str(mapped.get('lote_id') or '').strip():
            errors.append('Falta identidad del lote')
        try:
            mapped['fecha'] = _date(mapped.get('fecha'), date_format)
        except ValueError as exc:
            errors.append(str(exc))
        for target in NUMERIC_FIELDS.intersection(mapped):
            value = mapped[target]
            if value is None or str(value).strip() == '':
                mapped[target] = None
                absent.append(target)
                continue
            try:
                numeric = number(value, nonnegative=target != 'temperature_c')
                if target in INTEGER_FIELDS and not numeric.is_integer():
                    raise ValueError('Conteo no entero')
                if target in UNIT_TARGETS:
                    unit = units.get(target)
                    if unit not in UNIT_TARGETS[target][1]:
                        raise ValueError('Confirme la unidad de origen')
                    numeric *= UNIT_TARGETS[target][1][unit]
                if target == 'humidity_pct' and numeric > 100:
                    raise ValueError('Humedad fuera de 0–100 %')
                mapped[target] = int(numeric) if target in INTEGER_FIELDS else numeric
            except (ValueError, TypeError) as exc:
                errors.append(f'{target}: {exc}')
        if errors:
            invalid.append({'row_number': row_number, 'errors': errors})
            continue
        identity = [str(mapped.get(k, '')) for k in ('lote_id', 'box_id', 'fecha', 'event_type', 'source_event_id')]
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        content = hashlib.sha256(json.dumps(mapped, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        candidate = dict(mapped, _key=key, _content_sha256=content, _row_number=row_number)
        if key in seen:
            duplicates.append({'row_number': row_number, 'key': key, 'errors': ['Identidad existente: revisar reenvío o corrección']})
        elif absent:
            pending.append({'row_number': row_number, 'errors': ['Hay mediciones ausentes'], 'missing_fields': absent, 'candidate': candidate})
        else:
            valid.append(candidate)
        seen.add(key)
    return {'valid': valid, 'invalid': invalid, 'pending': pending, 'duplicates': duplicates,
            'sha256': inspected['sha256'], 'warnings': inspected['warnings'], 'period': period,
            'counts': {'valid': len(valid), 'invalid': len(invalid), 'pending': len(pending), 'duplicates': len(duplicates)}}
