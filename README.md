# Avi-data

Borrador de una aplicación Streamlit para organizar granjas, galpones, lotes y boxes, capturar datos de producción avícola y consultar indicadores diarios.

## Modelo de datos

- Los permisos de usuario y el plan comercial están separados. `organization_memberships.role` controla acceso (owner, admin, operator, analyst); `organization_subscriptions` controla límites y módulos contratados.
- Plan Básica: hasta 10 galpones. Plan Media: hasta 20 galpones y una incubadora. Plan Full: sin límites. El modelo guarda la capacidad de incubadora en el plan, pero las tablas y operaciones de incubadora quedan para una etapa posterior.
- El límite de galpones se valida en Postgres al crear o reasignar galpones.
- El registro diario guarda fecha y lote; las observaciones comunes se registran por box y los totales se derivan del detalle.
- Las métricas por tipo de producción usan un catálogo y mediciones normalizadas.
- El acceso de datos usa Supabase Auth y RLS.

## Organización de prueba y usuarios

La organización `Martinez_Poultry` tiene el plan `Full` activo, sin límite de galpones. La cuenta de prueba `jcmartinezreyes28@gmail.com` tiene rol `admin` y perfil `Jean Cristopher Martinez Reyes` · `@jcmartinezreyes28` · `Gerente general`.

El perfil se almacena en `user_profiles`; el rol sigue separado en `organization_memberships`. La app permite que cada usuario edite su perfil y que un `owner` o `admin` invite miembros, cambie los roles/perfiles y retire su membresía. Retirar acceso no elimina la cuenta de Supabase Auth.

Roles disponibles:

- `admin`: administra miembros, permisos y operación.
- `analyst`: accede a consultas gerenciales, con escritura bloqueada por RLS.
- `operator`: gestiona registros de la operación diaria.
- `owner`: propietario de organización, reservado para el titular.

La administración de usuarios usa la Edge Function `manage-organization-users` con verificación JWT activada. La función valida al usuario y su rol dentro de la organización antes de usar privilegios administrativos. Nunca se coloca una clave `service_role` en la app Streamlit.

## Ejecutar

Configura `SUPABASE_URL` y `SUPABASE_PUBLISHABLE_KEY` en el entorno, instala `requirements.txt` y ejecuta la app. La app requiere iniciar sesión con un usuario creado o invitado en Supabase Auth.

En Streamlit Community Cloud, las dos variables se pueden definir en **Settings → Secrets**.
No se incluyen credenciales en el código. Python de despliegue: **3.11**.
`requirements.txt` fija las versiones directas; `requirements.lock` conserva las
dependencias transitivas verificadas. Para reproducirlas: `pip install -r requirements.lock`.

## Correcciones de auditoría publicadas (21 de noviembre de 2026)

Se conservan el diseño, mapa, perfiles, administración de miembros y sesiones de
12 horas. La captura y configuración de lotes usan RPC transaccionales; el cierre
registra fecha, motivo y peso final. Los gráficos comparan hasta tres lotes por
genética y producción, con mediana histórica de ciclos cerrados y KPIs ponderados.
Los indicadores acumulados requieren cobertura completa desde el alojamiento.

Las seis migraciones de auditoría ya se aplicaron al proyecto Supabase. El MCP
asigna sus propias versiones: **no volver a ejecutarlas por una diferencia de fecha**.

| Archivo local (prefijo `2026112100000`) | Versión remota |
| --- | --- |
| `1_fix_rls_delete_permissions.sql` | `20261121130620` |
| `2_fix_create_organization_plan.sql` | `20261121130625` |
| `3_protect_boxes_and_add_indexes.sql` | `20261121130629` |
| `4_daily_totals_trigger.sql` | `20261121130633` |
| `5_lot_closure_and_daily_batch.sql` | `20261121130638` |
| `6_weighted_daily_weights.sql` | `20261121130641` |

`supabase/seed_martinez_poultry.sql` añade un conjunto sintético **adicional** de
60 lotes con fotografía fija al 2026-11-21. No se ejecuta al arrancar ni durante
este despliegue: se conservan los 60 lotes existentes para evitar duplicarlos.
Su comprobación reversible está en `tests/phase5_seed_rollback.py`.

## Migraciones aplicadas

- `20261103102544_multi_producer_production_model.sql`
- `20261103102839_secure_organization_bootstrap.sql`
- `20261103102935_require_farm_organization_and_indexes.sql`
- `20261103201838_commercial_plans_and_galpon_limit.sql`
- `20261103201844_seed_cristopher_full_test_organization.sql`
- `20261103201948_serialize_galpon_plan_limit.sql`
- `20261103233442_user_profiles_for_org_members.sql`

## Centro de operación

El menú **Jornada** abre la captura por lote. Un día sin captura permanece
pendiente; guardar un borrador no incorpora sus valores a los indicadores. Los
ceros medidos se distinguen de campos sin medición. El envío sigue siendo una
transacción con todos los boxes; los pesos son opcionales. Una modificación exige
la versión de origen y, si corrige un registro, su motivo.

En **Centro de operación** se encuentran:

- Eventos de pesaje, movimientos por sexo, contadores de agua, alimento, ambiente,
  salud, preparación, recepción y cambios de etapa.
- Recolecciones por ronda, clasificación, unidades de huevo, división y combinación,
  recepción externa e incubación con varios orígenes y resultados por muestra.
- Agenda e incidencias con responsables, evidencia real e historial.
- Importación CSV/XLSX con mapeo, unidades, vista previa y confirmación atómica.
- Cronología, inventario, QR, objetivos documentados, planes e informes versionados.

Administradores y propietarios revisan, cierran y reabren períodos. Los analistas
consultan; los operadores capturan. Estas reglas se validan también en Supabase.
El módulo de incubación y su límite de instalaciones dependen de la suscripción,
independientemente de los permisos personales. Ningún plan, tarea o pronóstico crea
existencias, mediciones, cierres ni tratamientos automáticamente.

La captura sin conexión usa un formulario HTML descargable y un archivo JSON de
borrador con caducidad de siete días. Es necesario descargarlo mientras haya
conexión y recuperar el archivo en la app para revisar y sincronizar. No guarda
contraseñas ni tokens. La versión del borrador permite detectar conflictos.

Los informes se calculan desde hechos congelados, con definiciones y cobertura.
Conservar una versión mantiene sus resultados; una corrección posterior requiere
otra versión. El modo anonimizado excluye identidades y notas libres. La línea
base de pronóstico repite la última observación y no acredita precisión productiva:
la evaluación retrospectiva excluye ciclos sintéticos.

### Desarrollo y validación

Aplicar la migración operacional después de las seis correcciones de auditoría.
No ejecutar de nuevo los scripts semilla en una organización ya poblada.

```sh
python -m unittest discover -s tests -v
```

`tests/operations_backend.sql` necesita una transacción desechable en un entorno
con el esquema aplicado y se ejecuta con rollback: crea datos sintéticos aislados,
comprueba permisos y balances y no debe ejecutarse como una carga de producción.
Las planillas de `avilab/referencias/` permanecen privadas y están excluidas del
versionado. AviLab sigue bajo activación manual, sin ejecuciones programadas.

## Interfaz orientada al trabajo diario

Inicio ofrece accesos a Registrar jornada, Ver agenda y Comparar lotes según el
perfil. La navegación lateral identifica la página activa; Centro de operación
muestra sus siete áreas como opciones visibles. Jornada reúne lote, fecha y
estado, abre el primer box pendiente y muestra avance real sin completar ceros.
La recuperación, el historial y los detalles técnicos permanecen en paneles
secundarios. En móvil los campos se apilan y los controles principales mantienen
44 píxeles de alto.

La investigación y evaluación de esta entrega están en
`avilab/resultados/2026-11-28_interfaz_moderna/`. La revisión con usuarios reales
sigue siendo necesaria para medir facilidad de uso y tiempos de operación.
