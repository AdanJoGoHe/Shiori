# Shiori en Augment con memoria de trabajo

Esta instalación crea una memoria nueva en el equipo de trabajo. El programa es el mismo;
las notas, configuración e índice se guardan separados de cualquier memoria personal.
Usa únicamente material y herramientas permitidos por tu organización, incluida su política
sobre enviar contexto a un proveedor de IA.

El instalador está preparado para Windows, PowerShell, Python 3.12 y `uv`. La conexión usa
MCP local por stdio: Augment inicia el proceso cuando lo necesita. No hace falta abrir puertos.
La integración real con tu versión de JetBrains/Augment necesita la comprobación final de abajo.

## Instalar una vez

Descarga de una misma release el wheel, constraints, `SHA256SUMS` e `install-shiori.ps1`.
Conserva los archivos juntos en una carpeta. Revisa la procedencia y las notas de esa versión;
los hashes detectan cambios en los archivos, pero no son una firma del editor.
Si aún no hay una release publicada, [la preparación local](release-workflow.md) genera esos
mismos archivos desde el código revisado.

En PowerShell, ajusta las dos rutas. La carpeta de instalación debe ser **nueva**, privada y
estar fuera de repositorios Git y de carpetas compartidas o sincronizadas.

```powershell
$ReleaseDir = 'C:\Downloads\Shiori-release'
$InstallDir = Join-Path $env:LOCALAPPDATA 'Shiori\work'

# Revisar archivos y destino; no instala nada.
& "$ReleaseDir\install-shiori.ps1" -ReleaseDir $ReleaseDir -InstallDir $InstallDir

# Instalar después de revisar el resultado.
& "$ReleaseDir\install-shiori.ps1" -ReleaseDir $ReleaseDir -InstallDir $InstallDir `
    -Timezone 'Europe/Madrid' -Apply

& "$InstallDir\shiori.cmd" status
& "$InstallDir\shiori.cmd" run doctor --provider
```

Necesitas `uv` en PATH; descargará Python 3.12 si falta y las dependencias fijadas desde el
índice de paquetes configurado. Algunas dependencias se construyen desde fuente si no tienen wheel.
No cambia la memoria personal ni instala un servicio automático.
Un fallo deja el directorio parcial para inspeccionarlo: no vuelvas a usarlo como destino nuevo.

La carpeta queda así:

```text
work/
  shiori.py, shiori.cmd     rutas estables; contenido gestionado por el instalador
  installation.json        versión activa y anterior
  versions/<version>/     programa y dependencias de cada versión
  data/config.json         configuración de esta instalación
  data/vault/              notas, diario e historial
  data/state/              registro, anotaciones e índice local
  recovery/                copias anteriores a los cambios de versión
```

Conserva el directorio en su ruta original. Los entornos Python y los marcadores del almacén
no son portables moviendo la carpeta; usa exportación/restauración para recuperar datos aparte.
Los marcadores emparejan vault y estado: cambiar solo `scope` o seleccionar un almacén personal
no lo convierte en memoria de trabajo. Esto protege las interfaces de Shiori, no aísla un agente
que ya tenga acceso general a los archivos del equipo.

## Conectar Augment

```powershell
# Ver nombre, comando y destino de la skill.
& "$InstallDir\shiori.cmd" augment

# Instalar solo la skill propia de trabajo en el usuario actual.
& "$InstallDir\shiori.cmd" augment --apply
```

En JetBrains abre **Augment → Settings → MCP servers** y añade el `name` y `command` que
devuelva ese comando. El nombre es `shiori_work`. El comando llama a Python con `shiori.py`
y `run serve`; no apunta a una carpeta de versión concreta. No añadas una variable
`SECOND_BRAIN_CONFIG`: la ruta de esta memoria ya va fijada en el lanzador.
No se modifica un archivo de configuración del plugin suponiendo su formato.

La skill queda en `~/.augment/skills/shiori-work/SKILL.md`. Si Skills aparece como Beta,
actívala en los ajustes y comprueba que Augment descubre `shiori-work`; puedes elegir Auto
en su interfaz. Según la [documentación de Skills de Augment](https://docs.augmentcode.com/jetbrains/using-augment/skills),
requiere una versión compatible del plugin. La [configuración MCP](https://docs.augmentcode.com/jetbrains/setup-augment/mcp)
describe los campos del servidor local. Un archivo existente ajeno o editado se conserva y
requiere resolver la diferencia manualmente.

## Primera comprobación en el IDE

Abre una conversación nueva y pide consultar `memory_status`: debe devolver `scope: work`.
Comprueba que aparecen las nueve herramientas. Con un ejemplo ficticio, consulta contexto,
clasifica una captura y guarda un comando con `scope: work` y `source_agent: augment-jetbrains`.
Léelo por su ID, reinicia la conexión y confirma que sigue disponible. Una captura `personal`
debe fallar. Estas comprobaciones requieren tu IDE; las pruebas de protocolo locales no las sustituyen.

La skill consulta antes de trabajar y propone guardar al terminar. Es una instrucción para el
agente, no un hook que garantice captura automática en todas las conversaciones.

## Actualizar con el updater

Desde alpha.3 puedes comprobar y descargar una actualización desde el repositorio oficial,
sin buscar los archivos a mano. En PowerShell, con `$InstallDir` apuntando a tu instalación:

```powershell
# Solo consultar la última versión estable publicada; no descarga paquetes ni escribe archivos.
& "$InstallDir\shiori.cmd" update

# Mientras uses las alphas, incluir versiones preliminares publicadas.
& "$InstallDir\shiori.cmd" update --prerelease

# Cerrar MCP y visor, revisar la versión ofrecida y descargar e instalar.
& "$InstallDir\shiori.cmd" update --prerelease --apply
```

El primer paso solo consulta metadatos públicos de GitHub. Al aplicar se descargan los tres
archivos necesarios con límites de tamaño, se verifican hashes y versión y se usa el mismo
proceso con copia de recuperación y comprobación de compatibilidad. Las descargas temporales
se eliminan al terminar; las versiones instaladas y las copias de recuperación se conservan.

Si la skill de Augment fue instalada con `augment --apply` y sigue intacta, el updater la
refresca usando el paquete nuevo. Si la editaste, conserva el archivo y devuelve
`skill: manual-reconciliation-required`: el programa ya está actualizado y la skill necesita
revisión. Vuelve a conectar el MCP y abre una conversación nueva después de actualizar.

No requiere login ni lee tokens de GitHub. Usa HTTPS y los assets del repositorio
`AdanJoGoHe/Shiori`; respeta la configuración de proxy del sistema. Si la red falla o GitHub
limita peticiones, informa del problema sin cambiar la versión activa; puedes reintentarlo
más tarde o usar los archivos locales. No se instala un servicio en segundo plano.

**Solo se ofrecen releases publicadas.** Un borrador no cuenta como actualización. Sin releases
estables publicadas, `update` devuelve `no-published-release`; usa `--prerelease` para las alphas.
Ese modo revisa como máximo las 100 releases más recientes y elige la versión mayor compatible
con los nombres oficiales. No instala versiones iguales o anteriores a la activa.

Una instalación alpha.2 todavía no tiene este updater: actualiza una vez desde los archivos
locales de alpha.3. Los comandos siguientes sirven también cuando prefieres trasladar paquetes
a un equipo sin acceso a GitHub.

## Actualizar desde archivos locales

Descarga y revisa los archivos de la siguiente versión en **otra carpeta**. Detén la conexión
MCP y el visor; cierra también procesos CLI que usen esta memoria directamente.

```powershell
$NextRelease = 'C:\Downloads\Shiori-siguiente'
& "$InstallDir\shiori.cmd" update --release-dir $NextRelease
& "$InstallDir\shiori.cmd" update --release-dir $NextRelease --apply
& "$InstallDir\shiori.cmd" augment
& "$InstallDir\shiori.cmd" augment --apply
& "$InstallDir\shiori.cmd" run doctor --provider
```

Se instala la nueva versión al lado de la anterior. Antes de activarla se guardan configuración,
manifiesto y una copia validada de notas, diario, historial y anotaciones. Se comprueban versión,
notas, identidad del almacén, pendientes y esquema de anotaciones. Solo entonces cambia la versión
activa. Los pendientes deben resolverse con sus candidatos JSON originales antes de actualizar.

Augment mantiene el mismo comando. Vuelve a conectar el MCP y abre una conversación nueva para
cargar la skill actualizada. La actualización de software y la de la skill son pasos explícitos;
si editaste la skill, el segundo se detiene sin deshacer la actualización del programa.

La comprobación se inicia con `update`; no hay tareas ni instalaciones en segundo plano. Las sesiones
arrancadas con el lanzador bloquean el cambio de versión mientras estén abiertas. Los procesos
arrancados por otra vía quedan fuera de ese control y debes detenerlos tú.

## Volver a la versión anterior

```powershell
& "$InstallDir\shiori.cmd" rollback
& "$InstallDir\shiori.cmd" rollback --apply
& "$InstallDir\shiori.cmd" augment --apply
```

El rollback comprueba la versión anterior contra **los datos actuales**. Si son incompatibles,
no la activa. No borra notas nuevas ni restaura automáticamente una copia antigua. Las copias
de `recovery` contienen texto sin cifrar: protégelas igual que la memoria. Para recuperar datos,
usa [restore en un destino nuevo y pausado](backup-restore.md), revisa el resultado y decide aparte
cómo seleccionarlo. El rollback del programa no deshace futuras migraciones de datos.
