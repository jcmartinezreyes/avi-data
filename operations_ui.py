"""Operational workspace for AviData. All mutations use authorized transactional RPCs.

The module deliberately does not own authentication or create an administrative client.
The caller supplies the current user's Supabase client and organization context.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from ui_design import context_card, section_intro, workflow_steps

MANAGERS = {'owner', 'admin'}
WRITERS = {'owner', 'admin', 'operator'}
STATUS = {'draft': 'Borrador', 'submitted': 'Enviado', 'reviewed': 'Revisado', 'closed': 'Período cerrado'}
SECTIONS = ['Jornada', 'Eventos productivos', 'Huevos e incubación', 'Agenda e incidencias', 'Importar planillas', 'Trazabilidad y análisis', 'Configuración guiada']
FIELDS = [
    ('mortalidad_hembra', 'Muertas · hembras', 'count', 'h'),
    ('mortalidad_macho', 'Muertas · machos', 'count', 'm'),
    ('descarte_hembra', 'Descartes · hembras', 'count', 'h'),
    ('descarte_macho', 'Descartes · machos', 'count', 'm'),
    ('consumo_alimento_kg', 'Alimento consumido · kg', 'decimal', None),
    ('consumo_agua_litros', 'Agua consumida · L', 'decimal', None),
    ('peso_promedio_hembra_g', 'Peso medio · hembras · g', 'weight', 'h'),
    ('peso_promedio_macho_g', 'Peso medio · machos · g', 'weight', 'm'),
]


def _rows(client, table, organization_id, **filters):
    result = []
    for offset in range(0, 100000, 500):
        query = client.table(table).select('*').eq('organization_id', organization_id)
        for field, value in filters.items():
            query = query.eq(field, value)
        order_columns = {'daily_capture_versions': ('capture_id', 'version'), 'egg_unit_links': ('parent_id', 'child_id'), 'hatch_inputs': ('batch_id', 'unit_id')}.get(table, ('id',))
        for column in order_columns:
            query = query.order(column)
        page = query.range(offset, offset + 499).execute().data or []
        result.extend(page)
        if len(page) < 500:
            break
    return result


def _table(rows, columns=None, empty_title="Aún no hay registros", empty_description="Los datos aparecerán aquí cuando se registren en esta sección.", empty_action=None):
    if not rows:
        st.info(empty_title + '. ' + empty_description + (' ' + empty_action if empty_action else ''))
        return
    frame = pd.DataFrame(rows)
    if columns:
        frame = frame[[c for c in columns if c in frame.columns]]
    enum_labels = {
        'status': {'draft':'Borrador','submitted':'Enviado','reviewed':'Revisado','closed':'Cerrado', 'open':'Pendiente','done':'Realizada','cancelled':'Cancelada','acknowledged':'Reconocida','resolved':'Resuelta','set':'Cargada','transferred':'Transferida','hatched':'Nacida'},
        'quality': {'observed':'Observado','estimated':'Estimado','corrected':'Corregido'},
        'source': {'manual':'Manual','import':'Importación','sensor':'Sensor','legacy':'Histórico'},
        'kind': {'bird_movement':'Movimiento de aves','weighing':'Pesaje','water_reading':'Lectura de agua','feed_movement':'Movimiento de alimento','environment':'Ambiente','health':'Salud','stage':'Cambio de etapa','readiness':'Preparación','arrival':'Recepción de aves','egg_collection':'Recolección','egg_receipt':'Recepción de huevos','egg_classification':'Clasificación','egg_transfer':'Movimiento de huevos','egg_split':'División','egg_merge':'Combinación','hatch_set':'Carga de incubación','hatch_transfer':'Transferencia de incubación','hatch_result':'Resultado de nacimiento','task':'Tarea','task_update':'Actualización de tarea','incident':'Incidencia','incident_update':'Seguimiento de incidencia','plan':'Plan','target':'Objetivo documentado','snapshot':'Informe conservado'}}
    for field, values in enum_labels.items():
        if field in frame:
            frame[field] = frame[field].map(lambda value: values.get(value, value) if isinstance(value, str) else value)
    labels = {**{code: label for code, label, _, _ in FIELDS},
        'box_id': 'Box', 'lote_id': 'Lote', 'id': 'Identificador', 'kind': 'Tipo de hecho',
        'observed_at': 'Fecha y hora observadas', 'received_at': 'Fecha de recepción',
        'quantity': 'Cantidad', 'quantity_female': 'Hembras', 'quantity_male': 'Machos',
        'weight_g': 'Peso medio · g', 'unit': 'Unidad', 'sex': 'Sexo', 'stage': 'Etapa',
        'source': 'Procedencia', 'quality': 'Condición del dato', 'note': 'Observación',
        'version': 'Versión', 'status': 'Estado', 'reason': 'Motivo',
        'created_by': 'Responsable del registro', 'created_at': 'Fecha de creación',
        'payload': 'Datos de la versión', 'title': 'Descripción', 'due_date': 'Vencimiento',
        'assigned_to': 'Responsable', 'evidence_event_id': 'Hecho que acredita la tarea',
        'rule_version': 'Regla y versión', 'explanation': 'Explicación',
        'name': 'Nombre', 'edition': 'Edición', 'genetics': 'Genética', 'metric': 'Indicador',
        'denominator': 'Denominador', 'source_url': 'Fuente', 'target_date': 'Fecha prevista',
        'value': 'Valor', 'temperature_c': 'Temperatura · °C', 'humidity_pct': 'Humedad · %',
        'row_number': 'Fila', 'errors': 'Observaciones de validación', 'missing_fields': 'Campos pendientes',
        'parent_id': 'Unidad de origen', 'child_id': 'Unidad derivada', 'unit_id': 'Unidad de huevo',
        'batch_id': 'Carga de incubación', 'quantity_kg': 'Cantidad · kg', 'warehouse': 'Almacén',
        'closing_kg': 'Existencia · kg', 'coverage_days': 'Días de cobertura',
        'sample_n': 'Tamaño de muestra', 'mean_g': 'Media muestral · g',
        'sd_g': 'Desviación muestral · g', 'cv_pct': 'CV muestral · %', 'uniformity_pct': 'Uniformidad muestral · %'}
    st.dataframe(frame.rename(columns=labels), hide_index=True, use_container_width=True,
                 height=min(420, 70 + 35 * len(frame)))


def _rpc(client, name, params):
    try:
        return client.rpc(name, params).execute().data
    except Exception as exc:
        message = str(exc).lower()
        if any(x in message for x in ['conflict', 'version', '40001']):
            st.error('Otra persona cambió este registro. Recarga la versión actual y revisa tus cambios antes de reenviarlos.')
        elif any(x in message for x in ['incubadora', 'incubation module', 'hatchery module', 'hatchery tools', 'incubator']):
            st.error('Esta operación requiere el módulo de incubación en la suscripción de tu organización. Un administrador puede revisar el plan.')
        elif any(x in message for x in ['42501', 'permission', 'access', 'authorized']):
            st.error('Tu perfil no tiene permiso para esta operación o el registro pertenece a otra organización.')
        else:
            st.error('No se pudo confirmar la operación. Revisa fecha, saldos, campos obligatorios y estado del lote. Tus datos siguen en el formulario.')
        return None


def _lot_options(lotes, active=False):
    options = {}
    for lot in lotes:
        if active and not lot.get('activo'):
            continue
        farm = (lot.get('galpones') or {}).get('granjas') or {}
        options[f"{lot.get('codigo_lote', lot['id'])} · {farm.get('nombre', '')} · {(lot.get('galpones') or {}).get('nombre', '')}"] = lot
    return options


def _lot_picker(lotes, key, active=False):
    options = _lot_options(lotes, active)
    if not options:
        st.info('No hay lotes activos disponibles.' if active else 'Primero configura un lote.')
        return None
    return options[st.selectbox('Lote', list(options), key=key)]


def _idempotency(key):
    state_key = 'op_request_' + key
    if state_key not in st.session_state:
        st.session_state[state_key] = str(uuid.uuid4())
    return st.session_state[state_key]


def _record(client, org, kind, data, key):
    result = _rpc(client, 'record_operation', {'p_organization_id': org, 'p_kind': kind,
                  'p_data': data, 'p_idempotency_key': _idempotency(key)})
    if result:
        st.session_state.pop('op_request_' + key, None)
        st.success('Operación registrada con trazabilidad.')
    return result


def _number(label, key, integer=False, optional=False, value=None):
    options = {'label': label, 'min_value': 0 if integer else 0.0, 'key': key}
    options['value'] = value if value is not None else (None if optional else (0 if integer else 0.0))
    if optional:
        options['placeholder'] = 'Sin medir'
    if integer:
        options['step'] = 1
    else:
        options['step'] = 0.1
    return st.number_input(**options)


def _download_draft(org, user, lot_id, day, boxes, version):
    now = datetime.now(timezone.utc)
    draft = {'format': 'avidata-draft-v1', 'organization_id': org, 'user_id': user,
             'lote_id': lot_id, 'fecha': str(day), 'version': version,
             'created_at': now.isoformat(), 'expires_at': (now + timedelta(days=7)).isoformat(),
             'boxes': boxes}
    st.download_button('Descargar borrador de respaldo', json.dumps(draft, ensure_ascii=False, indent=2),
                       file_name='avidata-borrador.json', mime='application/json', key='op_download_draft')
    from offline_drafts import offline_editor
    st.download_button('Descargar editor para usar sin conexión', offline_editor(org, user, lot_id, day, boxes, version),
                       file_name='avidata-jornada-offline.html', mime='text/html', key='op_download_offline')
    st.caption('El archivo permite preparar o conservar datos durante una interrupción. No contiene credenciales. Streamlit necesita conexión para abrir la aplicación y sincronizar. El respaldo caduca en 7 días.')


def _load_draft(org, user, lot_id, day):
    upload = st.file_uploader('Recuperar respaldo de borrador', type=['json'], key='op_restore_draft')
    if not upload:
        return None
    try:
        if upload.size > 1_000_000:
            raise ValueError()
        data = json.loads(upload.getvalue())
        if data.get('format') != 'avidata-draft-v1' or data.get('organization_id') != org or data.get('user_id') != user:
            raise ValueError()
        if data.get('lote_id') != lot_id or data.get('fecha') != str(day):
            raise ValueError()
        if datetime.fromisoformat(data['expires_at']) <= datetime.now(timezone.utc) or not isinstance(data['boxes'], list):
            raise ValueError()
        st.info('Respaldo válido. Se mostrará para revisión; todavía no se ha escrito nada en la base.')
        return data
    except (ValueError, TypeError, KeyError):
        st.error('El respaldo no corresponde a esta persona, organización, lote y fecha, ha caducado o no tiene un formato válido.')
        return None


def _jornada(client, org, user, role, lotes, today):
    section_intro('Completa tu jornada', 'Elige el lote, registra lo observado y revisa los datos antes de enviarlos.')
    captures = _rows(client, 'daily_captures', org)
    active = [l for l in lotes if l.get('activo') and str(l.get('fecha_encaste', '')) <= str(today)]
    summary = []
    for item in active:
        capture = next((c for c in captures if c['lote_id'] == item['id'] and str(c['fecha']) == str(today)), None)
        summary.append({'Lote': item.get('codigo_lote'), 'Fecha': str(today),
                        'Estado': STATUS.get(capture['status'], capture['status']) if capture else 'Pendiente'})
    pending = sum(row['Estado'] == 'Pendiente' for row in summary)
    drafts = sum(row['Estado'] == 'Borrador' for row in summary)
    sent = len(summary) - pending - drafts
    summary_items = [('Por registrar hoy', pending), ('En borrador', drafts), ('Jornadas enviadas', sent)]
    st.markdown('<dl class="avi-day-summary" aria-label="Estado de las jornadas de hoy">'
        + ''.join('<div><dt>' + title + '</dt><dd>' + str(amount) + '</dd></div>' for title, amount in summary_items)
        + '</dl>', unsafe_allow_html=True)
    with st.expander('Ver el estado de todos los lotes de hoy'):
        _table(summary, empty_title='No hay lotes en producción',
               empty_description='Los lotes activos aparecerán aquí desde su fecha de alojamiento.',
               empty_action='Revisa tus alojamientos en el menú Lotes.')
    historic = st.checkbox('Consultar o corregir un período de un lote cerrado', key='op_daily_historic') if role in MANAGERS else False
    candidates = lotes if historic else active
    context_columns = st.columns([2, 1])
    with context_columns[0]:
        lot = _lot_picker(candidates, 'op_daily_lot', active=not historic)
    if not lot:
        return
    default_day = min(today, date.fromisoformat(str(lot['fecha_cierre'])[:10])) if lot.get('fecha_cierre') else today
    with context_columns[1]:
        day = st.date_input('Fecha de la jornada', default_day,
            min_value=date.fromisoformat(str(lot['fecha_encaste'])[:10]), max_value=default_day,
            key=f'op_daily_date_{lot["id"]}')
    previous = next((c for c in captures if c['lote_id'] == lot['id'] and str(c['fecha']) == str(day)), {})
    edit_key = f'op_capture_loaded_{org}_{lot["id"]}_{day}'
    if edit_key not in st.session_state:
        st.session_state[edit_key] = previous
    pinned = st.session_state[edit_key]
    if previous.get('version', 0) != pinned.get('version', 0):
        st.warning('Existe una versión más reciente. Tu edición conserva la versión de origen para evitar sobrescribir cambios ajenos.')
    previous = pinned
    version = previous.get('version', 0)
    farm = (lot.get('galpones') or {}).get('granjas') or {}
    age = (day - date.fromisoformat(str(lot['fecha_encaste'])[:10])).days + 1
    status = STATUS.get(previous.get('status'), 'Pendiente')
    context_card(lot.get('codigo_lote', str(lot['id'])),
        f"{farm.get('nombre', 'Granja sin nombre')} · {(lot.get('galpones') or {}).get('nombre', 'Galpón')} · {lot.get('tipo_produccion', 'engorde').capitalize()} · {day.strftime('%d/%m/%Y')} · Día {age}",
        status=status, tone='pending' if status in ('Pendiente', 'Borrador') else 'success')
    if previous.get('source') == 'legacy':
        st.warning('Registro histórico: se conservaron los valores originales, pero su estado de medición no está documentado. Un cero antiguo no acredita por sí solo que se haya medido. Revisa la fuente antes de corregir o confirmar.')
    boxes = client.table('galpon_boxes').select('*').eq('lote_id', lot['id']).order('nombre_box').execute().data or []
    if not boxes:
        st.info('Configura los boxes de este lote en el menú Lotes para comenzar la jornada.')
        return
    with st.expander('Recuperar un borrador de respaldo'):
        restored = _load_draft(org, user, lot['id'], day)
    prior_boxes = (restored or {}).get('boxes', previous.get('payload') or [])
    if isinstance(prior_boxes, dict):
        prior_boxes = prior_boxes.get('boxes', [])
    defaults = {str(b['box_id']): b for b in prior_boxes}
    movement_context = _rows(client, 'effective_operations_events', org)
    net_by_box = {}
    for event in movement_context:
        if event.get('kind') != 'bird_movement':
            continue
        effective_day = datetime.fromisoformat(event['observed_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/Bogota')).date()
        if effective_day > day:
            continue
        data = event.get('data') or {}
        kind = data.get('movement')
        for box_id, sign in [(event.get('box_id'), 1 if kind == 'arrival' else -1)] + ([(data.get('destination_box_id'), 1)] if kind == 'transfer' else []):
            totals = net_by_box.setdefault(str(box_id), [0, 0])
            totals[0] += sign * (event.get('quantity_female') or 0)
            totals[1] += sign * (event.get('quantity_male') or 0)
    readonly = role not in WRITERS or previous.get('status') in ('reviewed', 'closed') or (not lot.get('activo') and not previous)
    st.caption('Vacío = no medido. Cero = cero observado. El sexo ausente queda como No aplica. Los pesos son opcionales.')

    def absent_sex(box, sex):
        moved_h, moved_m = net_by_box.get(str(box['id']), [0, 0])
        return (sex == 'h' and not box.get('aves_hembra_inicial') and moved_h == 0) or (sex == 'm' and not box.get('aves_macho_inicial') and moved_m == 0)

    def input_key(box, code):
        key = f'op_daily_{lot["id"]}_{day}_{version}_{box["id"]}_{code}'
        if restored:
            key += '_' + hashlib.sha256(json.dumps(restored, sort_keys=True).encode()).hexdigest()[:8]
        return key

    box_progress = {}
    for box in boxes:
        prior = defaults.get(str(box['id']), {})
        required = [code for code, _, kind, sex in FIELDS if kind != 'weight' and not absent_sex(box, sex)]
        complete = sum((prior.get(code) if readonly else st.session_state.get(input_key(box, code), prior.get(code))) is not None for code in required)
        box_progress[box['id']] = (complete, len(required))
    first_pending = next((box['id'] for box in boxes if box_progress[box['id']][0] < box_progress[box['id']][1]), None)
    workflow_steps(['Lote y fecha', 'Datos por box', 'Revisar y enviar'], current=1 if first_pending is not None else 2)
    payload, required_missing = [], []
    for box in boxes:
        prior = defaults.get(str(box['id']), {})
        complete, required_total = box_progress[box['id']]
        with st.expander(f"{box.get('nombre_box', str(box['id']))} · {complete}/{required_total} datos",
                         expanded=len(boxes) == 1 or box['id'] == first_pending):
            row = {'box_id': box['id'], 'metricas': prior.get('metricas', [])}
            states = {}

            def capture_field(field, container):
                code, label, kind, sex = field
                if absent_sex(box, sex):
                    row[code], states[code] = None, 'not_applicable'
                    return
                value = prior.get(code)
                if readonly:
                    container.write(f'{label}: {value if value is not None else "No medido"}')
                    row[code] = value
                else:
                    with container:
                        row[code] = _number(label, input_key(box, code), integer=kind == 'count', optional=True, value=value)
                states[code] = 'measured' if row[code] is not None else 'not_measured'
                if kind != 'weight' and row[code] is None:
                    required_missing.append(box.get('nombre_box', str(box['id'])) + ' · ' + label)

            st.markdown('**Bajas de aves**')
            loss_fields = [field for field in FIELDS[:4] if not absent_sex(box, field[3])]
            loss_columns = st.columns(2)
            for index, field in enumerate(loss_fields):
                capture_field(field, loss_columns[index % 2])
            for field in FIELDS[:4]:
                if absent_sex(box, field[3]):
                    row[field[0]], states[field[0]] = None, 'not_applicable'
            st.markdown('**Consumo del día**')
            for field, container in zip(FIELDS[4:6], st.columns(2)):
                capture_field(field, container)
            show_weights = st.checkbox('Registrar peso medio tomado hoy · opcional',
                value=any(prior.get(field[0]) is not None for field in FIELDS if field[2] == 'weight'),
                key=f'op_daily_weights_{lot["id"]}_{day}_{version}_{box["id"]}', disabled=readonly)
            weight_columns = st.columns(2) if show_weights else []
            for index, field in enumerate(FIELDS[6:]):
                if absent_sex(box, field[3]):
                    row[field[0]], states[field[0]] = None, 'not_applicable'
                elif show_weights:
                    capture_field(field, weight_columns[index])
                else:
                    row[field[0]], states[field[0]] = None, 'not_measured'
            row['measurement_states'] = states
            payload.append(row)
    required_total = sum(total for _, total in box_progress.values())
    completed_total = required_total - len(required_missing)
    st.progress(completed_total / required_total if required_total else 1.0,
                text=f"{completed_total} de {required_total} datos obligatorios listos · {len(boxes)} {'box' if len(boxes) == 1 else 'boxes'}")
    st.markdown('**Resumen de la jornada**')

    def observed_total(fields):
        fields = tuple(fields)
        values = []
        for box_row in payload:
            for code in fields:
                if box_row['measurement_states'].get(code) == 'not_applicable':
                    continue
                if box_row.get(code) is None:
                    return None
                values.append(box_row[code])
        return sum(values) if values else None

    totals = [('Muertas', observed_total(FIELDS[i][0] for i in (0, 1)), 'aves'),
              ('Descartes', observed_total(FIELDS[i][0] for i in (2, 3)), 'aves'),
              ('Alimento', observed_total(['consumo_alimento_kg']), 'kg'),
              ('Agua', observed_total(['consumo_agua_litros']), 'L')]
    for column, (label, value, unit) in zip(st.columns(4), totals):
        column.metric(label, 'Pendiente' if value is None else f'{value:,.1f} {unit}' if unit != 'aves' else f'{int(value):,} aves')
    box_names = {box['id']: box.get('nombre_box', str(box['id'])) for box in boxes}
    relevant_fields = [code for code, _, _, _ in FIELDS if not all(row['measurement_states'].get(code) == 'not_applicable' for row in payload)]
    with st.expander('Revisar el detalle por box antes de enviar'):
        _table([{key: (box_names.get(value, value) if key == 'box_id' else value) for key, value in row.items()
                 if key == 'box_id' or key in relevant_fields} for row in payload])
    reason = st.text_input('Observación o motivo de corrección', key=f'op_daily_reason_{lot["id"]}_{day}',
                           help='Obligatorio al corregir datos enviados o reabrir un período.')

    def save(status):
        result = _rpc(client, 'save_daily_capture', {'p_lote_id': lot['id'], 'p_fecha': str(day),
                       'p_boxes': previous.get('payload', payload) if status in ('reviewed', 'closed', 'reopen') else payload,
                       'p_status': status, 'p_expected_version': (restored or {}).get('version', version),
                       'p_reason': reason, 'p_source': 'manual', 'p_external_id': None})
        if result:
            st.session_state.pop(edit_key, None)
            st.session_state['op_daily_notice'] = 'Borrador guardado. Puedes continuar más tarde.' if status == 'draft' else 'Jornada actualizada correctamente. Se conserva su historial de cambios.'
            st.rerun()

    if not readonly:
        if required_missing:
            st.info(f'Faltan {len(required_missing)} datos obligatorios. Puedes guardar un borrador y completarlo después.')
            with st.expander('Ver los datos que faltan'):
                for missing in required_missing:
                    st.write(missing)
        confirm_context = (org, lot['id'], str(day), version, (restored or {}).get('version'))
        if st.session_state.get('op_daily_confirm_context') != confirm_context:
            st.session_state.pop('op_daily_confirm', None)
            st.session_state['op_daily_confirm_context'] = confirm_context
        confirm = st.checkbox('Revisé los datos y sus unidades', key='op_daily_confirm')
        submit_column, draft_column = st.columns([2, 1])
        if submit_column.button('Enviar jornada', type='primary', disabled=not confirm or bool(required_missing), key='op_daily_submit', use_container_width=True):
            save('submitted')
        if draft_column.button('Guardar borrador', key='op_daily_save', use_container_width=True):
            save('draft')
    if role in MANAGERS and previous:
        with st.expander('Revisión y cierre del período'):
            st.caption(f'Versión {version} · {status}. La revisión se aplica a los datos guardados: envía los cambios del formulario antes de revisar. Los períodos revisados necesitan reapertura para corregirlos.')
            c1, c2, c3 = st.columns(3)
            if c1.button('Marcar revisado', disabled=previous.get('status') != 'submitted', key='op_review'):
                save('reviewed')
            if c2.button('Cerrar período', disabled=previous.get('status') != 'reviewed', key='op_period_close'):
                save('closed')
            if c3.button('Reabrir para corregir', disabled=previous.get('status') not in ('reviewed', 'closed') or not reason.strip(), key='op_period_reopen'):
                save('reopen')
    with st.expander('Trabajar sin conexión y descargar respaldo'):
        _download_draft(org, user, lot['id'], day, payload, version)
    with st.expander('Historial de versiones y responsables'):
        if previous:
            versions = _rows(client, 'daily_capture_versions', org, capture_id=previous['id'])
            _table(versions, ['version', 'status', 'reason', 'created_by', 'created_at', 'payload'])
        else:
            st.caption('Las versiones aparecerán aquí después de guardar tu primera jornada.')
    with st.expander('Recargar datos si otra persona está editando'):
        st.caption('Recargar descarta los cambios de esta edición y trae la última versión guardada.')
        if st.button('Recargar versión actual', key='op_daily_reload'):
            st.session_state.pop(edit_key, None)
            prefixes = (f'op_daily_{lot["id"]}_{day}_', f'op_daily_weights_{lot["id"]}_{day}_')
            for widget_key in list(st.session_state):
                if widget_key.startswith(prefixes):
                    st.session_state.pop(widget_key, None)
            st.session_state.pop('op_daily_confirm', None)
            st.session_state.pop('op_daily_confirm_context', None)
            st.rerun()

def _provenance_fields(data, key):
    with st.expander('Origen y calidad del dato · opciones adicionales'):
        st.caption('El ingreso habitual es manual y observado. Cambia estas opciones solo si corresponde al origen real.')
        data['source'] = st.selectbox('Procedencia', ['manual', 'import', 'sensor'],
            format_func=lambda value: {'manual': 'Manual', 'import': 'Importación verificada', 'sensor': 'Sensor · ingreso manual de lectura'}[value], key=key+'_source')
        quality = st.selectbox('Calidad', ['observed', 'estimated', 'corrected'],
            format_func=lambda value: {'observed': 'Medido / observado', 'estimated': 'Estimado', 'corrected': 'Corregido con motivo'}[value], key=key+'_quality')
        data['quality'] = 'corrected' if data.get('supersedes_id') else quality
        data['external_id'] = st.text_input('Identificador del origen · opcional', key=key+'_external') or None
        if data.get('supersedes_id'):
            st.caption('Este registro es una corrección: conservará el vínculo al original y requiere un motivo.')


def _event_context(client, lotes, today, key, active=True, include_provenance=True):
    lot = _lot_picker(lotes, key + '_lot', active=active)
    if not lot:
        return None
    boxes = client.table('galpon_boxes').select('*').eq('lote_id', lot['id']).order('nombre_box').execute().data or []
    options = {'Todo el lote / galpón': None, **{b['nombre_box']: b['id'] for b in boxes}}
    box = options[st.selectbox('Alcance', list(options), key=key+'_box')]
    date_column, time_column = st.columns(2)
    day = date_column.date_input('Fecha observada', today, max_value=today, key=key+'_date')
    clock = time_column.time_input('Hora observada · Colombia', value=datetime.now(ZoneInfo('America/Bogota')).time().replace(tzinfo=None), key=key+'_time')
    data = {'lote_id': lot['id'], 'box_id': box, 'observed_at': f'{day}T{clock.isoformat()}-05:00',
            'source': 'manual', 'quality': 'observed', 'external_id': None}
    if include_provenance:
        _provenance_fields(data, key)
    return lot, boxes, data


def _events(client, org, user, role, lotes, today):
    from avilab_domain import sample_statistics, feed_inventory
    section_intro('Registra un evento productivo', 'Elige qué ocurrió y dónde. Los pesajes, movimientos y observaciones conservan su propia historia.')
    choices = {'Pesaje de muestra': 'weighing', 'Movimiento de aves': 'bird_movement', 'Contador de agua': 'water_reading',
               'Inventario de alimento': 'feed_movement', 'Ambiente del galpón': 'environment', 'Sanidad y observaciones': 'health',
               'Cambio de etapa': 'stage', 'Preparación del galpón': 'readiness', 'Recepción de aves': 'arrival'}
    kind = choices[st.selectbox('Tipo de evento', list(choices), key='op_event_kind')]
    context = _event_context(client, lotes, today, 'op_event', include_provenance=False)
    if not context:
        return
    lot, boxes, data = context
    if kind in ('bird_movement', 'feed_movement', 'weighing', 'environment', 'health', 'stage', 'readiness', 'arrival') and st.checkbox('Corregir un evento anterior de este tipo', key='op_event_correct'):
        candidates = [e for e in _rows(client, 'effective_operations_events', org, lote_id=lot['id']) if e['kind'] == kind]
        options = {f"{e['observed_at']} · {str(e['id'])[:8]}": e for e in candidates}
        if options:
            original = options[st.selectbox('Evento original que será sustituido', list(options), key='op_event_original')]
            data['supersedes_id'] = original['id']
            data['quality'] = 'corrected'
            _table([_flatten_event(original)])
            st.caption('Escribe los valores completos corregidos. El original se conserva y los informes usarán la versión efectiva. No se suma una segunda medición.')
        else:
            st.warning('No hay eventos de este tipo que puedas corregir.')
    if role not in WRITERS:
        st.info('Tu perfil permite consultar eventos. La captura requiere permiso de operación.')
    valid = True
    if kind == 'weighing':
        data['sex'] = st.selectbox('Sexo de la muestra', ['hembra', 'macho', 'mixto'], key='op_weigh_sex')
        text = st.text_area('Pesos individuales en gramos · uno por línea', placeholder='Ejemplo sintético:\n1800\n1850\n1720', key='op_weights')
        try:
            weights = [float(s.strip().replace(',', '.')) for s in text.splitlines() if s.strip()]
            data['weights_g'] = weights
            if weights:
                stats = sample_statistics(samples=weights)
                _table([stats])
                st.caption('CV y uniformidad corresponden a la muestra, no a toda la población. Uniformidad: ±10 % de la media muestral; no es un objetivo genético.')
            valid = bool(weights)
        except (ValueError, TypeError):
            st.warning('Escribe un peso positivo por línea, en gramos.')
            valid = False
    elif kind == 'bird_movement':
        data['movement'] = st.selectbox('Movimiento', ['arrival', 'sale', 'transfer'], format_func=lambda x: {'arrival': 'Ingreso adicional real', 'sale': 'Salida / venta', 'transfer': 'Transferencia entre boxes'}[x], key='op_bird_move')
        data['female'] = _number('Hembras · aves', 'op_move_h', integer=True)
        data['male'] = _number('Machos · aves', 'op_move_m', integer=True)
        data['weight_g'] = _number('Peso medio de salida · g · opcional', 'op_move_w', optional=True)
        if data['movement'] == 'transfer':
            destinations = [(b, l) for l in lotes if l.get('activo') for b in (l.get('galpon_boxes') or []) if b['id'] != data.get('box_id')]
            if not destinations:
                for target_lot in lotes:
                    if target_lot.get('activo'):
                        target_boxes = client.table('galpon_boxes').select('*').eq('lote_id', target_lot['id']).execute().data or []
                        destinations.extend((b, target_lot) for b in target_boxes if b['id'] != data.get('box_id'))
            options = {f"{l.get('codigo_lote')} · {b.get('nombre_box')}": b['id'] for b, l in destinations}
            if options:
                data['destination_box_id'] = options[st.selectbox('Box de destino', list(options), key='op_move_dest')]
            else:
                st.warning('No hay box de destino disponible.')
                valid = False
        st.caption('La transferencia es atómica: salida y entrada quedan unidas. Una venta o transferencia no se clasifica como mortalidad.')
    elif kind == 'water_reading':
        data['meter_id'] = st.text_input('Identificador estable del contador', key='op_meter')
        data['reading_l'] = _number('Lectura acumulada · L', 'op_water_reading')
        data['reset'] = st.checkbox('Reinicio o sustitución del contador', key='op_water_reset')
        if data['reset']:
            data['previous_end_l'] = _number('Lectura final del contador anterior · L', 'op_water_end', optional=True)
            data['new_start_l'] = _number('Lectura inicial del nuevo contador · L', 'op_water_start')
        st.caption('Una lectura acumulada no equivale a consumo diario. El intervalo se calcula con las lecturas comparables; un reinicio sin lectura final deja el consumo desconocido.')
    elif kind == 'feed_movement':
        data['warehouse'] = st.text_input('Almacén / silo', key='op_feed_store')
        data['movement'] = st.selectbox('Movimiento de alimento', ['opening', 'receipt', 'consumption', 'return', 'transfer'],
            format_func=lambda x: {'opening': 'Saldo inicial', 'receipt': 'Recepción', 'consumption': 'Consumo observado', 'return': 'Devolución al almacén', 'transfer': 'Transferencia a otro almacén'}[x], key='op_feed_type')
        data['quantity_kg'] = _number('Cantidad · kg', 'op_feed_amount')
        data['sex'] = st.selectbox('Medición de alimento', ['mixto', 'hembra', 'macho'], key='op_feed_sex')
        if data['movement'] == 'transfer':
            data['destination_warehouse'] = st.text_input('Almacén de destino', key='op_feed_destination')
        st.caption('“Mixto” conserva una medición conjunta. No se reparte artificialmente entre sexos. Las recepciones no aumentan el alimento consumido del lote.')
    elif kind == 'environment':
        data['temperature_c'] = st.number_input('Temperatura puntual · °C', value=None, key='op_temp')
        data['humidity_pct'] = st.number_input('Humedad relativa puntual · %', min_value=0.0, max_value=100.0, value=None, key='op_humidity')
        data['box_id'] = None
        st.caption('La medición del galpón se guarda una vez. No se replica como si cada box tuviera un sensor independiente.')
    elif kind == 'health':
        data['action'] = st.selectbox('Acción', ['observation', 'vaccination', 'treatment'], format_func=lambda x: {'observation': 'Observación', 'vaccination': 'Vacunación registrada', 'treatment': 'Tratamiento indicado por responsable sanitario'}[x], key='op_health_type')
        data['cause'] = st.text_input('Causa informada · deja vacío si se desconoce', key='op_health_cause') or 'unknown'
        st.caption('Este registro conserva lo informado; no diagnostica ni prescribe tratamientos.')
    elif kind == 'stage':
        stages = ['engorde'] if lot.get('tipo_produccion') == 'engorde' else ['levante', 'prepostura', 'produccion']
        data['stage'] = st.selectbox('Nueva etapa', stages, key='op_stage')
        st.caption('La etapa se conserva como un cambio en la historia del mismo lote.')
    elif kind == 'readiness':
        data['item'] = st.text_input('Requisito definido por tu organización', key='op_ready_item')
        data['completed'] = st.checkbox('Verificado por la persona responsable', key='op_ready_check')
        st.caption('Registrar una verificación no certifica automáticamente aptitud sanitaria ni completa otros requisitos.')
    elif kind == 'arrival':
        data['expected'] = _number('Aves previstas', 'op_arrival_expected', integer=True)
        data['received'] = _number('Aves recibidas', 'op_arrival_received', integer=True)
        st.caption('Recepción documental vinculada al alojamiento. No duplica las aves iniciales del lote. Para ingresos adicionales usa Movimiento de aves.')
    _provenance_fields(data, 'op_event')
    data['note'] = st.text_area('Observación / motivo', key='op_event_note')
    if data.get('quality') == 'corrected' and not data['note'].strip():
        valid = False
        st.warning('Una corrección necesita un motivo.')
    if st.button('Registrar evento', type='primary', disabled=role not in WRITERS or not valid, key='op_event_save'):
        _record(client, org, kind, data, 'event')
    with st.expander('Historial original y correcciones'):
        _table(_rows(client, 'operations_events', org, lote_id=lot['id']), ['observed_at', 'kind', 'supersedes_id', 'source', 'quality', 'note', 'id'])
    with st.expander('Cronología de este lote'):
        events = _rows(client, 'effective_operations_events', org, lote_id=lot['id'])
        _table(sorted(events, key=lambda x: x.get('observed_at', ''), reverse=True), ['observed_at', 'kind', 'quantity', 'unit', 'source', 'quality', 'note', 'id'])


def _eggs(client, org, user, role, lotes, today):
    section_intro('Huevos e incubación', 'Sigue cada unidad desde su recolección o recepción hasta el despacho o nacimiento.')
    choices = {'Recolección por ronda': 'egg_collection', 'Recibir huevos de origen externo': 'egg_receipt', 'Clasificar una unidad': 'egg_classification',
               'Mover huevos entre etapas': 'egg_transfer', 'Dividir unidad': 'egg_split', 'Combinar unidades': 'egg_merge',
               'Cargar incubadora': 'hatch_set', 'Transferir tanda': 'hatch_transfer', 'Registrar nacimiento y muestra': 'hatch_result'}
    kind = choices[st.selectbox('Proceso', list(choices), key='op_egg_kind')]
    if kind == 'egg_collection':
        context = _event_context(client, lotes, today, 'op_egg', active=True)
        if not context:
            return
        lot, boxes, data = context
    else:
        lot, boxes = {}, []
        day = st.date_input('Fecha del proceso', today, max_value=today, key='op_egg_process_day')
        clock = st.time_input('Hora del proceso · Colombia', value=datetime.now(ZoneInfo('America/Bogota')).time().replace(tzinfo=None), key='op_egg_process_time')
        data = {'observed_at': f'{day}T{clock.isoformat()}-05:00', 'source': 'manual', 'quality': 'observed'}
        st.caption('La identidad viene de la unidad o tanda y sus orígenes. Incubación no necesita un galpón ficticio.')
    if kind == 'egg_classification' and st.checkbox('Reclasificar con historial', key='op_egg_regrade'):
        prior = [e for e in _rows(client, 'effective_operations_events', org) if e['kind'] == 'egg_classification']
        options = {f"{e['observed_at']} · {str(e['id'])[:8]}": e for e in prior}
        if options:
            original = options[st.selectbox('Clasificación anterior', list(options), key='op_egg_priorgrade')]
            data['supersedes_id'] = original['id']
            data['quality'] = 'corrected'
            data['lote_id'] = original.get('lote_id')
            data['box_id'] = original.get('box_id')
            _table([_flatten_event(original)])
    units = _rows(client, 'egg_units', org)
    batches = _rows(client, 'hatch_batches', org)
    movements = _rows(client, 'egg_movements', org)
    balances = {}
    stage_balances = {}
    for movement in movements:
        unit_id = movement['unit_id']
        balances[unit_id] = balances.get(unit_id, 0) + float(movement.get('quantity') or 0)
        stage = movement.get('stage', '—')
        stage_balances[(unit_id, stage)] = stage_balances.get((unit_id, stage), 0) + float(movement.get('quantity') or 0)
    unit_options = {f"{str(u['id'])[:8]} · origen {u.get('lote_id') or 'externo'} · disponibles {balances.get(u['id'], 0):g}": u['id'] for u in units if balances.get(u['id'], 0) > 0}
    batch_options = {f"{b.get('machine', 'Equipo')} · {str(b['id'])[:8]}": b['id'] for b in batches}
    valid = True
    if kind == 'egg_collection':
        if lot.get('tipo_produccion') not in ('postura', 'reproductoras'):
            st.warning('La recolección requiere un lote de postura o reproductoras.')
            valid = False
        data['round'] = st.text_input('Ronda / sesión de recolección', placeholder='Mañana · ronda 1', key='op_egg_round')
        data['quantity'] = _number('Huevos recolectados · unidades enteras', 'op_egg_count', integer=True)
        valid = valid and bool(data['round'].strip()) and data['quantity'] > 0
        st.caption('Cada ronda conserva su identidad. El total diario se deriva de las rondas; no se ingresa una segunda vez.')
    elif kind == 'egg_receipt':
        data['origin_ref'] = st.text_input('Referencia anónima y estable del origen', placeholder='ORIG-001', key='op_receipt_origin')
        data['quantity'] = _number('Huevos recibidos · unidades enteras', 'op_receipt_quantity', integer=True)
        data['storage_temp_c'] = st.number_input('Temperatura de almacenamiento observada · °C · opcional', value=None, key='op_receipt_storage_temp')
        valid = bool(data['origin_ref'].strip()) and data['quantity'] > 0 and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,120}', data['origin_ref']))
        st.caption('Usa un código de origen, sin nombres de clientes o proveedores. La recepción crea una unidad trazable y no requiere inventar granja ni galpón. Su posterior almacenamiento, división y carga se registran por separado. Requiere el módulo de incubación en la suscripción.')
    elif kind in ('egg_classification', 'egg_transfer', 'egg_split'):
        if not unit_options:
            st.info('Primero registra una recolección o una recepción externa para obtener una unidad trazable.')
            return
        data['unit_id'] = unit_options[st.selectbox('Unidad de huevo de origen', list(unit_options), key='op_egg_unit')]
        if kind == 'egg_classification':
            grades = st.data_editor(pd.DataFrame([{'categoria': 'Aptos', 'cantidad': 0}, {'categoria': 'Rotos', 'cantidad': 0}, {'categoria': 'Otros', 'cantidad': 0}]),
                                    num_rows='dynamic', hide_index=True, key='op_grades', use_container_width=True)
            try:
                raw = [(str(r['categoria']).strip(), float(r['cantidad'])) for r in grades.to_dict('records') if str(r['categoria']).strip()]
                valid = all(q >= 0 and q.is_integer() for _, q in raw) and len({n for n, _ in raw}) == len(raw)
                data['categories'] = {n: int(q) for n, q in raw}
            except (TypeError, ValueError):
                valid = False
            data['attributes'] = {'labels': st.multiselect('Atributos superpuestos · no se suman como categorías', ['Sucio', 'Piso', 'Doble yema', 'Otro'], key='op_egg_attributes')}
            st.caption('Las categorías deben conciliar la unidad. Un atributo superpuesto describe el huevo y no agrega un segundo conteo. Reclasificar requiere motivo y conserva el evento anterior.')
        else:
            data['quantity'] = _number('Cantidad · huevos', 'op_egg_quantity', integer=True)
            data['source_stage'] = st.selectbox('Etapa de origen', ['collection', 'classification', 'storage'], format_func=lambda x: {'collection': 'Recolección', 'classification': 'Clasificación', 'storage': 'Almacenamiento'}[x], key='op_egg_source_stage')
            if kind == 'egg_transfer':
                data['destination'] = st.selectbox('Etapa de destino', ['classification', 'storage', 'dispatch', 'rejected'],
                    format_func=lambda x: {'classification': 'Clasificación', 'storage': 'Almacenamiento', 'dispatch': 'Despacho', 'rejected': 'Rechazo'}[x], key='op_egg_dest')
    elif kind == 'egg_merge':
        selected = st.multiselect('Unidades que se combinarán', list(unit_options), key='op_egg_merge')
        data['unit_ids'] = [unit_options[s] for s in selected]
        valid = len(selected) >= 2
        st.caption('La nueva unidad mantiene las relaciones con todos sus orígenes. No se duplica la existencia.')
    elif kind == 'hatch_set':
        if not unit_options:
            st.info('Primero registra las unidades de huevo que se recibirán en incubación.')
            return
        data['hatchery_ref'] = st.text_input('Código de instalación de incubación', value='principal', key='op_hatch_site')
        data['machine'] = st.text_input('Equipo / incubadora y tanda', key='op_hatch_machine')
        st.caption('La suscripción limita instalaciones de incubación; cada instalación puede registrar sus equipos.')
        selected = st.multiselect('Unidades de origen incluidas en la carga', list(unit_options), key='op_hatch_origins')
        data['inputs'] = [{'unit_id': unit_options[s], 'quantity': _number(f'Huevos de {s}', 'op_hatch_amount_'+unit_options[s], integer=True)} for s in selected]
        valid = bool(selected) and bool(data['machine'].strip())
        st.caption('Una tanda puede mezclar orígenes. El sistema registra la cantidad aportada por cada unidad y evita reutilizar huevos ya cargados.')
    else:
        if not batch_options:
            st.info('Primero registra una carga de incubación.')
            return
        data['batch_id'] = batch_options[st.selectbox('Tanda', list(batch_options), key='op_hatch_batch')]
        if kind == 'hatch_transfer':
            data['machine'] = st.text_input('Equipo de nacimiento / destino', key='op_hatch_transfer')
        else:
            data['hatched'] = _number('Pollitos nacidos', 'op_hatched', integer=True)
            data['rejected'] = _number('Rechazados', 'op_hatch_rejected', integer=True)
            data['unhatched'] = _number('No nacidos', 'op_unhatched', integer=True)
            measured_sample = st.checkbox('Se realizó una muestra de fertilidad / embriodiagnóstico', key='op_hatch_sample_measured')
            data['sample_n'] = _number('Huevos examinados en la muestra', 'op_hatch_n', integer=True, optional=True) if measured_sample else None
            data['fertile_sample'] = _number('Huevos fértiles de esa muestra · opcional', 'op_fertile', integer=True, optional=True) if measured_sample else None
            if measured_sample and (not data['sample_n'] or (data['fertile_sample'] is not None and data['fertile_sample'] > data['sample_n'])):
                valid = False
                st.warning('La muestra requiere tamaño positivo y un conteo de fértiles que no lo supere.')
            st.caption('Fertilidad = fértiles observados / huevos examinados de la muestra. El denominador muestral no se presenta como toda la carga.')
    data['note'] = st.text_area('Condiciones de almacenamiento / motivo / observación', key='op_egg_note')
    if data.get('quality') == 'corrected' and not data['note'].strip():
        valid = False
        st.warning('La reclasificación requiere un motivo.')
    if st.button('Confirmar operación de trazabilidad', type='primary', disabled=role not in WRITERS or not valid, key='op_egg_save'):
        _record(client, org, kind, data, 'eggs')
    with st.expander('Existencias y relaciones de origen'):
        _table([{**u, 'saldo_disponible': balances.get(u['id'], 0)} for u in units])
        _table([{'unit_id': unit_id, 'etapa': stage, 'saldo': amount} for (unit_id, stage), amount in stage_balances.items()])
        _table(_rows(client, 'egg_unit_links', org))
    with st.expander('Cargas y asignación de orígenes'):
        _table(batches)
        _table(_rows(client, 'hatch_inputs', org))


def _agenda(client, org, user, role, lotes, today):
    section_intro('Tu agenda de producción', 'Organiza los pendientes, asigna responsables y da seguimiento a cada incidencia.')
    tasks = _rows(client, 'operation_tasks', org)
    incidents = _rows(client, 'operation_incidents', org)
    open_tasks = [t for t in tasks if t.get('status') == 'open']
    overdue = [t for t in open_tasks if str(t.get('due_date', '')) < str(today)]
    a, b, c = st.columns(3)
    a.metric('Tareas pendientes', len(open_tasks))
    b.metric('Vencidas', len(overdue))
    c.metric('Incidencias abiertas', len([i for i in incidents if i.get('status') != 'resolved']))
    mode = st.radio('Acción', ['Crear tarea', 'Actualizar tarea', 'Abrir incidencia', 'Gestionar incidencia'], horizontal=True, key='op_agenda_mode')
    lot = _lot_picker(lotes, 'op_agenda_lot', active=True)
    if not lot:
        return
    data = {'lote_id': lot['id'], 'observed_at': datetime.now(timezone.utc).isoformat(), 'source': 'manual', 'quality': 'observed'}
    memberships = client.table('organization_memberships').select('user_id,role').eq('organization_id', org).execute().data or []
    profiles = {}
    for offset in range(0, len(memberships), 100):
        ids = [member['user_id'] for member in memberships[offset:offset + 100]]
        try:
            rows = client.table('user_profiles').select('user_id,full_name,username').in_('user_id', ids).execute().data or []
            profiles.update({person['user_id']: person for person in rows})
        except Exception:
            pass  # Profiles may be scoped to the current account; memberships remain authoritative.
    members = {'Sin asignar': None}
    for member in memberships:
        person = profiles.get(member['user_id'], {})
        label = person.get('full_name') or person.get('username') or ('Usuario ' + member['user_id'][:8])
        label += ' · ' + {'owner':'Propietario','admin':'Administrador','operator':'Operador','analyst':'Analista'}.get(member['role'], member['role'])
        members[label + ' · ' + member['user_id'][:6]] = member['user_id']
    valid = True
    if mode == 'Crear tarea':
        kind = 'task'
        data['title'] = st.text_input('Trabajo a realizar', key='op_task_title')
        data['due_date'] = str(st.date_input('Vencimiento', today, key='op_task_due'))
        data['assigned_to'] = members[st.selectbox('Responsable', list(members), key='op_task_owner')]
        valid = bool(data['title'].strip())
        st.caption('Vencer una tarea no genera pesajes, vacunaciones ni registros. Se completa al verificar el trabajo realizado.')
    elif mode == 'Actualizar tarea':
        kind = 'task_update'
        choices = {f"{t['title']} · {t.get('status')}": t for t in tasks if t.get('lote_id') == lot['id']}
        if not choices:
            st.info('Este lote aún no tiene tareas.')
            _table(tasks)
            return
        task = choices[st.selectbox('Tarea', list(choices), key='op_task_select')]
        data['task_id'] = task['id']
        pin = 'op_task_version_' + task['id']
        if pin not in st.session_state:
            st.session_state[pin] = task.get('version', 1)
        data['expected_version'] = st.session_state[pin]
        if st.button('Recargar estado de la tarea', key='op_task_reload'):
            st.session_state[pin] = task.get('version', 1)
            st.rerun()
        data['status'] = st.selectbox('Nuevo estado', ['open', 'done', 'cancelled'], format_func=lambda x: {'open': 'Pendiente', 'done': 'Realizada', 'cancelled': 'Cancelada'}[x], key='op_task_status')
        events = _rows(client, 'effective_operations_events', org, lote_id=lot['id'])
        events = [e for e in events if e['kind'] != 'readiness' or (e.get('data') or {}).get('completed') is True]
        evidence = {'Sin evidencia asociada': None, **{f"{e['kind']} · {e.get('observed_at')} · {str(e['id'])[:8]}": e['id'] for e in events if e['kind'] in ('bird_movement', 'weighing', 'water_reading', 'feed_movement', 'environment', 'health', 'stage', 'readiness', 'arrival', 'egg_collection', 'egg_receipt', 'egg_classification', 'egg_transfer', 'egg_split', 'egg_merge', 'hatch_set', 'hatch_transfer', 'hatch_result') }}
        data['evidence_event_id'] = evidence[st.selectbox('Evento que acredita la realización', list(evidence), key='op_task_evidence')]
        if data['status'] == 'done' and not data['evidence_event_id']:
            st.warning('Asocia un hecho registrado para confirmar la realización de esta tarea.')
            valid = False
    elif mode == 'Abrir incidencia':
        kind = 'incident'
        data['title'] = st.text_input('Incidencia', key='op_inc_title')
        data['rule_version'] = st.text_input('Regla y versión aplicada', placeholder='Revisión humana v1', key='op_inc_rule')
        data['explanation'] = st.text_area('Qué dato falta o qué observación origina la incidencia', key='op_inc_explain')
        data['assigned_to'] = members[st.selectbox('Responsable', list(members), key='op_inc_owner')]
        valid = all(str(data[k]).strip() for k in ('title', 'rule_version', 'explanation'))
        st.caption('Una ausencia se registra como sin dato. No se interpreta como normal. La misma incidencia del lote y regla se actualiza sin repetirse por cada visita.')
    else:
        kind = 'incident_update'
        choices = {f"{i['title']} · {i.get('status')}": i for i in incidents if i.get('lote_id') == lot['id']}
        if not choices:
            st.info('Este lote no tiene incidencias.')
            return
        incident = choices[st.selectbox('Incidencia', list(choices), key='op_inc_select')]
        st.write(incident.get('explanation', ''))
        data['incident_id'] = incident['id']
        pin = 'op_incident_version_' + incident['id']
        if pin not in st.session_state:
            st.session_state[pin] = incident.get('version', 1)
        data['expected_version'] = st.session_state[pin]
        if st.button('Recargar estado de la incidencia', key='op_incident_reload'):
            st.session_state[pin] = incident.get('version', 1)
            st.rerun()
        data['status'] = st.selectbox('Estado de seguimiento', ['open', 'acknowledged', 'resolved'], format_func=lambda x: {'open': 'Abierta', 'acknowledged': 'Reconocida', 'resolved': 'Resuelta'}[x], key='op_inc_status')
    data['note'] = st.text_area('Nota / motivo de actualización', key='op_agenda_note')
    if mode == 'Gestionar incidencia' and data.get('status') == 'resolved' and not data['note'].strip():
        valid = False
    if st.button('Guardar seguimiento', type='primary', disabled=role not in WRITERS or not valid, key='op_agenda_save'):
        if _record(client, org, kind, data, 'agenda'):
            if kind == 'task_update':
                st.session_state.pop('op_task_version_' + data['task_id'], None)
            if kind == 'incident_update':
                st.session_state.pop('op_incident_version_' + data['incident_id'], None)
            st.session_state['op_notice'] = 'Seguimiento guardado. La agenda muestra el estado actualizado.'
            st.rerun()
    st.markdown('**Agenda de la organización**')
    _table(tasks, ['title', 'lote_id', 'due_date', 'assigned_to', 'status', 'evidence_event_id'])
    st.markdown('**Bandeja de incidencias**')
    _table(incidents, ['title', 'lote_id', 'rule_version', 'explanation', 'assigned_to', 'status'])


def _importer(client, org, user, role, lotes, today):
    from import_tools import inspect_upload, preview_import, UNIT_TARGETS
    section_intro('Importa una planilla con confianza', 'Carga el archivo, relaciona sus columnas y revisa el resultado antes de guardarlo.')
    workflow_steps(['Elegir archivo', 'Relacionar columnas', 'Revisar y confirmar'], current=0)
    st.caption('Solo se leen CSV y XLSX. No se ejecutan macros, fórmulas ni vínculos externos. Los resúmenes semanales quedan pendientes y no se convierten en días inventados.')
    example = 'lote_id,box_id,fecha,event_type,source_event_id,count,temperature_c,humidity_pct\n1,1,2026-11-25,egg_collection,ronda-1,100,,\n'
    st.download_button('Plantilla de ejemplo · sintética · reemplazar identidades', example, file_name='avidata-ejemplo-sintetico.csv', mime='text/csv', key='op_import_example')
    uploaded = st.file_uploader('Planilla de origen', type=['xlsx', 'csv'], key='op_import_file')
    if not uploaded:
        return
    sheet = st.number_input('Hoja · ordinal desde 1', min_value=1, value=1, step=1, key='op_import_sheet')
    try:
        inspected = inspect_upload(uploaded.getvalue(), uploaded.name, sheet_index=sheet-1)
    except (ValueError, TypeError):
        st.error('No se pudo leer este archivo de forma segura. Revisa formato, tamaño, hoja, macros y vínculos externos.')
        return
    for warning in inspected.get('warnings', []):
        st.warning(warning)
    fields = ['lote_id', 'box_id', 'fecha', 'event_type', 'source_event_id', 'count', 'temperature_c', 'humidity_pct',
              'mortalidad_hembra', 'mortalidad_macho', 'descarte_hembra', 'descarte_macho', 'consumo_alimento_kg',
              'consumo_agua_litros', 'peso_promedio_hembra_g', 'peso_promedio_macho_g']
    labels = {**{code: label for code, label, _, _ in FIELDS},
              'lote_id': 'ID del lote', 'box_id': 'ID del box', 'fecha': 'Fecha efectiva',
              'event_type': 'Tipo de evento', 'source_event_id': 'ID de fila / ronda en el origen',
              'count': 'Cantidad de huevos · unidades', 'temperature_c': 'Temperatura · °C',
              'humidity_pct': 'Humedad relativa · %'}
    mapping, units = {}, {}
    st.caption('Asigna identidad y fecha primero. Abre solo los grupos que correspondan a tu planilla; los campos sin asignar no se importan.')
    groups = [
        ('1 · Lote, box y fecha', ['lote_id', 'box_id', 'fecha'], True),
        ('2 · Muertas, descartes y consumos', fields[8:14], True),
        ('Pesos opcionales', fields[14:], False),
        ('Recolecciones, ambiente y origen de los eventos', fields[3:8], False),
    ]
    for title, group, expanded in groups:
        with st.expander(title, expanded=expanded):
            containers = st.columns(2)
            for index_in_group, field in enumerate(group):
                with containers[index_in_group % 2]:
                    columns = ['Sin asignar'] + inspected['columns']
                    index = columns.index(field) if field in columns else 0
                    selection = st.selectbox(labels.get(field, field), columns, index=index, key='op_import_map_'+field)
                    if selection != 'Sin asignar':
                        mapping[field] = selection
                        if field in UNIT_TARGETS:
                            units[field] = st.selectbox('Unidad de origen · '+labels.get(field, field),
                                list(UNIT_TARGETS[field][1]), key='op_import_unit_'+field)
    format_columns = st.columns(2)
    period = format_columns[0].selectbox('Frecuencia real del origen', ['daily', 'weekly', 'summary'], format_func=lambda x: {'daily': 'Filas diarias / eventos', 'weekly': 'Resumen semanal', 'summary': 'Totales / resumen'}[x], key='op_import_period')
    date_format = format_columns[1].selectbox('Formato de fecha del archivo', ['ISO (AAAA-MM-DD)', '%d/%m/%Y', '%m/%d/%Y'], key='op_import_dateformat')
    st.caption('Revisa el significado: mortalidad son muertas; descartes van por separado. Un contador acumulado de agua no se importa como consumo diario. ID de lote y box deben corresponder a tu organización.')
    existing = _rows(client, 'effective_operations_events', org)
    keys = [e.get('external_id') for e in existing if e.get('external_id')]
    try:
        preview = preview_import(uploaded.getvalue(), uploaded.name, mapping, units=units, period=period,
                                 date_format=None if date_format.startswith('ISO') else date_format, existing_keys=keys, sheet_index=sheet-1)
    except (ValueError, TypeError):
        st.info('Asigna al menos ID del lote y fecha y revisa los formatos para generar la vista previa.')
        return
    cols = st.columns(4)
    for col, code, title in zip(cols, ['valid', 'invalid', 'pending', 'duplicates'], ['Válidas', 'Inválidas', 'Pendientes', 'Identidad repetida']):
        col.metric(title, len(preview[code]))
    st.markdown('**Vista previa de campos asignados**')
    _table(preview['valid'])
    for code, title in [('invalid', 'Errores por fila'), ('pending', 'Revisión pendiente'), ('duplicates', 'Conflictos de identidad')]:
        with st.expander(title):
            _table(preview[code])
    reviewed = st.checkbox('Verifiqué significado, unidades, identidades y conciliación con el origen', key='op_import_confirm')
    if st.button('Importar filas válidas', type='primary', disabled=role not in WRITERS or not reviewed or not preview['valid'] or bool(preview['invalid'] or preview['pending'] or preview['duplicates']), key='op_import_save'):
        _submit_import(client, org, preview)


def _submit_import(client, org, preview):
    """Adapt only documented event schemas, never infer daily facts from totals."""
    rows = []
    daily = {}
    allowed = {'egg_collection', 'environment', 'daily'}
    for row in preview['valid']:
        kind = row.get('event_type') or 'daily'
        if kind not in allowed:
            st.error('Esta plantilla admite daily, egg_collection y environment. Los demás eventos tienen formularios con su contexto específico.')
            return
        try:
            lote_id = int(row['lote_id'])
            box_id = int(row['box_id']) if row.get('box_id') not in (None, '') else None
        except (ValueError, TypeError):
            st.error('Las identidades de lote y box deben ser números enteros existentes.')
            return
        data = {'lote_id': lote_id, 'box_id': box_id, 'observed_at': row['fecha']+'T12:00:00-05:00',
                'source': 'import', 'quality': 'observed', 'external_id': row['_key'], 'note': 'Importación revisada'}
        if kind == 'egg_collection':
            if 'count' not in row or not row.get('source_event_id'):
                st.error('Cada recolección necesita cantidad e identificador de ronda en el origen.')
                return
            data.update(quantity=row['count'], round=str(row['source_event_id']))
        elif kind == 'environment':
            data.update(temperature_c=row.get('temperature_c'), humidity_pct=row.get('humidity_pct'))
        else:
            group = daily.setdefault((lote_id, row['fecha']), [])
            group.append({k: v for k, v in row.items() if k in {f[0] for f in FIELDS} or k == 'box_id'})
            continue
        rows.append({'kind': kind, 'data': data, 'key': row['_key']})
    for (lot_id, day), boxes in daily.items():
        rows.append({'kind': 'daily', 'data': {'lote_id': lot_id, 'fecha': day, 'boxes': boxes},
                     'key': hashlib.sha256(json.dumps([lot_id, day, boxes], sort_keys=True).encode()).hexdigest()})
    result = _rpc(client, 'import_operations', {'p_organization_id': org, 'p_rows': rows, 'p_import_key': preview['sha256']})
    if result is not None:
        st.success('Importación confirmada. Las identidades repetidas se conservan sin duplicar hechos.')


def _flatten_event(event):
    return {**event, **(event.get('data') or {})}


def _trace(client, org, user, role, lotes, today):
    section_intro('Explora tu producción', 'Consulta el ciclo, revisa existencias y comparte informes con sus datos de respaldo.')
    mode = st.selectbox('Herramienta', ['Cronología del ciclo', 'Inventario y cobertura de alimento', 'Identidad y QR', 'Objetivos versionados', 'Plan y pronóstico', 'Informe reproducible de ciclo'], index=2 if st.query_params.get('trace') else 0, key='op_trace_mode')
    lot = _lot_picker(lotes, 'op_trace_lot')
    if not lot:
        return
    events = _rows(client, 'effective_operations_events', org, lote_id=lot['id'])
    flattened = [_flatten_event(e) for e in events]
    if mode == 'Cronología del ciclo':
        selected = st.multiselect('Tipos de hecho', sorted({e['kind'] for e in events}), default=sorted({e['kind'] for e in events}), key='op_timeline_types')
        focus = {'Todo el ciclo': None, **{f"{e['observed_at']} · {e['kind']} · {str(e['id'])[:8]}": e for e in flattened}}
        chosen = focus[st.selectbox('Investigar alrededor de un hecho', list(focus), key='op_timeline_focus')]
        window = st.slider('Días antes y después del hecho', 1, 14, 3, key='op_timeline_window') if chosen else None
        context_events = flattened
        if chosen:
            center = datetime.fromisoformat(chosen['observed_at'].replace('Z', '+00:00'))
            context_events = [e for e in flattened if abs((datetime.fromisoformat(e['observed_at'].replace('Z', '+00:00')) - center).total_seconds()) <= window * 86400]
            _table([chosen])
            st.caption('La ventana muestra los hechos registrados y su procedencia. Los intervalos sin mediciones quedan sin cobertura.')
        _table(sorted([e for e in context_events if e['kind'] in selected], key=lambda e: e['observed_at']), ['observed_at', 'kind', 'box_id', 'quantity', 'weight_g', 'temperature_c', 'humidity_pct', 'source', 'quality', 'note'])
        ambient = [e for e in context_events if e['kind'] == 'environment']
        if ambient:
            frame = pd.DataFrame(ambient)
            cols = [c for c in ('temperature_c', 'humidity_pct') if c in frame]
            if cols:
                st.line_chart(frame.set_index('observed_at')[cols], use_container_width=True)
        st.caption('Son lecturas puntuales: no se suman como consumo. Las coincidencias temporales ayudan a investigar hipótesis; no demuestran causalidad.')
    elif mode == 'Inventario y cobertura de alimento':
        from avilab_domain import feed_inventory
        all_events = [_flatten_event(e) for e in _rows(client, 'effective_operations_events', org) if e['kind'] == 'feed_movement']
        stores = sorted({e.get('warehouse') for e in all_events if e.get('warehouse')} | {e.get('destination_warehouse') for e in all_events if e.get('destination_warehouse')})
        if not stores:
            st.info('Registra el saldo inicial y los movimientos de tu almacén para ver su balance.')
            return
        store = st.selectbox('Almacén / silo', stores, key='op_stock_store')
        opening, ledger, consumption_by_day = 0, [], {}
        for e in sorted(all_events, key=lambda r: r['observed_at']):
            movement = e.get('movement')
            amount = e.get('quantity_kg', e.get('quantity', 0))
            if e.get('warehouse') == store:
                if movement == 'opening':
                    opening += float(amount or 0)
                    continue
                kind = {'receipt': 'receipt', 'return': 'return_in', 'consumption': 'consumption', 'transfer': 'transfer_out'}.get(movement)
                if kind:
                    ledger.append({'kind': kind, 'kg': amount, 'observed_at': e['observed_at']})
                if movement == 'consumption':
                    day = e['observed_at'][:10]
                    consumption_by_day[day] = consumption_by_day.get(day, 0) + float(amount or 0)
            elif e.get('destination_warehouse') == store and movement == 'transfer':
                ledger.append({'kind': 'transfer_in', 'kg': amount, 'observed_at': e['observed_at']})
        try:
            window_start = today - timedelta(days=6)
            consumption = [{'fecha': str(window_start + timedelta(days=i)), 'kg': consumption_by_day.get(str(window_start + timedelta(days=i)))} for i in range(7)]
            summary = feed_inventory(opening, ledger, consumption)
            a, b = st.columns(2)
            a.metric('Existencia conciliada', f"{summary['closing_kg']:.1f} kg")
            b.metric('Cobertura estimada', f"{summary['coverage_days']:.1f} días" if summary['coverage_days'] is not None else 'Sin cobertura suficiente')
            st.caption('La cobertura exige 7 días consecutivos medidos hasta hoy. Una ausencia no se transforma en cero. Las existencias no se alteran con el pronóstico.')
            _table(ledger)
        except (ValueError, TypeError):
            st.warning('El inventario no concilia. Revisa apertura, fechas y movimientos antes de interpretar cobertura.')
    elif mode == 'Identidad y QR':
        import qrcode
        units = _rows(client, 'egg_units', org)
        options = {f"Lote {l.get('codigo_lote')}": f"lot:{l['id']}" for l in lotes}
        options.update({f"Unidad de huevo {str(u['id'])[:8]}": f"egg:{u['id']}" for u in units})
        reference = options[st.selectbox('Crear etiqueta de', list(options), key='op_qr_entity')]
        url = 'https://avidata.streamlit.app/?trace=' + reference
        image = qrcode.make(url)
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        st.image(buffer.getvalue(), width=210)
        st.code(reference)
        st.download_button('Descargar etiqueta QR', buffer.getvalue(), file_name='avidata-etiqueta.png', mime='image/png', key='op_qr_download')
        lookup = st.text_input('Referencia escaneada / búsqueda manual', value=st.query_params.get('trace', ''), key='op_qr_lookup')
        if lookup:
            reference = lookup.rsplit('trace=', 1)[-1]
            matches = [l for l in lotes if reference == f"lot:{l['id']}"] + [u for u in units if reference == f"egg:{u['id']}"]
            if matches:
                _table(matches)
                if reference.startswith('egg:'):
                    links = _rows(client, 'egg_unit_links', org)
                    _table([r for r in links if reference[4:] in (str(r.get('parent_id')), str(r.get('child_id')), str(r.get('source_unit_id')), str(r.get('destination_unit_id')))])
            else:
                st.warning('Referencia no disponible para tu organización. Escanear no otorga permisos ni crea movimientos.')
        st.caption('La etiqueta contiene únicamente tipo e identidad estable. Siempre se requiere iniciar sesión y tener acceso a la organización.')
    elif mode == 'Objetivos versionados':
        effective_ids = {e['id'] for e in _rows(client, 'effective_operations_events', org) if e['kind'] == 'target'}
        targets = [r for r in _rows(client, 'production_targets', org) if r['id'] in effective_ids]
        _table(targets, ['name', 'edition', 'genetics', 'sex', 'stage', 'metric', 'unit', 'denominator', 'source_url'])
        st.caption('Una guía sin edición o contexto compatible no se aplica silenciosamente. Los objetivos son referencias, nunca mediciones del lote.')
        if role in MANAGERS:
            data = {'lote_id': lot['id'], 'observed_at': datetime.now(timezone.utc).isoformat(), 'source': 'manual', 'quality': 'observed'}
            with st.expander('Registrar referencia verificada'):
                for field, label in [('name', 'Nombre de la guía'), ('edition', 'Edición / fecha'), ('genetics', 'Genética'), ('source_url', 'URL de la fuente oficial')]:
                    data[field] = st.text_input(label, key='op_target_'+field)
                data['sex'] = st.selectbox('Sexo aplicable', ['hembra', 'macho', 'mixto'], key='op_target_sex')
                data['stage'] = st.selectbox('Etapa aplicable', ['engorde', 'levante', 'prepostura', 'produccion'], key='op_target_stage')
                indicators = {'peso_promedio_mixto_g': ('g', 'ave_viva'), 'peso_promedio_hembra_g': ('g', 'ave_viva'), 'peso_promedio_macho_g': ('g', 'ave_viva'), 'fcr_acumulado': ('kg/kg', 'biomasa_viva_kg'), 'consumo_g_ave': ('g/ave', 'ave_viva_dia'), 'ratio_agua_alimento': ('L/kg', 'alimento_kg'), 'gmd_g': ('g/día', 'dias_entre_pesajes'), 'mortalidad_pct': ('%', 'aves_iniciales'), 'mortalidad_hembra_pct': ('%', 'aves_iniciales'), 'mortalidad_macho_pct': ('%', 'aves_iniciales'), 'epef': ('índice', 'edad_fcr_viabilidad')}
                data['metric'] = st.selectbox('Indicador de la guía', list(indicators), key='op_target_metric')
                data['unit'], data['denominator'] = indicators[data['metric']]
                st.caption(f"Unidad: {data['unit']} · Denominador: {data['denominator']}. Si la guía usa otra definición, no es compatible con este indicador.")
                curve = st.data_editor(pd.DataFrame([{'age': 1, 'value': None}]), num_rows='dynamic', hide_index=True, key='op_target_curve', use_container_width=True)
                import math
                data['points'] = []
                curve_valid = True
                for point in curve.to_dict('records'):
                    try:
                        age, value = float(point['age']), float(point['value'])
                        if not age.is_integer() or age < 1 or not math.isfinite(value) or value < 0:
                            raise ValueError()
                        data['points'].append({'age': int(age), 'value': value})
                    except (TypeError, ValueError, OverflowError):
                        curve_valid = False
                if not curve_valid:
                    st.info('Completa cada día de vida y su valor antes de guardar la curva.')
                st.caption('Edad en AviData: día 1 = fecha de alojamiento. Revisa la correspondencia si la fuente empieza en día 0; no se desplazan edades automáticamente.')
                confirmed = st.checkbox('Verifiqué fuente, edición, sexo, etapa, unidades y denominador', key='op_target_confirm')
                if st.button('Guardar nueva versión de referencia', disabled=not confirmed or not curve_valid or not data['points'], key='op_target_save'):
                    _record(client, org, 'target', data, 'target')
    elif mode == 'Plan y pronóstico':
        _plans(client, org, role, lot, today)
    else:
        _snapshots(client, org, role, lot, today)


def _plans(client, org, role, lot, today):
    from avilab_domain import forecast_baseline, chronological_backtest
    effective_ids = {e['id'] for e in _rows(client, 'effective_operations_events', org, lote_id=lot['id']) if e['kind'] == 'plan'}
    plans = [r for r in _rows(client, 'production_plans', org, lote_id=lot['id']) if r['id'] in effective_ids]
    _table(plans, ['target_date', 'metric', 'unit', 'value'])
    with st.expander('Registrar un plan · no modifica existencias'):
        metric = st.selectbox('Indicador previsto', ['consumo_alimento_kg', 'consumo_agua_litros', 'peso_promedio_hembra_g', 'peso_promedio_macho_g'], key='op_plan_metric')
        unit = 'kg' if metric == 'consumo_alimento_kg' else 'L' if metric == 'consumo_agua_litros' else 'g'
        value = _number('Objetivo previsto · '+unit, 'op_plan_value')
        target_date = st.date_input('Fecha prevista', today, key='op_plan_date')
        note = st.text_input('Supuestos del plan', key='op_plan_note')
        if st.button('Guardar plan', disabled=role not in MANAGERS, key='op_plan_save'):
            _record(client, org, 'plan', {'lote_id': lot['id'], 'observed_at': datetime.now(timezone.utc).isoformat(), 'target_date': str(target_date), 'metric': metric, 'unit': unit, 'value': value, 'note': note}, 'plan')
    metric = st.selectbox('Indicador para línea base', ['consumo_alimento_kg', 'consumo_agua_litros', 'peso_promedio_hembra_g', 'peso_promedio_macho_g'], key='op_forecast_metric')
    horizon = st.slider('Horizonte · días', 1, 30, 7, key='op_forecast_horizon')
    cutoff = st.date_input('Fecha de corte del pronóstico', today, max_value=today, key='op_forecast_cutoff')
    rows = client.table('registros_diarios').select('*,daily_captures!inner(status)').in_('daily_captures.status', ['submitted', 'reviewed', 'closed']).eq('lote_id', lot['id']).lte('fecha', str(cutoff)).order('fecha').limit(1000).execute().data or []
    forecast = forecast_baseline(rows, horizon, metric=metric, cutoff=str(cutoff))
    _table([{'fecha': r['fecha'], 'valor': r.get(metric), 'tipo': 'Observado'} for r in rows] + [{'fecha': r['fecha'], 'valor': r['value'], 'tipo': 'Pronóstico · última observación'} for r in forecast['points']])
    if rows or forecast['points']:
        actual = pd.DataFrame([{'fecha': r['fecha'], 'Observado': r.get(metric)} for r in rows])
        predicted = pd.DataFrame([{'fecha': r['fecha'], 'Pronóstico': r['value']} for r in forecast['points']])
        planned = pd.DataFrame([{'fecha': p['target_date'], 'Plan': p['value']} for p in plans if p['metric'] == metric])
        if not planned.empty:
            planned = planned.groupby('fecha', as_index=False).last()
        frames = [f.set_index('fecha') for f in (actual, predicted, planned) if not f.empty]
        if frames:
            st.line_chart(pd.concat(frames, axis=1), use_container_width=True)
    st.caption('Línea base transparente: repite la última observación disponible a la fecha de corte. No es una predicción validada ni actualiza inventarios. Las fechas previstas no cierran lotes automáticamente.')
    if st.button('Evaluar línea base con ciclos reales cerrados', key='op_forecast_backtest'):
        accessible = client.table('lotes').select('id,activo,fecha_cierre,is_synthetic,galpones!inner(granjas!inner(organization_id))').eq('galpones.granjas.organization_id', org).eq('activo', False).eq('is_synthetic', False).limit(1000).execute().data or []
        cycles = []
        for closed in accessible:
            history = client.table('registros_diarios').select('*,daily_captures!inner(status)').in_('daily_captures.status', ['submitted', 'reviewed', 'closed']).eq('lote_id', closed['id']).order('fecha').limit(1000).execute().data or []
            cycles.append(dict(closed, estado='closed', history=history))
        result = chronological_backtest(cycles, metric=metric, horizon=horizon)
        if result['status'] == 'insufficient_real_cycles':
            st.info('No hay suficientes ciclos reales cerrados y completos para evaluar. Los lotes sintéticos están excluidos.')
        else:
            st.metric('Error absoluto medio de la línea base', f"{result['mae']:.3f}")
            _table(result['folds'])


def _snapshots(client, org, role, lot, today):
    from cycle_report import build_frozen_report
    snapshots = _rows(client, 'cycle_snapshots', org, lote_id=lot['id'])
    st.caption('Una instantánea conserva los hechos y reglas a una fecha de corte. Regenerar la misma versión exporta los mismos datos; nuevas correcciones producen otra versión.')
    cutoff = st.date_input('Corte del informe', today, max_value=today, key='op_snapshot_cutoff')
    title = st.text_input('Título del informe', value='Informe de ciclo', key='op_snapshot_title')
    if st.button('Crear instantánea versionada', disabled=role not in MANAGERS, key='op_snapshot_save'):
        _record(client, org, 'snapshot', {'lote_id': lot['id'], 'observed_at': datetime.now(timezone.utc).isoformat(), 'title': title, 'cutoff': str(cutoff)}, 'snapshot')
    if not snapshots:
        st.info('Aún no se ha generado una instantánea de este ciclo.')
        return
    options = {f"Versión {s['version']} · corte {s['cutoff']} · {s['title']}": s for s in snapshots}
    selected = options[st.selectbox('Versión conservada', list(options), key='op_snapshot_select')]
    content = selected.get('content') or {}
    if isinstance(content, str):
        content = json.loads(content)
    anonymous = st.checkbox('Anonimizar para compartir', value=True, key='op_snapshot_anon')
    snapshot = build_frozen_report(content, selected['version'], anonymize=anonymous)
    if not snapshot['has_frozen_production']:
        st.warning('Esta versión no contiene todos los encabezados y detalles productivos congelados. Conserva la evidencia disponible, pero no se presenta como un informe zootécnico completo.')
    if snapshot['indicators']:
        st.markdown('**Indicadores del ciclo conservado**')
        _table(snapshot['indicators'])
    if snapshot['coverage']:
        with st.expander('Cobertura por indicador y edad'):
            _table(snapshot['coverage'])
    with st.expander('Definiciones, unidades y límites de interpretación'):
        st.json(snapshot['definitions'])
    st.code(snapshot['sha256'], language=None)
    st.download_button('Descargar informe JSON', snapshot['content'], file_name=f'avidata-ciclo-v{selected["version"]}.json', mime='application/json', key='op_snapshot_json')
    st.download_button('Descargar hechos CSV', snapshot['csv'], file_name=f'avidata-ciclo-v{selected["version"]}.csv', mime='text/csv', key='op_snapshot_csv')
    if not anonymous:
        st.caption('El archivo completo puede contener datos internos de tu organización. El modo anonimizado excluye identidades y notas libres.')


def _onboarding(client, org, user, role, lotes, today):
    section_intro('Prepara tu primera jornada', 'Revisa la estructura de tu organización y practica con un ejemplo antes de registrar datos reales.')
    organization = client.table('organizations').select('name').eq('id', org).execute().data or []
    farms = client.table('granjas').select('id,nombre').eq('organization_id', org).execute().data or []
    st.markdown('**1 · Organización y estructura**')
    _table([{'Organización': organization[0]['name'] if organization else 'Pendiente', 'Granjas': len(farms), 'Lotes': len(lotes), 'Perfil': role}])
    if not farms:
        st.info('Crea primero una granja en el menú Granjas y luego un galpón. Este asistente no inventa direcciones ni coordenadas.')
    lot = _lot_picker(lotes, 'op_setup_lot')
    if lot:
        st.markdown('**2 · Producción y etapa**')
        _table([{'Tipo': lot.get('tipo_produccion', 'Pendiente'), 'Genética': lot.get('linea_genetica') or 'Pendiente', 'Alojamiento': lot.get('fecha_encaste') or 'Pendiente', 'Estado': 'Activo' if lot.get('activo') else 'Cerrado'}])
        stages = _rows(client, 'effective_operations_events', org, lote_id=lot['id'])
        actual_stage = [e for e in stages if e.get('kind') == 'stage']
        if not actual_stage:
            st.info('La etapa no está registrada. Puedes declarar su inicio en Eventos productivos → Cambio de etapa.')
    st.markdown('**3 · Unidades y ensayo sintético**')
    unit = st.selectbox('Unidad que usa tu planilla para alimento', ['kg', 'g', 't'], key='op_setup_feedunit')
    raw = _number('Cantidad del ejemplo sintético', 'op_setup_raw', value=1000.0)
    converted = raw * {'kg': 1, 'g': .001, 't': 1000}[unit]
    st.metric('Cantidad que quedaría guardada', f'{converted:,.3f} kg')
    st.warning('EJEMPLO SINTÉTICO · esta vista no se guarda como un registro productivo.')
    st.markdown('**4 · Antes de importar**')
    st.checkbox('Separé muertas de descartes y lecturas acumuladas de consumo', key='op_setup_semantics')
    st.checkbox('Verifiqué identificadores de lote/box, fechas y unidades', key='op_setup_identity')
    st.checkbox('Revisé la vista previa y los campos pendientes', key='op_setup_preview')
    st.caption('Para terminar: revisa la estructura en Granjas/Lotes, registra preparación y recepción si corresponden y realiza la primera captura en Jornada. El importador siempre exige otra confirmación explícita.')


def render_operations(supabase, organization_id, user_id, role, lotes, today, initial_section=None):
    """Render the operational area without changing the caller's authentication."""
    if isinstance(today, datetime):
        today = today.date()
    if initial_section:
        section = initial_section
    else:
        labels = {'Jornada': 'Jornada', 'Eventos productivos': 'Eventos', 'Huevos e incubación': 'Huevos e incubación',
                  'Agenda e incidencias': 'Agenda', 'Importar planillas': 'Importar',
                  'Trazabilidad y análisis': 'Trazabilidad', 'Configuración guiada': 'Primeros pasos'}
        if st.session_state.get('op_workspace_section') not in SECTIONS:
            st.session_state['op_workspace_section'] = SECTIONS[0]
        with st.container(key='operation_navigation'):
            section = st.pills('Espacio de trabajo', SECTIONS, selection_mode='single', required=True,
                               format_func=labels.get, key='op_workspace_section', wrap=True) or SECTIONS[0]
    notice = st.session_state.pop('op_daily_notice', None)
    operation_notice = st.session_state.pop('op_notice', None)
    if notice or operation_notice:
        st.success(notice or operation_notice)
    renderers = {'Jornada': _jornada, 'Eventos productivos': _events, 'Huevos e incubación': _eggs,
                 'Agenda e incidencias': _agenda, 'Importar planillas': _importer,
                 'Trazabilidad y análisis': _trace, 'Configuración guiada': _onboarding}
    try:
        renderers[section](supabase, organization_id, user_id, role, lotes, today)
    except Exception as exc:
        # No raw server/row details are displayed to avoid leaking internal data.
        if type(exc).__name__ in ('RerunException', 'StopException'):
            raise
        code = str(exc).lower()
        if any(c in code for c in ('42p01', 'pgrst205', 'pgrst202', 'does not exist', 'schema cache')):
            st.info('El centro de operación estará disponible cuando finalice la actualización del esquema. Los datos existentes se conservan.')
        else:
            st.error('No se pudo abrir esta sección. Reintenta o cambia de sección; no se realizaron escrituras automáticas.')
