"""Reproducible cycle reports calculated exclusively from a stored snapshot."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from analytics import build_production_series
from avilab_domain import cycle_snapshot, snapshot_csv, metric_coverage

INDICATORS = {
    'peso_promedio_mixto_g': ('g', 'aves vivas representadas', 'Σ(peso de box y sexo × saldo vivo) / Σ(saldo vivo)'),
    'mortalidad_pct': ('%', 'aves iniciales + entradas externas', 'muertas acumuladas / población expuesta × 100'),
    'viabilidad_pct': ('%', 'aves iniciales + entradas externas', 'saldo vivo / población expuesta × 100'),
    'consumo_g_ave': ('g/ave/día', 'promedio de aves vivas al inicio y final del día', 'alimento diario kg × 1000 / aves vivas promedio'),
    'ratio_agua_alimento': ('L/kg', 'alimento diario kg', 'agua diaria L / alimento diario kg'),
    'fcr_acumulado': ('kg/kg', 'biomasa viva kg', 'alimento acumulado kg / biomasa viva kg; no disponible tras salidas sin biomasa comercializada'),
    'gmd_g': ('g/día', 'días entre pesajes', '(peso actual − peso anterior) / días transcurridos'),
    'epef': ('índice', 'edad × conversión', 'viabilidad % × peso kg × 100 / (edad × FCR)'),
}


def build_frozen_report(content, version, anonymize=True):
    if isinstance(content, str):
        content = json.loads(content)
    lot = content.get('lote') or content.get('context') or {}
    headers = content.get('daily_records') or []
    boxes = content.get('boxes') or []
    details = content.get('daily_details') or []
    events = content.get('events') or []
    by_box = {str(b['id']): b for b in boxes}
    # New snapshots preserve only effective events; older ones may include history.
    replaced = {e.get('supersedes_id') for e in events if e.get('supersedes_id')}
    effective = [e for e in events if e.get('id') not in replaced]
    movements = []
    for event in effective:
        if event.get('kind') != 'bird_movement':
            continue
        data = event.get('data') or {}
        movement = data.get('movement')
        if movement not in ('arrival', 'sale', 'transfer'):
            continue
        day = datetime.fromisoformat(event['observed_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/Bogota')).date().isoformat()
        ends = [(event.get('lote_id'), event.get('box_id'), 'transfer_out' if movement == 'transfer' else movement)]
        if movement == 'transfer':
            target = by_box.get(str(data.get('destination_box_id')))
            if target:
                ends.append((target['lote_id'], target['id'], 'transfer_in'))
        for lot_id, box_id, kind in ends:
            for sex, field in [('hembra', 'quantity_female'), ('macho', 'quantity_male')]:
                count = event.get(field) or 0
                if count:
                    movements.append({'event_id': event['id'], 'lote_id': lot_id, 'box_id': box_id,
                                      'fecha': day, 'sex': sex, 'kind': kind, 'count': count})
    series = build_production_series(headers, [lot], boxes, details, movements=movements) if lot.get('id') and headers else []
    rows = []
    for row in series:
        rows.append({'kind': 'daily_indicators', 'fecha': row['fecha'], 'payload': {
            **{metric: row.get(metric) for metric in INDICATORS},
            'dia_vida': row.get('dia_vida'), 'aves_vivas': row.get('aves_vivas'),
            'bajas_acum': row.get('bajas_acum'), 'alimento_acum_kg': row.get('alimento_acum_kg'),
            'cobertura_completa': row.get('cobertura_completa'),
        }})
    rows += [{'kind': 'daily_observed', 'fecha': h['fecha'], 'payload': h} for h in headers]
    rows += [{**e, 'payload': e.get('data') or {}} for e in effective]
    # Evidence is retained in a full internal export; anonymous mode strips identities/notes.
    rows += [{'kind': 'incident', 'payload': i} for i in content.get('incidents') or []]
    rows += [{'kind': 'task', 'payload': t} for t in content.get('tasks') or []]
    rules = [{'id': metric, 'version': content.get('rules_version', 'avilab-2026-11'),
              'metric': metric, 'unit': unit, 'denominator': denominator, 'formula': formula}
             for metric, (unit, denominator, formula) in INDICATORS.items()]
    context = dict(lot, units={metric: unit for metric, (unit, _, _) in INDICATORS.items()})
    result = cycle_snapshot(context, rows, rules, version, anonymize=anonymize)
    result['csv'] = snapshot_csv(result)
    result['indicators'] = series
    result['coverage'] = metric_coverage(series, list(INDICATORS))
    result['definitions'] = rules
    result['has_frozen_production'] = bool(headers)
    if not anonymize:
        # A full export additionally carries original frozen details/reference versions.
        export = json.loads(result['content'])
        export['evidence'] = content
        import hashlib
        result['content'] = json.dumps(export, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        result['sha256'] = hashlib.sha256(result['content'].encode()).hexdigest()
        result['csv'] = snapshot_csv(result)
    return result
