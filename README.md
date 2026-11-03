# Avi-data

Borrador de una aplicación Streamlit para organizar granjas, galpones, lotes y boxes, capturar datos de producción avícola y consultar indicadores diarios.

## Modelo de datos

- Los permisos de usuario y el plan comercial están separados. `organization_memberships.role` controla acceso (owner, admin, operator, analyst); `organization_subscriptions` controla límites y módulos contratados.
- Plan Básica: hasta 10 galpones. Plan Media: hasta 20 galpones y una incubadora. Plan Full: sin límites. El modelo guarda la capacidad de incubadora en el plan, pero las tablas y operaciones de incubadora quedan para una etapa posterior.
- El límite de galpones se valida en Postgres al crear o reasignar galpones.
- El registro diario guarda fecha y lote; las observaciones comunes se registran por box y los totales se derivan del detalle.
- Las métricas por tipo de producción usan un catálogo y mediciones normalizadas.
- El acceso de datos usa Supabase Auth y RLS.

## Datos de prueba

La organización `Cristopher Martinez` tiene el plan `full` activo. Las granjas existentes se asignaron a esa organización. No hay usuarios en Supabase Auth todavía, así que la organización no tiene una membresía propietaria y sus datos siguen protegidos por RLS hasta que se cree y vincule la cuenta del propietario.

Después de crear/invitar la cuenta en Supabase Auth, asocia su UUID con esta organización desde SQL Editor:

```sql
-- Reemplaza el UUID de usuario por el que aparece en auth.users.
update public.organizations
set created_by = 'UUID-DEL-USUARIO'
where name = 'Cristopher Martinez';

insert into public.organization_memberships (organization_id, user_id, role)
select id, 'UUID-DEL-USUARIO', 'owner'
from public.organizations
where name = 'Cristopher Martinez'
on conflict (organization_id, user_id) do update set role = 'owner';
```

## Ejecutar

Configura `SUPABASE_URL` y `SUPABASE_PUBLISHABLE_KEY` en el entorno, instala `requirements.txt` y ejecuta la app. La app requiere iniciar sesión con un usuario creado o invitado en Supabase Auth.

## Migraciones aplicadas

- `20261103102544_multi_producer_production_model.sql`
- `20261103102839_secure_organization_bootstrap.sql`
- `20261103102935_require_farm_organization_and_indexes.sql`
- `20261103201838_commercial_plans_and_galpon_limit.sql`
- `20261103201844_seed_cristopher_full_test_organization.sql`
- `20261103201948_serialize_galpon_plan_limit.sql`
