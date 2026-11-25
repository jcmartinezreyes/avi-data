# Implementación de propuestas AviLab

Solicitud del propietario: 25 de noviembre de 2026. La implementación integra los
paquetes A/B/C, M-01 a M-09, V-01 a V-03, R-01 a R-07 y S-01 a S-05.
No activa trabajos programados ni vuelve a ejecutar las semillas de 60 lotes.

## Secuencia y revisión

1. Contratos y migración aditiva: captura, versiones, permisos, eventos e inventarios.
2. Cálculos e importación: ausencias, unidades, muestras, conciliación y pronósticos.
3. Interfaz: jornada, eventos por producción, incubación, agenda, trazabilidad y configuración.
4. Integración, pruebas de aislamiento y concurrencia, publicación y verificación web.

## Matriz de aceptación

| Propuestas | Entrega | Verificación requerida |
| --- | --- | --- |
| A, M-01/02/03/09 | Jornada compacta, borradores, pendiente frente a cero, recuperación local | Captura incompleta no altera KPIs; reintentos no duplican |
| B, M-04/07 | Eventos por producción y etapa, movimientos, muestras, salud, huevos e incubación | Saldos y denominadores explícitos; sin doble conteo |
| C, M-05/06/08, S-04 | Versiones, conflictos, revisión/reapertura, importación y fuentes versionadas | Permisos en servidor, antes/después, vista previa e idempotencia |
| V-01, R-02, S-01 | Agenda, responsables, preparación, recepción e incidencias | Pendiente no equivale a completado; evidencia enlazada |
| V-02, R-01/05, S-02/03 | Cronología, procedencia, etiquetas, unidades y clasificación por etapa | Identidad estable sin credenciales; conservación de cantidades |
| V-03, R-03/04/06/07 | Inventario, cobertura, informe reproducible, planes y pronóstico evaluable | Validación cronológica; sintéticos no acreditan precisión real |
| S-05 | Incorporación guiada y ejemplo sintético | Revisar unidades antes de cualquier escritura real |

## Límites de validación

No se incorporarán curvas genéticas sin fuente y edición verificadas, ni umbrales
sanitarios inventados. No se afirmará validación predictiva con datos sintéticos.
El trabajo sin conexión se documentará conforme a la capacidad efectivamente
implementada; Streamlit necesita conexión para cargar la aplicación.
Las planillas originales de clientes permanecen privadas y fuera de publicación.

## Evidencia de partida

- Copia local sin `.git`, conservada; no se clonó ni inicializó un repositorio.
- GitHub `main`: `94565b4ef27306de6c9b0a89651f03415978983f`.
- Base remota: 60 lotes, 10 activos; no se regenera esta población.
- Las 20 pruebas existentes pasan antes de modificar el código.

## Resultado de implementación

Los contratos se implementan en la migración operacional y se documentan en
`docs/operations_backend_contract.md`. La aplicación incorpora siete áreas en
`operations_ui.py`, cálculos en `analytics.py` y `avilab_domain.py`, lectura segura
en `import_tools.py`, borradores portables en `offline_drafts.py` y reconstrucción
de informes congelados en `cycle_report.py`.

Se probaron permisos y aislamiento con el rol real `authenticated`, versiones
obsoletas, envío/revisión/cierre/reapertura, bloqueo de escrituras directas,
transferencias y mortalidad posterior, pesos por población viva, correcciones,
inventarios, varios orígenes de incubación, fracciones rechazadas, muestras,
evidencia de tareas, incidencias sostenidas e importaciones con rollback completo.
El ensayo SQL de la migración completa alcanzó `AVILAB_DRYRUN_OK`: la excepción
intencional posterior a las aserciones revirtió el esquema y los fixtures.
Una consulta independiente confirmó 60 lotes, 2241 diarios y 140 detalles originales.

Las pruebas Python incluyen carga de las siete áreas, variantes de eventos y
herramientas gerenciales, conflictos durante una edición, fechas de Bogotá,
separación por sexo, exclusión de borradores, ausencia frente a cero, fórmulas y
archivos peligrosos, anonimización y reproducibilidad de informes.

### Límites de esta entrega

- La importación inicial admite jornadas, recolecciones y ambiente; otros hechos
  se capturan con formularios que exigen su contexto y conciliación específicos.
- Las lecturas de contador se conservan cronológicamente con reinicio documentado.
  Unidades de huevo consumidas no se reemplazan mediante ediciones genéricas:
  se usan movimientos conciliados y reclasificaciones con motivo.
- Se ofrece formulario descargable sin red y recuperación con conflictos; no una
  aplicación Streamlit instalable que cargue completamente sin conexión.
- Las incidencias se registran y siguen por observación humana. No se activan
  umbrales biológicos automáticos ni tareas programadas sin una regla validada.
- Las conexiones reales con sensores, maquinaria y evidencia fotográfica privada
  no forman parte de la primera integración. No se aparentan dispositivos conectados.
- El histórico sin detalle de box conserva sus hechos originales; no se inventa
  el detalle ausente. Las ediciones operativas necesitan estructura verificable.
- Las guías requieren validación de fuente, edición, sexo, etapa, unidades,
  denominador y convención de edad antes de usarlas como comparación.
- Falta medir usabilidad con operadores reales y validar pronósticos con ciclos
  reales. Las pruebas técnicas no acreditan beneficios comerciales o sanitarios.

## Publicación del 25 de noviembre de 2026

La migración `operational_workflows` se aplicó a Avi-data con versión remota
`20261125163546`. Su SHA-256 es
`2a2f9c16b2a0c83590b10e4232cfc484a3698a56d2946f7909d234294974d522`.
El archivo local conserva la fecha de creación del CLI; la versión del historial
remoto identifica la aplicación efectiva, no una segunda migración pendiente.

Las 52 pruebas Python pasan. Las pruebas SQL posteriores a aplicar el esquema
terminaron en `OPERATIONS_POSTAPPLY_TESTS_OK` y se revirtieron. Se conservaron
60 lotes (10 activos), 2241 diarios y 140 detalles; existen 2241 capturas con su
primera versión histórica. No quedaron lotes ni eventos de los fixtures.
Las 14 tablas nuevas tienen RLS; las escrituras directas, también mediante la
vista de hechos efectivos, se rechazaron con el rol autenticado.

El asesor de seguridad conserva el aviso previo de protección contra contraseñas
filtradas desactivada: no es una regla de las nuevas tablas. Configuración y alcance:
https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection
El asesor de rendimiento solo informó índices todavía sin uso; no se eliminaron
los índices nuevos antes de que exista carga representativa.
