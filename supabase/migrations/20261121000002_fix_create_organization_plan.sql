-- Provision the default plan in the same transaction as organization creation.
-- authenticated keeps read-only access to subscriptions: it cannot choose a plan,
-- alter billing dates or promote itself to full through the Data API.
create or replace function private.provision_basic_organization_subscription()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if auth.uid() is not null and new.created_by is distinct from auth.uid() then
    raise exception 'Organization creator must match the authenticated user';
  end if;

  if not exists (
    select 1 from public.subscription_plans p
    where p.code = 'basic' and p.active
  ) then
    raise exception 'The default basic plan is not available';
  end if;

  insert into public.organization_subscriptions
    (organization_id, plan_code, status, starts_at)
  values (new.id, 'basic', 'active', pg_catalog.now());

  return new;
end;
$$;

-- Only the organizations trigger may invoke this privileged operation.
revoke all on function private.provision_basic_organization_subscription()
  from public, anon, authenticated;

create trigger organizations_provision_basic_subscription
after insert on public.organizations
for each row execute function private.provision_basic_organization_subscription();

create or replace function public.create_organization(p_name text)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_organization_id uuid := pg_catalog.gen_random_uuid();
begin
  if v_user_id is null then
    raise exception 'Authentication required';
  end if;
  if length(pg_catalog.btrim(coalesce(p_name, ''))) = 0 then
    raise exception 'Organization name is required';
  end if;

  -- Calls for one user serialize before checking membership, including concurrent
  -- requests from different browser tabs. Other users do not share this lock.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('avidata:create_organization:' || v_user_id::text, 0)
  );

  if exists (
    select 1 from public.organization_memberships m
    where m.user_id = v_user_id
  ) then
    raise exception 'This user already belongs to an organization';
  end if;

  insert into public.organizations (id, name, created_by)
  values (v_organization_id, pg_catalog.btrim(p_name), v_user_id);

  -- The AFTER INSERT trigger has already inserted an active basic subscription.
  -- A failure below also rolls back the organization and its subscription.
  insert into public.organization_memberships (organization_id, user_id, role)
  values (v_organization_id, v_user_id, 'owner');

  return v_organization_id;
end;
$$;

revoke all on function public.create_organization(text) from public, anon;
grant execute on function public.create_organization(text) to authenticated;
