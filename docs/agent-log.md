# Qué hizo el agente

**Agent log** guarda acciones informadas: comandos, comprobaciones, archivos cambiados y enlaces.
El **Diario** cuenta resultados y próximos pasos; las **notas** guardan conocimiento. Registrar una
acción no crea una nota ni un avance y no demuestra por sí mismo que su resultado sea correcto.

## Activarlo y consultarlo

Abre Agent log y pulsa **Activar registro** en el perfil seleccionado. También puedes preparar
la activación desde el CLI gestionado de esa misma instalación:

```powershell
.\shiori.cmd run agent-log status
.\shiori.cmd run agent-log enable
.\shiori.cmd run agent-log enable --apply
.\shiori.cmd run agent-log list --project laboratorio --session sesion-demo
.\shiori.cmd run agent-log list "kubectl" --kind command-executed
.\shiori.cmd run agent-log read accion-demo
.\shiori.cmd run agent-log disable --apply
```

Sin `--apply`, activar/desactivar solo muestra la propuesta. Desactivar conserva lo anterior;
la pausa de la memoria bloquea acciones nuevas. El registro empieza desactivado en cada perfil.
Personal y trabajo tienen almacenes separados. La skill registra acciones significativas cuando
la función está disponible y activa; depende de que el agente siga esas instrucciones. No hay
captura automática de herramientas, conversaciones ni historial del navegador.

El visor permite Hoy/Ayer o cualquier periodo histórico de hasta 31 días, proyecto, sesión,
agente, acción y resultado. El buscador visible consulta resumen, comando, contexto y referencias;
los términos se combinan con Y, sin distinguir mayúsculas. Los filtros de identidad son exactos.
Las filas van de más reciente a más antigua, por hora de la acción, usando la zona del despliegue.
Si esa hora no se conoce, se usa la de registro y se indica. Una llegada tardía con hora conocida
aparece en el día en que ocurrió. Las páginas están acotadas: sigue Siguiente para continuar.

Abre **Ver acción** para el comando completo, contexto y referencias. **Copiar comando** copia el
texto exacto, también si la fila está abreviada. Las URLs se abren por clic; guardarlas no descarga
su contenido. Las rutas de archivos son texto para copiar. Las páginas y avances se abren solo
si siguen dentro de las fuentes autorizadas; una referencia ausente se conserva como no disponible.
Desde el Diario, **Ver acciones asociadas** filtra por el ID del avance. Sin registros no significa
que no se trabajara. Favoritos se incorporará con su propio almacenamiento.

## Registrar desde un agente

MCP anuncia `record_agent_action` y `read_agent_log`. `memory_status.agent_log` permite comprobar
disponibilidad, activación y alcance sin iniciar el proveedor. Un servidor actualizado anuncia
trece herramientas; reinicia la conexión para descubrirlas. El CLI configurado es el respaldo.

Ejemplo ficticio de propuesta, cuyo resultado aún es desconocido:

```json
{
  "schema_version": 1,
  "scope": "work",
  "event_id": "accion-demo",
  "agent": "manual",
  "session": "sesion-demo",
  "project": "laboratorio",
  "occurred_at": null,
  "kind": "command-proposed",
  "outcome": "unknown",
  "summary": "Propuesto consultar los pods del ejemplo",
  "command": "kubectl get pods",
  "context": "Ejemplo sintético; el comando no se ha ejecutado.",
  "references": [],
  "corrects": null,
  "correction_reason": "",
  "coverage": "reported"
}
```

Guarda el JSON revisado en un archivo privado y usa `run agent-log record --event-file evento.json`.
También acepta stdin con `--event-file -`. Conserva el candidato enviado y su ID hasta obtener
`saved` o `duplicate`. Ante un timeout, consulta ese ID: registrar otra vez no vuelve a ejecutar
el comando, pero repetir la acción de origen podría tener efectos. Un candidato distinto con el
mismo ID se rechaza. Un error no devuelve el texto sensible rechazado.

Tipos: `command-proposed`, `command-attempted`, `command-executed`, `check`, `file-changed`,
`link-found`, `page-visited`. Resultados: `success`, `failure`, `cancelled`, `unknown`. Una propuesta
usa `unknown`; un intento con éxito se registra como ejecución. Un timeout no demuestra fallo
ni ausencia de efectos. `occurred_at` es ISO con zona o `null`; el servidor pone `recorded_at`.
`coverage` admite solo `reported`: las integraciones observadas requieren otra entrega validada.

Las referencias son hasta seis objetos `{kind, target, label}`: `url` HTTP(S), `content` con ID
lógico del catálogo, `file` como ruta informada o `journal-event` con ID de un avance confirmado.
Ejemplo: `{"kind":"journal-event","target":"avance-demo","label":"Resultado del día"}`.
Las referencias pueden faltar al consultarlas; no se busca una página parecida automáticamente.
Para corregir, crea otro evento con `corrects` apuntando al último registro de la cadena y
`correction_reason` explicando el cambio. Debe conservar el proyecto; originales y procedencia
permanecen visibles. Corregir el log no cambia notas ni estados de pendientes.

`read_agent_log` acepta texto, filtros exactos, `offset` y `max_chars` (4000–20000, por defecto
8000). Devuelve hasta 20 vistas previas y `next_offset`; usa `event_id` solo para leer el evento
completo. No consultes toda la sesión en el contexto del agente si basta un filtro o ID.

## Conservación y recuperación

Se guarda en `state/agent-log.json`, esquema 1, dentro del despliegue. Límites: 10000 eventos,
8 MB por almacén, 12000 bytes por evento, resumen de 600 caracteres, comando de 4000 y contexto
de 1000. Al llenarse se rechazan escrituras nuevas; no se eliminan eventos silenciosamente.
La validación detecta patrones comunes de secretos y limita los campos, pero la revisión del
agente sigue siendo necesaria: no es un detector semántico ni una auditoría inviolable.

Backup/restauración incluye configuración, eventos y correcciones del log; se valida alcance,
esquema, tamaño y hashes. La restauración crea un destino nuevo y pausado. La importación agregativa
de notas excluye el log. Una actualización gestionada rechaza una versión que no pueda leer el
formato presente antes de activarla. No se modifica una instalación real al publicar código.

No hay borrado por antigüedad. Para retirar todo el log, detén sus procesos y elimina manualmente
solo `state/agent-log.json` del perfil elegido, tras revisar qué necesitas conservar. Esto reinicia
activación e IDs de ese registro; las notas y el diario siguen aparte. Pueden quedar copias en
backups antiguos: desactivar o retirar el archivo no las borra. Mantén esos respaldos privados.
