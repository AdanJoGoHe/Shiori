# Un diario para poder retomar lo que estabas haciendo

Shiori guarda avances por día, además de las notas de conocimiento. Las skills de personal
y trabajo registran resultados al cerrar una parte significativa de una tarea o preparar un
relevo. Puedes pedir «¿qué hice hoy?», «resume esta semana» o «retomemos este proyecto».
El agente consulta el diario y prepara la respuesta a partir de lo guardado.

Cada avance puede incluir lo terminado, las comprobaciones realizadas, decisiones, bloqueos
y próximos pasos. No hace falta rellenar todo. Una prueba que falta va en pendientes; una
decisión propuesta se describe como propuesta. El diario no calcula horas ni convierte un
resumen en conocimiento verificado. Los pendientes reflejan el momento en que se guardaron:
hay que comprobar si siguen abiertos antes de tratarlos como tareas actuales.

## Guardar un avance

Ejemplo sintético para `capture_memory`, después de revisar `classify_memory`:

```json
{
  "scope": "personal",
  "mode": "journal-only",
  "event_id": "ejemplo-parser-001",
  "title": "Parser revisado",
  "source_agent": "manual",
  "project": "ejemplo",
  "summary": "Corregida la lectura del formato de ejemplo.",
  "progress": {
    "completed": ["Añadida la corrección del parser."],
    "checks": ["Tres pruebas locales pasaron."],
    "decisions": ["Conservar el formato de entrada."],
    "blockers": ["Falta probarlo en el editor."],
    "next_steps": ["Abrir el editor y ejecutar un ejemplo sintético."]
  }
}
```

`project` es un slug o `null`. `progress` admite esas cinco listas opcionales, con hasta ocho
textos no vacíos de 500 caracteres por lista. También se puede añadir a una captura de nota:
así guardas el aprendizaje y su avance con un solo evento. No genera una segunda nota.
La clasificación conserva estos campos cuando devuelve un candidato `journal-only`.

Los seis campos básicos del diario siguen funcionando. Conserva exactamente el JSON y el
`event_id` para reintentar: el mismo evento no se duplica y un contenido diferente exige un
evento nuevo. Un reintento después de medianoche conserva el día original.

## Consultarlo

MCP: `read_journal` acepta `start_date`, `end_date`, `project`, `offset` y `max_chars`.
Las fechas son inclusivas, en formato YYYY-MM-DD. Por defecto devuelve los últimos siete días
según la zona horaria del despliegue; una consulta admite hasta 31 días, con avances recientes
primero. Se puede filtrar por un proyecto exacto.

```powershell
shiori --config '<config-personal.json>' journal --project ejemplo
shiori --config '<config-personal.json>' journal --start-date 2026-10-20 --end-date 2026-10-27
# Instalación de trabajo gestionada: usa su propia memoria.
.\shiori.cmd run journal --project ejemplo
```

El resultado está limitado a 8000 caracteres JSON por defecto (entre 1000 y 20000).
Sigue `next_offset` para más entradas; si una entrada por sí sola excede el presupuesto,
`content_truncated` indica que solo recibiste un fragmento. Para leerla entera, abre ese día
en el visor. Revisa `errors` y `truncated` antes de afirmar que tienes todo el periodo.
`error_count` conserva el número de días con problemas aunque el presupuesto recorte los detalles.
Las entradas antiguas se leen, pero quedan fuera del filtro por proyecto si no tenían ese dato.
Una captura pendiente de confirmar no aparece como avance completado.

Los diarios siguen en `journal/AÑO/AAAA-MM-DD.md`, se ven en el visor y se incluyen en los
backups/restauraciones actuales. La importación agregativa de notas no mezcla diarios de otro
despliegue. La búsqueda de conocimiento y el aprendizaje de skills siguen usando notas,
no convierten automáticamente estos avances en lecciones verificadas.

La captura depende de que el agente siga la skill durante la sesión; no se instala un servicio
que registre todo. Guarda resultados revisados, sin conversaciones ni logs en bruto. Cada
perfil usa su propio servidor: la memoria de trabajo no se manda al perfil personal.
Para usar los campos y la consulta nuevos hace falta actualizar Shiori y reiniciar el MCP;
un servidor antiguo puede seguir usando el resumen de seis campos.

## Verlo y mantener los pendientes

Abre **Diario** en el visor. Verás avances agrupados por actividad, con su historial desplegable,
el proyecto y el periodo. En escritorio, los pendientes están al lado; en móvil y tablet, cambia
entre **Avances** y **Pendientes**. Los temas Claro, Oscuro y Café Latte siguen disponibles.
**Abrir día completo** lleva al lector con todo el texto, sin los metadatos internos.

El periodo filtra los avances. Los pendientes se calculan desde todo el historial conservado del
proyecto, de modo que uno antiguo no desaparezca al cambiar de semana. El selector permite ver
abiertos/bloqueados o todos los estados. Puedes crear un pendiente, cambiar su estado, reabrirlo
y consultar sus cambios. Escribe un slug de proyecto nuevo o elige uno de las sugerencias.

Un pendiente tiene un ID estable dentro de su proyecto y una versión. Ejemplo sintético para
añadir al candidato anterior:

```json
{
  "activity": "parser",
  "tasks": [
    {
      "id": "comprobar-editor",
      "title": "Comprobar el parser en el editor",
      "status": "open",
      "details": "Usar el documento de ejemplo.",
      "version": 0
    }
  ]
}
```

Esto es un fragmento: incluye también los campos básicos de captura y un `project` explícito.
Se admiten hasta ocho cambios de pendientes por evento. Cada uno requiere los cinco campos
mostrados; `details` puede estar vacío. Estados: `open`, `blocked`, `done` y `discarded`.
Una creación usa versión 0 y devuelve estado actual versión 1 al consultarlo. Para cambiarla,
envía su versión actual y un evento nuevo; el ID se conserva. Dos sesiones con la misma versión
no pueden sobrescribirse: una guardará y la otra deberá releer y reconciliar el cambio.
Un reintento idéntico sigue siendo seguro, incluso tras una interrupción o medianoche.

MCP: `read_journal(view="tasks", project="ejemplo", offset=0)` devuelve los estados actuales,
incluidos los cerrados, y su historial. Sigue `next_offset`; revisa `history_truncated` y
`error_count`. Esta vista exige proyecto y no acepta fechas: su presupuesto JSON es 2000–20000.
Las sugerencias de `progress.next_steps` siguen siendo texto histórico; no se convierten
automáticamente en pendientes ni se consideran resueltas por haber pasado tiempo.

## Agrupar avances y corregir capturas

Usa el mismo `activity` para una actividad que continúa. Sus capturas aparecen juntas, con la
más reciente delante y las anteriores desplegables. Un avance `journal-only` con idénticos
título, resumen y progreso para esa actividad el mismo día se omite como `unchanged-activity`.
Un resultado nuevo, un cambio de pendiente o un avance de otro día sí se guarda. Las capturas
de notas conservan su comportamiento: no se descarta una actualización de conocimiento por
tener el mismo resumen de diario.

Para corregir una captura, añade `supersedes: ["evento-original"]` y un `change_reason` que explique
qué cambia. Los enlaces deben apuntar a eventos confirmados, aún no sustituidos, del mismo
proyecto; admite hasta ocho para agrupar expresamente varias capturas. El original permanece.
En el visor, **Corregir o agrupar esta captura** prepara una corrección enlazada y permite indicar
una actividad compartida. La vista muestra solo una parte del progreso muy largo; en ese caso
hay que abrir el día completo y preparar la corrección desde MCP/CLI para conservar los detalles.

Corregir el texto no deshace los estados de pendientes que se registraron allí. Si también había
un estado incorrecto, haz un cambio explícito con su versión actual. Así ambos historiales siguen
siendo claros. Las skills agrupan de forma deliberada, sin asumir que dos frases parecidas
representan el mismo trabajo.

## Retomar un proyecto

El botón **Retomar proyecto** y MCP `resume_project(project="ejemplo")` preparan el último
resultado efectivo, los pendientes activos con versiones y las sugerencias/comprobaciones/
decisiones de esa captura. Una corrección sustituye el resultado usado; una simple actualización
de estado no oculta el último resultado de trabajo. Los pendientes tienen prioridad en el
presupuesto, para que un relato largo no se lleve todo el espacio.

```powershell
shiori --config '<config-personal.json>' project-resume ejemplo
shiori --config '<config-personal.json>' journal --view tasks --project ejemplo
.\shiori.cmd run project-resume ejemplo
```

El paquete de reanudación admite 2000–20000 caracteres, por defecto 8000. Revisa `tasks_omitted`,
`truncated` y `error_count`; consulta la vista paginada de pendientes si falta alguno. Es estado
registrado, no una comprobación independiente. El agente consulta también las notas canónicas
y el entorno actual antes de actuar. Ninguna consulta ejecuta los comandos recordados.

## Compatibilidad y límites

No hay migración del ledger ni otra base de datos. Los nuevos eventos añaden un comentario con
datos estructurados al Markdown y mantienen texto legible. Los backups/restauraciones existentes
lo conservan; los eventos antiguos de seis campos y el progreso anterior siguen siendo legibles.
No se reconstruyen pendientes a partir de texto libre. Las versiones antiguas pueden leer el
Markdown, pero no mantienen estos estados: actualiza el programa y reinicia MCP antes de enviar
campos nuevos. Una captura de resumen en un servidor antiguo no equivale a actualizar un pendiente.

La proyección del historial tiene límites locales: hasta 2000 días, 5000 entradas y 16 MiB leídos,
con un máximo de 2 MiB por día. Si falta un archivo, hay datos inconsistentes o se alcanza un
límite, se señala lectura incompleta. Los cambios de seguimiento se rechazan hasta recuperar
un historial íntegro; no se inventan estados. Una captura interrumpida también impide que otro
cambio de seguimiento la adelante: reintenta su JSON original, sin reconstruirlo de fragmentos.
Las vistas acotan páginas y el historial visible; los originales permanecen en los diarios.

El visor permite añadir eventos de diario manuales, con la misma protección de origen y URL
privada de sesión que sus otras escrituras. Los documentos y notas no se editan desde ese
endpoint. Guarda solo material permitido en el perfil seleccionado; el perfil de trabajo sigue
siendo una memoria separada.
