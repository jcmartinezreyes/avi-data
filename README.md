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

## Migraciones aplicadas

- `20261103102544_multi_producer_production_model.sql`
- `20261103102839_secure_organization_bootstrap.sql`
- `20261103102935_require_farm_organization_and_indexes.sql`
- `20261103201838_commercial_plans_and_galpon_limit.sql`
- `20261103201844_seed_cristopher_full_test_organization.sql`
- `20261103201948_serialize_galpon_plan_limit.sql`
- `20261103233442_user_profiles_for_org_members.sql`
