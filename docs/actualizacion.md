# Actualizar un despliegue existente

Para la instalación gestionada de trabajo con Augment, usa [update y rollback](augment-trabajo.md#actualizar-más-adelante).
Lo que sigue describe la instalación personal con Codex que ya existía.

La actualización tiene dos partes: instalar el programa elegido y actualizar su integración
con Codex. El workflow de release prepara paquetes; no actualiza los equipos desplegados.
`upgrade-codex` actualiza la integración local desde el Python que lo ejecuta. No descarga
paquetes, migra datos ni reinicia procesos.

## Antes del cambio

1. Identifica el Python, versión y archivo de configuración usados por el MCP actual.
   No deduzcas el despliegue desde el directorio del repositorio. Conserva la configuración
   anterior y el entorno/commit anterior para poder volver atrás.
2. Comprueba las notas de la versión de destino y su compatibilidad con los datos.
   Haz una copia privada de la memoria con `backup`; conserva aparte los documentos externos,
   configuración del host y JSON originales de capturas pendientes, excluidos de esa copia.
3. Pausa capturas, detén el visor y desconecta el MCP antes de aplicar cambios.
   `pause` permite lecturas y no impide escribir anotaciones desde un visor todavía abierto.
   No ejecutes instalación/desinstalación ni edites ajustes del host durante la actualización.

## Instalar el programa

**Desde código:** conserva cambios propios, comprueba `git status --short`, selecciona la rama
o versión de destino y actualiza con `git pull --ff-only` y `uv sync --locked --extra dev`
cuando corresponda. No uses reset/force para resolver diferencias. Guarda el commit anterior
y su lockfile; sincronizar el mismo `.venv` reemplaza su programa anterior.

**Desde paquete:** usa el wheel y constraints de la misma release, verifica sus hashes y
créale otro entorno Python. Conserva el entorno anterior. No presupongas que el paquete ya
está publicado ni que una actualización del ejecutable pueda deshacer una migración de datos.

## Revisar y aplicar la integración

Ejecuta desde el **Python de destino** y pasa explícitamente la configuración del despliegue.
En PowerShell, con esas dos rutas ya identificadas:

```powershell
# Solo revisa; no crea archivos ni modifica el despliegue.
& $BrainPython -m second_brain.cli --config $BrainConfig upgrade-codex

# Después de revisar las rutas propuestas, guarda copias y aplica.
& $BrainPython -m second_brain.cli --config $BrainConfig upgrade-codex --apply
```

La revisión devuelve `upgrade available` con las rutas afectadas, o `up to date`.
`--apply` vuelve a comprobar los archivos; devuelve `upgraded`, `restart_required: true`
y una ruta privada `recovery`. Una segunda ejecución sin cambios devuelve `up to date`.
El modo de aplicación puede crear un archivo de bloqueo incluso si termina sin cambios.

El comando necesita el manifiesto de la instalación existente. Compara los bloques propios
de `config.toml` y `AGENTS.md`, y el hash de la skill. Actualiza el intérprete/configuración
del MCP y la skill a los de destino, preservando otros ajustes, instrucciones, BOM y finales
de línea fuera del bloque. Si encuentra bloques cambiados, duplicados, skill editada, archivos
ausentes, rutas enlazadas o copias alteradas necesarias para desinstalar, falla sin reemplazar
los archivos de integración. No utiliza `--force` ni sobrescribe personalizaciones propias.
Revisa diferencias y reconcilia manualmente antes de reintentar.

Las copias anteriores completas de `config.toml`, `AGENTS.md`, `SKILL.md` y
`install-manifest.json` se guardan bajo `state_path/backups/upgrade-<id>/` antes de reemplazar
archivos. El manifiesto se actualiza al final y mantiene la desinstalación posterior compatible
con los ajustes ajenos. Estas copias pueden contener datos privados del host: no las publiques.

## Comprobar y reanudar

Ejecuta `doctor`, una lectura y una consulta conocidas con la configuración elegida. Reconecta
MCP o reinicia Codex y comprueba las herramientas anunciadas por el proceso nuevo. Reinicia el
visor desde su gestor habitual y revisa documentos, notas y anotaciones. Solo entonces usa
`resume` para permitir capturas. Un `doctor` correcto no prueba por sí solo la conexión del host.

## Recuperación y límites

Un error de escritura ordinario intenta restaurar los archivos ya reemplazados y conserva
las copias. Un cierre abrupto o un fallo de disco durante esa restauración puede dejar una
integración parcial: no es una transacción frente a cortes de energía.

Para volver a la integración anterior, detén sus procesos, comprueba que existen las cuatro
copias completas en `recovery` y compara los archivos actuales para preservar cambios posteriores.
Restaura cada archivo completo en su ubicación anterior y el manifiesto en el `state_path`
correspondiente; vuelve a seleccionar el entorno Python anterior y reconecta el host.
No ejecutes una desinstalación sobre una integración parcial para intentar arreglarla.
Si las copias están incompletas, conserva el estado y reconcilia manualmente.

Esto revierte la integración, **no los datos**. Un ejecutable que solo entiende esquemas 1/2 no puede leer
anotaciones de esquema 3 (títulos/descripciones). Leer esquemas anteriores los adopta en memoria;
la primera modificación de marcas o categorías guarda esquema 3 y conserva el archivo anterior
exacto en una sola instantánea rotatoria. Guarda una copia privada independiente antes de escribir
si necesitas poder volver atrás. Usa una copia compatible y una restauración separada/pausada cuando
sea necesario; no reemplaces ni edites el ledger para ocultar pendientes.

La validación automatizada usa instalaciones sintéticas, incluidos cambios de intérprete,
skill anterior, conflictos, conservación de ajustes, fallos de escritura y desinstalación.
El smoke del wheel prueba también revisión/aplicación/repetición desde el paquete instalado.
Todavía falta probar el salto entre dos releases realmente publicadas y añadir una comprobación
general de compatibilidad/migraciones antes de automatizar la instalación de paquetes.


Para raíces nominales/físicas incoherentes en Windows, diagnostica y prepara primero la reparación
del mismo almacén con [`paths` / `repair-paths`](windows-paths.md). La vista previa no inicializa
raíces; la aplicación explícita conserva copia del JSON. No es una migración de datos ni un cambio
automático del proveedor o de Codex.

## Cambio de repositorio en GitHub

El repositorio público es [AdanJoGoHe/Shiori](https://github.com/AdanJoGoHe/Shiori). Su historial
empieza en una raíz revisada. El desarrollo previo y su planificación se conservan por separado
en privado. Las URL antiguas pueden dirigirse al archivo privado; usa siempre la URL canónica.

**Si tu clon contiene el historial antiguo:** conserva una copia privada del código/cambios propios
y utiliza un clon nuevo para desarrollar contra el repositorio público. No ejecutes `git pull` ni
mezcles las historias: podrías reintroducir commits retirados. Reaplica solo cambios revisados.
Conserva el entorno instalado y sus rutas de configuración/vault; clonar código no migra tus datos.

```powershell
# Una carpeta de código nueva, distinta del despliegue existente.
git clone https://github.com/AdanJoGoHe/Shiori.git 'D:\repo\Shiori-public'
```

**Si tu clon ya procede del historial público:** un cambio de URL conserva sus commits y archivos:

```powershell
git remote set-url origin https://github.com/AdanJoGoHe/Shiori.git
git remote -v
git fetch origin
```

La configuración MCP y las rutas del despliegue existente siguen siendo la referencia para
actualizarlo. El paquete `second-brain`, módulo `second_brain` y entrada `second_brain_personal`
conservan sus identificadores. `shiori` es el comando recomendado y el alias anterior funciona.
