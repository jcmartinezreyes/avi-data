create function private.require_active_lot_for_daily_write()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    target_lot bigint;
    is_active boolean;
begin
    if tg_table_name = 'registros_diarios' then
        target_lot := new.lote_id;
    else
        select r.lote_id into target_lot
        from public.registros_diarios r
        where r.id = new.registro_diario_id;
    end if;

    select l.activo into is_active
    from public.lotes l
    where l.id = target_lot
    for share;

    if is_active is distinct from true then
        raise exception 'El ingreso diario solo está disponible para lotes activos.' using errcode = '23514';
    end if;
    return new;
end;
$$;

-- End users cannot capture or edit daily measurements after closing a lot.
-- Administrative imports can load historical data directly.
create trigger registros_diarios_require_active_lot
before insert or update on public.registros_diarios
for each row when (current_user = 'authenticated')
execute function private.require_active_lot_for_daily_write();

create trigger registros_diarios_box_require_active_lot
before insert or update on public.registros_diarios_box
for each row when (current_user = 'authenticated')
execute function private.require_active_lot_for_daily_write();

create trigger mediciones_produccion_require_active_lot
before insert or update on public.mediciones_produccion
for each row when (current_user = 'authenticated')
execute function private.require_active_lot_for_daily_write();
