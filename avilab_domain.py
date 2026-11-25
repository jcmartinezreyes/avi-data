"""Auditable domain calculations. No database, network, or implicit biological targets.

All quantities are observed unless a returned field explicitly says forecast.
Missing input is never silently substituted with a measured zero.
"""
import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from math import isfinite, sqrt
from statistics import median


def number(value, *, nonnegative=True):
    if isinstance(value, bool) or value is None:
        raise ValueError('Se requiere un número medido')
    result = float(value)
    if not isfinite(result) or (nonnegative and result < 0):
        raise ValueError('Cantidad fuera de rango')
    return result


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def sample_statistics(samples=None, frequency=None, tolerance_pct=10):
    """Sample SD (n-1), CV and fraction inside mean ± tolerance.

    frequency is exact weight/count pairs, not interval midpoints. Summary means
    with sample counts cannot recover dispersion or uniformity.
    """
    tolerance = number(tolerance_pct)
    if (samples is None) == (frequency is None):
        raise ValueError('Seleccione pesos individuales o frecuencias exactas')
    pairs = [(number(v), 1) for v in samples] if samples is not None else []
    if frequency is not None:
        for weight, count in frequency:
            count_value = number(count)
            if not count_value.is_integer():
                raise ValueError('La frecuencia debe ser entera')
            pairs.append((number(weight), int(count_value)))
    if any(weight <= 0 for weight, count in pairs if count):
        raise ValueError('Los pesos deben ser mayores que cero')
    n = sum(count for _, count in pairs)
    if not n:
        return dict(n=0, mean_g=None, sd_g=None, cv_pct=None, uniformity_pct=None, method='sample')
    mean = sum(weight * count for weight, count in pairs) / n
    sd = sqrt(sum(count * (weight - mean) ** 2 for weight, count in pairs) / (n - 1)) if n > 1 else None
    lower, upper = mean * (1 - tolerance / 100), mean * (1 + tolerance / 100)
    return dict(n=n, mean_g=mean, sd_g=sd, cv_pct=sd / mean * 100 if sd is not None else None,
                uniformity_pct=sum(count for weight, count in pairs if lower <= weight <= upper) / n * 100,
                tolerance_pct=tolerance, method='individual_sample' if samples is not None else 'exact_frequency_sample')


def weighted_sample_mean(groups):
    """Combine measured sample means by sample size; not population estimation."""
    pairs = [(number(g['mean_g']), number(g['sample_n'])) for g in groups]
    if any(n <= 0 or not n.is_integer() or weight <= 0 for weight, n in pairs):
        raise ValueError('Peso y tamaño de muestra deben ser positivos')
    n = sum(count for _, count in pairs)
    return {'sample_n': int(n), 'mean_g': sum(w * count for w, count in pairs) / n if n else None,
            'method': 'sample_size_weighted', 'cv_pct': None, 'uniformity_pct': None}


def water_consumption(previous, current, reset=False, previous_end=None, new_start=0):
    previous, current = number(previous), number(current)
    if reset:
        if previous_end is None:
            raise ValueError('Indique la lectura final del contador anterior')
        previous_end, new_start = number(previous_end), number(new_start)
        if previous_end < previous or current < new_start:
            raise ValueError('Lecturas incompatibles con el cambio de contador')
        return previous_end - previous + current - new_start
    if current < previous:
        raise ValueError('Lectura descendente: registre reinicio o sustitución')
    return current - previous


def bird_balance(initial, movements):
    """Balance by sex; sales/transfers are not mortality. Positive counts only."""
    balance = {sex: number(initial.get(sex, 0)) for sex in ('hembra', 'macho', 'mixto')}
    if any(not count.is_integer() for count in balance.values()):
        raise ValueError('Las aves iniciales deben ser enteras')
    deaths = 0
    signs = {'arrival': 1, 'transfer_in': 1, 'sale': -1, 'transfer_out': -1, 'death': -1, 'cull': -1}
    for movement in sorted(movements, key=lambda r: (str(r.get('observed_at', r.get('fecha', ''))), str(r.get('id', '')))):
        kind, sex = movement['kind'], movement['sex']
        if kind not in signs or sex not in balance:
            raise ValueError('Movimiento o sexo no reconocido')
        count = number(movement['count'])
        if not count.is_integer():
            raise ValueError('Las aves deben ser enteras')
        balance[sex] += signs[kind] * count
        if balance[sex] < 0:
            raise ValueError('El movimiento supera el saldo disponible')
        if kind == 'death':
            deaths += count
    return dict(by_sex=balance, live=sum(balance.values()), deaths=deaths)


def egg_reconciliation(received, categories, losses=0, tolerance=0):
    """Categories must be mutually exclusive; attributes are supplied separately."""
    received, losses, tolerance = number(received), number(losses), number(tolerance)
    values = [number(value) for value in categories.values()]
    if any(not value.is_integer() for value in [received, losses] + values):
        raise ValueError('Los huevos deben ser enteros')
    classified = sum(values)
    difference = received - classified - losses
    return {'received': received, 'classified': classified, 'losses': losses, 'difference': difference,
            'balanced': abs(difference) <= tolerance, 'tolerance': tolerance}


def hatchery_indicators(set_eggs, hatched, fertile=None, sample_examined=None, sample_fertile=None):
    set_eggs, hatched = number(set_eggs), number(hatched)
    if not set_eggs.is_integer() or not hatched.is_integer():
        raise ValueError('Los huevos y nacimientos deben ser enteros')
    if hatched > set_eggs:
        raise ValueError('Los nacimientos superan los huevos cargados')
    result = {'hatch_of_set_pct': hatched / set_eggs * 100 if set_eggs else None,
              'hatch_of_fertile_pct': None, 'sample_fertility_pct': None}
    if fertile is not None:
        fertile = number(fertile)
        if not fertile.is_integer() or fertile > set_eggs or hatched > fertile:
            raise ValueError('Balance de fertilidad incompatible')
        result['hatch_of_fertile_pct'] = hatched / fertile * 100 if fertile else None
    if sample_examined is not None or sample_fertile is not None:
        examined, positive = number(sample_examined), number(sample_fertile)
        if not positive.is_integer() or not examined.is_integer() or positive > examined or examined > set_eggs:
            raise ValueError('Muestra incompatible')
        result['sample_fertility_pct'] = positive / examined * 100 if examined else None
    return result


def feed_inventory(opening, events, consumptions):
    """Feed balance in kg and coverage from contiguous, measured recent days."""
    balance = number(opening)
    signs = {'receipt': 1, 'transfer_in': 1, 'return_in': 1, 'transfer_out': -1, 'return_out': -1, 'consumption': -1}
    for event in sorted(events, key=lambda r: str(r.get('observed_at', r.get('fecha', '')))):
        if event['kind'] not in signs:
            raise ValueError('Movimiento de alimento no reconocido')
        balance += signs[event['kind']] * number(event['kg'])
        if balance < -0.000001:
            raise ValueError('Saldo de alimento negativo')
    ordered = sorted(consumptions, key=lambda r: str(r['fecha']))
    valid = bool(ordered)
    days, amounts = [], []
    for row in ordered:
        days.append(_day(row['fecha']))
        try:
            amounts.append(number(row.get('kg')))
        except (TypeError, ValueError):
            valid = False
    valid = valid and len(set(days)) == len(days) and all((b - a).days == 1 for a, b in zip(days, days[1:]))
    mean = sum(amounts) / len(amounts) if valid else None
    return {'closing_kg': max(balance, 0), 'daily_mean_kg': mean,
            'coverage_days': balance / mean if mean is not None and mean > 0 else None,
            'consumption_days': len(days), 'coverage_valid': valid}


def _quantile(values, probability):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * probability
    lower = int(pos)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (pos - lower)


def metric_coverage(rows, metrics, group_fields=('dia_vida',)):
    """One contribution per lot/group/metric; duplicate values are rejected."""
    grouped = defaultdict(dict)
    for row in rows:
        if row.get('status', row.get('estado_captura')) in ('draft', 'borrador', 'pending', 'pendiente'):
            continue
        for metric in metrics:
            key = tuple(row.get(field) for field in group_fields) + (metric,)
            grouped.setdefault(key, {})
            try:
                value = number(row.get(metric), nonnegative=False)
            except (TypeError, ValueError):
                continue
            key = tuple(row.get(field) for field in group_fields) + (metric,)
            lot = row['lote_id']
            if lot in grouped[key]:
                raise ValueError('Más de una observación por lote, grupo e indicador')
            grouped[key][lot] = value
    results = []
    for key, observations in grouped.items():
        values = list(observations.values())
        results.append(dict(zip(group_fields, key[:-1]), metric=key[-1], n_lots=len(observations),
                            n_observations=len(values), median=median(values) if values else None,
                            p25=_quantile(values, .25), p75=_quantile(values, .75)))
    return sorted(results, key=lambda row: tuple(str(row[k]) for k in group_fields) + (row['metric'],))


def forecast_baseline(history, horizon, metric='value', cutoff=None):
    """Last-observation baseline. Predictions never enter actual inventories."""
    if isinstance(horizon, bool) or int(horizon) != horizon or not 1 <= horizon <= 90:
        raise ValueError('Horizonte entre 1 y 90 días')
    cutoff_date = _day(cutoff) if cutoff else max((_day(row['fecha']) for row in history), default=None)
    observed = []
    for row in history:
        if cutoff_date is None or _day(row['fecha']) > cutoff_date or row.get('kind') == 'forecast':
            continue
        if row.get('status') in ('draft', 'pending', 'borrador'):
            continue
        try:
            observed.append((_day(row['fecha']), number(row.get(metric), nonnegative=False)))
        except (TypeError, ValueError):
            pass
    if not observed:
        return {'status': 'insufficient_data', 'model_version': 'last-observation-v1', 'cutoff': cutoff_date.isoformat() if cutoff_date else None, 'points': []}
    observed.sort()
    last_day, value = observed[-1]
    return {'status': 'baseline_only', 'model_version': 'last-observation-v1', 'cutoff': cutoff_date.isoformat(),
            'last_observed_at': last_day.isoformat(), 'metric': metric, 'validated_for_real_use': False,
            'points': [{'fecha': (cutoff_date + timedelta(days=i)).isoformat(), 'value': value, 'kind': 'forecast'} for i in range(1, int(horizon) + 1)]}


def chronological_backtest(cycles, metric='value', horizon=7):
    """Hold out last horizon days per real closed cycle, no future leakage.

    Missing synthetic marker is not proof of real provenance. Only explicitly
    is_synthetic=False, estado=cerrado/closed cycles qualify.
    """
    if int(horizon) != horizon or not 1 <= horizon <= 90:
        raise ValueError('Horizonte entre 1 y 90 días')
    eligible = [c for c in cycles if c.get('is_synthetic') is False and c.get('estado') in ('cerrado', 'closed')]
    eligible.sort(key=lambda c: str(c.get('fecha_cierre', '')))
    folds = []
    for cycle in eligible:
        rows = sorted(cycle.get('history', []), key=lambda r: str(r['fecha']))
        observed = []
        for row in rows:
            if row.get('kind') == 'forecast' or row.get('status') in ('draft', 'pending', 'borrador'):
                continue
            try:
                observed.append((_day(row['fecha']), number(row.get(metric), nonnegative=False)))
            except (TypeError, ValueError):
                continue
        if len(observed) < horizon + 2 or len({d for d, _ in observed}) != len(observed):
            continue
        train, test = observed[:-horizon], observed[-horizon:]
        if any((b[0] - a[0]).days != 1 for a, b in zip(observed, observed[1:])):
            continue
        errors = [abs(value - train[-1][1]) for _, value in test]
        folds.append({'cycle_id': cycle.get('id'), 'cutoff': train[-1][0].isoformat(),
                      'test_start': test[0][0].isoformat(), 'test_end': test[-1][0].isoformat(),
                      'mae': sum(errors) / len(errors), 'n': len(errors)})
    count = sum(f['n'] for f in folds)
    return {'status': 'evaluated_baseline' if len(folds) >= 2 else 'insufficient_real_cycles',
            'model_version': 'last-observation-v1', 'n_cycles': len(folds), 'folds': folds,
            'mae': sum(f['mae'] * f['n'] for f in folds) / count if count else None,
            'validated_for_real_use': False, 'synthetic_excluded': True}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False, default=lambda v: v.isoformat() if isinstance(v, (date, datetime)) else str(v))


def cycle_snapshot(context, events, rules, version, anonymize=True):
    """Deterministic snapshot. Anonymous export uses an allowlist, not name guesses.

    No current timestamps are injected. Same frozen inputs + version = same bytes.
    Unstructured notes are excluded from anonymous output to prevent client leaks.
    """
    if not str(version).strip():
        raise ValueError('Indique una versión de cierre')
    if anonymize:
        allowed_context = {'tipo_produccion', 'linea_genetica', 'fecha_encaste', 'fecha_cierre', 'is_synthetic', 'stage', 'units'}
        allowed_event = {'fecha', 'observed_at', 'kind', 'event_type', 'sex', 'value', 'unit', 'count', 'kg', 'liters', 'status', 'version', 'source_kind', 'quality', 'payload', 'is_synthetic', 'quantity', 'quantity_female', 'quantity_male', 'weight_g'}
        # JSON payload can include customer text: only scalar numeric/boolean fields survive.
        safe_events = []
        for event in events:
            safe = {k: v for k, v in event.items() if k in allowed_event and k != 'payload'}
            if isinstance(event.get('payload'), dict):
                allowed_numeric = {'count', 'quantity', 'quantity_female', 'quantity_male', 'kg', 'liters',
                                   'sample_n', 'mean_g', 'sd_g', 'cv_pct', 'uniformity_pct',
                                   'temperature_c', 'humidity_pct', 'received', 'classified', 'losses',
                                   'set_eggs', 'hatched', 'sample_examined', 'sample_fertile',
                                   'mortalidad_hembra', 'mortalidad_macho', 'descarte_hembra', 'descarte_macho',
                                   'consumo_alimento_kg', 'consumo_agua_litros', 'peso_promedio_hembra_g',
                                   'peso_promedio_macho_g', 'peso_promedio_mixto_g', 'mortalidad_pct',
                                   'viabilidad_pct', 'consumo_g_ave', 'ratio_agua_alimento', 'fcr_acumulado',
                                   'gmd_g', 'epef', 'dia_vida', 'aves_vivas', 'bajas_acum', 'alimento_acum_kg',
                                   'cobertura_completa'}
                safe['payload'] = {k: v for k, v in event['payload'].items()
                                   if k in allowed_numeric and (v is None or isinstance(v, (int, float, bool)))}
            safe_events.append(safe)
        context = {k: v for k, v in context.items() if k in allowed_context}
        events = safe_events
        # Rule metadata must avoid free text, sources can be public reference identifiers.
        rules = [{k: r[k] for k in ('id', 'version', 'metric', 'unit', 'minimum', 'maximum', 'denominator', 'formula') if k in r} for r in rules]
    payload = {'schema': 'avidata-cycle-v1', 'version': str(version), 'anonymized': bool(anonymize),
               'context': context, 'events': sorted(events, key=_canonical), 'rules': sorted(rules, key=_canonical)}
    content = _canonical(payload)
    return {'version': str(version), 'sha256': hashlib.sha256(content.encode()).hexdigest(), 'content': content}


def snapshot_csv(snapshot):
    payload = json.loads(snapshot['content'])
    rows = payload['events']
    fields = sorted({key for row in rows for key in row})
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        clean = {}
        for key, value in row.items():
            value = _canonical(value) if isinstance(value, (dict, list)) else value
            # Spreadsheet formula injection protection, preserving numbers as numbers.
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                value = "'" + value
            clean[key] = value
        writer.writerow(clean)
    return stream.getvalue()
