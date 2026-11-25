"""Self-contained offline draft editor. No network, tokens or automatic sync."""
from datetime import datetime, timedelta, timezone
import json

FIELDS = (
    ('mortalidad_hembra', 'Muertas · hembras', True),
    ('mortalidad_macho', 'Muertas · machos', True),
    ('descarte_hembra', 'Descartes · hembras', True),
    ('descarte_macho', 'Descartes · machos', True),
    ('consumo_alimento_kg', 'Alimento consumido · kg', False),
    ('consumo_agua_litros', 'Agua consumida · L', False),
    ('peso_promedio_hembra_g', 'Peso medio · hembras · g', False),
    ('peso_promedio_macho_g', 'Peso medio · machos · g', False),
)


def offline_editor(organization_id, user_id, lot_id, day, boxes, version, now=None):
    """Return an HTML editor whose JSON output is reviewed by the online importer.

    The version is fixed at export, so a stale offline file cannot silently replace
    a newer server version. Files expire in seven days and contain no auth material.
    """
    now = now or datetime.now(timezone.utc)
    payload = {'format': 'avidata-draft-v1', 'organization_id': organization_id,
               'user_id': user_id, 'lote_id': lot_id, 'fecha': str(day),
               'version': version, 'created_at': now.isoformat(),
               'expires_at': (now + timedelta(days=7)).isoformat(), 'boxes': boxes}
    safe = json.dumps(payload, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    fields = json.dumps(FIELDS, ensure_ascii=True)
    return '''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'">
<title>AviData · Borrador sin conexión</title><style>
*{box-sizing:border-box}body{font:16px system-ui,sans-serif;background:#f8fafd;color:#1f2937;margin:0;padding:18px}main{max-width:720px;margin:auto}section{background:white;border:1px solid #d8e2f0;border-radius:16px;padding:18px;margin:16px 0}label{display:block;margin-top:16px}input,select,button{font:inherit;padding:12px;border:1px solid #b8c7da;border-radius:10px;width:100%;margin:6px 0}button{background:#0b57d0;color:white;cursor:pointer}small,p{line-height:1.5}h1{font-size:26px}#error{color:#9f1c20}input:disabled{background:#edf3fc}
</style><main><h1>Borrador de jornada</h1><p id="context"></p><p>Esta copia funciona sin conexión después de descargarla. Los cambios se conservan al descargar el archivo JSON. Recupera ese archivo en AviData para revisar y sincronizar; no se envía nada desde aquí.</p><div id="fields"></div><p id="error" role="alert"></p><button id="save">Descargar borrador JSON</button><small>Guarda este archivo en un equipo de confianza. No contiene contraseñas; sí contiene datos de producción. Caduca en siete días. La aplicación comprobará tus permisos y la versión al sincronizar.</small></main><script>
'use strict';
const draft=__PAYLOAD__, fields=__FIELDS__;
const root=document.getElementById('fields');
document.getElementById('context').textContent='Lote '+draft.lote_id+' · '+draft.fecha+' · Versión '+draft.version;
for(const box of draft.boxes){
 const section=document.createElement('section'),heading=document.createElement('h2');heading.textContent='Box '+box.box_id;section.append(heading);
 box.measurement_states=box.measurement_states||{};
 for(const [code,label,integer] of fields){
  const caption=document.createElement('label');caption.textContent=label;
  const select=document.createElement('select'),input=document.createElement('input');
  for(const [value,text] of [['not_measured','No medido'],['measured','Medido'],['not_applicable','No aplica']]){const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}
  select.value=box.measurement_states[code]||(box[code]==null?'not_measured':'measured');
  input.type='number';input.min='0';input.step=integer?'1':'any';input.value=box[code]==null?'':box[code];input.disabled=select.value!=='measured';
  select.addEventListener('change',()=>{input.disabled=select.value!=='measured';box.measurement_states[code]=select.value;if(input.disabled){input.value='';box[code]=null;}});
  input.addEventListener('input',()=>{box[code]=input.value===''?null:Number(input.value);});
  box.measurement_states[code]=select.value;caption.append(select,input);section.append(caption);
 }
 root.append(section);
}
document.getElementById('save').addEventListener('click',()=>{
 const error=document.getElementById('error');error.textContent='';
 if(new Date(draft.expires_at)<=new Date()){error.textContent='Este borrador caducó. Exporta uno nuevo desde AviData.';return;}
 for(const box of draft.boxes)for(const [code,label,integer] of fields){const value=box[code];if(box.measurement_states[code]==='measured'&&(value==null||!Number.isFinite(value)||value<0||(integer&&!Number.isInteger(value)))){error.textContent='Revisa '+label+': un valor medido debe ser válido; puedes usar No medido.';return;}}
 const blob=new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='avidata-borrador.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});</script></html>'''.replace('__PAYLOAD__', safe).replace('__FIELDS__', fields)
