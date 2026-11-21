"""Production indicators with explicit units and incomplete-data handling.

Weights use surviving birds represented by each box and sex. There is no sample
count in the current schema. Feed conversion estimates standing live biomass,
not marketed output, because partial bird departures are not recorded yet.
"""
from collections import defaultdict
from datetime import date
from math import isfinite


LOSS_FIELDS = ('mortalidad_hembra', 'mortalidad_macho', 'descarte_hembra', 'descarte_macho')
CONSUMPTION_FIELDS = ('consumo_alimento_kg', 'consumo_agua_litros')


def _number(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number >= 0 else None


def _positive(value):
    number = _number(value)
    return number if number is not None and number > 0 else None


def _sum_observed(rows, field):
    values = [_number(row.get(field)) for row in rows]
    return sum(values) if values and all(value is not None for value in values) else None


def _weighted(observations):
    represented = [(weight, count) for weight, count in observations if count > 0]
    if not represented or any(weight is None for weight, _ in represented):
        return None
    return sum(weight * count for weight, count in represented) / sum(count for _, count in represented)


def build_production_series(diarios, lotes, boxes, detalles):
    """Return one row per lot/date, ordered by lot and placement-based age.

    Missing weights and undefined ratios are None. Cumulative indicators require
    an uninterrupted sequence from placement day 1. Daily observed totals remain
    visible even when earlier days are missing.
    """
    by_lot = {lot['id']: lot for lot in lotes}
    lot_boxes = defaultdict(dict)
    for box in boxes:
        lot_boxes[box['lote_id']][box['id']] = box
    by_daily = defaultdict(list)
    for detail in detalles:
        by_daily[detail['registro_diario_id']].append(detail)
    grouped = defaultdict(list)
    for daily in diarios:
        if daily['lote_id'] in by_lot:
            grouped[daily['lote_id']].append(daily)
    output = []
    for lot_id, records in grouped.items():
        lot = by_lot[lot_id]
        placement = date.fromisoformat(str(lot['fecha_encaste'])[:10])
        initial_h = _number(lot.get('aves_hembra')) or 0
        initial_m = _number(lot.get('aves_macho')) or 0
        initial = _number(lot.get('aves_totales'))
        if initial is None:
            initial = initial_h + initial_m
        cumulative_losses = cumulative_deaths = cumulative_feed = 0.0
        losses_h = losses_m = 0.0
        box_losses = defaultdict(lambda: [0.0, 0.0])
        complete = True
        box_balance_known = True
        previous_day = 0
        previous_weight = None
        previous_weight_day = None
        for record in sorted(records, key=lambda row: str(row['fecha'])):
            current_date = date.fromisoformat(str(record['fecha'])[:10])
            age = (current_date - placement).days + 1
            if age <= previous_day:
                raise ValueError('Duplicate or invalid production date for lot')
            details = by_daily.get(record['id'], [])
            row = dict(record)
            sources = details or [record]
            for field in LOSS_FIELDS:
                # Absent legacy loss columns correspond to historical schema defaults.
                values = [_number(source.get(field, 0)) for source in sources]
                row[field] = sum(values) if all(value is not None for value in values) else None
            for field in CONSUMPTION_FIELDS:
                row[field] = _sum_observed(sources, field)
            losses_known = all(row[field] is not None for field in LOSS_FIELDS)
            day_losses = sum(row[field] or 0 for field in LOSS_FIELDS)
            if not details and not sum(row[field] or 0 for field in LOSS_FIELDS[2:]):
                day_losses += _number(record.get('descartes')) or 0
            live_before = initial - cumulative_losses
            cumulative_losses += day_losses
            cumulative_deaths += (row['mortalidad_hembra'] or 0) + (row['mortalidad_macho'] or 0)
            losses_h += (row['mortalidad_hembra'] or 0) + (row['descarte_hembra'] or 0)
            losses_m += (row['mortalidad_macho'] or 0) + (row['descarte_macho'] or 0)
            live = initial - cumulative_losses
            detail_coverage = True
            if details:
                seen_boxes = set()
                for detail in details:
                    box_id = detail['box_id']
                    if box_id in seen_boxes:
                        raise ValueError('Duplicate box observation in daily record')
                    seen_boxes.add(box_id)
                    box_losses[box_id][0] += (_number(detail.get('mortalidad_hembra')) or 0) + (_number(detail.get('descarte_hembra')) or 0)
                    box_losses[box_id][1] += (_number(detail.get('mortalidad_macho')) or 0) + (_number(detail.get('descarte_macho')) or 0)
                weights_h, weights_m = [], []
                details_by_box = {detail['box_id']: detail for detail in details}
                detail_coverage = bool(lot_boxes[lot_id]) and set(details_by_box) == set(lot_boxes[lot_id])
                for box_id, box in lot_boxes[lot_id].items():
                    detail = details_by_box.get(box_id, {})
                    count_h = (_number(box.get('aves_hembra_inicial')) or 0) - box_losses[box_id][0]
                    count_m = (_number(box.get('aves_macho_inicial')) or 0) - box_losses[box_id][1]
                    if count_h < 0 or count_m < 0:
                        box_balance_known = False
                    weights_h.append((_positive(detail.get('peso_promedio_hembra_g')), max(count_h, 0)))
                    weights_m.append((_positive(detail.get('peso_promedio_macho_g')), max(count_m, 0)))
                represented = sum(count for _, count in weights_h + weights_m)
                populations_match = abs(represented - live) < 0.001
                if not populations_match or not box_balance_known:
                    weights_h = weights_m = []
                row['peso_promedio_hembra_g'] = _weighted(weights_h)
                row['peso_promedio_macho_g'] = _weighted(weights_m)
                row['peso_promedio_mixto_g'] = _weighted(weights_h + weights_m)
            else:
                if day_losses:
                    box_balance_known = False
                for field in ('peso_promedio_hembra_g', 'peso_promedio_macho_g', 'peso_promedio_mixto_g'):
                    row[field] = _positive(record.get(field))
                if row['peso_promedio_mixto_g'] is None:
                    row['peso_promedio_mixto_g'] = _weighted([
                        (row['peso_promedio_hembra_g'], max(initial_h - losses_h, 0)),
                        (row['peso_promedio_macho_g'], max(initial_m - losses_m, 0)),
                    ])
            feed = row['consumo_alimento_kg']
            water = row['consumo_agua_litros']
            complete = complete and age == previous_day + 1 and losses_known and detail_coverage and feed is not None and live >= 0
            if record.get('dia_vida') is not None and record['dia_vida'] != age:
                complete = False
            cumulative_feed += feed or 0
            weight = row['peso_promedio_mixto_g']
            gmd = None
            if weight is not None:
                if previous_weight is not None:
                    gmd = (weight - previous_weight) / (age - previous_weight_day)
                previous_weight, previous_weight_day = weight, age
            fcr = None
            if lot.get('tipo_produccion', 'engorde') == 'engorde' and complete and weight is not None and live > 0:
                fcr = cumulative_feed / (live * weight / 1000)
            survival = live / initial * 100 if complete and initial > 0 else None
            average_live = (live_before + live) / 2
            row.update({
                'codigo_lote': lot.get('codigo_lote', str(lot_id)),
                'linea_genetica': lot.get('linea_genetica'),
                'tipo_produccion': lot.get('tipo_produccion', 'engorde'),
                'dia_vida': age,
                'bajas_dia': day_losses if losses_known else None,
                'bajas_acum': cumulative_losses if complete else None,
                'alimento_acum_kg': cumulative_feed if complete else None,
                'aves_vivas': live if complete else None,
                'mortalidad_pct': cumulative_deaths / initial * 100 if complete and initial > 0 else None,
                'viabilidad_pct': survival,
                'consumo_g_ave': feed * 1000 / average_live if feed is not None and complete and average_live > 0 else None,
                'ratio_agua_alimento': water / feed if water is not None and feed is not None and feed > 0 else None,
                'fcr_acumulado': fcr,
                'gmd_g': gmd,
                'epef': survival * (weight / 1000) / (age * fcr) * 100 if survival is not None and fcr is not None and fcr > 0 else None,
                'cobertura_completa': complete,
            })
            output.append(row)
            previous_day = age
    return sorted(output, key=lambda row: (row['lote_id'], row['dia_vida']))
