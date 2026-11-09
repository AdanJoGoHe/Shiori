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

### Abrir una sesión con tiempo limitado

Con el registro del perfil desactivado, elige un ID nuevo y permite solo las acciones que te interesan.
Sin `--apply`, el CLI muestra la política propuesta. Usa `--apply` para empezar.

```powershell
.\shiori.cmd run agent-log start-session sesion-demo --agent augment-jetbrains --project laboratorio --kind check --kind command-executed --minutes 90 --apply
.\shiori.cmd run agent-log status
.\shiori.cmd run agent-log list --session sesion-demo
```

Comparte el ID con el agente que hará el trabajo. El registro exige coincidencia de sesión,
agente, proyecto y tipo de acción. Si omites `--project`, admite acciones sin proyecto.
Si omites `--kind`, admite solo comprobaciones. Puedes repetirlo para elegir varios tipos.
La duración es de 120 minutos por defecto y admite de 1 a 480. El plazo empieza al aplicar.
El visor indica cuándo caduca y permite **Cerrar sesión**. También puedes usar
`agent-log disable --apply`. Después del cierre o de la caducidad, el historial sigue disponible.
Cierra la sesión anterior antes de abrir otra o activar el registro para todo el perfil.

La sesión solo admite acciones que el agente revisó y envió localmente. Sus identificadores son
filtros de acciones informadas. Guarda un resumen corto, usa `context: ""` y reserva el comando
literal para los tipos `command-*`. Los enlaces y visitas requieren una URL revisada sin query ni
fragmento. Revisa también la ruta y el texto libre para retirar datos sensibles. Las rutas de
archivo se admiten en cambios de archivo. Los vínculos internos al catálogo o al Diario siguen
disponibles para cualquier tipo. Ante un bloqueo, revisa la causa antes de preparar otro envío.
Un checkpoint puede completar después de la caducidad una acción que ya reservó. Cerrar la
sesión impide guardar esa acción si el registro aún no se había escrito. El checkpoint del
Diario y de la ficha sigue siendo recuperable.

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

MCP anuncia `record_agent_action` y `read_agent_log`. `memory_status.agent_log` muestra
disponibilidad y activación, y en local incluye `session_policy` si hay una sesión configurada.
Reconecta MCP después de actualizar para cargar los cambios. El CLI configurado es el respaldo.

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

Se guarda en `state/agent-log.json`, dentro del despliegue. Límites: 10000 eventos,
8 MB por almacén, 12000 bytes por evento, resumen de 600 caracteres, comando de 4000 y contexto
de 1000. Al llenarse se rechazan escrituras nuevas; no se eliminan eventos silenciosamente.
La validación detecta patrones comunes de secretos y limita los campos, pero la revisión del
agente sigue siendo necesaria: no es un detector semántico ni una auditoría inviolable.

Backup/restauración incluye configuración, eventos y correcciones del log; se valida alcance,
esquema, tamaño y hashes. La restauración crea un destino nuevo y pausado. Si había una sesión
configurada, conserva sus eventos y requiere una nueva activación local tras restaurar.
La importación agregativa de notas excluye el log.

La sesión configurada usa esquema 2 para impedir que una versión antigua ignore sus restricciones.
Cierra la sesión para volver al esquema 1 antes de recuperar una versión que solo lea ese formato.
Una actualización gestionada comprueba que la versión candidata pueda leer los datos presentes.

No hay borrado por antigüedad. Para retirar todo el log, detén sus procesos y elimina manualmente
solo `state/agent-log.json` del perfil elegido, tras revisar qué necesitas conservar. Esto reinicia
activación e IDs de ese registro; las notas y el diario siguen aparte. Pueden quedar copias en
backups antiguos: desactivar o retirar el archivo no las borra. Mantén esos respaldos privados.
