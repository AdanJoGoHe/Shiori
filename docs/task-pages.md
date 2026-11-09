# Tareas por código

Una ficha reúne el contexto de una incidencia como `DEMO-1234`: título, cuerpo Markdown,
estado, proyecto opcional, etiquetas y vínculos. El código se normaliza a mayúsculas y es estable.
Los ejemplos de esta guía son ficticios. Los datos se guardan solo en el despliegue configurado.

## En el visor

1. Abre **Tareas → Nueva tarea**, completa código/título/notas y guarda.
2. La ficha se abre en el lector existente. Selecciona o busca texto exacto para marcarlo,
   elegir color/categorías y poner título o descripción a la marca.
3. Desde cualquier lector, **Vincular a una tarea** acepta un código exacto y permite elegir
   la página completa o una marca guardada. Puedes vincular documentación, notas, días de diario
   y otras fichas. El vínculo conserva el ID lógico, nunca la URL temporal del visor.
4. En una ficha, despliega **Vínculos de esta tarea** para abrir/quitar referencias o añadir una
   URL web. No se descarga el destino. Un vínculo ausente se conserva como no disponible.
5. **Editar tarea** modifica las notas y metadatos. Los códigos no se renombran. Para apartar una
   tarea terminada usa su estado y los filtros; esta versión no incluye borrado de fichas.

La búsqueda de Tareas reutiliza términos, proyecto, etiquetas exactas y estados del catálogo.
El texto marcado de las fichas aparece en Fragmentos junto al de otras fuentes. Desde Tareas,
seleccionar **Fragmentos marcados** en **Buscar en** limita esa vista a marcas de fichas. Abrir una referencia
a una marca usa su ancla existente; si el texto cambió, se aplica la reparación normal, sin elegir
automáticamente otro texto parecido. Cambiar metadatos o vínculos no altera el cuerpo ni sus anclas.
Editar título/cuerpo sí puede requerir reparar marcas. Se conserva la última revisión de la ficha,
con versión para detectar conflictos; no hay un historial completo de ediciones ni deshacer del cuerpo.
Los pendientes del Diario mantienen su historial independiente.

## Consulta desde el CLI y agentes

```powershell
shiori --config <config-del-perfil> task list
shiori --config <config-del-perfil> task read DEMO-1234
shiori --config <config-del-perfil> task read DEMO-1234 --format text
shiori --config <config-del-perfil> catalog --kind task
```

En una instalación gestionada: `shiori.cmd run task read DEMO-1234 --format text`.
`list` pagina metadatos de veinte en veinte mediante `--offset`. `read` devuelve la ficha exacta;
no busca códigos parecidos. El formato texto devuelve el cuerpo Markdown con su título; JSON incluye
los vínculos y metadatos. El contenido de las fichas se trata como contexto, separado de las notas
canónicas y de los candidatos a skills aprendidas.

## Edición con MCP local

- `get_task_page(issue_key)` devuelve la ficha exacta, con su cuerpo, vínculos y versión.
- `list_task_pages(filters, offset)` devuelve veinte fichas por página, ordenadas por código,
  con metadatos y versión. Filtra por `status`, `project` y `tags` exactas. Para paginar, pasa
  `next_offset` de la respuesta como `offset` de la siguiente llamada.
- `save_task_page(issue_key, expected_version, changes, event_id)` aplica solo los campos enviados.
  Usa la versión `0` y un título al crear. En una ficha existente, usa la versión leída.
  `changes` admite `title`, `body`, `status`, `project`, `tags` y `links`. Las listas enviadas
  reemplazan ese campo completo. Cada vínculo contiene `target`, `label` y `annotation_id`
  (ID de marca o `null`).

Ejemplo de argumentos para cambiar el estado tras leer la versión `3`:

```json
{
  "issue_key": "DEMO-1234",
  "expected_version": 3,
  "changes": {"status": "in-progress"},
  "event_id": "demo-1234-start-01"
}
```

Si se pierde la respuesta, reenvía los mismos argumentos con el mismo `event_id`. La respuesta
`duplicate` indica la versión que se guardó entonces. Para ver la versión actual usa
`get_task_page`. Ante `version-mismatch`, lee la ficha, revisa el cambio y usa un evento nuevo
para la edición revisada. Un evento ya registrado con argumentos distintos da `event-id-reused`.
Un cambio sin diferencias registra el evento con estado `unchanged` y conserva la versión.

Las herramientas operan por stdio en el perfil configurado. Pausar la memoria bloquea nuevas
ediciones del agente, con las lecturas y los reintentos ya registrados disponibles. La ficha
concentra el estado actual de la incidencia. El Diario conserva el avance cronológico.

## Persistencia y límites

- Almacén privado `state/task-pages.json` con ámbito explícito. Lecturas y escrituras vuelven
  a comprobar la identidad del despliegue; el trabajo no se reenvía al perfil personal.
- Hasta 1000 fichas y 8 MB por almacén; cuerpo de 12000 caracteres y hasta cuarenta vínculos por
  ficha. Los códigos tienen prefijo alfanumérico, guion y parte numérica; los títulos son obligatorios.
- Escritura JSON atómica bajo bloqueo y versión optimista por ficha. Reintentar el mismo contenido
  no crea duplicados. Un conflicto conserva el texto del formulario; revisa la ficha actual antes
  de volver a guardarlo. No es sincronización entre servidores.
- Referencias internas validadas contra el catálogo autorizado y marcas existentes al añadirlas.
  El visor vuelve a comprobar su disponibilidad al abrir la ficha. Las rutas arbitrarias,
  esquemas activos y URLs con credenciales no se aceptan; la detección de posibles secretos es
  adicional y no sustituye la revisión del contenido antes de guardarlo.
- No se guardan imágenes remotas ni se ejecutan comandos. El HTML del Markdown permanece inerte.
  Pausar capturas no desactiva la edición manual del visor, igual que ocurre con sus anotaciones.

## Backup, restauración y actualizaciones

El backup normal incluye el almacén completo y las anotaciones, con hash, validación de esquema,
límites y ámbito. Restore sigue creando un despliegue nuevo y pausado; comprueba sus datos antes
de utilizarlo. Las referencias a documentación necesitan las mismas fuentes aprobadas: guardar
el vínculo no copia sus archivos. La importación agregativa de notas declara las fichas fuera
de su alcance y no las mezcla entre perfiles.

Se siguen leyendo las fichas del esquema 1. El primer evento MCP confirmado guarda la ficha y
su recibo en una única escritura atómica con esquema 2. El recibo conserva el identificador, la
huella y la versión aplicada. El almacén admite hasta 10 000 recibos por perfil, sin expulsar
eventos antiguos. También se aplica el límite total de 8 MB.

Al cambiar de versión desde el runtime actualizado, si existe el almacén se exige que el intérprete
candidato pueda leerlo antes de activar el software. Alpha.7 entiende el esquema 1. Una vez
registrado un evento MCP se requiere una versión compatible con el esquema 2.
Una versión incompatible se rechaza conservando la activa. Esto no puede proteger un arranque
manual con software antiguo ni una copia incompleta de los datos. Conserva un backup compatible.

## Validación reproducible

```powershell
python -m pytest tests/test_task_pages.py -q
python scripts/check-workspace-workflow.py --task-pages
```

El recorrido de navegador requiere Node/Playwright. Crea dos perfiles temporales con documentación
y marcas ficticias: crea una ficha, marca un comando, vincula web/página/fragmento, abre su ubicación,
comprueba Atrás, conserva un borrador ante un conflicto, recarga y quita un vínculo. Revisa tres
temas, ausencia de peticiones externas y rechazo de IDs de otro perfil. Las pruebas Python cubren
persistencia, catálogo, CLI, límites de referencias, origen HTTP, corrupción, ámbito y recuperación.
La integración real de un IDE y cualquier sincronización externa requieren sus propias pruebas.
