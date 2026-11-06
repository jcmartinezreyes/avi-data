-- Reuse the lot read policy so access is checked once per lot instead of once per daily row.
alter policy registros_diarios_member_access on public.registros_diarios
using (lote_id in (select l.id from public.lotes l));
