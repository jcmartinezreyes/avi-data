"""Emit an administrator SQL integration test; all changes are rolled back.

Usage: python3 tests/phase5_seed_rollback.py | psql -X -v ON_ERROR_STOP=1 ...
Uses the existing Martinez_Poultry/full organization, without changing its data.
The six pending audit migrations are installed only inside the test transaction.
"""
from pathlib import Path
import re


def build_sql():
    root = Path(__file__).resolve().parents[1]
    seed = (root / "supabase/seed_martinez_poultry.sql").read_text()
    # Never embed the production seed's COMMIT into a rollback test.
    seed, starts = re.subn(r"^begin;\s*$", "", seed, flags=re.M | re.I)
    seed, ends = re.subn(r"^commit;\s*$", "", seed, flags=re.M | re.I)
    if (starts, ends) != (1, 1):
        raise ValueError("Expected exactly one seed transaction")
    migrations = sorted((root / "supabase/migrations").glob("2026112100000[1-6]_*.sql"))
    if len(migrations) != 6:
        raise ValueError("Expected all six Phase 1–4 migrations")
    parts = ["begin; set local statement_timeout='120s';"]
    parts.extend(p.read_text() for p in migrations)
    # ALTER SEQUENCE RESTART is transactional, unlike ordinary nextval calls.
    parts.append("""
do $$ declare t text; seq regclass; n bigint; begin
 foreach t in array array['granjas','galpones','lotes','galpon_boxes',
                          'registros_diarios','registros_diarios_box'] loop
  select pg_get_serial_sequence('public.'||t,'id')::regclass into seq;
  execute format('select greatest(coalesce(max(id),0)+100000,100000) from public.%I',t) into n;
  execute format('alter sequence %s restart with %s',seq,n);
 end loop;
end $$;
""")
    parts.append(seed)
    parts.append("""
create temp table phase5_before as
select md5(string_agg(to_jsonb(r)::text,'' order by r.id)) checksum
from public.registros_diarios r join public.lotes l on l.id=r.lote_id
where l.codigo_lote like 'SEMILLA-MP-v1-%';
""")
    # Support temporary staging tables even when the production seed retains
    # them until COMMIT. Drop staging only; never alter application tables.
    cleanup = """
do $$ declare t record; begin
 for t in select tablename from pg_tables where schemaname like 'pg_temp_%'
           and tablename like 'mp_seed_%' loop
  execute format('drop table pg_temp.%I cascade',t.tablename);
 end loop;
end $$;
"""
    parts.extend([cleanup, seed])
    parts.append("""
do $$ declare n integer; begin
 if (select checksum from phase5_before) is distinct from (
  select md5(string_agg(to_jsonb(r)::text,'' order by r.id))
  from public.registros_diarios r join public.lotes l on l.id=r.lote_id
  where l.codigo_lote like 'SEMILLA-MP-v1-%'
 ) then raise exception 'Second seed changed persisted daily records'; end if;
 select count(*) into n from public.lotes where codigo_lote like 'SEMILLA-MP-v1-%';
 if n<>60 then raise exception 'Expected 60 lots'; end if;
 if exists(
  select 1 from public.registros_diarios r join public.lotes l on l.id=r.lote_id
  where l.codigo_lote like 'SEMILLA-MP-v1-%' and (
   r.fecha<>l.fecha_encaste+r.dia_vida-1 or r.consumo_alimento_kg<=0
   or r.peso_promedio_mixto_g<=0 or r.fecha>date '2026-11-21')
 ) then raise exception 'Daily biological/calendar consistency failed'; end if;
 if exists(
  select l.id from public.lotes l join public.registros_diarios r on r.lote_id=l.id
  where l.codigo_lote like 'SEMILLA-MP-v1-%' and not l.activo
  group by l.id,l.aves_totales having count(*)<>42 or
   sum(r.mortalidad_hembra+r.mortalidad_macho)::numeric/l.aves_totales not between 0.02 and 0.04
 ) then raise exception 'Closed lot coverage/mortality failed'; end if;
 if (select count(*) from public.registros_diarios_box b
     join public.registros_diarios r on r.id=b.registro_diario_id
     join public.lotes l on l.id=r.lote_id
     where l.codigo_lote like 'SEMILLA-MP-v1-%' and l.activo)<>197 then
  raise exception 'Active lots need 197 complete box details'; end if;
end $$;
""")
    parts.append("""
update public.registros_diarios r set consumo_alimento_kg=consumo_alimento_kg+1
where r.id=(select min(d.id) from public.registros_diarios d
 join public.lotes l on l.id=d.lote_id where l.codigo_lote='SEMILLA-MP-v1-001');
do $guard$ declare rejected boolean:=false; begin
 begin
  execute $seedbody$""" + seed + """$seedbody$;
 exception when raise_exception then
  if sqlerrm<>'Namespaced daily data contains manual or differing values' then raise; end if;
  rejected:=true;
 end;
 if not rejected then raise exception 'Seed accepted modified daily data'; end if;
end $guard$;
rollback;
select 'Phase 5 passed: 60 lots, 2297 daily rows, 197 active details; rerun unchanged; manual changes rejected; all writes rolled back' as result;
""")
    return "\n".join(parts)


if __name__ == "__main__":
    print(build_sql())
