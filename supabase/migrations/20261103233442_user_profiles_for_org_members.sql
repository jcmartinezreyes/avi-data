create table if not exists public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  full_name text not null default '',
  username text not null,
  job_title text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_profiles_full_name_nonempty check (length(trim(full_name)) > 0),
  constraint user_profiles_username_nonempty check (length(trim(username)) > 0)
);

create unique index if not exists user_profiles_username_lower_uidx
  on public.user_profiles (lower(username));

alter table public.user_profiles enable row level security;

drop policy if exists user_profiles_select_self on public.user_profiles;
create policy user_profiles_select_self on public.user_profiles
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists user_profiles_insert_self on public.user_profiles;
create policy user_profiles_insert_self on public.user_profiles
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists user_profiles_update_self on public.user_profiles;
create policy user_profiles_update_self on public.user_profiles
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

grant select, insert, update on public.user_profiles to authenticated;

-- Perfil inicial para la cuenta de prueba de Martinez_Poultry.
do $$
declare
  v_user_id uuid;
  v_organization_id uuid;
begin
  select id into v_user_id
  from auth.users
  where lower(email) = lower('jcmartinezreyes28@gmail.com')
  limit 1;

  if v_user_id is not null then
    select id into v_organization_id
    from public.organizations
    where name in ('Martinez_Poultry', 'Cristopher Martinez')
       or created_by = v_user_id
    order by created_at
    limit 1;

    if v_organization_id is not null then
      update public.organizations
      set name = 'Martinez_Poultry', created_by = v_user_id
      where id = v_organization_id;

      insert into public.organization_memberships(organization_id, user_id, role)
      values (v_organization_id, v_user_id, 'admin')
      on conflict (organization_id, user_id) do update set role = 'admin';

      insert into public.user_profiles(user_id, full_name, username, job_title)
      values (v_user_id, 'Jean Cristopher Martinez Reyes', 'jcmartinezreyes28', 'Gerente general')
      on conflict (user_id) do update set
        full_name = excluded.full_name,
        username = excluded.username,
        job_title = excluded.job_title,
        updated_at = now();
    end if;
  end if;
end;
$$;
