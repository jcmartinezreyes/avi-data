drop function public.create_organization(text);

drop policy organizations_select_member on public.organizations;
create policy organizations_select_creator_or_member on public.organizations
for select to authenticated
using (
  created_by = (select auth.uid())
  or private.user_can_access_organization(id, false)
);

create policy organizations_insert_creator on public.organizations
for insert to authenticated
with check (created_by = (select auth.uid()));

create policy organization_memberships_insert_owner_self on public.organization_memberships
for insert to authenticated
with check (
  user_id = (select auth.uid())
  and role = 'owner'
  and exists (
    select 1 from public.organizations o
    where o.id = organization_id and o.created_by = (select auth.uid())
  )
);

grant insert on public.organizations, public.organization_memberships to authenticated;

create function public.create_organization(p_name text)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_organization_id uuid := gen_random_uuid();
begin
  if v_user_id is null then
    raise exception 'Authentication required';
  end if;
  if length(trim(coalesce(p_name, ''))) = 0 then
    raise exception 'Organization name is required';
  end if;
  if exists (
    select 1 from public.organization_memberships m
    where m.user_id = v_user_id
  ) then
    raise exception 'This user already belongs to an organization';
  end if;

  insert into public.organizations(id, name, created_by)
  values (v_organization_id, trim(p_name), v_user_id);

  insert into public.organization_memberships(organization_id, user_id, role)
  values (v_organization_id, v_user_id, 'owner');

  return v_organization_id;
end;
$$;
revoke all on function public.create_organization(text) from public, anon;
grant execute on function public.create_organization(text) to authenticated;