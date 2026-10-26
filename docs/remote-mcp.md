# Servidor central y MCP por HTTP — base inicial

El mismo almacén personal puede atender varios clientes MCP mediante el comando optativo
`serve-http`. Las credenciales distinguen consulta y captura. La conexión stdio y el visor
local siguen funcionando como antes; instalar/actualizar el paquete no inicia este servicio.

El despliegue se divide en estas entregas:

| Tarea | Alcance |
|---|---|
| #76 | Endpoint HTTP autenticado, permisos y pruebas locales: este incremento |
| #77 | Host exacto para proxy y guía HTTPS preparados; red/dispositivos pendientes |
| #79 | Registro/actualización/desinstalación de cliente remoto Codex: pendiente |
| #80 | Aceptación real desde dos dispositivos: pendiente |

**Esta base solo escucha en127.0.0.1.** Otro PC necesita un proxy HTTPS privado aprobado.
La [guía de acceso privado](private-ingress.md) prepara Tailscale Serve y `--proxy-host`;
no activa la red ni sustituye la aceptación desde dos dispositivos.
No abras el puerto en el router ni publiques el visor para suplir las tareas pendientes.
La memoria personal sigue separada del material corporativo; usar un equipo del trabajo no
autoriza capturar datos de la empresa. Su conectividad debe estar permitida por su política.
El propietario ha elegido empezar en local y dejar la activación remota para más adelante.
Para trasladar notas sin red central, usa [exportación/importación agregativa](memory-transfer.md).

## Preparar una prueba controlada

Usa el Python/archivo de configuración aprobados del despliegue. Las rutas que siguen son
placeholders: prepara una carpeta privada fuera de Git, carpetas compartidas y fuentes Markdown.
No vuelvas a inicializar el vault para probar la conexión. El JSON de credenciales puede vivir
en el estado privado, pero nunca dentro del vault o de `documentation_roots`.

El archivo requiere exactamente este esquema; el hash ilustrativo no habilita una credencial:

```json
{
  "schema_version": 1,
  "clients": [
    {
      "id": "portatil-consulta",
      "token_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "permission": "read",
      "expires_at": 1893456000
    }
  ]
}
```

`permission` acepta `read` o `write`; el segundo incluye lectura. `expires_at` es un entero Unix
en segundos y debe estar en el futuro. Usa vencimientos cortos y un token aleatorio distinto por
equipo. Hasta64 clientes y64KB por registro; IDs/hashes duplicados, campos extra o tipos erróneos
se rechazan. Un registro vacío es válido y deja todos los clientes sin acceso.

En una terminal privada puedes generar un token sin imprimirlo y obtener su hash:

```powershell
$RemoteToken = & $BrainPython -c "import secrets; print(secrets.token_urlsafe(32))"
$RemoteDigest = $RemoteToken | & $BrainPython -c "import sys,hashlib; print(hashlib.sha256(sys.stdin.read().strip().encode('ascii')).hexdigest())"
$ExpiresAt = [DateTimeOffset]::UtcNow.AddDays(30).ToUnixTimeSeconds()
```

Pon el hash en el registro; el cliente necesita el token original, no el hash. El servidor no
lo guarda en ese archivo. Transfiere credenciales solo por un canal privado aprobado; no las
pegues en incidencias, recuerdos, URLs o argumentos de comandos. Crear el JSON no aplica ACL:
restringe su lectura/escritura al propietario y administradores, igual que el estado privado.
Quien puede cambiar el registro puede conceder acceso. No lo edites desde una carpeta publicada.

Arranque explícito, desde una terminal que permanecerá abierta:

```powershell
$RegistryPath = '<archivo-absoluto-privado-de-credenciales.json>'
& $BrainPython -m second_brain.cli --config $BrainConfig serve-http --credentials-file $RegistryPath --port 8794
```

El endpoint es `http://127.0.0.1:8794/mcp`; Ctrl+C lo detiene. No hay bandera para escuchar en
otras interfaces ni modo anónimo. Una credencial/configuración inválida impide arrancar; el
registro se valida antes de que el núcleo pueda crear raíces. Un puerto ocupado se rechaza,
sin detener a su ocupante. Esta fase no instala un servicio ni reinicia MCP.

Para probar manualmente un cliente del SDK ya instalado, con el token solo en su entorno:

```powershell
$env:SECOND_BRAIN_REMOTE_TOKEN = $RemoteToken
@'
import asyncio
import os
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8794/mcp", auth=os.environ["SECOND_BRAIN_REMOTE_TOKEN"]) as client:
        print((await client.call_tool("memory_status", {})).data)

asyncio.run(main())
'@ | & $BrainPython -
Remove-Item Env:SECOND_BRAIN_REMOTE_TOKEN
Remove-Variable RemoteToken
```

No sustituye una prueba de Codex ni conecta otro PC. La futura instalación remota usará una URL
HTTPS privada y una referencia a la variable de credencial, con su propia skill y sin copiar
vault/estado/proveedor. [OpenAI Docs sobre MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
describe `url` y `bearer_token_env_var`; el instalador de este proyecto todavía registra stdio.
No sobrescribas la entrada gestionada actual para ensayar la fase remota.

## Permisos, revocación y límites

- Consulta anuncia siete herramientas: contexto, búsqueda, lectura, clasificación, catálogo,
  pendientes y estado. Captura se anuncia solo a escritores. Llamarla directamente con credencial
  de lectura también se rechaza. Una herramienta futura queda denegada hasta revisión explícita.
- Los permisos no aíslan documentos por equipo: cada lector ve la memoria personal autorizada
  del mismo despliegue. No hay múltiples usuarios/tenants ni memoria corporativa habilitada.
- El registro se vuelve a leer en cada petición. Eliminar una entrada, cambiar su hash/permiso o
  caducarla afecta las peticiones siguientes, incluso de clientes ya conectados. No cancela una
  operación que ya estaba autorizada y en curso. Registro ausente/corrupto/enlazado deniega acceso;
  corregirlo permite nuevas conexiones. Al actualizarlo, usa reemplazo atómico revisado o detén
  el servicio para evitar un intervalo de JSON incompleto.
- El transporte es Streamable HTTP sin sesión persistente y con respuestas JSON. Cada petición
  autentica de nuevo. La idempotencia del núcleo persiste entre clientes/reconexiones; no depende
  de una sesión HTTP. No hay cola offline, réplica local o sincronización automática.
- La búsqueda HTTP usa el almacén canónico y no lanza reindexados por petición. El estado permite
  la comprobación explícita y acotada del proveedor; el funcionamiento stdio no cambia.
- Se validan Host, Origin y peticiones: sin CORS, orígenes de navegador rechazados, sin confiar en
  cabeceras de proxy. `--proxy-host` permite además una autoridad HTTPS exacta, sin autenticar
  por cabeceras reenviadas ni cambiar el bind. No es un endpoint para JavaScript en páginas web. Peticiones POST de hasta
  64KB, lectura de cuerpo acotada a10s y límite de16 conexiones; framing duplicado/chunked, tokens
  en query y cabeceras Authorization duplicadas se rechazan. Una captura próxima al máximo Unicode
  puede exceder64KB; reduce el contenido y no dividas/reutilices eventos para eludir validaciones.
- Sin logs de acceso ni cuerpos/tokens. Errores de herramienta se ocultan; captura inválida
  devuelve `capture-failed`. La CLI usa logging crítico para evitar trazas con entradas privadas;
  no ofrece auditoría operativa completa. Un fallo de arranque informa un mensaje genérico.
- Esto usa credenciales bearer provisionadas privadamente, **no un servidor OAuth ni descubrimiento
  de login**. No se presenta como servicio público listo para producción. La guía y las pruebas
  TLS sintéticas preparan #77; falta aprobar/verificar el ingress real antes de usar otra máquina.

Si el PC duerme, se apaga o pierde red, los clientes pierden disponibilidad. Mantén copias privadas
de la memoria y del registro/credenciales por separado: `backup` de Shiori incluye conocimiento
y estado de captura/anotaciones, pero no este registro ni secretos de clientes. Pausar capturas
impide guardar también por HTTP; las consultas siguen disponibles.

## Evidencia local — 2026-10-23

`tests/test_remote.py` realiza conexiones TCP/HTTP reales con el SDK contra un servidor sintético:
lectores/escritores, llamadas directas denegadas, todos los grupos de herramientas, captura y replay,
dos escritores concurrentes, reconexión, revocación/caducidad/corrupción, límites de cuerpo y framing,
Host/Origin, rechazo de trabajo y errores sin datos privados. Un proceso CLI real comprueba también
la política de logs. Los tests ASGI directos complementan los límites de framing/timeout, no
sustituyen las conexiones reales. Los fallos de configuración no inicializan un almacén nuevo.

Las pruebas son locales y sintéticas; no se modificó configuración/vault/ACL del propietario,
se expuso un servicio de red ni se despachó Actions. Falta #77–#80 y la aceptación física desde
otro equipo. Referencias de implementación:
[FastMCP HTTP](https://gofastmcp.com/deployment/running-server),
[verificación de tokens](https://gofastmcp.com/servers/auth/token-verification).
