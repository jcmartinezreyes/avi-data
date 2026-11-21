-- Phase 1: keep analyst access read-only across the production hierarchy.
-- Apply this migration inside a transaction using the migration runner.
-- The existing write helper permits owner, admin and operator; analyst stays read-only.
-- WITH CHECK does not protect DELETE, so each mutation needs its own write USING.

-- 1. Granjas
drop policy if exists granjas_member_access on public.granjas;

create policy granjas_select on public.granjas
  for select to authenticated
  using (private.user_can_access_organization(organization_id, false));

create policy granjas_insert on public.granjas
  for insert to authenticated
  with check (private.user_can_access_organization(organization_id, true));

create policy granjas_update on public.granjas
  for update to authenticated
  using (private.user_can_access_organization(organization_id, true))
  with check (private.user_can_access_organization(organization_id, true));

create policy granjas_delete on public.granjas
  for delete to authenticated
  using (private.user_can_access_organization(organization_id, true));

-- 2. Galpones
drop policy if exists galpones_member_access on public.galpones;

create policy galpones_select on public.galpones
  for select to authenticated
  using (private.user_can_access_farm(granja_id, false));

create policy galpones_insert on public.galpones
  for insert to authenticated
  with check (private.user_can_access_farm(granja_id, true));

create policy galpones_update on public.galpones
  for update to authenticated
  using (private.user_can_access_farm(granja_id, true))
  with check (private.user_can_access_farm(granja_id, true));

create policy galpones_delete on public.galpones
  for delete to authenticated
  using (private.user_can_access_farm(granja_id, true));

-- 3. Lotes
drop policy if exists lotes_member_access on public.lotes;

create policy lotes_select on public.lotes
  for select to authenticated
  using (private.user_can_access_lote(id, false));

create policy lotes_insert on public.lotes
  for insert to authenticated
  with check (private.user_can_access_farm(
    (select g.granja_id from public.galpones g where g.id = lotes.galpon_id), true
  ));

create policy lotes_update on public.lotes
  for update to authenticated
  using (private.user_can_access_lote(id, true))
  with check (private.user_can_access_farm(
    (select g.granja_id from public.galpones g where g.id = lotes.galpon_id), true
  ));

create policy lotes_delete on public.lotes
  for delete to authenticated
  using (private.user_can_access_lote(id, true));

-- 4. Galpón Boxes
drop policy if exists galpon_boxes_member_access on public.galpon_boxes;

create policy galpon_boxes_select on public.galpon_boxes
  for select to authenticated
  using (private.user_can_access_lote(lote_id, false));

create policy galpon_boxes_insert on public.galpon_boxes
  for insert to authenticated
  with check (private.user_can_access_lote(lote_id, true));

create policy galpon_boxes_update on public.galpon_boxes
  for update to authenticated
  using (private.user_can_access_lote(lote_id, true))
  with check (private.user_can_access_lote(lote_id, true));

create policy galpon_boxes_delete on public.galpon_boxes
  for delete to authenticated
  using (private.user_can_access_lote(lote_id, true));

-- 5. Registros Diarios
drop policy if exists registros_diarios_member_access on public.registros_diarios;

-- Preserve the 20261106000224 read optimization on the hosted database.
-- The subquery uses lotes SELECT RLS, retaining organization isolation.
create policy registros_diarios_select on public.registros_diarios
  for select to authenticated
  using (lote_id in (select l.id from public.lotes l));

create policy registros_diarios_insert on public.registros_diarios
  for insert to authenticated
  with check (private.user_can_access_lote(lote_id, true));

create policy registros_diarios_update on public.registros_diarios
  for update to authenticated
  using (private.user_can_access_lote(lote_id, true))
  with check (private.user_can_access_lote(lote_id, true));

create policy registros_diarios_delete on public.registros_diarios
  for delete to authenticated
  using (private.user_can_access_lote(lote_id, true));

-- 6. Registros Diarios Box
drop policy if exists registros_diarios_box_member_access on public.registros_diarios_box;

create policy registros_diarios_box_select on public.registros_diarios_box
  for select to authenticated
  using (
    private.user_can_access_daily(registro_diario_id, false)
    and private.user_can_access_box(box_id, false)
  );

create policy registros_diarios_box_insert on public.registros_diarios_box
  for insert to authenticated
  with check (
    private.user_can_access_daily(registro_diario_id, true)
    and private.user_can_access_box(box_id, true)
  );

create policy registros_diarios_box_update on public.registros_diarios_box
  for update to authenticated
  using (
    private.user_can_access_daily(registro_diario_id, true)
    and private.user_can_access_box(box_id, true)
  )
  with check (
    private.user_can_access_daily(registro_diario_id, true)
    and private.user_can_access_box(box_id, true)
  );

create policy registros_diarios_box_delete on public.registros_diarios_box
  for delete to authenticated
  using (
    private.user_can_access_daily(registro_diario_id, true)
    and private.user_can_access_box(box_id, true)
  );

-- 7. Mediciones Producción
drop policy if exists mediciones_produccion_member_access on public.mediciones_produccion;

create policy mediciones_produccion_select on public.mediciones_produccion
  for select to authenticated
  using (
    private.user_can_access_daily(registro_diario_id, false)
    and (box_id is null or private.user_can_access_box(box_id, false))
  );

create policy mediciones_produccion_insert on public.mediciones_produccion
  for insert to authenticated
  with check (
    private.user_can_access_daily(registro_diario_id, true)
    and (box_id is null or private.user_can_access_box(box_id, true))
  );

create policy mediciones_produccion_update on public.mediciones_produccion
  for update to authenticated
  using (
    private.user_can_access_daily(registro_diario_id, true)
    and (box_id is null or private.user_can_access_box(box_id, true))
  )
  with check (
    private.user_can_access_daily(registro_diario_id, true)
    and (box_id is null or private.user_can_access_box(box_id, true))
  );

create policy mediciones_produccion_delete on public.mediciones_produccion
  for delete to authenticated
  using (
    private.user_can_access_daily(registro_diario_id, true)
    and (box_id is null or private.user_can_access_box(box_id, true))
  );
