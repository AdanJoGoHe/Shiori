# Visor de escritorio: Inicio y recuperación de fragmentos

La dirección elegida es **A · Mesa de trabajo**, del prototipo de la PR #37: menú lateral,
búsqueda visible y textos útiles antes que controles secundarios. Conserva el stack local,
la marca Shiori y los temas Claro, Oscuro y Café Latte. El prototipo comparativo permanece
en su propia rama; este visor usa las APIs y datos del despliegue seleccionado.

## Qué funciona

- Inicio reúne hasta dos fragmentos recientes, dos páginas recientes y dos avances vigentes de
  Hoy. Cada bloque tiene acceso a su sección completa, estado vacío, error y reintento.
  Una lectura incompleta no se presenta como una colección vacía. Las vistas son resúmenes,
  no totales de toda la memoria; el catálogo mantiene sus límites de escaneo existentes.
- El ámbito y el día vienen del servidor local. Inicio vuelve a pedir la fecha en cada carga,
  sin usar el reloj o la zona horaria del navegador para decidir qué es Hoy.
- Biblioteca mantiene las colecciones, filtros exactos, paginación, lector y anotaciones.
  El buscador superior consulta documentos o fragmentos; desde Diario abre esa búsqueda
  en Biblioteca/Fragmentos. No busca dentro de los avances del diario.
- Fragmentos da acceso directo a las categorías estables Comando, Dirección IP, Ruta e
  Información importante. Sus nombres se leen de las categorías existentes; las archivadas
  desaparecen de los accesos rápidos, conservando el filtro completo y las marcas anteriores.
  Las categorías personalizadas siguen disponibles. Elegir un acceso selecciona una categoría
  exacta; las categorías combinadas del filtro completo conservan la semántica Y.
- Los resultados muestran cita, contexto, origen y estado del ancla. Los comandos y direcciones
  usan tipo de código; la información importante usa texto normal. Copiar envía la cita completa,
  sin el contexto. En Windows, el portapapeles puede representar LF como CRLF.
- El resumen de Inicio limita visualmente el contexto y permite desplazar citas muy largas;
  Fragmentos muestra el texto completo. Abrir ubicación conserva búsqueda, filtros, página y
  posición al volver. Las marcas ambiguas o ausentes siguen usando la reparación existente.
- Atrás/Adelante restaura el estado de esta pestaña. Las consultas y los identificadores de
  documentos no se incluyen en la URL; solo nombres de vistas. El estado de historial lo gestiona
  el navegador, sin persistencia nueva de la aplicación. Recargar inicia la vista nombrada sin filtros.
  `#diario` conserva su destino. El tema sigue siendo la única preferencia en app localStorage.

Favoritos y Agent log muestran explícitamente que están pendientes. Este incremento no guarda
favoritos, no registra herramientas y no migra ningún almacén. El diario conserva su flujo actual;
su rework de Hoy/Ayer y el lector mejorado continúan en las tareas #33 y #34.

## Decisiones visuales

Seguimos la dirección Taste **Editorial greeting**, manteniendo la paleta y tipografía del
producto y la composición del prototipo A. La pregunta de Inicio es «¿qué quiero recuperar y qué
avancé hoy?». Biblioteca responde «¿dónde está esta página?»; Fragmentos, «¿cuál era ese comando?».
El marcador de Shiori identifica el producto, y las citas reales son el elemento principal.
Cada destino mantiene una identidad discreta en menú, cabeceras y etiquetas de resultados:

| Destino | Símbolo | Acento |
| --- | --- | --- |
| Inicio | 🗂 | Verde salvia |
| Biblioteca | 📚 | Azul pizarra |
| Fragmentos | 🏷 | Ocre |
| Favoritos | 🔖 | Ciruela |
| Diario | 📓 | Tierra |
| Agent log | 📋 | Gris azulado |
| Tareas | 🗒 | Verde petróleo suave |

Los accesos a comandos, IPs, rutas e información importante también llevan símbolos. Los emojis
se muestran con saturación reducida y siempre acompañan al texto; se ocultan al lector de pantalla
para no repetir el nombre. El dibujo concreto depende de las fuentes del sistema. Los acentos
identifican destinos, no estados de verificación, y no cambian los colores de las marcas guardadas.
Oscuro usa pares de tinta/fondo propios; Claro y Café Latte conservan tonos oscuros legibles.
No hay métricas inventadas, fuentes remotas, controles flotantes ni cambio de framework.

El marco tiene un menú de 224 px, un ancho total máximo de 1680 px y márgenes de contenido de
36 px; Inicio reparte su contenido 3:2 con un espacio de 24 px. Las columnas crecen según sus
datos. El lector comparte la pantalla con resultados en escritorio y conserva vuelta directa.
El reflujo estrecho sirve al zoom de escritorio; esta entrega no incluye aceptación móvil.

## Fichas por tarea

El menú **Tareas** añade contexto por código, con cuerpo Markdown, estados y vínculos a páginas,
marcas y URLs. Reutiliza las anotaciones y el lector. No sustituye los pendientes del Diario ni
convierte su contenido en conocimiento verificado. [Uso y contratos](task-pages.md).

## Comprobarlo

Con Python 3.12 y las dependencias de desarrollo instaladas:

```powershell
python scripts/demo-viewer.py
python scripts/check-local.py
python scripts/check-repository.py --secrets
```

La demo crea documentación, notas, diario y marcas ficticias en una carpeta temporal. No carga
la configuración del usuario. Las comprobaciones opcionales de navegador necesitan Node y
Playwright disponibles; `SB_TEST_NODE` y `NODE_PATH` pueden seleccionar instalaciones existentes:

```powershell
python scripts/check-workspace-workflow.py
python scripts/check-workspace-workflow.py --task-pages
python scripts/check-annotation-workflow.py
python scripts/check-journal-workflow.py
```

El primer recorrido comprueba perfiles personal/trabajo independientes, día del servidor,
comando multilínea, copia, lector, Atrás/Adelante, filtros individuales, paginación, errores por
sección y catálogos parciales. Revisa 1280/1440/1920 y tres temas. Los otros recorridos comprueban
marcas, reparación, reinicio, categorías y pendientes existentes. Todo usa datos ficticios;
las capturas quedan en carpetas temporales fuera del repositorio.

La revisión Taste del visor usa `--app`. La opción `--allow emoji` respeta la identidad por símbolos solicitada por el propietario,
además del carácter Unicode que forma parte del comando de prueba. Es una excepción deliberada
a la regla general de Taste; los símbolos no sustituyen etiquetas o estados. El inspector también
cuenta la fuente del sistema para emojis como una tercera familia junto al texto y el código; ese
aviso se acepta únicamente para los símbolos. El texto mantiene su tipografía anterior. El aviso estático sobre
`padStart(2, "0")` en el diario corresponde a bytes de un identificador SHA-256, no a numeración
decorativa. El inspector es un complemento: también se revisan las capturas y se recorren las vistas.

Las tareas #24 y #26 cubren este incremento. #25 avanza con búsqueda visible y filtros retirables,
pero siguen pendientes los alcances nuevos y la navegación de coincidencias en el lector.
Las pruebas locales no sustituyen la aceptación de Augment real (#2), la aceptación integrada
de toda la épica (#36) ni una publicación de release.
