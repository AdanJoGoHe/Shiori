# Acceso HTTPS privado al MCP central

Preparación del despliegue remoto opcional:
Tailscale Serve termina TLS dentro de una red privada y reenvía únicamente al MCP
`127.0.0.1:8794`. El visor conserva su puerto local independiente.
El servidor exige además una credencial por equipo; pertenecer a la VPN no concede
permiso de lectura o captura. Consulta primero [credenciales y permisos](remote-mcp.md).

```text
Cliente MCP → HTTPS privado :8443 → Tailscale Serve → HTTP loopback :8794/mcp
             red autorizada                         token read/write obligatorio
```

Esta opción requiere confirmación del propietario y conectividad autorizada en cada equipo.
El propietario ha elegido empezar **en local** y conservar el acceso remoto como posibilidad
futura. No hace falta iniciar sesión ni activar esta red para usar [exportación/importación](memory-transfer.md).
No instala Tailscale, inicia sesión, cambia reglas de red ni publica servicios al instalar el
paquete. El equipo gestionado del trabajo necesita autorización para esa VPN y sigue sin
poder aportar material corporativo al despliegue personal.

## Preparación del despliegue real

1. Conecta los dos equipos autorizados a la red privada elegida. En este PC, la inspección
   de solo lectura del 2026-10-23 encontró Tailscale **1.104.2**, estado `NeedsLogin` y
   configuración Serve vacía. Esto no demuestra conectividad entre dispositivos.
2. Revisa MagicDNS, HTTPS y las reglas de acceso en la consola de Tailscale. Autoriza solo
   los dispositivos/usuarios previstos hacia el puerto dedicado **8443**. Las reglas son
   acumulativas: añadir una regla estrecha no elimina permisos de una regla amplia existente.
   Prueba también un dispositivo sin permiso. No copies una política completa que sustituya
   reglas de otros servicios.
3. Antes de habilitar certificados, elige nombres de máquina y red sin información sensible:
   esos nombres aparecen en Certificate Transparency. Serve gestiona emisión/renovación;
   el cliente verifica el certificado y el nombre. No uses `--insecure` ni desactives TLS.
4. Inspecciona el estado existente y conserva una copia privada si ya hay configuración.
   No sobrescribas rutas, puertos o servicios ajenos. Detente si 8443 está ocupado en Serve
   o Funnel. No utilices `serve reset`, que afectaría a otros servicios.

```powershell
$Tailscale = 'C:\Program Files\Tailscale\tailscale.exe'
& $Tailscale status
& $Tailscale serve status
& $Tailscale funnel status
```

Los resultados contienen nombres y direcciones privados: no los adjuntes a issues.
Si no puedes utilizar Tailscale en ambos equipos, hace falta otra VPN/proxy autorizado y
repetir la aceptación de TLS, nombre Host y aislamiento. No abras el MCP HTTP en la LAN.

## Arranque controlado

Usa un paquete que incluya `serve-http --proxy-host` y el Python/configuración del despliegue
aprobado. El registro privado se prepara como indica la guía del servidor central, fuera
de fuentes legibles y Git. No inicialices otro vault ni copies el existente al cliente.

En la primera terminal privada, sustituye el nombre ilustrativo por el DNS exacto del servidor:

```powershell
$ProxyHost = 'servidor.red-ejemplo.ts.net:8443'
& $BrainPython -m second_brain.cli --config $BrainConfig serve-http --credentials-file $RegistryPath --port 8794 --proxy-host $ProxyHost
```

`--proxy-host` permite una sola autoridad DNS exacta con puerto opcional. Sin puerto se
aceptan el nombre y su forma `:443`; con `:8443` se admite solo esa combinación. Rechaza
URLs, rutas, IPs, comodines y puertos inválidos antes de inicializar el almacén. No cambia
el bind `127.0.0.1`, ni activa TLS por sí mismo. No es una prueba de que una petición local
haya llegado a través del proxy: otros procesos del mismo PC pueden enviar ese Host y
siguen necesitando el token. El acceso HTTP loopback directo continúa disponible.

En otra terminal, una vez comprobados los requisitos y el puerto dedicado libre:

```powershell
& $Tailscale serve --https=8443 http://127.0.0.1:8794
```

El comando se mantiene en primer plano. Debe anunciar **Available within your tailnet** y
un único destino `http://127.0.0.1:8794`. La URL MCP será
`https://servidor.red-ejemplo.ts.net:8443/mcp`. Se reenvía la raíz del servicio MCP;
no añadas `--set-path=/mcp`, que cambia la ruta reenviada. Nunca apuntes al visor,
un directorio o el vault. No utilices Funnel: publicaría el servicio en Internet.

Tailscale 1.104.2 conserva Host al reenviar HTTP. El SDK permite el nombre configurado y
la protección propia exige además el puerto exacto; rechaza cualquier Origin, incluso
el mismo origen HTTPS. Ignora
`Forwarded`, `X-Forwarded-*`, identidad y capacidades de Tailscale para autenticar: ninguna
de esas cabeceras sustituye al bearer. No hay CORS ni login de navegador.

## Comprobaciones desde el otro dispositivo

Usa el DNS anunciado, HTTPS y la ruta `/mcp`, sin tokens en la URL. Una petición sin
credencial debe devolver **401**, y una petición con Origin debe devolver **403**:

```powershell
$RemoteUrl = 'https://servidor.red-ejemplo.ts.net:8443/mcp'
curl.exe --connect-timeout 5 --max-time 15 -s -o NUL -w "%{http_code}\n" -H "Content-Type: application/json" -d "{}" $RemoteUrl
curl.exe --connect-timeout 5 --max-time 15 -s -o NUL -w "%{http_code}\n" -H "Content-Type: application/json" -H "Origin: https://example.invalid" -d "{}" $RemoteUrl
```

Un error TLS/DNS o timeout no cuenta como denegación autenticada. No lo soluciones
desactivando la comprobación del certificado. Con token privado en una variable de entorno,
el cliente SDK de la [prueba local](remote-mcp.md) puede usar esta URL HTTPS en lugar de
loopback; configura timeout de 15 segundos. Comprueba siete herramientas para consulta y
ocho para captura; el lector tampoco puede ejecutar `capture_memory` directamente.
Haz la captura de aceptación con datos sintéticos y confirma su recuperación desde el
segundo cliente. La instalación remota de Codex es #79 y la aceptación física es #80.

Comprueba que `/`, `/viewer` y `/admin` no ofrecen interfaz/documentos y que no hay proxy
hacia 8793/8787. Un Host diferente debe fallar (421/403). POST de más de64KB falla con413;
el backend conserva el límite de10s para recibir el cuerpo y16 conexiones. El timeout del
cliente limita su espera; no cancela necesariamente una operación ya autorizada. Las
pruebas locales de TLS no verifican los límites de handshake/entrada del daemon Tailscale.

## Revocación, desconexión y recuperación

- Elimina/caduca la credencial de un equipo en el registro privado: las siguientes
  peticiones, incluidas conexiones existentes, deben fallar con401. Retirar el dispositivo
  o su permiso de red en Tailscale corta otra capa de acceso. Comprueba ambas por separado.
- Ctrl+C en Serve detiene esta sesión de publicación; Ctrl+C en el MCP detiene el backend.
  Revisa `serve status` y `funnel status` después. Si decidiste usar modo persistente en
  otro despliegue, detén únicamente su listener mediante `tailscale serve --https=8443 off`
  después de verificar que sigue siendo el propio. No restablezcas toda la configuración.
- PC apagado, suspendido, sin red, VPN desconectada o backend caído: no hay memoria remota
  disponible ni réplica offline. No generes otro evento para reintentar una captura incierta;
  conserva el mismo evento y payload para que la idempotencia evite duplicados.
- Después de despertar/reconectar, comprueba la URL, certificado y lectura. Antes de
  capturar de nuevo, comprueba pendientes y reintenta el evento original cuando corresponda.
  Disponibilidad tras suspensión y renovación real del certificado requieren pruebas reales.
- Mantén backups privados de conocimiento y del registro por separado. No cambies la
  configuración MCP stdio actual hasta completar la aceptación del cliente remoto.

## Evidencia y trabajo pendiente

El test TLS sintético usa sockets reales, un certificado efímero de confianza explícita
solo en el test y un proxy local de prueba que conserva Host. Verifica rechazo de
certificado desconocido/nombre incorrecto, Host/Origin, falta de bearer, herramientas y
captura por rol, recuperación de la nota y revocación en conexión existente. No es Serve,
un certificado público, una prueba de reglas de red ni un segundo PC. El proceso CLI real
también prueba el nuevo argumento y sigue sin registrar tokens ni contenido de herramientas.

**#77 permanece abierta y su despliegue está aplazado por decisión del propietario** hasta aprobar/conectar la red y verificar en dispositivos reales
TLS, aislamiento, revocación, límites y suspensión. No se activó un ingress del propietario.

Referencias revisadas el 2026-10-23:
[Serve y reglas de acceso](https://tailscale.com/docs/features/tailscale-serve),
[certificados y transparencia de nombres](https://tailscale.com/docs/how-to/set-up-https-certificates),
[reenvío de Host en v1.104.2](https://github.com/tailscale/tailscale/blob/v1.104.2/ipn/ipnlocal/serve.go#L910-L928).
