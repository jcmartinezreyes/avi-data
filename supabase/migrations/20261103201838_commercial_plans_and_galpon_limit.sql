alter table public.organizations
  alter column created_by drop not null;
comment on column public.organizations.created_by is
  'Supabase Auth owner account. Nullable only for the test seed until its Auth user is created.';

create table public.subscription_plans (
  code text primary key,
  name text not null,
  max_galpones integer,
  incubadora_incluida boolean not null default false,
  max_incubadoras integer default 0,
  active boolean not null default true,
  check (max_galpones is null or max_galpones >= 0),
  check (max_incubadoras is null or max_incubadoras >= 0)
);

insert into public.subscription_plans
  (code, name, max_galpones, incubadora_incluida, max_incubadoras)
values
  ('basic', 'Básica', 10, false, 0),
  ('medium', 'Media', 20, true, 1),
  ('full', 'Full', null, true, null);

create table public.organization_subscriptions (
  organization_id uuid primary key references public.organizations(id) on delete cascade,
  plan_code text not null references public.subscription_plans(code) on delete restrict,
  status text not null default 'active'
    check (status in ('trial', 'active', 'past_due', 'canceled')),
  starts_at timestamptz not null default now(),
  ends_at timestamptz,
  created_at timestamptz not null default now(),
  check (ends_at is null or ends_at > starts_at)
);
create index organization_subscriptions_plan_code_idx
  on public.organization_subscriptions(plan_code);

alter table public.subscription_plans enable row level security;
alter table public.organization_subscriptions enable row level security;

create policy subscription_plans_authenticated_read on public.subscription_plans
for select to authenticated using (active);

create policy organization_subscriptions_member_read on public.organization_subscriptions
for select to authenticated
using (private.user_can_access_organization(organization_id, false));

grant select on public.subscription_plans, public.organization_subscriptions to authenticated;

create or replace function private.enforce_galpon_plan_limit()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_organization_id uuid;
  v_max_galpones integer;
  v_current_count bigint;
begin
  select f.organization_id into v_organization_id
  from public.granjas f
  where f.id = new.granja_id;

  if v_organization_id is null then
    raise exception 'La granja debe pertenecer a una organización';
  end if;

  select p.max_galpones into v_max_galpones
  from public.organization_subscriptions s
  join public.subscription_plans p on p.code = s.plan_code
  where s.organization_id = v_organization_id
    and s.status = 'active'
    and s.starts_at <= now()
    and (s.ends_at is null or s.ends_at > now())
    and p.active;

  if not found then
    raise exception 'La organización no tiene un plan activo';
  end if;

  if v_max_galpones is not null then
    select count(*) into v_current_count
    from public.galpones g
    join public.granjas f on f.id = g.granja_id
    where f.organization_id = v_organization_id
      and (tg_op = 'INSERT' or g.id <> new.id);

    if v_current_count >= v_max_galpones then
      raise exception 'El plan permite hasta % galpones', v_max_galpones;
    end if;
  end if;

  return new;
end;
$$;
revoke all on function private.enforce_galpon_plan_limit() from public;

create trigger galpones_enforce_plan_limit
before insert or update of granja_id on public.galpones
for each row execute function private.enforce_galpon_plan_limit();