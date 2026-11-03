do $$
declare
  v_organization_id uuid;
begin
  select id into v_organization_id
  from public.organizations
  where name = 'Cristopher Martinez'
  order by created_at
  limit 1;

  if v_organization_id is null then
    insert into public.organizations(name, created_by)
    values ('Cristopher Martinez', null)
    returning id into v_organization_id;
  end if;

  insert into public.organization_subscriptions(organization_id, plan_code, status)
  values (v_organization_id, 'full', 'active')
  on conflict (organization_id) do update
    set plan_code = excluded.plan_code,
        status = 'active',
        ends_at = null;

  update public.granjas
  set organization_id = v_organization_id
  where organization_id is null;
end
$$;