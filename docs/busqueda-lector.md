# Buscar y leer

El buscador superior tiene cinco alcances: **Biblioteca**, **Fragmentos marcados**, **Favoritos**,
**Diario** y **Agent log**. Cambiar el selector conserva el texto para buscarlo en otro sitio.
El menú lateral abre una sección con el texto limpio. `Ctrl+K` lleva al buscador.

- Biblioteca busca documentación, notas y páginas autorizadas. Combina todos los términos y muestra
  contexto cercano a la coincidencia, incluidos comandos de bloques de código. Ignora mayúsculas y
  acentos. Proyecto, etiquetas y demás filtros mantienen su coincidencia exacta.
- Fragmentos busca en la cita, título, descripción y nombres de sus categorías. Una categoría de
  fragmento es distinta de una etiqueta de documento. Copiar devuelve la cita completa sin contexto.
- Favoritos busca solo lo guardado en este perfil. [Contrato y límites](favoritos.md).
- Diario busca en el texto de las capturas del periodo seleccionado, antes de paginar. Ignora
  mayúsculas y acentos. Los pendientes actuales conservan su lista completa: no los oculta la búsqueda
  de avances. Cada consulta abarca hasta 31 días, con cualquier antigüedad conservada.
- Agent log busca acciones informadas, comandos, contexto y referencias del periodo. Mantiene sus
  filtros propios y no convierte actividad en conocimiento verificado. [Detalles](agent-log.md).

Los términos se combinan con Y; las etiquetas/categorías elegidas también. Los filtros activos
pueden quitarse individualmente. **Limpiar filtros** restablece el alcance actual; en Diario y
Agent log vuelve a Hoy. Revisa los avisos de lectura incompleta y sigue la paginación: cero
coincidencias con fuentes inaccesibles no demuestra que la información no exista.

## El lector

El lector abre junto a los resultados en PC. **Centrar lectura** amplía el documento y oculta la
lista; **Ver resultados y lector** recupera ambas columnas. **Volver a resultados**, Atrás y Adelante
conservan la consulta, filtros, página, modo de lectura, búsqueda local y posición. El índice mueve
la lectura sin crear pasos extra en el historial. La fecha, procedencia y estado declarado aparecen
en la cabecera; las notas con una sección de evidencia ofrecen **Ver evidencia**.

**Buscar en esta página** busca en el título y texto visibles, sin alterar la búsqueda de resultados.
**Anterior/Siguiente** o Intro/Mayús+Intro recorren las coincidencias; al final vuelven al principio.
El subrayado es temporal, distinto de las marcas de color guardadas. Se muestran hasta 500
coincidencias con aviso al superar ese límite. Una coincidencia en metadatos o en el destino de
un enlace puede no aparecer en el texto visible de la página.

En navegadores con Custom Highlight API se usan rangos que no modifican el DOM ni las posiciones
de las anotaciones ([especificación del W3C](https://www.w3.org/TR/css-highlight-api-1/)). Si esa API
no está disponible, la navegación usa selección temporal del texto. No crea marcas persistentes.

**Textos marcados** reúne citas, categorías, títulos y descripciones cerca de la cabecera. Copia el
texto exacto o ve a su ubicación. Un anclaje ambiguo o desaparecido pide revisión; no se inventa
una ubicación. Los controles de edición, reparación, eliminación y deshacer siguen disponibles
en Marcas guardadas. El texto fuente permanece de solo lectura. Las tablas y el código ancho
se desplazan dentro de su bloque; no se ejecutan comandos ni se cargan recursos externos.

## Buscar avances desde la IA o terminal

```powershell
.\shiori.cmd run journal --project laboratorio --query "192.0.2.10"
.\shiori.cmd run journal --start-date 2026-05-01 --end-date 2026-05-31 --query "conexión"
```

MCP `read_journal` acepta `query` con la misma combinación de términos, fechas y proyecto, antes
de paginar. `view=tasks` conserva su contrato y rechaza texto de búsqueda; consulta el estado actual
de pendientes aparte. Las herramientas y el CLI devuelven capturas informadas, no prueba de que
un comando se haya ejecutado o una nota esté verificada. Si el servidor antiguo carece de `query`,
usa únicamente el CLI compatible de esa misma instalación/configuración o indica que requiere
actualización. No cambies al perfil personal como respaldo de una consulta de trabajo.
