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
