# Investigación de interfaces modernas aplicables a AviData

Fecha de consulta: 28 de noviembre de 2026. Rol: investigador de producto.
Misión autorizada: investigar referencias y patrones, aportar propuestas al evaluador
y al implementador de interfaz; detenerse al entregar. Este documento es investigación,
no prueba de usabilidad ni autorización de actividades adicionales.

## Alcance y evidencia

Se consultaron documentación oficial de Google/Material, W3C, GOV.UK, IBM Carbon y
Streamlit, páginas públicas de productos avícolas y los informes de investigación
anteriores del proyecto. Se leyeron `app.py` y `operations_ui.py` de la copia local
cuya referencia de partida comunicada por el coordinador es el commit
`3d1897fa717d7ec7c57c4c02b136263e9bf4397e`. La carpeta carece de `.git`; no se
clonó ni se modificó su contenido de producción. La observación del código no
sustituye la revisión visual de Safari encargada al evaluador.

La carpeta `referencias/software/` conserva cinco enlaces: AviSoft y Avícola en
YouTube, PoultryOS, Unitas y PoultryPlan. No se procesaron planillas privadas ni se
transmitieron datos de clientes a buscadores o proveedores. Los videos no fueron
vistos en esta misión. Sus límites audiovisuales previos permanecen documentados
como evidencia anterior, no como observaciones nuevas.

## Fuentes contrastadas

| Fuente y enlace directo | Evidencia de esta misión | Aplicación propuesta |
| --- | --- | --- |
| [Material 3: navigation rail](https://m3.material.io/components/navigation-rail/overview) | Página documental abierta y leída en Safari tras el aviso JavaScript de la consulta automática. | Destino activo con indicador visible, posición coherente y variantes colapsada/expandida. La página describe 3–7 destinos para rail; no es el límite de una barra inferior. |
| [Google: layouts y navegación](https://developer.android.com/design/ui/mobile/guides/layout-and-content/layout-and-nav-patterns) | Documentación oficial accesible. Distingue navegación primaria/secundaria y adaptación por tamaño. | Pocos grupos principales, espacio actual identificable y acciones frecuentes cerca de la tarea. Su implementación Android no se incorpora a Streamlit. |
| [GOV.UK: revisar respuestas](https://design-system.service.gov.uk/patterns/check-answers/) | Guía y ejemplos de revisión previa. | Resumen antes del envío, posibilidad de volver a corregir y conservación de lo escrito. |
| [GOV.UK: detalles](https://design-system.service.gov.uk/components/details/) | Guía de cuándo ocultar información secundaria. | Colapsar historial y procedencia avanzada; mantener visibles contexto, campos obligatorios y acción de guardado. |
| [GOV.UK: lista de tareas](https://design-system.service.gov.uk/components/task-list/) | Guía de tareas con estado y agrupación. | Separar pendiente, borrador y enviado; indicar qué falta sin confundir finalización visual con escritura confirmada. |
| [Carbon: estados vacíos](https://www.carbondesignsystem.com/building-blocks/core/patterns/empty-states) | Página oficial, actualizada el 11 de agosto de 2026 según su encabezado. | Cada vacío debe explicar qué aparecerá y cómo continuar; ausencia de resultados, falta de permisos y primer uso requieren mensajes distintos. |
| [W3C: etiquetas e instrucciones](https://www.w3.org/WAI/WCAG22/Understanding/labels-or-instructions) | Explicación del criterio 3.3.2. | Etiquetas persistentes, unidades y obligatoriedad identificables; ayuda breve, junto al campo. |
| [W3C: tamaño del objetivo](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | Explicación del criterio 2.5.8. | Mínimo de 24 × 24 píxeles CSS o excepciones/espaciado aplicables. Como decisión de diseño de AviData se propone 44 píxeles de altura en controles frecuentes; no se presenta 44 como el requisito AA. |
| [W3C: contraste](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) | Explicación del criterio 1.4.3. | Comprobar 4,5:1 para texto normal y 3:1 para texto grande; no comunicar estados solo con color. |
| [Streamlit 1.67: pills](https://docs.streamlit.io/develop/api-reference/widgets/st.pills) y [tabs](https://docs.streamlit.io/develop/api-reference/layout/st.tabs) | Documentación de la versión fijada por el proyecto. | Preferir controles nativos. `st.pills` admite selección única requerida y ajuste de línea. Las pestañas ejecutan todo por defecto; con seguimiento de estado y renderizado condicional puede limitarse al panel activo. |
| [PoultryOS: funciones](https://poultryos.com/features) | Nueva lectura de página pública con referencias a pantallas móviles, captura y tareas. | Conservar contexto del ciclo y acceso orientado al trabajo diario. Las afirmaciones del proveedor no acreditan superioridad, modo offline o ahorro real para AviData. |
| [Unitas: plataforma](https://unitassoftware.com/es/plataforma/) | Nueva apertura en Safari tras timeout automático; se leyeron categorías y enlaces de módulos. | Agrupar por tarea y proceso. La página es comercial; no demuestra el comportamiento de formularios de su aplicación privada. |
| [PoultryPlan: OptiLayers](https://www.poultryplan.com/solutions/optilayers) | Nueva lectura de página pública; evidencia comercial. | Organizar la información por proceso y origen, con una ruta de consulta comprensible. No se probaron módulos privados. |

La consulta automática de navegación de Material 3 devolvió un aviso de
JavaScript y una ruta antigua de layout devolvió 404. Se resolvió la primera en
Safari: la página documental muestra navegación lateral y pestañas de artículo, y
explica el indicador activo, variantes colapsada/expandida y actualización
Expressive de mayo de 2025. Su tabla señala la implementación web del componente
como no disponible; se proponen patrones adaptados a controles nativos de Streamlit,
no instalar ni aparentar una biblioteca web oficial de ese componente.

Unitas produjo un timeout automático y después cargó en Safari. Se identificaron
su página de plataforma y enlaces de gestión de rebaños, clasificación,
planificación, alimentación e integraciones. Esto acredita lectura del catálogo,
no acceso a módulos privados. Se abrieron dos pestañas de investigación, sin
cuentas, formularios ni cambios de configuración. El navegador se devolvió al
coordinador para la revisión de AviData.

## Diagnóstico verificable en el código de partida

1. `app.py` crea un bloque `avi-hero` para Centro de operación y `operations_ui.py`
   vuelve a imprimir su título. La duplicación consume espacio antes de la tarea.
2. El selector `Espacio de trabajo` oculta las otras seis áreas hasta abrirlo. Es
   funcional, pero no muestra de un vistazo el conjunto ni la ubicación activa.
3. La jornada presenta una tabla de pendientes antes del selector de lote. En
   clientes con muchos lotes puede desplazar la acción cotidiana hacia abajo.
4. La recuperación y descarga de borradores, el motivo, la revisión y el historial
   están juntos con la captura. Tienen utilidad distinta y no todos se necesitan
   cada día.
5. Todos los boxes de un lote con varios boxes empiezan colapsados. Esto reduce
   longitud, pero obliga a abrirlos para descubrir dónde falta información.
6. El estado vacío genérico de `_table` no explica el siguiente paso ni distingue
   ausencia de hechos de ausencia de coincidencias.
7. Las mejoras existentes de null frente a cero, permisos y versiones son valiosas.
   El rediseño debe conservarlas; reemplazar inputs por una planilla sin esos
   contratos puede hacer la pantalla más corta y los datos menos fiables.

Estas son observaciones de código y propuestas de diseño, no mediciones de tiempo
ni resultados con productores reales.

## Propuestas prioritarias y contrato para implementación

| ID | Prioridad | Cambio propuesto | Criterio de aceptación técnico |
| --- | --- | --- | --- |
| UI-01 | P0 | Un encabezado compacto por página, con organización y descripción breve. Reducir bandas decorativas y títulos repetidos. | El usuario alcanza el contexto de la tarea antes; jerarquía única de título, sin ocultar nombre/organización. |
| UI-02 | P0 | Navegación de áreas visible mediante controles nativos, selección activa textual y ajuste a varias líneas en móvil. Mantener pocos grupos principales. | Se reconocen las siete áreas y la seleccionada sin abrir un menú; teclado funciona y solo se renderiza el área elegida. |
| UI-03 | P0 | Jornada organizada en contexto, captura por box y revisión/envío; contexto visible de lote, granja, galpón, fecha, edad y estado. | Cambiar de box no altera fecha o lote. Ninguna etiqueta de progreso afirma guardado si no hubo respuesta del servidor. |
| UI-04 | P0 | Resumen de avance por box: número real de campos obligatorios pendientes y estado textual. Abrir de entrada el primer box que requiere atención. | Un null no cuenta como cero medido; el sexo ausente no genera tareas imposibles; pesajes opcionales no bloquean el envío. |
| UI-05 | P0 | Etiquetas y ayuda persistentes; panel de revisión legible; Enviar como acción principal y Guardar borrador como secundaria. | La revisión conserva los datos; el envío mantiene confirmación, versión de origen y validación atómica. Un error conserva lo escrito. |
| UI-06 | P1 | Consultas de pendientes, historial, corrección, procedencia avanzada y respaldo como ayudas secundarias bien tituladas. | Los datos necesarios para la captura cotidiana no quedan ocultos; las opciones avanzadas siguen disponibles según el rol. |
| UI-07 | P1 | Vacíos con título, explicación y próximo paso; mensajes distintos para filtro sin coincidencias, primer uso y permisos. | Cada área vacía informa cómo empezar sin crear datos ficticios ni mostrar un error técnico. |
| UI-08 | P1 | Superficies claras, tipografía legible, bordes discretos, escala coherente de espacios, foco visible y estados con texto además de color. | Comprobación de contraste, foco de teclado y reflujo a 360 px. No utilizar selectores CSS que afecten otros widgets por accidente. |
| UI-09 | P1 | Accesos directos a tareas frecuentes desde Inicio: registrar jornada, revisar pendientes, consultar análisis. | Cada acceso cambia la vista correcta y respeta el rol; no escribe ni autocompleta datos productivos. |

### Propuesta visual propia

No se prescribe copiar una interfaz comercial. Se propone conservar el azul de
AviData y utilizar una escala simple: espacios de 8/12/16/24 px; texto principal
16 px y ayuda 14 px; títulos contenidos; iconos acompañados de texto. Los controles
principales deben ser cómodos al tacto y las acciones secundarias menos dominantes.
Una barra fija de acciones solo se recomienda si se verifica que no tapa campos
ni el teclado del móvil; en caso contrario, mantenerla en el flujo del documento.

Como ejemplo de tokens, se calcularon estas parejas con luminancia relativa:

| Texto | Fondo | Contraste calculado |
| --- | --- | --- |
| `#172B4D` | `#FFFFFF` | 14,10:1 |
| `#52637A` | `#FFFFFF` | 6,13:1 |
| `#52637A` | `#F7F9FC` | 5,81:1 |
| `#FFFFFF` | `#0B57D0` | 6,39:1 |
| `#0B57D0` | `#E8F0FE` | 5,57:1 |

El cálculo comprueba estas parejas, no la accesibilidad integral de la aplicación
ni todos sus estados, placeholders, gráficos o controles deshabilitados.

## Condiciones de conservación y evaluación

- Reutilizar los mismos RPC, campos, reglas de permisos y límite de suscripción.
- Mantener identidad del lote/box y versión fijada al inicio de la edición.
- Conservar las entradas durante correcciones; no reemplazar vacíos por ceros.
- No presentar guardado automático, sincronización o precisión predictiva que no
  hayan ocurrido y sido verificadas.
- Evitar que pestañas decorativas calculen áreas ocultas o dupliquen consultas.
- Probar tareas representativas: localizar la jornada, completar un box, revisar
  un campo ausente, recuperar un borrador, consultar una historia y cambiar de área.
- Complementar AppTest y revisión de Safari con operadores reales antes de afirmar
  ahorro de tiempo, menos errores o una mejora porcentual de facilidad de uso.

La investigación entrega estas propuestas al evaluador y al implementador. No ha
modificado código de la aplicación, esquema, datos, dependencias ni despliegues.
