# CLI para trabajar con agentes

Estas mejoras se preparan para alpha.6 y no están en la release publicada alpha.5. Para usarlas
hace falta instalar una versión que las incluya y reiniciar la conexión MCP.

En una instalación gestionada de trabajo, usa su propio `shiori.cmd`. En personal, usa el
Python y el `--config` aprobados de la conexión MCP, como se explica en la guía de actualización.
Los ejemplos siguientes usan una memoria ficticia de trabajo y se ejecutan en su carpeta.

## Ayuda, búsqueda y lectura

```powershell
.\shiori.cmd run --help
.\shiori.cmd run search --help
.\shiori.cmd run search --id ejemplo-comando
.\shiori.cmd run search --tag kubernetes --tag windows
.\shiori.cmd run read ejemplo-comando --format text
```

La ayuda termina con código 0 y enumera los comandos realmente permitidos. Un comando desconocido
o ausente muestra el uso y termina con error; eso es distinto de un manifiesto o intérprete roto.
El modo gestionado sigue rechazando un cambio de `--config`.

`search --id` devuelve `found`, `id` y `notes`. Si no existe, `found` es `false`; una nota registrada
pero ilegible produce error, no una falsa ausencia. No se combina ID con texto u otros filtros.
Desde MCP, `search_memory(note_id="ejemplo-comando")` tiene el mismo comportamiento.

`--tag` ya filtraba por etiqueta exacta normalizada. Ahora no necesitas añadir una consulta de
texto vacía para buscar solo por etiquetas. Repetirlo exige todas las etiquetas (AND).
La palabra en el cuerpo o una etiqueta `kubernetes-prod` no cumple `--tag kubernetes`.
En MCP puedes omitir `query` y pasar `filters={"tags": ["kubernetes", "windows"]}`.

`read` conserva JSON por defecto. `--format text` imprime el Markdown UTF-8 con sus saltos de
línea reales y sin ejecutarlo. Los errores van por stderr y no se mezclan con una nota parcial.

## Clasificar y guardar sin reenviar el JSON equivocado

Guarda un archivo privado `propuesta.json` con el candidato y sus declaraciones revisadas:

```json
{
  "candidate": {
    "scope": "work",
    "id": "ejemplo-comando",
    "event_id": "ejemplo-comando-001",
    "title": "Consultar la versión de Git",
    "type": "command",
    "status": "unverified",
    "source_agent": "manual",
    "body": "Ejemplo ficticio: git --version. Requiere Git en PATH.",
    "evidence": "Todavía no comprobado en el entorno de destino.",
    "summary": "Preparado un ejemplo para revisar.",
    "tags": ["command"],
    "project": "ejemplo"
  },
  "assessment": {
    "material": "corporate",
    "reusable": true,
    "meaningful": true,
    "evidence_kind": "none"
  }
}
```

Las declaraciones las revisa el agente; no son permisos ni una detección automática de privacidad.
En personal, el candidato y `material` deben ser `personal` y solo contener material personal.

```powershell
# Busca el ID y notas relacionadas; clasifica y muestra el candidato, sin guardarlo.
.\shiori.cmd run note --request-file '.\propuesta.json'

# Repite el flujo y guarda únicamente el candidato devuelto por la clasificación.
.\shiori.cmd run note --request-file '.\propuesta.json' --apply
```

`skip` y `deny` no guardan nada. La respuesta incluye `applied` y, si se intentó guardar,
el resultado real en `capture`. Un conflicto o una decisión deny termina con error. Las notas
parecidas se muestran como contexto y no cambian automáticamente el ID de destino.

En una actualización, `classify`/`classify_memory` y `note` incluyen `diff` con texto unificado,
hash `base_revision`, `unchanged` y `truncated`. Se comparan contenido y metadatos editables,
conservando lo omitido; los timestamps generados se excluyen. El diff se limita a 12000 caracteres.
Si está recortado, revisa también la nota y el candidato completos.

Para mantener la revisión entre una vista previa y otro proceso de aplicación, pasa el hash
devuelto con `note ... --apply --expect-revision '<hash>'`. Para exigir que siga siendo nueva,
usa `--expect-revision absent`. Sin esa opción, `--apply` clasifica y captura contra el estado
actual bajo el mismo bloqueo. Nunca aplica un diff calculado antes de ese bloqueo.

## JSON por stdin y reintentos

`classify --request-file -`, `capture --event-file -` y `note --request-file -` leen JSON UTF-8
por stdin. Los dos primeros mantienen sus formatos distintos: classify recibe el wrapper con
`candidate` y `assessment`; capture recibe únicamente el candidato que devolvió classify.
La entrada y el archivo admiten hasta 40000 bytes. JSON vacío, inválido o de más tamaño se rechaza.
Una terminal interactiva sin tubería recibe una explicación en vez de quedar esperando.

En PowerShell 7, por ejemplo:

```powershell
Get-Content -Raw -Encoding utf8 '.\propuesta.json' | .\shiori.cmd run note --request-file -
```

En Windows PowerShell 5.1 hay que configurar la codificación UTF-8 de la tubería antes de pasar
acentos o emojis a un proceso externo; usar el archivo evita ese problema.

Los archivos suministrados no se borran ni sobrescriben. Conserva el JSON exacto del candidato
enviado y su `event_id` en una ubicación privada, fuera del código y de logs. La identidad del
reintento usa el JSON con claves ordenadas, no los espacios externos del archivo: no alteres
los textos ni valores. Un evento con un candidato distinto se rechaza.
Si existe una captura pendiente, reintenta su candidato original; no lo reconstruyas de un diff
o un fragmento ni inventes otro ID. Una reanudación de ese evento exacto tiene prioridad sobre
un hash de vista previa que pudo cambiar durante la escritura interrumpida.

## Si MCP no responde

Un error de validación de una herramienta es distinto de un fallo de arranque/transporte o
un timeout. Shiori añade pistas de respaldo a los fallos de proceso que controla, siempre en
stderr: stdout de stdio queda para el protocolo. Si el proceso ni se ejecuta, el launcher y la
skill indican el mismo camino; no se puede modificar desde Shiori el error de un host externo.

En el mismo despliegue gestionado de trabajo:

```powershell
.\shiori.cmd run status
.\shiori.cmd run doctor --catalog
.\shiori.cmd run pending
```

En personal usa el intérprete/configuración aprobados del MCP con esos mismos subcomandos.
No elijas otra memoria por la carpeta del repo y no uses personal como respaldo de trabajo.
Si también falla la CLI, comprueba el manifiesto, el intérprete activo y la configuración de esa
instalación. La disponibilidad de la CLI no prueba que el host haya reconectado MCP.

Un timeout de escritura no demuestra que no se guardara: conserva candidato/ID, consulta el
estado y reintenta solo el mismo evento cuando proceda. No recaptures con otro ID ni reinicies
procesos automáticamente. Una caída de memoria no debe bloquear la tarea principal del usuario.
