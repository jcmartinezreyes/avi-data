alter table public.granjas
  add constraint granjas_organization_id_required
  check (organization_id is not null) not valid;

create index mediciones_produccion_box_id_idx
  on public.mediciones_produccion(box_id);
create index mediciones_produccion_created_by_idx
  on public.mediciones_produccion(created_by);
create index organizations_created_by_idx
  on public.organizations(created_by);
create index registros_diarios_created_by_idx
  on public.registros_diarios(created_by);
create index registros_diarios_box_created_by_idx
  on public.registros_diarios_box(created_by);