# Evaluación de interfaz: tareas antes que herramientas

Fecha: 28 de noviembre de 2026. Rol: evaluador de interfaz de AviLab.
Alcance: revisión de lectura de AviData en Safari y del código local de
`app.py` y `operations_ui.py`, con versión publicada de partida
`3d1897fa717d7ec7c57c4c02b136263e9bf4397e` indicada por el coordinador.
No se guardaron registros de producción, importaciones, tareas ni datos de prueba.
No se modificaron código de aplicación, esquema, permisos ni referencias privadas.

## Evidencia y límites

Se inició sesión con la cuenta de prueba autorizada y se recorrieron Inicio,
Ingreso diario, Centro de operación y Eventos productivos. La lectura del árbol de
accesibilidad confirmó los controles y su orden. Se abrió un box sin introducir
valores. El formulario de pesaje se abrió sin registrar una muestra.

Las capturas nativas de Safari llegaron como miniaturas oblicuas. Por ello no se
presentan como prueba de legibilidad visual, contraste o tamaño real de toque.
No se consiguió una sesión real a 360 px de ancho y no se afirma haberla probado.
Los criterios móviles siguientes deben verificarse después de la implementación.
No hubo entrevistas con productores ni medición cronometrada de tareas humanas.
Las prioridades son una evaluación profesional, no porcentajes de mejora medidos.

## Hallazgos priorizados

| ID | Prioridad | Evidencia confirmada | Propuesta y aceptación |
| --- | --- | --- | --- |
| UI-01 | Alta | Ingreso diario muestra H1 «Registro diario», H3 «Centro de operación» y H3 «Tu jornada, con cada dato en su lugar». Centro de operación añade un selector con siete áreas. | Un título principal y una introducción breve; navegación visible con área activa y nombres por tarea. Cambiar de área no debe crear hechos ni exigir conocer la estructura interna. |
| UI-02 | Alta | La jornada comienza con una tabla de diez lotes pendientes antes de seleccionar lote/fecha. El lote inicial tiene ocho boxes colapsados y 32 campos requeridos ausentes. Recuperar un archivo aparece antes de la captura habitual. | Mostrar contexto y avance primero; desplegar el primer box incompleto; indicar campos completos/requeridos por box. Plegar lista general y recuperación de respaldo. No completar ceros automáticamente. |
| UI-03 | Alta | En pesaje, antes del área de pesos se muestran lote, alcance, fecha, hora, procedencia, calidad, identificador de origen y sexo. Los tres metadatos técnicos pesan tanto como la tarea principal. | Conservar lote/fecha/alcance/sexo visibles y reunir procedencia/calidad/origen en un área avanzada. Los valores existentes y una corrección deben conservar su semántica aunque el área esté plegada. |
| UI-04 | Alta | Inicio muestra 0/10 lotes con registros recientes y un mensaje sin acción próxima. Debajo aparece el listado de engorde por edad. | Acción «Registrar jornada» y acceso a revisar pendientes, sin confundir dato ausente con cero ni cerrar lotes por edad. Una persona operadora debe encontrar su acción habitual antes de revisar el histórico. |
| UI-05 | Alta | El envío está deshabilitado y se explica el número de campos faltantes. El detalle ya está plegado, pero los boxes no indican cuál falta ni cuánto avance tiene cada uno. | Mantener bloqueo y explicación; localizar el siguiente box pendiente. Al enviar, conservar validación de todos los boxes, versión y permisos. Un envío incompleto nunca debe transformarse en un registro confirmado. |
| UI-06 | Media | El resumen de jornada incluye columnas de machos vacías en un lote sin machos, aun cuando el formulario los omite correctamente. | Resumen adaptado a los sexos presentes, con unidades y ausencia explícita. El detalle completo puede seguir disponible bajo revisión; no omitir un sexo que haya ingresado por transferencia real. |
| UI-07 | Media | La mayoría de espacios vacíos usa «Todavía no hay registros en esta vista». El contexto puede ser agenda, cronología o inventario, con próximos pasos diferentes. | Mensaje específico: qué falta, por qué está vacío y qué acción autorizada permite empezar. El analista de lectura no recibe una acción de escritura imposible. |
| UI-08 | Media | Código `_jornada.save`: éxito y `st.rerun()` consecutivos. No se hizo una escritura en producción para observar su duración. | Verificar con prueba sintética que el mensaje de confirmación sobreviva al rerun y sea específico de la tarea. Navegar o refrescar no repite el RPC. |
| UI-09 | Media | La importación muestra 16 asignaciones de campos en un panel antes de interpretar el tipo de captura. Este hallazgo procede de lectura del código; no se subió una planilla en Safari. | Agrupar por identidad/fecha, mediciones y campos opcionales; ofrecer ruta por tipo de importación. Conservar revisión de unidades, frecuencia y conflictos antes del envío atómico. |
| UI-10 | Media | La estructura de estilos tiene un breakpoint a 760 px, pero no constituye una prueba móvil. Tablas, controles repetidos y botones en varias columnas necesitan revisión real. | A 360 px: captura principal sin desplazamiento horizontal, botones con etiqueta completa, foco visible y ayudas cercanas. Las tablas anchas pueden desplazarse dentro de su propio contenedor. |

## Flujo propuesto de jornada

1. Elegir lote y fecha, con granja, galpón, edad y estado visibles.
2. Ver avance de la captura, empezando por el primer box pendiente.
3. Registrar conteos y consumos; mostrar pesaje como sección opcional.
4. Revisar resumen legible y campos pendientes; guardar borrador o enviar cuando
   estén completos los requisitos aplicables.
5. Conservar confirmación, autoría, versión e historial; las tareas de revisión
   y reapertura aparecen solo a los perfiles autorizados.

La copia sin conexión, la recuperación y el historial son capacidades útiles,
pero deben aparecer como herramientas de apoyo. Su plegado no cambia sus permisos,
fecha de caducidad, versión de origen ni comportamiento de sincronización.

## Invariantes de aceptación

- Vacío = no medido; cero = medición de cero; no aplica exige contexto verificable.
- No repartir alimento mixto artificialmente entre sexos.
- No ocultar un sexo recibido por movimientos solo porque su alojamiento inicial
  haya sido cero.
- No perder la versión cargada al rerenderizar. Un servidor con una versión nueva
  debe provocar conflicto explícito, no sobrescritura silenciosa.
- Cambiar navegación, abrir paneles, QR o ayudas no escribe datos.
- El analista mantiene lectura; operador no revisa/cierra períodos mediante UI.
- Los textos de éxito describen la acción realizada, sin afirmar mejoras biológicas.

## Entrega al implementador

Los hallazgos UI-01 a UI-08 se enviaron al coordinador y al implementador antes de
editar la interfaz. UI-09 y UI-10 requieren comprobar su alcance con las fuentes de
investigación y el resultado implementado. Se prioriza reducir decisiones y
repeticiones antes de añadir más colores, animaciones o servicios externos.

Safari quedó libre para el investigador al terminar esta inspección. Las reglas
de activación siguen siendo manuales; la evaluación no crea tareas periódicas.

## Revisión de la implementación y pruebas sintéticas

Durante la misión se revisó la nueva `operations_ui.py` en lectura. Se incorporaron
indicadores de pendientes/borradores/enviados, contexto compacto del lote, ayudas
plegadas y paneles de box con avance y apertura del primero incompleto. Estos son
cambios inspeccionados en código; la comprobación de la publicación corresponde
al coordinador al integrar.

Se añadieron cuatro pruebas de comportamiento en `tests/test_modern_ui.py` y se
ejecutaron con `/private/tmp/avidata-ui311/bin/python`. Resultado: **4 aprobadas**.

1. Un borrador conserva una mortalidad medida de cero y un consumo ausente como
   valores distintos, junto a sus estados de medición.
2. Marcar «Revisé los datos» no habilita enviar una jornada incompleta.
3. El formulario muestra machos recibidos por transferencia aunque el alojamiento
   inicial de machos del box fuera cero.
4. El primer box incompleto se abre y un box ya completo permanece plegado.

Estas pruebas utilizan exclusivamente un cliente sintético sin red y no escriben
hechos de producción. Complementan las regresiones de permisos y concurrencia
existentes; no sustituyen una evaluación con operadores reales o la revisión
visual a 360 px. No se atribuyen tiempos ahorrados, menos errores humanos ni
satisfacción medida sin un ensayo específico.

## Verificación posterior del coordinador

Después de esta evaluación se comprobó la implementación en un navegador real
con datos sintéticos aislados. A 360 × 800 píxeles, el área principal midió
360 píxeles de ancho y scrollWidth 360: no hubo desbordamiento horizontal en la
captura revisada. Los botones Enviar jornada y Guardar borrador midieron
334,4 × 44 píxeles. Se revisó también la captura de escritorio en dos columnas.
Estas comprobaciones complementan la evaluación inicial de Safari; no son una
certificación de accesibilidad ni una prueba con dispositivos u operadores reales.
