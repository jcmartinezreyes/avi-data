-- AviLab operational contracts. Additive: no production seed or destructive rewrite.
-- Privileged workers are PRIVATE, fixed-search-path, explicitly authorize auth.uid(),
-- and are required because audit/version/ledger tables deliberately grant no API writes.
create or replace function private.operation_manager(p_org uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select auth.uid() is not null and exists(select 1 from public.organization_memberships
 where organization_id=p_org and user_id=auth.uid() and role in ('owner','admin'));
$$;
revoke all on function private.operation_manager(uuid) from public,anon;
grant execute on function private.operation_manager(uuid) to authenticated;

create table public.daily_captures (
 id uuid primary key default gen_random_uuid(), organization_id uuid not null references public.organizations(id),
 lote_id bigint not null references public.lotes(id), fecha date not null,
 status text not null check(status in ('draft','submitted','reviewed','closed')),
 version integer not null check(version>0), payload jsonb not null check(jsonb_typeof(payload)='array'),
 daily_id bigint unique references public.registros_diarios(id) on delete restrict,
 source text not null check(source in ('manual','import','sensor','legacy')),
 external_id text, created_by uuid references auth.users(id), updated_at timestamptz not null default now(),
 unique(lote_id,fecha), unique(organization_id,source,external_id)
);
create table public.daily_capture_versions (
 capture_id uuid not null references public.daily_captures(id),organization_id uuid not null references public.organizations(id),
 version integer not null, status text not null,payload jsonb not null,reason text not null,
 created_by uuid references auth.users(id),created_at timestamptz not null default now(),primary key(capture_id,version)
);
-- Legacy data remains usable, but its old zeros do not acquire measurement provenance.
insert into public.daily_captures(organization_id,lote_id,fecha,status,version,payload,daily_id,source,created_by)
select f.organization_id,d.lote_id,d.fecha,'submitted',1,
 coalesce((select jsonb_agg(to_jsonb(b)-'id'-'created_at'-'created_by'-'registro_diario_id' order by b.box_id)
 from public.registros_diarios_box b where b.registro_diario_id=d.id),'[]'::jsonb),d.id,'legacy',d.created_by
from public.registros_diarios d join public.lotes l on l.id=d.lote_id
join public.galpones g on g.id=l.galpon_id join public.granjas f on f.id=g.granja_id
where f.organization_id is not null;
insert into public.daily_capture_versions(capture_id,organization_id,version,status,payload,reason,created_by)
select id,organization_id,version,status,payload,'Migrated legacy record: measurement provenance unknown',created_by from public.daily_captures;

create table public.operations_events (
 id uuid primary key default gen_random_uuid(), organization_id uuid not null references public.organizations(id),
 kind text not null check(kind in ('bird_movement','weighing','water_reading','feed_movement','environment','health','stage','readiness','arrival','egg_collection','egg_receipt','egg_classification','egg_transfer','egg_split','egg_merge','hatch_set','hatch_transfer','hatch_result','task','task_update','incident','incident_update','plan','target','snapshot')),
 lote_id bigint references public.lotes(id),box_id bigint references public.galpon_boxes(id),
 observed_at timestamptz not null,received_at timestamptz not null default clock_timestamp(),
 quantity numeric,quantity_male integer,quantity_female integer,weight_g numeric,unit text,sex text,stage text,note text,
 source text not null check(source in ('manual','import','sensor')),quality text not null check(quality in ('observed','estimated','corrected')),
 supersedes_id uuid unique references public.operations_events(id),external_id text,idempotency_key text not null check(length(idempotency_key) between 1 and 200),
 data jsonb not null check(jsonb_typeof(data)='object'), created_by uuid not null references auth.users(id),
 unique(organization_id,idempotency_key),unique(organization_id,source,external_id)
);
create index operations_events_org_date_idx on public.operations_events(organization_id,observed_at);
create index operations_events_lote_date_idx on public.operations_events(lote_id,observed_at);
create index operations_events_box_idx on public.operations_events(box_id);
create table public.egg_units (
 id uuid primary key references public.operations_events(id),organization_id uuid not null references public.organizations(id),
 lote_id bigint references public.lotes(id),quantity integer not null check(quantity>0),created_at timestamptz not null default now()
);
create table public.egg_unit_links (
 parent_id uuid not null references public.egg_units(id),child_id uuid not null references public.egg_units(id),
 organization_id uuid not null references public.organizations(id),quantity integer not null check(quantity>0),primary key(parent_id,child_id),check(parent_id<>child_id)
);
create table public.egg_movements (
 id bigint generated always as identity primary key,organization_id uuid not null references public.organizations(id),
 event_id uuid not null references public.operations_events(id),unit_id uuid not null references public.egg_units(id),
 stage text not null check(stage in ('collection','classification','storage','dispatch','rejected','split','merge','incubation')),
 quantity integer not null check(quantity<>0),created_at timestamptz not null default now()
);
create index egg_movements_unit_idx on public.egg_movements(unit_id);
create table public.incubation_sites (
 id uuid primary key default gen_random_uuid(),organization_id uuid not null references public.organizations(id),
 site_code text not null,created_at timestamptz not null default now(),unique(organization_id,site_code)
);
create table public.hatch_batches (
 id uuid primary key references public.operations_events(id),organization_id uuid not null references public.organizations(id),
 site_id uuid not null references public.incubation_sites(id),machine text not null,eggs_set integer not null check(eggs_set>0),status text not null check(status in ('set','transferred','hatched')),
 set_at timestamptz not null,hatched integer,rejected integer,unhatched integer,sample_n integer,fertile_sample integer,
 check(hatched is null or hatched>=0),check(rejected is null or rejected>=0),check(unhatched is null or unhatched>=0),
 check(sample_n is null or sample_n>0),check(fertile_sample is null or fertile_sample between 0 and sample_n)
);
create table public.hatch_inputs (
 batch_id uuid not null references public.hatch_batches(id),unit_id uuid not null references public.egg_units(id),
 organization_id uuid not null references public.organizations(id),quantity integer not null check(quantity>0),primary key(batch_id,unit_id)
);
create table public.operation_tasks (
 id uuid primary key references public.operations_events(id),organization_id uuid not null references public.organizations(id),lote_id bigint references public.lotes(id),
 version integer not null default 1,title text not null,due_date date not null,assigned_to uuid references auth.users(id),status text not null check(status in ('open','done','cancelled')),
 evidence_event_id uuid references public.operations_events(id),updated_at timestamptz not null default now()
);
create table public.operation_incidents (
 id uuid primary key references public.operations_events(id),organization_id uuid not null references public.organizations(id),lote_id bigint references public.lotes(id),
 version integer not null default 1,title text not null,rule_version text not null,explanation text not null,assigned_to uuid references auth.users(id),
 status text not null check(status in ('open','acknowledged','resolved')),updated_at timestamptz not null default now()
);
alter table public.operations_events add column related_incident_id uuid references public.operation_incidents(id);
create index operations_events_related_incident_idx on public.operations_events(related_incident_id);
create unique index operation_incidents_one_open_rule on public.operation_incidents(organization_id,coalesce(lote_id,0),rule_version) where status<>'resolved';
create table public.production_targets (
 id uuid primary key references public.operations_events(id),organization_id uuid not null references public.organizations(id),
 name text not null,edition text not null,genetics text not null,sex text not null,stage text not null,metric text not null,unit text not null,
 denominator text not null,source_url text not null,points jsonb not null
);
create table public.production_plans (
 id uuid primary key references public.operations_events(id),organization_id uuid not null references public.organizations(id),lote_id bigint references public.lotes(id),
 target_date date not null,metric text not null,unit text not null,value numeric not null check(value>=0)
);
create table public.cycle_snapshots (
 id uuid primary key references public.operations_events(id),organization_id uuid not null references public.organizations(id),lote_id bigint not null references public.lotes(id),
 title text not null,cutoff date not null,version integer not null,content jsonb not null,created_at timestamptz not null default now(),unique(lote_id,version)
);
-- Exposed relations are read-only to API users. All commands pass private workers.
do $$ declare t text;begin
 foreach t in array array['daily_captures','daily_capture_versions','operations_events','egg_units','egg_unit_links','egg_movements','incubation_sites','hatch_batches','hatch_inputs','operation_tasks','operation_incidents','production_targets','production_plans','cycle_snapshots'] loop
 execute format('alter table public.%I enable row level security',t);
 execute format('revoke all on public.%I from public,anon,authenticated',t);
 execute format('grant select on public.%I to authenticated',t);
 execute format('create policy org_read on public.%I for select to authenticated using (private.user_can_access_organization(organization_id,false))',t);
 execute format('create index %I on public.%I(organization_id)',t||'_org_idx',t);
 end loop;
end $$;

create or replace function private.save_daily_capture_worker(p_lote_id bigint,p_fecha date,p_boxes jsonb,p_status text,p_expected_version integer,p_reason text,p_source text,p_external_id text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare v_org uuid;v_lot public.lotes;v_capture public.daily_captures;v_id uuid;v_daily bigint;v_version integer;v_state text;v_normalized jsonb;v_b jsonb;v_key text;v_ms text;v_initial bigint;
begin
 if auth.uid() is null or not private.user_can_access_lote(p_lote_id,true) then raise exception 'No write access to lot' using errcode='42501';end if;
 select * into v_lot from public.lotes where id=p_lote_id;
 select f.organization_id into v_org from public.galpones g join public.granjas f on f.id=g.granja_id where g.id=v_lot.galpon_id;
 perform 1 from public.organizations where id=v_org for update;
 perform 1 from public.lotes where id=p_lote_id for update;
 if p_status is null or p_source is null or p_status not in ('draft','submitted','reviewed','closed','reopen') or p_source not in ('manual','import','sensor','legacy')
 or p_boxes is null or jsonb_typeof(p_boxes)<>'array' or p_fecha is null or p_fecha<v_lot.fecha_encaste or p_fecha>(now() at time zone 'America/Bogota')::date
 then raise exception 'Invalid capture status, payload or date' using errcode='22023';end if;
 select * into v_capture from public.daily_captures where lote_id=p_lote_id and fecha=p_fecha for update;
 if coalesce(v_capture.version,0) is distinct from p_expected_version then raise exception 'Capture changed: reload before saving' using errcode='40001';end if;
 if p_status in ('reviewed','closed','reopen') and not private.operation_manager(v_org) then raise exception 'Manager permission required' using errcode='42501';end if;
 if v_capture.status in ('reviewed','closed') and p_status<>'reopen' and not (v_capture.status='reviewed' and p_status='closed') then raise exception 'Reopen reviewed or closed capture before correction' using errcode='22023';end if;
 if p_status='reopen' then
  if v_capture.id is null or nullif(btrim(p_reason),'') is null then raise exception 'Reopening requires existing capture and reason' using errcode='22023';end if;
  v_state:='draft';p_boxes:=v_capture.payload;
 elsif p_status in ('reviewed','closed') then
  if v_capture.id is null or v_capture.status not in ('submitted','reviewed') or p_boxes is distinct from v_capture.payload then raise exception 'Review requires unchanged submitted capture' using errcode='22023';end if;
  if p_status='closed' and v_capture.status<>'reviewed' then raise exception 'Review capture before closing period' using errcode='22023';end if;
  v_state:=p_status;
 else
  if not v_lot.activo and not(private.operation_manager(v_org) and v_capture.id is not null and v_capture.status='draft' and nullif(btrim(p_reason),'') is not null) then raise exception 'Only active lots accept capture; historical correction requires manager, reopened capture and reason' using errcode='22023';end if;
  if v_capture.daily_id is not null and nullif(btrim(p_reason),'') is null then raise exception 'Correction reason required' using errcode='22023';end if;
  v_state:=p_status;
 end if;
 -- Drafts accept missing measurements, never manufacture zero or modify reported facts.
 if exists(select 1 from jsonb_array_elements(p_boxes)b where jsonb_typeof(b)<>'object' or coalesce(b->>'box_id','') !~ '^[0-9]+$' or not exists(select 1 from public.galpon_boxes x where x.id=(b->>'box_id')::bigint and x.lote_id=p_lote_id)) then raise exception 'Invalid capture box' using errcode='22023';end if;
 if exists(select 1 from jsonb_array_elements(p_boxes)b group by b->>'box_id' having count(*)>1) then raise exception 'Duplicate capture box' using errcode='22023';end if;
 if p_status in ('reviewed','closed','reopen') then p_source:=v_capture.source;p_external_id:=v_capture.external_id;end if;
 if p_source='legacy' and (v_capture.source is distinct from 'legacy' or p_status in ('draft','submitted')) then raise exception 'Legacy provenance is reserved for migrated history' using errcode='22023';end if;
 for v_b in select value from jsonb_array_elements(p_boxes) loop
  if v_b ? 'measurement_states' and jsonb_typeof(v_b->'measurement_states')<>'object' then raise exception 'Invalid measurement states' using errcode='22023';end if;
  foreach v_key in array array['mortalidad_hembra','mortalidad_macho','descarte_hembra','descarte_macho','consumo_alimento_kg','consumo_agua_litros','peso_promedio_hembra_g','peso_promedio_macho_g'] loop
   v_ms:=v_b->'measurement_states'->>v_key;
   if v_ms is not null and v_ms not in ('measured','not_measured','not_applicable') then raise exception 'Invalid measurement state' using errcode='22023';end if;
   if v_b->>v_key is not null and (jsonb_typeof(v_b->v_key)<>'number' or (v_b->>v_key)::numeric<0) then raise exception 'Measurement must be a nonnegative number' using errcode='22023';end if;
   if v_ms='not_measured' and v_b->>v_key is not null then raise exception 'Unmeasured field cannot contain a numeric fact' using errcode='22023';end if;
   if v_ms='measured' and v_b->>v_key is null then raise exception 'Measured field requires actual value' using errcode='22023';end if;
   if v_ms='not_applicable' and v_b->>v_key is not null then raise exception 'Not-applicable field must have no numerical fact' using errcode='22023';end if;
   if v_ms='not_applicable' and p_status='submitted' and v_key not like 'peso_%' then
    if v_key like '%hembra%' then select coalesce(aves_hembra_inicial,0)+private.box_movement(id,p_fecha,'hembra') into v_initial from public.galpon_boxes where id=(v_b->>'box_id')::bigint;
    elsif v_key like '%macho%' then select coalesce(aves_macho_inicial,0)+private.box_movement(id,p_fecha,'macho') into v_initial from public.galpon_boxes where id=(v_b->>'box_id')::bigint;
    else v_initial:=1;end if;
    if v_initial<>0 then raise exception 'Not applicable only for a sex verified absent from box' using errcode='22023';end if;
   end if;
  end loop;
 end loop;
 v_daily:=v_capture.daily_id;
 if p_status='submitted' then
  select jsonb_agg(b || case when coalesce(x.aves_hembra_inicial,0)=0 and private.box_movement(x.id,p_fecha,'hembra')=0 then jsonb_build_object('mortalidad_hembra',coalesce((b->>'mortalidad_hembra')::int,0),'descarte_hembra',coalesce((b->>'descarte_hembra')::int,0)) else '{}'::jsonb end ||
  case when coalesce(x.aves_macho_inicial,0)=0 and private.box_movement(x.id,p_fecha,'macho')=0 then jsonb_build_object('mortalidad_macho',coalesce((b->>'mortalidad_macho')::int,0),'descarte_macho',coalesce((b->>'descarte_macho')::int,0)) else '{}'::jsonb end)
  into v_normalized from jsonb_array_elements(p_boxes)b join public.galpon_boxes x on x.id=(b->>'box_id')::bigint;
  update public.daily_captures set status='submitted' where id=v_capture.id;
  v_daily:=public.save_daily_record(p_lote_id,p_fecha,v_normalized);
  perform private.check_bird_balances(v_org);
 end if;
 v_id:=coalesce(v_capture.id,gen_random_uuid());v_version:=coalesce(v_capture.version,0)+1;
 insert into public.daily_captures(id,organization_id,lote_id,fecha,status,version,payload,daily_id,source,external_id,created_by)
 values(v_id,v_org,p_lote_id,p_fecha,v_state,v_version,p_boxes,v_daily,p_source,p_external_id,auth.uid())
 on conflict(lote_id,fecha) do update set status=excluded.status,version=excluded.version,payload=excluded.payload,daily_id=excluded.daily_id,source=excluded.source,external_id=excluded.external_id,updated_at=now();
 insert into public.daily_capture_versions(capture_id,organization_id,version,status,payload,reason,created_by)
 values(v_id,v_org,v_version,v_state,p_boxes,coalesce(p_reason,''),auth.uid());
 -- Reopening/drafting withdraws previous facts, so later live-weight proxies must follow effective coverage.
 update public.registros_diarios_box r set peso_promedio_hembra_g=r.peso_promedio_hembra_g
 where r.id=(select min(x.id) from public.registros_diarios_box x join public.registros_diarios d on d.id=x.registro_diario_id where d.lote_id=p_lote_id);
 perform private.check_bird_balances(v_org);
 return jsonb_build_object('id',v_id,'version',v_version,'status',v_state,'daily_id',v_daily);
end $$;
revoke all on function private.save_daily_capture_worker(bigint,date,jsonb,text,integer,text,text,text) from public,anon;
grant execute on function private.save_daily_capture_worker(bigint,date,jsonb,text,integer,text,text,text) to authenticated;
create or replace function public.save_daily_capture(p_lote_id bigint,p_fecha date,p_boxes jsonb,p_status text,p_expected_version integer,p_reason text default '',p_source text default 'manual',p_external_id text default null)
returns jsonb language sql security invoker set search_path='' as $$
 select private.save_daily_capture_worker(p_lote_id,p_fecha,p_boxes,p_status,p_expected_version,p_reason,p_source,p_external_id);
$$;
revoke all on function public.save_daily_capture(bigint,date,jsonb,text,integer,text,text,text) from public,anon;
grant execute on function public.save_daily_capture(bigint,date,jsonb,text,integer,text,text,text) to authenticated;

-- API callers cannot bypass versioning or review by mutating old tables directly.
create or replace function private.daily_versioned_api_guard() returns trigger language plpgsql security invoker set search_path='' as $$
begin raise exception 'Use save_daily_capture for versioned daily changes' using errcode='42501';end $$;
revoke all on function private.daily_versioned_api_guard() from public,anon,authenticated;
do $$ declare t text;begin
 foreach t in array array['registros_diarios','registros_diarios_box','mediciones_produccion'] loop
 execute format('create trigger daily_versioned_api_guard before insert or update or delete on public.%I for each row when(current_user=''authenticated'') execute function private.daily_versioned_api_guard()',t);
 end loop;
end $$;

create view public.effective_operations_events with (security_invoker=true) as
 select e.* from public.operations_events e where not exists(select 1 from public.operations_events correction where correction.supersedes_id=e.id);
revoke all on public.effective_operations_events from public,anon;
grant select on public.effective_operations_events to authenticated;

-- Population changes are separate facts: a receipt checklist does not add birds twice.
create or replace function private.box_movement(p_box bigint,p_fecha date,p_sex text) returns bigint
language sql stable security definer set search_path='' as $$
 select coalesce(sum(case when e.box_id=p_box then case when e.data->>'movement'='arrival' then 1 else -1 end else 1 end *
 case when p_sex='hembra' then e.quantity_female else e.quantity_male end),0)::bigint
 from public.effective_operations_events e where e.kind='bird_movement' and (e.observed_at at time zone 'America/Bogota')::date<=p_fecha
 and (e.box_id=p_box or (e.data->>'movement'='transfer' and (e.data->>'destination_box_id')::bigint=p_box));
$$;
revoke all on function private.box_movement(bigint,date,text) from public,anon,authenticated;
create or replace function private.check_bird_balances(p_org uuid) returns void
language plpgsql security definer set search_path='' as $$
begin
 if exists(
 select 1 from public.galpon_boxes b join public.lotes l on l.id=b.lote_id join public.galpones g on g.id=l.galpon_id join public.granjas f on f.id=g.granja_id
 cross join lateral (
 select d.fecha as record_date from public.registros_diarios d where d.lote_id=b.lote_id
 union select (e.observed_at at time zone 'America/Bogota')::date from public.effective_operations_events e where e.kind='bird_movement'
 and (e.box_id=b.id or (e.data->>'destination_box_id')::bigint=b.id)
 ) dates
 left join lateral (select coalesce(sum(r.mortalidad_hembra+r.descarte_hembra),0) h,
 coalesce(sum(r.mortalidad_macho+r.descarte_macho),0) m from public.registros_diarios_box r
 join public.registros_diarios d on d.id=r.registro_diario_id where r.box_id=b.id and d.fecha<=dates.record_date and not exists(select 1 from public.daily_captures c where c.daily_id=d.id and c.status='draft')) losses on true
 where f.organization_id=p_org and
 (coalesce(b.aves_hembra_inicial,0)+private.box_movement(b.id,dates.record_date,'hembra')-losses.h<0
 or coalesce(b.aves_macho_inicial,0)+private.box_movement(b.id,dates.record_date,'macho')-losses.m<0)
 ) then raise exception 'Movement or correction produces negative bird balance on a recorded date' using errcode='23514';end if;
 if exists(with dates as (
  select d.fecha record_date from public.registros_diarios d join public.lotes l on l.id=d.lote_id join public.galpones g on g.id=l.galpon_id join public.granjas f on f.id=g.granja_id where f.organization_id=p_org
  union select (e.observed_at at time zone 'America/Bogota')::date from public.effective_operations_events e where e.organization_id=p_org and e.kind='bird_movement'
 ), populations as (
  select g.id,g.capacidad,dates.record_date,
   sum(coalesce(b.aves_hembra_inicial,0)+coalesce(b.aves_macho_inicial,0)+private.box_movement(b.id,dates.record_date,'hembra')+private.box_movement(b.id,dates.record_date,'macho')-coalesce(losses.total,0)) live
  from dates join public.lotes l on l.fecha_encaste<=dates.record_date and (l.fecha_cierre is null or l.fecha_cierre>=dates.record_date)
  join public.galpones g on g.id=l.galpon_id join public.granjas f on f.id=g.granja_id join public.galpon_boxes b on b.lote_id=l.id
  left join lateral (select sum(r.mortalidad_hembra+r.mortalidad_macho+r.descarte_hembra+r.descarte_macho) total from public.registros_diarios_box r join public.registros_diarios d on d.id=r.registro_diario_id where r.box_id=b.id and d.fecha<=dates.record_date and not exists(select 1 from public.daily_captures c where c.daily_id=d.id and c.status='draft'))losses on true
  where f.organization_id=p_org group by g.id,g.capacidad,dates.record_date
 ) select 1 from populations where capacidad is not null and capacidad>0 and live>capacidad)
 then raise exception 'Bird balance exceeds house capacity on a recorded date' using errcode='23514';end if;

end $$;
revoke all on function private.check_bird_balances(uuid) from public,anon,authenticated;


-- Follow derived units to their original production lots when enforcing review locks.
create or replace function private.assert_egg_unit_access(p_org uuid,p_unit uuid,p_date date) returns void
language plpgsql security definer set search_path='' as $$
begin
 if p_unit is null or not exists(select 1 from public.egg_units where id=p_unit and organization_id=p_org) then raise exception 'No egg unit access' using errcode='42501';end if;
 if exists(with recursive origins as (
  select id,lote_id from public.egg_units where id=p_unit
  union select u.id,u.lote_id from public.egg_units u join public.egg_unit_links k on k.parent_id=u.id join origins o on o.id=k.child_id
 ) select 1 from origins o join public.daily_captures c on c.lote_id=o.lote_id where c.fecha=p_date and c.status in ('reviewed','closed')) then raise exception 'Reopen origin production period before egg operation' using errcode='22023';end if;
end $$;
revoke all on function private.assert_egg_unit_access(uuid,uuid,date) from public,anon,authenticated;

create or replace function private.record_operation_worker(p_organization_id uuid,p_kind text,p_data jsonb,p_idempotency_key text)
returns uuid language plpgsql security definer set search_path='' as $$
declare
 v_id uuid:=gen_random_uuid();v_old public.operations_events;v_lote bigint;v_box bigint;v_dest bigint;v_dest_lote bigint;v_lot public.lotes;
 v_observed timestamptz;v_source text;v_quality text;v_qty numeric;v_h integer;v_m integer;v_weight numeric;
 v_unit uuid;v_batch uuid;v_n integer;v_sum integer;v_available bigint;v_previous numeric;v_current numeric;v_key text;
 v_row record;v_input jsonb;v_supersedes uuid;v_existing jsonb;v_content jsonb;v_org uuid;v_sex text;v_stage text;v_incubators integer;v_limit integer;v_site uuid;v_incident uuid;
begin
 if auth.uid() is null or not private.user_can_access_organization(p_organization_id,true) then raise exception 'No organization write permission' using errcode='42501';end if;
 if p_data is null or jsonb_typeof(p_data)<>'object' or nullif(btrim(p_idempotency_key),'') is null or length(p_idempotency_key)>200 then raise exception 'Invalid event payload or idempotency key' using errcode='22023';end if;
 -- One org lock serializes balances, duplicate checks, and immutable event fan-out.
 perform 1 from public.organizations where id=p_organization_id for update;
 select * into v_old from public.operations_events where organization_id=p_organization_id and
 (idempotency_key=p_idempotency_key or (p_data->>'external_id' is not null and source=coalesce(p_data->>'source','manual') and external_id=p_data->>'external_id'));
 if found then
  if v_old.kind=p_kind and v_old.data=p_data then return v_old.id;end if;
  raise exception 'Origin or idempotency key already exists with different content' using errcode='40001';
 end if;
 v_supersedes:=nullif(p_data->>'supersedes_id','')::uuid;
 if v_supersedes is not null then
  if p_kind not in ('bird_movement','feed_movement','weighing','environment','health','stage','readiness','arrival','egg_classification','plan','target') then raise exception 'This event requires a reconciled compensating transaction, not replacement' using errcode='22023';end if;
  if nullif(btrim(p_data->>'note'),'') is null or coalesce(p_data->>'quality','')<>'corrected' then raise exception 'Correction reason and corrected quality required' using errcode='22023';end if;
  if not exists(select 1 from public.effective_operations_events e where e.id=v_supersedes and e.organization_id=p_organization_id and e.kind=p_kind and e.lote_id is not distinct from nullif(p_data->>'lote_id','')::bigint and e.box_id is not distinct from nullif(p_data->>'box_id','')::bigint and (p_kind<>'egg_classification' or e.data->>'unit_id'=p_data->>'unit_id')) then raise exception 'Correction must replace current event in same context' using errcode='42501';end if;
  select * into v_old from public.operations_events where id=v_supersedes;
  if exists(select 1 from public.daily_captures c where c.lote_id=v_old.lote_id and c.fecha=(v_old.observed_at at time zone 'America/Bogota')::date and c.status in ('reviewed','closed')) then raise exception 'Reopen original period before correction' using errcode='22023';end if;
  if p_kind='egg_classification' then perform private.assert_egg_unit_access(p_organization_id,(v_old.data->>'unit_id')::uuid,(v_old.observed_at at time zone 'America/Bogota')::date);end if;
  if p_kind='bird_movement' and v_old.data->>'movement'='transfer' and exists(select 1 from public.daily_captures c join public.galpon_boxes b on b.lote_id=c.lote_id where b.id=(v_old.data->>'destination_box_id')::bigint and c.fecha=(v_old.observed_at at time zone 'America/Bogota')::date and c.status in ('reviewed','closed')) then raise exception 'Reopen original transfer destination period before correction' using errcode='22023';end if;

 end if;
 foreach v_key in array array['female','male','expected','received','quantity','hatched','rejected','unhatched','sample_n','fertile_sample'] loop
  if p_data ? v_key and p_data->v_key<>'null'::jsonb and (jsonb_typeof(p_data->v_key)<>'number' or (p_data->v_key)::text !~ '^[0-9]+$') then raise exception 'Count must be a nonnegative integer: %',v_key using errcode='22023';end if;
 end loop;
 foreach v_key in array array['quantity_kg','weight_g','reading_l','previous_end_l','new_start_l','temperature_c','humidity_pct','value'] loop
  if p_data ? v_key and p_data->v_key<>'null'::jsonb and jsonb_typeof(p_data->v_key)<>'number' then raise exception 'Measurement must be numeric: %',v_key using errcode='22023';end if;
  if v_key<>'temperature_c' and (p_data->>v_key)::numeric<0 then raise exception 'Measurement must be nonnegative: %',v_key using errcode='22023';end if;
 end loop;
 if p_kind in ('egg_receipt','hatch_set','hatch_transfer','hatch_result') then
  select p.max_incubadoras into v_limit from public.organization_subscriptions s join public.subscription_plans p on p.code=s.plan_code
  where s.organization_id=p_organization_id and s.status='active' and s.starts_at<=now() and (s.ends_at is null or s.ends_at>now()) and p.active and p.incubadora_incluida;
  if not found then raise exception 'Subscription does not include hatchery tools' using errcode='42501';end if;
 end if;
 v_lote:=nullif(p_data->>'lote_id','')::bigint;v_box:=nullif(p_data->>'box_id','')::bigint;
 v_observed:=(p_data->>'observed_at')::timestamptz;v_source:=coalesce(p_data->>'source','manual');v_quality:=coalesce(p_data->>'quality','observed');
 if v_observed is null or v_observed>now()+interval '10 minutes' then raise exception 'Observed time required and cannot be in future' using errcode='22023';end if;
 if v_lote is not null then
  if not private.user_can_access_lote(v_lote,true) then raise exception 'No lot access' using errcode='42501';end if;
  select * into v_lot from public.lotes where id=v_lote for update;
  select f.organization_id into v_org from public.galpones g join public.granjas f on f.id=g.granja_id where g.id=v_lot.galpon_id;
  if v_org<>p_organization_id then raise exception 'Cross organization lot' using errcode='42501';end if;
  if p_kind not in ('snapshot','plan','task','task_update','incident','incident_update','target') and (not v_lot.activo or (p_kind<>'readiness' and (v_observed at time zone 'America/Bogota')::date<v_lot.fecha_encaste)) then raise exception 'Production events require active lot and valid date' using errcode='22023';end if;
  if exists(select 1 from public.daily_captures where lote_id=v_lote and fecha=(v_observed at time zone 'America/Bogota')::date and status in ('reviewed','closed')) and p_kind not in ('task_update','incident_update','snapshot','plan','target') then raise exception 'Reopen reviewed period before recording production events' using errcode='22023';end if;
 end if;
 if v_box is not null and not exists(select 1 from public.galpon_boxes b where b.id=v_box and b.lote_id=v_lote) then raise exception 'Box does not belong to selected lot' using errcode='22023';end if;
 if p_kind in ('bird_movement','weighing','water_reading','environment','health','stage','readiness','arrival','egg_collection','snapshot') and v_lote is null then raise exception 'Lot required for event' using errcode='22023';end if;
 v_sex:=p_data->>'sex';v_stage:=p_data->>'stage';
 if v_sex is not null and v_sex not in ('hembra','macho','mixto') then raise exception 'Invalid sex' using errcode='22023';end if;
 if v_stage is not null and v_stage not in ('levante','prepostura','produccion','engorde') then raise exception 'Invalid production stage' using errcode='22023';end if;
 -- All persisted facts have typed quantities and explicit units; payload retains provenance.
 case p_kind
 when 'bird_movement' then
  v_h:=(p_data->>'female')::integer;v_m:=(p_data->>'male')::integer;v_dest:=nullif(p_data->>'destination_box_id','')::bigint;
  if v_box is null or v_h is null or v_m is null or v_h<0 or v_m<0 or v_h+v_m=0 or (p_data->>'movement' is null or p_data->>'movement' not in ('arrival','sale','transfer')) then raise exception 'Invalid bird movement' using errcode='22023';end if;
  if p_data->>'movement'='transfer' then
   if v_dest is null or v_dest=v_box then raise exception 'Distinct destination box required' using errcode='22023';end if;
   select b.lote_id into v_dest_lote from public.galpon_boxes b where b.id=v_dest;
   if v_dest_lote is null or not private.user_can_access_lote(v_dest_lote,true) then raise exception 'No destination box access' using errcode='42501';end if;
   if not exists(select 1 from public.lotes l join public.galpones g on g.id=l.galpon_id join public.granjas f on f.id=g.granja_id where l.id=v_dest_lote and l.activo and l.fecha_encaste<=(v_observed at time zone 'America/Bogota')::date and f.organization_id=p_organization_id)
   then raise exception 'Destination must be active in same organization' using errcode='42501';end if;
   perform 1 from public.lotes where id=v_dest_lote for update;
   if exists(select 1 from public.daily_captures where lote_id=v_dest_lote and fecha=(v_observed at time zone 'America/Bogota')::date and status in ('reviewed','closed')) then raise exception 'Destination period is reviewed or closed' using errcode='22023';end if;
  elsif v_dest is not null then raise exception 'Destination only allowed for transfer' using errcode='22023';end if;
  v_qty:=v_h+v_m;v_weight:=nullif(p_data->>'weight_g','')::numeric;
 when 'weighing' then
  if v_sex is null or jsonb_typeof(p_data->'weights_g') is distinct from 'array' or jsonb_array_length(p_data->'weights_g')<1 or jsonb_array_length(p_data->'weights_g')>10000 then raise exception 'Weighing requires sex and individual sample weights' using errcode='22023';end if;
  if exists(select 1 from jsonb_array_elements(p_data->'weights_g')w where jsonb_typeof(w)<>'number' or (w#>>'{}')::numeric<=0 or (w#>>'{}')::numeric::text in ('NaN','Infinity','-Infinity')) then raise exception 'Invalid individual weights' using errcode='22023';end if;
  select avg((w#>>'{}')::numeric),count(*) into v_weight,v_qty from jsonb_array_elements(p_data->'weights_g')w;
 when 'water_reading' then
  v_current:=(p_data->>'reading_l')::numeric;
  if nullif(btrim(p_data->>'meter_id'),'') is null or v_current is null or v_current<0 then raise exception 'Meter identity and nonnegative reading required' using errcode='22023';end if;
  if exists(select 1 from public.effective_operations_events where organization_id=p_organization_id and kind='water_reading' and lote_id=v_lote and data->>'meter_id'=p_data->>'meter_id' and observed_at>=v_observed) then raise exception 'Meter readings must be chronological; retain correction as separate documented measurement' using errcode='22023';end if;
  select (data->>'reading_l')::numeric into v_previous from public.effective_operations_events where organization_id=p_organization_id and kind='water_reading' and lote_id=v_lote and data->>'meter_id'=p_data->>'meter_id' order by observed_at desc limit 1;
  if coalesce((p_data->>'reset')::boolean,false) then
   if p_data->>'previous_end_l' is not null and p_data->>'new_start_l' is not null and v_previous is not null then
    v_qty:=(p_data->>'previous_end_l')::numeric-v_previous+v_current-(p_data->>'new_start_l')::numeric;
   else v_qty:=null;end if;
  elsif v_previous is not null then v_qty:=v_current-v_previous;end if;
  if v_qty<0 then raise exception 'Negative interval: document meter reset or replacement' using errcode='22023';end if;
 when 'feed_movement' then
  v_qty:=(p_data->>'quantity_kg')::numeric;
  if nullif(btrim(p_data->>'warehouse'),'') is null or v_qty is null or v_qty<=0 or (p_data->>'movement' is null or p_data->>'movement' not in ('opening','receipt','consumption','return','transfer')) then raise exception 'Invalid feed movement' using errcode='22023';end if;
  if p_data->>'movement'='opening' and v_supersedes is null and exists(select 1 from public.effective_operations_events where organization_id=p_organization_id and kind='feed_movement' and data->>'warehouse'=p_data->>'warehouse') then raise exception 'Opening only allowed before warehouse movements' using errcode='22023';end if;
  if p_data->>'movement'='transfer' and (nullif(btrim(p_data->>'destination_warehouse'),'') is null or p_data->>'destination_warehouse'=p_data->>'warehouse') then raise exception 'Distinct destination warehouse required' using errcode='22023';end if;
 when 'environment' then
  if p_data->>'temperature_c' is null and p_data->>'humidity_pct' is null then raise exception 'At least one environmental measurement required' using errcode='22023';end if;
  if (p_data->>'humidity_pct')::numeric not between 0 and 100 then raise exception 'Humidity outside 0..100' using errcode='22023';end if;
 when 'health' then
  if (p_data->>'action' is null or p_data->>'action' not in ('observation','vaccination','treatment')) or nullif(btrim(p_data->>'note'),'') is null then raise exception 'Health action and observation required' using errcode='22023';end if;
 when 'stage' then
  if v_stage is null then raise exception 'Stage required' using errcode='22023';end if;
 when 'readiness' then
  if nullif(btrim(p_data->>'item'),'') is null or jsonb_typeof(p_data->'completed') is distinct from 'boolean' then raise exception 'Preparation item and explicit completion required' using errcode='22023';end if;
 when 'arrival' then
  v_qty:=(p_data->>'received')::integer;v_n:=(p_data->>'expected')::integer;
  if v_qty is null or v_n is null or v_qty<0 or v_n<0 then raise exception 'Expected and received quantities required' using errcode='22023';end if;
 when 'egg_receipt' then
  v_qty:=(p_data->>'quantity')::integer;
  if v_qty is null or v_qty<=0 or coalesce(p_data->>'origin_ref','') !~ '^[A-Za-z0-9_-]{1,120}$' then raise exception 'External eggs require positive quantity and opaque origin reference' using errcode='22023';end if;
 when 'egg_collection' then
  v_qty:=(p_data->>'quantity')::integer;
  if v_lot.tipo_produccion not in ('postura','reproductoras') or v_qty is null or v_qty<=0 or nullif(btrim(p_data->>'round'),'') is null then raise exception 'Egg collection requires laying or breeder lot, positive quantity and round' using errcode='22023';end if;
 when 'egg_classification' then
  v_unit:=(p_data->>'unit_id')::uuid;
  if jsonb_typeof(p_data->'categories') is distinct from 'object' or p_data->'categories'='{}'::jsonb then raise exception 'Mutually exclusive categories required' using errcode='22023';end if;
  if exists(select 1 from jsonb_each(p_data->'categories')x where jsonb_typeof(x.value)<>'number' or x.value::text !~ '^[0-9]+$') then raise exception 'Category quantities must be nonnegative integers' using errcode='22023';end if;
  select sum(value::text::integer) into v_qty from jsonb_each(p_data->'categories');
  if exists(select 1 from public.effective_operations_events where organization_id=p_organization_id and kind='egg_classification' and data->>'unit_id'=v_unit::text) and nullif(btrim(p_data->>'note'),'') is null then raise exception 'Reclassification requires reason; prior event retained' using errcode='22023';end if;
 when 'egg_transfer' then
  v_unit:=(p_data->>'unit_id')::uuid;v_qty:=(p_data->>'quantity')::integer;
  if (p_data->>'destination' is null or p_data->>'destination' not in ('classification','storage','dispatch','rejected')) or v_qty is null or v_qty<=0 then raise exception 'Invalid egg transfer' using errcode='22023';end if;
 when 'egg_split' then v_unit:=(p_data->>'unit_id')::uuid;v_qty:=(p_data->>'quantity')::integer;if v_qty is null or v_qty<=0 then raise exception 'Positive split quantity required' using errcode='22023';end if;
 when 'egg_merge' then
  if jsonb_typeof(p_data->'unit_ids') is distinct from 'array' or jsonb_array_length(p_data->'unit_ids')<2 or exists(select 1 from jsonb_array_elements_text(p_data->'unit_ids')x group by x having count(*)>1) then raise exception 'At least two distinct egg units required' using errcode='22023';end if;
 when 'hatch_set' then
  if coalesce(p_data->>'hatchery_ref','principal') !~ '^[A-Za-z0-9_-]{1,120}$' then raise exception 'Opaque hatchery reference required' using errcode='22023';end if;
  select id into v_site from public.incubation_sites where organization_id=p_organization_id and site_code=coalesce(p_data->>'hatchery_ref','principal');
  if not found then
   select count(*) into v_incubators from public.incubation_sites where organization_id=p_organization_id;
   if v_limit is not null and v_incubators>=v_limit then raise exception 'Subscription hatchery facility capacity reached' using errcode='42501';end if;
   insert into public.incubation_sites(organization_id,site_code) values(p_organization_id,coalesce(p_data->>'hatchery_ref','principal')) returning id into v_site;
  end if;
  if nullif(btrim(p_data->>'machine'),'') is null or jsonb_typeof(p_data->'inputs') is distinct from 'array' or jsonb_array_length(p_data->'inputs')<1 then raise exception 'Machine and origin units required' using errcode='22023';end if;
  if exists(select 1 from jsonb_array_elements(p_data->'inputs')x group by x->>'unit_id' having count(*)>1) then raise exception 'Duplicate incubation origin' using errcode='22023';end if;
  select sum((x->>'quantity')::integer) into v_qty from jsonb_array_elements(p_data->'inputs')x;
 when 'hatch_transfer' then
  v_batch:=(p_data->>'batch_id')::uuid;if nullif(btrim(p_data->>'machine'),'') is null then raise exception 'Transfer destination machine required' using errcode='22023';end if;
 when 'hatch_result' then
  v_batch:=(p_data->>'batch_id')::uuid;
  if (p_data->>'hatched')::integer<0 or (p_data->>'rejected')::integer<0 or (p_data->>'unhatched')::integer<0 then raise exception 'Nonnegative hatch categories required' using errcode='22023';end if;
  if (p_data->>'fertile_sample' is not null and p_data->>'sample_n' is null) or (p_data->>'sample_n')::integer<=0 or (p_data->>'fertile_sample')::integer not between 0 and (p_data->>'sample_n')::integer then raise exception 'Invalid embryology sample denominator' using errcode='22023';end if;
 when 'task' then
  if nullif(btrim(p_data->>'title'),'') is null or (p_data->>'due_date')::date is null then raise exception 'Task title and due date required' using errcode='22023';end if;
 when 'task_update' then
  if (p_data->>'status' is null or p_data->>'status' not in ('open','done','cancelled')) or p_data->>'task_id' is null then raise exception 'Invalid task update' using errcode='22023';end if;
 when 'incident' then
  if nullif(btrim(p_data->>'title'),'') is null or nullif(btrim(p_data->>'rule_version'),'') is null or nullif(btrim(p_data->>'explanation'),'') is null then raise exception 'Incident title, rule version and explanation required' using errcode='22023';end if;
  select id into v_incident from public.operation_incidents where organization_id=p_organization_id and lote_id is not distinct from v_lote and rule_version=p_data->>'rule_version' and status<>'resolved' for update;
 when 'incident_update' then
  if (p_data->>'status' is null or p_data->>'status' not in ('open','acknowledged','resolved')) or p_data->>'incident_id' is null then raise exception 'Invalid incident update' using errcode='22023';end if;
 when 'plan' then
  if not private.operation_manager(p_organization_id) then raise exception 'Only managers maintain plans' using errcode='42501';end if;
  v_qty:=(p_data->>'value')::numeric;if (p_data->>'target_date')::date is null or v_qty is null or v_qty<0 or nullif(p_data->>'metric','') is null or nullif(p_data->>'unit','') is null then raise exception 'Invalid plan' using errcode='22023';end if;
 when 'target' then
  if not private.operation_manager(p_organization_id) then raise exception 'Only managers maintain targets' using errcode='42501';end if;
  foreach v_key in array array['name','edition','genetics','sex','stage','metric','unit','denominator','source_url'] loop
   if nullif(btrim(p_data->>v_key),'') is null then raise exception 'Target metadata missing: %',v_key using errcode='22023';end if;
  end loop;
  if jsonb_typeof(p_data->'points') is distinct from 'array' or jsonb_array_length(p_data->'points')<1 or exists(select 1 from jsonb_array_elements(p_data->'points')x where coalesce(x->>'age','') !~ '^[0-9]+$' or jsonb_typeof(x->'value') is distinct from 'number' or (x->>'value')::numeric<0)
  or exists(select 1 from jsonb_array_elements(p_data->'points')x group by x->>'age' having count(*)>1) then raise exception 'Target points require unique nonnegative ages and values' using errcode='22023';end if;
 when 'snapshot' then
  if not private.operation_manager(p_organization_id) then raise exception 'Only managers create cycle snapshots' using errcode='42501';end if;
  if (p_data->>'cutoff')::date is null or (p_data->>'cutoff')::date>current_date or nullif(btrim(p_data->>'title'),'') is null then raise exception 'Snapshot cutoff and title required' using errcode='22023';end if;
 else raise exception 'Unsupported operation kind' using errcode='22023';
 end case;
 if v_qty::text in ('NaN','Infinity','-Infinity') or v_weight::text in ('NaN','Infinity','-Infinity') or v_weight<0 then raise exception 'Nonfinite or negative quantity' using errcode='22023';end if;
 if p_data->>'assigned_to' is not null and not exists(select 1 from public.organization_memberships where organization_id=p_organization_id and user_id=(p_data->>'assigned_to')::uuid) then raise exception 'Assignee must belong to organization' using errcode='42501';end if;
 insert into public.operations_events(id,organization_id,kind,lote_id,box_id,observed_at,quantity,quantity_female,quantity_male,weight_g,unit,sex,stage,note,source,quality,external_id,idempotency_key,data,created_by,supersedes_id,related_incident_id)
 values(v_id,p_organization_id,p_kind,v_lote,v_box,v_observed,v_qty,v_h,v_m,v_weight,
 case when p_kind='feed_movement' then 'kg' when p_kind='water_reading' then 'L' when p_kind='weighing' then 'birds_sampled' when p_kind='bird_movement' then 'birds' when p_kind like 'egg_%' or p_kind like 'hatch_%' then 'eggs' else p_data->>'unit' end,
 v_sex,v_stage,p_data->>'note',v_source,v_quality,p_data->>'external_id',p_idempotency_key,p_data,auth.uid(),v_supersedes,v_incident);
 if p_kind='bird_movement' then
  perform private.check_bird_balances(p_organization_id);
  -- Existing trigger recalculates all later headers for both source/destination lots.
  update public.registros_diarios_box r set peso_promedio_hembra_g=r.peso_promedio_hembra_g
  where r.id in (select min(x.id) from public.registros_diarios_box x join public.registros_diarios d on d.id=x.registro_diario_id
   where d.lote_id in (v_lote,(select lote_id from public.galpon_boxes where id=v_dest)) group by d.lote_id);
 end if;
 if p_kind='feed_movement' then
  -- Prefix balances include both warehouses of every atomic transfer, including late events.
  if exists(with ledger as (
   select e.observed_at,e.received_at,e.id,case when e.data->>'movement'='opening' then 0 else 1 end rank,e.data->>'warehouse' warehouse,case when e.data->>'movement' in ('consumption','transfer') then -e.quantity else e.quantity end delta
   from public.effective_operations_events e where e.organization_id=p_organization_id and e.kind='feed_movement'
   union all select e.observed_at,e.received_at,e.id,1,e.data->>'destination_warehouse',e.quantity from public.effective_operations_events e where e.organization_id=p_organization_id and e.kind='feed_movement' and e.data->>'movement'='transfer'
  ), balances as(select sum(delta) over(partition by warehouse order by observed_at,rank,received_at,id rows unbounded preceding) balance from ledger) select 1 from balances where balance<0)
  then raise exception 'Feed movement produces negative warehouse balance' using errcode='23514';end if;
 end if;
 -- Egg balances are conserved. Classification is observational and cannot create stock.
 if p_kind in ('egg_classification','egg_transfer','egg_split') and v_unit is null then raise exception 'Egg unit required' using errcode='22023';end if;
 if v_unit is not null then
  if exists(select 1 from public.operations_events e where e.id=v_unit and e.observed_at>v_observed) then raise exception 'Egg operation cannot precede origin receipt' using errcode='22023';end if;
  perform private.assert_egg_unit_access(p_organization_id,v_unit,(v_observed at time zone 'America/Bogota')::date);
  if not exists(select 1 from public.egg_units where id=v_unit and organization_id=p_organization_id) then raise exception 'No egg unit access' using errcode='42501';end if;
  select coalesce(sum(quantity),0) into v_available from public.egg_movements where unit_id=v_unit;
  if v_qty is null or v_qty>v_available then raise exception 'Egg quantity exceeds available unit balance' using errcode='23514';end if;
 end if;
 case p_kind
 when 'egg_receipt','egg_collection' then
  insert into public.egg_units(id,organization_id,lote_id,quantity) values(v_id,p_organization_id,v_lote,v_qty);
  insert into public.egg_movements(organization_id,event_id,unit_id,stage,quantity) values(p_organization_id,v_id,v_id,'collection',v_qty);
 when 'egg_classification' then
  if v_qty<>v_available then raise exception 'Classification categories must reconcile exactly with available eggs' using errcode='23514';end if;
 when 'egg_transfer' then
  v_stage:=coalesce(p_data->>'source_stage','collection');
  select coalesce(sum(quantity),0) into v_available from public.egg_movements where unit_id=v_unit and stage=v_stage;
  if v_qty>v_available or v_stage not in ('collection','classification','storage') or v_stage=p_data->>'destination' then raise exception 'Insufficient eggs at source stage or invalid stage transfer' using errcode='23514';end if;
  insert into public.egg_movements(organization_id,event_id,unit_id,stage,quantity) values(p_organization_id,v_id,v_unit,v_stage,-v_qty);
  if p_data->>'destination' in ('classification','storage') then
   insert into public.egg_movements(organization_id,event_id,unit_id,stage,quantity) values(p_organization_id,v_id,v_unit,p_data->>'destination',v_qty);
  end if;

 when 'egg_split' then
  v_stage:=coalesce(p_data->>'source_stage','collection');
  select coalesce(sum(quantity),0) into v_available from public.egg_movements where unit_id=v_unit and stage=v_stage;
  if v_qty>v_available or v_stage not in ('collection','classification','storage') then raise exception 'Insufficient eggs at split source stage' using errcode='23514';end if;
  insert into public.egg_units(id,organization_id,lote_id,quantity) select v_id,p_organization_id,lote_id,v_qty from public.egg_units where id=v_unit;
  insert into public.egg_unit_links(parent_id,child_id,organization_id,quantity) values(v_unit,v_id,p_organization_id,v_qty);
  insert into public.egg_movements(organization_id,event_id,unit_id,stage,quantity) values(p_organization_id,v_id,v_unit,v_stage,-v_qty),(p_organization_id,v_id,v_id,v_stage,v_qty);
 when 'egg_merge' then
  v_sum:=0;
  for v_input in select value from jsonb_array_elements(p_data->'unit_ids') loop
   v_unit:=(v_input#>>'{}')::uuid;
   perform private.assert_egg_unit_access(p_organization_id,v_unit,(v_observed at time zone 'America/Bogota')::date);
   if not exists(select 1 from public.egg_units where id=v_unit and organization_id=p_organization_id) then raise exception 'No merge origin access' using errcode='42501';end if;
   select coalesce(sum(quantity),0) into v_available from public.egg_movements where unit_id=v_unit;
   if v_available<=0 then raise exception 'Merge origin has no available eggs' using errcode='23514';end if;
   v_sum:=v_sum+v_available;
  end loop;
  insert into public.egg_units(id,organization_id,lote_id,quantity) values(v_id,p_organization_id,null,v_sum);
  for v_input in select value from jsonb_array_elements(p_data->'unit_ids') loop
   v_unit:=(v_input#>>'{}')::uuid;select sum(quantity) into v_available from public.egg_movements where unit_id=v_unit;
   insert into public.egg_unit_links(parent_id,child_id,organization_id,quantity) values(v_unit,v_id,p_organization_id,v_available);
   for v_row in select stage,sum(quantity) available from public.egg_movements where unit_id=v_unit group by stage having sum(quantity)>0 loop
    insert into public.egg_movements(organization_id,event_id,unit_id,stage,quantity) values(p_organization_id,v_id,v_unit,v_row.stage,-v_row.available),(p_organization_id,v_id,v_id,v_row.stage,v_row.available);
   end loop;
  end loop;

 when 'hatch_set' then
  insert into public.hatch_batches(id,organization_id,site_id,machine,eggs_set,status,set_at) values(v_id,p_organization_id,v_site,p_data->>'machine',v_qty,'set',v_observed);
  for v_input in select value from jsonb_array_elements(p_data->'inputs') loop
   v_unit:=(v_input->>'unit_id')::uuid;v_n:=(v_input->>'quantity')::integer;
   perform private.assert_egg_unit_access(p_organization_id,v_unit,(v_observed at time zone 'America/Bogota')::date);
   if v_n is null or v_n<=0 or not exists(select 1 from public.egg_units where id=v_unit and organization_id=p_organization_id) then raise exception 'Invalid incubation origin' using errcode='42501';end if;
   select coalesce(sum(quantity),0) into v_available from public.egg_movements where unit_id=v_unit;
   if v_n>v_available then raise exception 'Incubation origin exceeds available eggs' using errcode='23514';end if;
   insert into public.hatch_inputs(batch_id,unit_id,organization_id,quantity) values(v_id,v_unit,p_organization_id,v_n);
   for v_row in select stage,sum(quantity) available from public.egg_movements where unit_id=v_unit group by stage having sum(quantity)>0 order by stage loop
    v_sum:=least(v_n,v_row.available); if v_sum>0 then insert into public.egg_movements(organization_id,event_id,unit_id,stage,quantity) values(p_organization_id,v_id,v_unit,v_row.stage,-v_sum);v_n:=v_n-v_sum;end if;
   end loop;
  end loop;
 when 'hatch_transfer' then
  if exists(select 1 from public.hatch_batches b where b.id=v_batch and b.organization_id=p_organization_id and b.set_at>v_observed) then raise exception 'Hatch transfer cannot precede set time' using errcode='22023';end if;
  update public.hatch_batches set machine=p_data->>'machine',status='transferred' where id=v_batch and organization_id=p_organization_id and status='set';
  if not found then raise exception 'No open incubation batch access' using errcode='42501';end if;
 when 'hatch_result' then
  if exists(select 1 from public.hatch_batches b where b.id=v_batch and b.organization_id=p_organization_id and b.set_at>v_observed) or exists(select 1 from public.operations_events e where e.organization_id=p_organization_id and e.kind='hatch_transfer' and e.data->>'batch_id'=v_batch::text and e.observed_at>v_observed) then raise exception 'Hatch result cannot precede set or transfer' using errcode='22023';end if;
  select eggs_set into v_n from public.hatch_batches where id=v_batch and organization_id=p_organization_id and status in ('set','transferred') for update;
  if v_n is null then raise exception 'No open incubation batch access' using errcode='42501';end if;
  if (p_data->>'hatched')::integer+(p_data->>'rejected')::integer+(p_data->>'unhatched')::integer is distinct from v_n then raise exception 'Hatch categories must equal eggs set' using errcode='23514';end if;
  if (p_data->>'sample_n')::integer>v_n then raise exception 'Sample exceeds eggs set' using errcode='23514';end if;
  update public.hatch_batches set status='hatched',hatched=(p_data->>'hatched')::integer,rejected=(p_data->>'rejected')::integer,unhatched=(p_data->>'unhatched')::integer,sample_n=(p_data->>'sample_n')::integer,fertile_sample=(p_data->>'fertile_sample')::integer where id=v_batch;
 when 'task' then
  insert into public.operation_tasks(id,organization_id,lote_id,title,due_date,assigned_to,status) values(v_id,p_organization_id,v_lote,p_data->>'title',(p_data->>'due_date')::date,(p_data->>'assigned_to')::uuid,'open');
 when 'task_update' then
  select version into v_n from public.operation_tasks where id=(p_data->>'task_id')::uuid and organization_id=p_organization_id for update;
  if v_n is null then raise exception 'No task access' using errcode='42501';end if;
  if v_n is distinct from (p_data->>'expected_version')::integer then raise exception 'Task changed: reload before saving' using errcode='40001';end if;
  if p_data->>'evidence_event_id' is not null and not exists(select 1 from public.effective_operations_events e join public.operation_tasks t on t.id=(p_data->>'task_id')::uuid where e.id=(p_data->>'evidence_event_id')::uuid and e.organization_id=p_organization_id and (t.lote_id is null or e.lote_id=t.lote_id) and e.kind in ('bird_movement','weighing','water_reading','feed_movement','environment','health','stage','readiness','arrival','egg_collection','egg_receipt','egg_classification','egg_transfer','hatch_set','hatch_transfer','hatch_result') and (e.kind<>'readiness' or (e.data->>'completed')::boolean)) then raise exception 'Evidence must belong to organization' using errcode='42501';end if;
  if p_data->>'status'='done' and p_data->>'evidence_event_id' is null then raise exception 'Completion requires actual evidence event' using errcode='23514';end if;
  update public.operation_tasks set version=version+1,status=p_data->>'status',evidence_event_id=(p_data->>'evidence_event_id')::uuid,updated_at=now()
  where id=(p_data->>'task_id')::uuid and organization_id=p_organization_id;
  if not found then raise exception 'No task access' using errcode='42501';end if;
 when 'incident' then
  if v_incident is null then
   insert into public.operation_incidents(id,organization_id,lote_id,title,rule_version,explanation,assigned_to,status) values(v_id,p_organization_id,v_lote,p_data->>'title',p_data->>'rule_version',p_data->>'explanation',(p_data->>'assigned_to')::uuid,'open');
  else
   -- A sustained problem is one incident with another immutable observation.
   -- Keep its acknowledgement, owner and identity; optimistic editors now see a new version.
   update public.operation_incidents set explanation=p_data->>'explanation',version=version+1,updated_at=clock_timestamp() where id=v_incident;
  end if;
 when 'incident_update' then
  select version into v_n from public.operation_incidents where id=(p_data->>'incident_id')::uuid and organization_id=p_organization_id for update;
  if v_n is null then raise exception 'No incident access' using errcode='42501';end if;
  if v_n is distinct from (p_data->>'expected_version')::integer then raise exception 'Incident changed: reload before saving' using errcode='40001';end if;
  update public.operation_incidents set version=version+1,status=p_data->>'status',updated_at=now() where id=(p_data->>'incident_id')::uuid and organization_id=p_organization_id;
  if not found then raise exception 'No incident access' using errcode='42501';end if;
 when 'plan' then
  insert into public.production_plans(id,organization_id,lote_id,target_date,metric,unit,value) values(v_id,p_organization_id,v_lote,(p_data->>'target_date')::date,p_data->>'metric',p_data->>'unit',v_qty);
 when 'target' then
  insert into public.production_targets(id,organization_id,name,edition,genetics,sex,stage,metric,unit,denominator,source_url,points)
  values(v_id,p_organization_id,p_data->>'name',p_data->>'edition',p_data->>'genetics',v_sex,v_stage,p_data->>'metric',p_data->>'unit',p_data->>'denominator',p_data->>'source_url',p_data->'points');
 when 'snapshot' then
  select jsonb_build_object('schema_version',1,'rules_version','avilab-2026-11','generated_at',now(),'is_synthetic',v_lot.is_synthetic,'lote',to_jsonb(v_lot),
   'captures',coalesce((select jsonb_agg(to_jsonb(c) order by c.fecha) from public.daily_captures c where c.lote_id=v_lote and c.fecha<=(p_data->>'cutoff')::date and c.status in ('submitted','reviewed','closed')),'[]'::jsonb),
   'events',coalesce((select jsonb_agg(to_jsonb(e) order by e.observed_at,e.id) from public.operations_events e where (e.lote_id=v_lote or (e.kind='bird_movement' and e.data->>'movement'='transfer' and exists(select 1 from public.galpon_boxes b where b.id=(e.data->>'destination_box_id')::bigint and b.lote_id=v_lote))) and e.organization_id=p_organization_id and (e.observed_at at time zone 'America/Bogota')::date<=(p_data->>'cutoff')::date and e.kind<>'snapshot'),'[]'::jsonb),
   'daily_records',coalesce((select jsonb_agg(to_jsonb(d) order by d.fecha) from public.registros_diarios d where d.lote_id=v_lote and d.fecha<=(p_data->>'cutoff')::date and exists(select 1 from public.daily_captures c where c.daily_id=d.id and c.status in ('submitted','reviewed','closed'))),'[]'::jsonb),
   'daily_details',coalesce((select jsonb_agg(to_jsonb(r)) from public.registros_diarios_box r join public.registros_diarios d on d.id=r.registro_diario_id where d.lote_id=v_lote and d.fecha<=(p_data->>'cutoff')::date and exists(select 1 from public.daily_captures c where c.daily_id=d.id and c.status in ('submitted','reviewed','closed'))),'[]'::jsonb),
   'boxes',coalesce((select jsonb_agg(to_jsonb(b)) from public.galpon_boxes b where b.lote_id=v_lote),'[]'::jsonb),
   'measurements',coalesce((select jsonb_agg(to_jsonb(m)) from public.mediciones_produccion m join public.registros_diarios d on d.id=m.registro_diario_id where d.lote_id=v_lote and d.fecha<=(p_data->>'cutoff')::date and exists(select 1 from public.daily_captures c where c.daily_id=d.id and c.status in ('submitted','reviewed','closed'))),'[]'::jsonb),
   'measurement_catalog',coalesce((select jsonb_agg(to_jsonb(m)) from public.metricas_produccion m),'[]'::jsonb),
   'tasks',coalesce((select jsonb_agg(to_jsonb(t)) from public.operation_tasks t where t.lote_id=v_lote),'[]'::jsonb),
   'incidents',coalesce((select jsonb_agg(to_jsonb(t)) from public.operation_incidents t where t.lote_id=v_lote),'[]'::jsonb),
   'reference_scope','available_not_automatically_applied',
   'references',coalesce((select jsonb_agg(to_jsonb(t)) from public.production_targets t where t.organization_id=p_organization_id),'[]'::jsonb)) into v_content;
  insert into public.cycle_snapshots(id,organization_id,lote_id,title,cutoff,version,content)
  values(v_id,p_organization_id,v_lote,p_data->>'title',(p_data->>'cutoff')::date,coalesce((select max(version) from public.cycle_snapshots where lote_id=v_lote),0)+1,v_content);
 else null;
 end case;
 if p_kind like 'egg_%' or p_kind='hatch_set' then
  if exists(with balances as(select sum(m.quantity) over(partition by m.unit_id,m.stage order by e.observed_at,m.id rows unbounded preceding) balance
   from public.egg_movements m join public.operations_events e on e.id=m.event_id where m.organization_id=p_organization_id)
   select 1 from balances where balance<0) then raise exception 'Egg movement produces negative stage balance at event date' using errcode='23514';end if;
 end if;
 return v_id;
end $$;
revoke all on function private.record_operation_worker(uuid,text,jsonb,text) from public,anon;
grant execute on function private.record_operation_worker(uuid,text,jsonb,text) to authenticated;
create or replace function public.record_operation(p_organization_id uuid,p_kind text,p_data jsonb,p_idempotency_key text)
returns uuid language sql security invoker set search_path='' as $$
 select private.record_operation_worker(p_organization_id,p_kind,p_data,p_idempotency_key);
$$;
revoke all on function public.record_operation(uuid,text,jsonb,text) from public,anon;
grant execute on function public.record_operation(uuid,text,jsonb,text) to authenticated;

-- Preserve old RPC's atomism while making its population limit movement-aware.
do $$ declare v_sql text;begin
 select pg_get_functiondef('public.save_daily_record(bigint,date,jsonb)'::regprocedure) into v_sql;
 v_sql:=replace(v_sql,'and d.fecha<>p_fecha','and d.fecha<>p_fecha and not exists(select 1 from public.daily_captures c where c.daily_id=d.id and c.status=''draft'')');
 v_sql:=replace(v_sql,'if not found or v_lote.activo is distinct from true then','if not found or (v_lote.activo is distinct from true and current_user=''authenticated'') then');
 v_sql:=replace(v_sql,'coalesce(b.aves_hembra_inicial,0)','(coalesce(b.aves_hembra_inicial,0)+private.box_movement(b.id,''infinity''::date,''hembra''))');
 v_sql:=replace(v_sql,'coalesce(b.aves_macho_inicial,0)','(coalesce(b.aves_macho_inicial,0)+private.box_movement(b.id,''infinity''::date,''macho''))');
 execute v_sql;
 select pg_get_functiondef('private.sync_weighted_daily_weights()'::regprocedure) into v_sql;
 v_sql:=replace(v_sql,'and pd.fecha<=d.fecha','and pd.fecha<=d.fecha and not exists(select 1 from public.daily_captures c where c.daily_id=pd.id and c.status=''draft'')');
 v_sql:=replace(v_sql,'coalesce(b.aves_hembra_inicial,0) - coalesce(losses.hembras,0)','coalesce(b.aves_hembra_inicial,0) + private.box_movement(b.id,d.fecha,''hembra'') - coalesce(losses.hembras,0)');
 v_sql:=replace(v_sql,'coalesce(b.aves_macho_inicial,0) - coalesce(losses.machos,0)','coalesce(b.aves_macho_inicial,0) + private.box_movement(b.id,d.fecha,''macho'') - coalesce(losses.machos,0)');
 execute v_sql;
end $$;

-- Import is one transaction, never N partially committed row requests.
create or replace function private.import_operations_worker(p_organization_id uuid,p_rows jsonb,p_import_key text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r jsonb;v_result jsonb:='[]';v_existing public.daily_captures;v_org uuid;v_data jsonb;v_response jsonb;
begin
 if auth.uid() is null or not private.user_can_access_organization(p_organization_id,true) then raise exception 'No organization write permission' using errcode='42501';end if;
 if nullif(btrim(p_import_key),'') is null or jsonb_typeof(p_rows) is distinct from 'array' or jsonb_array_length(p_rows) not between 1 and 500 then raise exception 'Import requires 1..500 previewed rows and file key' using errcode='22023';end if;
 perform 1 from public.organizations where id=p_organization_id for update;
 for r in select value from jsonb_array_elements(p_rows) loop
  if jsonb_typeof(r) is distinct from 'object' or nullif(btrim(r->>'key'),'') is null or jsonb_typeof(r->'data') is distinct from 'object' then raise exception 'Invalid import row' using errcode='22023';end if;
  v_data:=r->'data';
  if r->>'kind'='daily' then
   select f.organization_id into v_org from public.lotes l join public.galpones g on g.id=l.galpon_id join public.granjas f on f.id=g.granja_id where l.id=(v_data->>'lote_id')::bigint;
   if v_org is distinct from p_organization_id then raise exception 'Import lot belongs to another organization' using errcode='42501';end if;
   select * into v_existing from public.daily_captures where lote_id=(v_data->>'lote_id')::bigint and fecha=(v_data->>'fecha')::date;
   if found then
    if v_existing.source='import' and v_existing.external_id=r->>'key' and v_existing.payload=v_data->'boxes' then
     v_response:=jsonb_build_object('id',v_existing.id,'version',v_existing.version,'status',v_existing.status,'reused',true);
    else raise exception 'Daily import conflicts with existing lot/date: review instead of overwriting' using errcode='40001';end if;
   else
    v_response:=private.save_daily_capture_worker((v_data->>'lote_id')::bigint,(v_data->>'fecha')::date,v_data->'boxes','submitted',0,'Excel preview confirmed','import',r->>'key');
   end if;
  else
   v_data:=v_data||jsonb_build_object('source','import','external_id',r->>'key');
   v_response:=jsonb_build_object('id',private.record_operation_worker(p_organization_id,r->>'kind',v_data,r->>'key'));
  end if;
  v_result:=v_result||jsonb_build_array(v_response);
 end loop;
 return jsonb_build_object('import_key',p_import_key,'count',jsonb_array_length(p_rows),'results',v_result);
end $$;
revoke all on function private.import_operations_worker(uuid,jsonb,text) from public,anon;
grant execute on function private.import_operations_worker(uuid,jsonb,text) to authenticated;
create or replace function public.import_operations(p_organization_id uuid,p_rows jsonb,p_import_key text)
returns jsonb language sql security invoker set search_path='' as $$
 select private.import_operations_worker(p_organization_id,p_rows,p_import_key);
$$;
revoke all on function public.import_operations(uuid,jsonb,text) from public,anon;
grant execute on function public.import_operations(uuid,jsonb,text) to authenticated;

create index daily_captures_org_id_idx on public.daily_captures(organization_id,id);
create index daily_capture_versions_org_capture_version_idx on public.daily_capture_versions(organization_id,capture_id,version);
create index operations_events_org_id_idx on public.operations_events(organization_id,id);
create index egg_unit_links_org_parent_child_idx on public.egg_unit_links(organization_id,parent_id,child_id);
create index hatch_inputs_org_batch_unit_idx on public.hatch_inputs(organization_id,batch_id,unit_id);
create index hatch_batches_site_idx on public.hatch_batches(site_id);
create index egg_unit_links_child_idx on public.egg_unit_links(child_id);
create index hatch_inputs_unit_idx on public.hatch_inputs(unit_id);
create index daily_captures_creator_idx on public.daily_captures(created_by);
create index daily_capture_versions_creator_idx on public.daily_capture_versions(created_by);
create index operations_events_creator_idx on public.operations_events(created_by);
create index operation_tasks_assignee_idx on public.operation_tasks(assigned_to);
create index operation_tasks_evidence_idx on public.operation_tasks(evidence_event_id);
create index operation_incidents_assignee_idx on public.operation_incidents(assigned_to);
create index operation_tasks_lote_idx on public.operation_tasks(lote_id);
create index operation_incidents_lote_idx on public.operation_incidents(lote_id);
create index production_plans_lote_idx on public.production_plans(lote_id);
create index egg_units_lote_idx on public.egg_units(lote_id);
create index egg_movements_event_idx on public.egg_movements(event_id);
