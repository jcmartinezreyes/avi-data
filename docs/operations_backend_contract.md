# Contrato operacional AviLab — 25 de noviembre de 2026

Migración: `20261125161417_operational_workflows.sql`, generada con Supabase CLI
3.4.0. Es aditiva y no ejecuta semillas. No altera las 60 producciones existentes;
crea una versión inicial de sus capturas con procedencia `legacy`, sin acreditar
que sus antiguos ceros hayan sido mediciones.

## Seguridad y transacciones

Las tablas nuevas tienen RLS por organización y solo SELECT para `authenticated`.
Los tres RPC públicos son SECURITY INVOKER. Sus trabajadores privados son
SECURITY DEFINER con búsqueda vacía, revocación de PUBLIC/anon y comprobaciones
explícitas de `auth.uid()`, organización y rol. El privilegio permite escribir
historial y saldos atómicamente sin conceder a clientes actualización libre de
libros ni auditorías. Llamar al trabajador directamente no elude esas comprobaciones.

No hay nuevas tareas programadas, servicios pagados, integraciones de maquinaria
ni credenciales de servicio en el cliente. La procedencia manual/import/sensor es
metadato del hecho aportado; no demuestra que exista un sensor conectado.

## Captura

`save_daily_capture(p_lote_id bigint,p_fecha date,p_boxes jsonb,p_status text,
p_expected_version integer,p_reason text='',p_source text='manual',p_external_id text=null)`
retorna `{id,version,status,daily_id}`.

- Versión inicial esperada: 0; edición concurrente devuelve SQLSTATE 40001.
- Estados: draft → submitted → reviewed → closed; `reopen` solicita volver a
  draft y exige administrador/propietario y motivo. La revisión y el cierre
  conservan el contenido enviado. El cierre requiere revisión previa.
- Draft acepta boxes incompletos y valores ausentes; no crea hechos diarios ni
  participa en KPIs. Una reapertura retira del cálculo la versión previamente
  enviada, conservando el historial y recalculando pesos posteriores.
- Submitted exige todos los boxes y los campos críticos reales del RPC existente:
  mortalidad/descarte por sexo, alimento kg, agua L. Los pesos son opcionales.
  Una población de sexo inicialmente ausente, sin movimientos de ese sexo,
  permite campos nulos de ese sexo y normalización interna a cero estructural.
- `measurement_states` por campo permite measured/not_measured/not_applicable.
  Ausente y cero no son equivalentes; un campo declarado no medido no admite
  simultáneamente valor numérico. Un núcleo desconocido mantiene el día en draft.
- La captura nueva requiere lote activo. Un gerente puede corregir una captura
  histórica ya existente, reabierta y con motivo, conservando cerrado el lote.
- Los RPC/direct API antiguos no pueden eludir el historial: las escrituras
  autenticadas directas a diario/detalles/mediciones se rechazan. El trabajador
  autorizado reutiliza el guardado transaccional original.

Consultar `daily_captures` (id, organization_id, lote_id, fecha, status, version,
payload, daily_id, source, external_id) y `daily_capture_versions` (capture_id,
version,status,payload,reason,created_by,created_at). Para hechos efectivos, unir
`registros_diarios` con `daily_captures` mediante daily_id y excluir draft.

## Eventos

`record_operation(p_organization_id uuid,p_kind text,p_data jsonb,p_idempotency_key text)`
retorna UUID. Cada reintento idéntico devuelve el mismo UUID; una identidad usada
con contenido distinto produce conflicto. `external_id` es único por organización
y procedencia. Cada hecho incluye observado y recibido; fechas de negocio usan
America/Bogota. Los eventos son inmutables.

Tabla `operations_events`: id, organization_id, kind, lote_id, box_id, observed_at,
received_at, quantity, quantity_female, quantity_male, weight_g, unit, sex, stage,
note, source, quality, external_id, idempotency_key, data, created_by, supersedes_id, related_incident_id.

`effective_operations_events` es una vista SECURITY INVOKER que excluye hechos
sustituidos. Toda estadística, saldo y lista de hechos actuales debe usarla.
El historial usa la tabla original. Corrección: nueva identidad, `supersedes_id`,
`quality=corrected`, motivo en note y mismo contexto. Debe reemplazar la última
versión; no admite ramas ni alteraciones de períodos revisados del origen o del
destino. Borrar external_id al corregir conserva la identidad original en el hecho
anterior y evita suplantarla. Se aceptan reemplazos de aves/alimento/pesajes/
ambiente/salud/etapa/checklist/recepción documental/clasificación/plan/referencia.
Los hechos de existencia de huevos o incubación requieren transacciones
conciliadas, no sustitución genérica de unidades ya consumidas. Los contadores
conservan su secuencia: un cambio de equipo se registra como reset/reemplazo.

Payload común: observed_at requerido, lote_id y box_id según contexto, note,
source (manual/import/sensor), quality (observed/estimated/corrected), external_id.

| kind | Datos específicos y controles |
| --- | --- |
| bird_movement | movement arrival/sale/transfer, female y male enteros, destination_box_id solo transferencia; dos saldos atómicos, pérdidas posteriores y capacidad del galpón verificadas cronológicamente. |
| weighing | sex hembra/macho/mixto, weights_g array de muestras positivas; cantidad y media tipadas, sin inventar n ni CV. |
| water_reading | meter_id, reading_l, reset boolean; previous_end_l/new_start_l opcionales en cambio; sin extremos no se inventa consumo del intervalo. |
| feed_movement | warehouse, movement opening/receipt/consumption/return/transfer, quantity_kg, destination_warehouse en transferencia; saldo no negativo por fecha. El consumo de almacén no vuelve a sumarse al diario. |
| environment | temperature_c o humidity_pct (0..100); una medición común no se repite por box. |
| health | action observation/vaccination/treatment y note; registra lo ocurrido, no diagnostica ni prescribe. |
| stage | stage levante/prepostura/produccion/engorde; conserva identidad del lote. |
| readiness | item y completed explícito; permite fecha anterior al alojamiento, sin certificación sanitaria automática. |
| arrival | expected/received; evidencia documental que no aumenta de nuevo el alojamiento inicial. |
| egg_collection | lote de postura/reproductoras, quantity positiva, round; genera unidad de huevo. |
| egg_receipt | quantity y origin_ref opaco alfanumérico; no exige lote inventado. |
| egg_classification | unit_id, categories excluyentes suman saldo disponible; attributes pueden superponerse y no se suman. Reclasificación conserva antes/después y motivo. |
| egg_transfer | unit_id, quantity, source_stage collection/classification/storage, destination classification/storage/dispatch/rejected; conserva saldos por etapa. |
| egg_split | unit_id, quantity, source_stage; genera unidad hija con relaciones de origen y saldo conservado. |
| egg_merge | unit_ids distintos; conserva orígenes y saldos por etapa en la nueva unidad. |
| hatch_set | machine, hatchery_ref opcional principal, inputs [{unit_id,quantity}]; orígenes múltiples sin galpón ficticio. |
| hatch_transfer | batch_id, machine; posterior a carga. |
| hatch_result | batch_id, hatched/rejected/unhatched suman eggs_set; sample_n y fertile_sample opcionales, nunca sustituye denominador de muestra por toda la carga. |
| task | title, due_date, assigned_to opcional miembro de organización. |
| task_update | task_id, expected_version, status open/done/cancelled; done requiere evento operacional efectivo del mismo lote, nunca la tarea misma. |
| incident | title, rule_version, explanation, assigned_to; una observación repetida por regla/lote actualiza explicación y versión del mismo problema abierto, conserva responsable/estado y crea otro evento inmutable vinculado mediante related_incident_id; después de resolución puede abrir un problema nuevo. |
| incident_update | incident_id, expected_version, status open/acknowledged/resolved. |
| plan | target_date, metric, unit, value; administrador, separado de hechos. |
| target | name, edition, genetics, sex, stage, metric, unit, denominator, source_url, points [{age,value}]; administrador, no aplica referencias automáticamente. |
| snapshot | lote_id, title, cutoff; administrador; congela datos del servidor, reglas, versiones, datos consolidados heredados y configuración de población. |

Tablas relacionales: egg_units (cantidad original, saldo es suma egg_movements),
egg_unit_links (parent_id/child_id/cantidad), egg_movements (unit_id/event_id/stage/
quantity con signo), incubation_sites (instalación/site_code), hatch_batches
(site_id/machine/eggs_set/status/set_at/resultados/muestra), hatch_inputs (orígenes
y cantidades). Todas usan organización y permisos. Incubación requiere un plan
activo con incubadora incluida; su límite cuenta instalaciones, no máquinas. Full
no tiene límite. Ni QR ni conocer un UUID concede acceso a una organización.

Agenda/incidencias tienen version inicial 1. Cambios con versión vieja devuelven
40001. Cada cambio queda como evento además del estado actual.

Los snapshots tienen título, corte, versión y content con lote, boxes,
daily_records, daily_details, captures, measurements, measurement_catalog, events,
tasks, incidents y referencias disponibles. reference_scope aclara que disponibilidad
no significa aplicación. Una regeneración crea versión nueva; descargar la misma
versión conserva su contenido. El exportador debe anonimizar nombres y IDs.

## Importación

`import_operations(p_organization_id uuid,p_rows jsonb,p_import_key text)` acepta
1..500 filas `{kind,data,key}` y retorna resultados de una sola transacción. Para
kind daily usa `data={lote_id,fecha,boxes}` y versión esperada 0: nunca sobreescribe
una jornada existente distinta. Igual origen/contenido se reutiliza; discrepancia
exige revisión. Otros eventos reciben source=import/external_id=key. Un fallo
revierte todas las filas, incluyendo las primeras válidas.

La UI debe verificar formato, unidades, semántica y conciliación antes del RPC.
El servidor vuelve a validar org, tipo, saldo y duplicados. No ejecuta Excel,
macros, vínculos externos ni inventa registros diarios de resúmenes semanales.

## Verificación

`tests/operations_backend.sql` se ejecutó después de la migración en una llamada de
ensayo con excepción intencional final AVILAB_DRYRUN_OK. Llegar a esa excepción
confirma que todas las aserciones previas pasaron; la transacción revierte esquema,
fixtures e historial de migración. Probar después del despliegue también con JWT
reales y flujos web. El ensayo no acredita usabilidad con operadores reales,
funcionamiento offline integral ni precisión predictiva en granjas reales.
