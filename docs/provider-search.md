# Búsqueda indexada y diagnóstico para agentes

`search_memory` sin filtros intenta usar Basic Memory 0.23.2. El adaptador selecciona el
ejecutable del entorno Python actual: `basic-memory.exe` en Windows y `basic-memory` en Linux.
No busca otro ejecutable en PATH ni resuelve el enlace del Python hacia un entorno base.
Inicialización, comprobación MCP y servidor comparten esta selección y las variables de entorno.

Antes de arrancar procesos, comprueba que el archivo `config.json` del directorio configurado
del proveedor contiene solamente `second-brain-personal`, en modo local y apuntando al mismo
vault que Shiori. No crea, corrige ni importa configuraciones automáticamente.
También desactiva cloud, búsqueda semántica, telemetría y actualización automática en el
entorno del proceso. Una configuración ausente, incompatible, con otro vault/proyecto o modo
cloud deja disponible la consulta canónica y devuelve un diagnóstico de configuración.
El proceso de reindexado y el inicializador descartan overrides ambientales `BASIC_MEMORY_*`
ajenos antes de aplicar su entorno explícito, para no redirigir el proyecto desde la shell.

Cada consulta indexada ejecuta `reindex --search --project second-brain-personal` antes de la
búsqueda MCP, para incluir escrituras externas de Markdown. La fase de reindexado tiene un
límite de 10 segundos; el intento completo desde `search_memory`, de 20 segundos más la
limpieza de procesos. Si se cancela el reindexado, se mata y espera el proceso hijo.
Esto mantiene el diseño actual de un proceso por consulta; no promete una latencia constante
ni reutiliza sesiones del proveedor.

La respuesta del proveedor debe contener un objeto JSON con una lista de hasta cinco resultados,
cada uno con `file_path` de tipo texto. Solo se devuelven IDs presentes en el ledger personal,
y sus cuerpos se leen y validan de nuevo desde los archivos canónicos. Texto, instrucciones,
enlaces o rutas no registradas recibidos del índice no autorizan accesos adicionales.
Los resultados canónicos completan la lista hasta un máximo de cinco notas.

## Cuando falla el índice

La búsqueda devuelve las notas canónicas con `provider: filesystem`,
`index_status: unavailable` y uno de estos códigos `index_reason`:

| Código | Significado |
|---|---|
| `not-configured` | El despliegue no declara directorio para Basic Memory. |
| `invalid-configuration` | No se pudo validar la configuración aislada/local del proveedor. |
| `executable-not-found` | Falta el ejecutable en el entorno del servidor. |
| `reindex-failed` | El proceso de reindexado terminó con un código distinto de cero. |
| `search-failed` | La herramienta MCP del proveedor devolvió error. |
| `invalid-response` | JSON, forma o número de resultados no cumplen el contrato. |
| `timeout` | Se agotó un plazo del intento indexado. |
| `provider-error` | Otro error; no se expone su mensaje original. |

Los códigos no copian consultas, logs, cuerpos ni mensajes privados de excepciones. Los logs
del propio proveedor permanecen bajo su responsabilidad; no se exportan a los resultados.
Una búsqueda indexada correcta devuelve `provider: basic-memory`, incluso si no encontró
resultados indexados y fue necesario completar la lista con la búsqueda canónica.

## Estado observado

`memory_status` añade `index: {status, reason}`. En cada nuevo proceso comienza como
`{status: not-checked, reason: null}`. Una consulta indexada terminada lo cambia a `available`
o `unavailable`; una consulta posterior correcta borra el motivo anterior. Concurrencia:
refleja el último intento que terminó, no necesariamente el último que comenzó.

Es una **observación del proceso**, no un chequeo de salud en vivo. Por defecto, consultar estado no inicia
el proveedor, y reiniciar el MCP pierde esa observación. Las consultas con filtros y
`get_context` continúan usando los archivos canónicos y no cambian el estado del índice.
El `status`/`doctor` de CLI no comparte la observación de un servidor MCP en ejecución.

## Chequeo explícito del proveedor

Para comprobar la respuesta actual de Basic Memory, utiliza el Python/CLI y la configuración
del despliegue elegido:

```powershell
second-brain --config "RUTA_A_CONFIG.json" doctor --provider
```

En MCP, llama a `memory_status` con `check_provider: true`. En ambos casos, el resultado añade
`provider_check` separado del último resultado de búsqueda `index`. La opción por defecto no
arranca el proveedor. El chequeo explícito tampoco cambia la observación `index` del servidor.

Ejecuta `basic-memory status --project second-brain-personal --json --local`, después de las
mismas validaciones de configuración/vault. No ejecuta `reindex` ni modifica notas, diario o
anotaciones; arrancar Basic Memory puede inicializar su base de datos y generar logs propios.
Su comunicación con el proceso tiene un plazo de 20 segundos y la respuesta se limita a 1 MiB;
un fallo/cancelación interrumpe y espera el proceso hijo. El arranque y la limpieza añaden tiempo.

Una respuesta válida devuelve `status: available`, `check: project-status` y `total_files`.
Ese contador representa archivos **observados** por el proveedor, no notas canónicas ni archivos
con búsqueda verificada. No prueba frescura del índice, ranking, coincidencias ni conexión de
Codex. Comprueba una búsqueda real si necesitas verificar esas capacidades.

Un fallo devuelve `status: unavailable`, `check: project-status` y un `reason` acotado:
`not-configured`, `invalid-configuration`, `executable-not-found`, `status-failed`,
`invalid-response`, `timeout` o `provider-error`. No devuelve rutas de archivos observados,
checksums, stdout/stderr ni mensajes privados del proveedor.

`doctor --provider` imprime JSON y termina con código 1 si el proveedor no está disponible,
aunque la validación canónica haya pasado. Sin `--provider`, conserva su comportamiento anterior.
MCP devuelve el diagnóstico como datos para permitir que el agente continúe con recuperación
canónica. Reconecta el MCP para cargar el nuevo parámetro; un proceso anterior puede no admitirlo.

Las pruebas combinan casos sintéticos de fallo/cancelación/recuperación y una búsqueda real
de Basic Memory desde el wheel instalado en un despliegue temporal. La CI repite esa búsqueda
en Windows/Linux, después de registrar/inicializar su proyecto temporal como hace el instalador.
La inicialización en frío no se incluye en esa prueba del plazo de búsqueda; un despliegue aún
sin inicializar puede agotar el plazo y seguir funcionando mediante consulta canónica.
Estas pruebas no sustituyen la aceptación de otros hosts ni modifican el índice personal.
