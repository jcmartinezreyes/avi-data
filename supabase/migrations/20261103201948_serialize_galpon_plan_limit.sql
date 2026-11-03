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

  -- Serialize quota checks within an organization so concurrent inserts cannot
  -- both consume the same last available spot.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_organization_id::text, 0)
  );

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