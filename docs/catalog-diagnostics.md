# Diagnóstico del catálogo y paridad de lectura

Un contador de notas en el ledger no demuestra que sus archivos se puedan leer. El catálogo
devuelve `diagnostics` en CLI, MCP `list_content` y API del visor. El visor añade `result_state`
después de aplicar los filtros. Los campos anteriores (`items`, `errors`, `truncated`) se conservan.

| Estado | Qué significa | Acción |
|---|---|---|
| `empty` / `empty-catalog` | Las colecciones seleccionadas se examinaron sin errores y están vacías | Añadir notas o configurar documentación |
| `ready` / `no-matches` | Hay contenido legible, pero los filtros no encuentran coincidencias | Cambiar búsqueda o filtros; en fragmentos, comprobar las marcas |
| `unavailable` | Ninguna colección seleccionada pudo aportar contenido ni confirmar que está vacía | Reintentar; revisar la configuración y acceso |
| `partial` | Hay errores, pero también contenido legible o una colección vacía examinada correctamente | Usar los resultados disponibles; la consulta es incompleta |
| `limited` | Se agotó el presupuesto de exploración | Seleccionar una colección/origen menor; no interpretar cero como ausencia |

Un fallo parcial puede devolver cero coincidencias; en ese caso el visor avisa que solo se buscó
en la parte legible. Los contadores son de colecciones seleccionadas, antes de filtros de texto,
metadatos o paginación. Una marca retenida puede seguir visible aunque su documento no esté disponible.

Los códigos incluyen `invalid-content`, `unavailable`, `invalid-root`, `linked-path`,
`content-changed` y `scan-limit`. `ledger-catalog-mismatch` indica que no se pudo catalogar
el mismo número de notas que figura en el ledger; no demuestra pérdida de datos ni autoriza
a recrear el almacén. No se añade ese código por una exploración truncada.

## Revisar el despliegue seleccionado

Usa el mismo intérprete y archivo de configuración explícito que el MCP y el visor:

```powershell
& $BrainPython -m second_brain.cli --config $BrainConfigPath doctor --catalog
& $BrainPython -m second_brain.cli --config $BrainConfigPath paths
& $BrainPython -m second_brain.cli --config $BrainConfigPath catalog --kind note
```

`doctor --catalog` no consulta el proveedor ni modifica la configuración; rechaza raíces ausentes
antes de construir el lector. Devuelve código de salida 1 ante lectura incompleta o configuración
no utilizable. `--catalog` y `--provider` son comprobaciones separadas y excluyentes. El `doctor`
habitual conserva su comportamiento anterior.

El diagnóstico incluye `registered_notes`, `readable_notes`, estado por colección y `store_id`.
Este último es un hash opaco de las raíces físicas: permite comparar lectores en el mismo sistema,
no prueba la identidad del contenido ni sustituye la comprobación de IDs y cuerpos. `paths` añade
`configuration_id`, revisión del JSON y hashes de raíces para distinguir la configuración efectiva
sin mostrar rutas completas. Esos identificadores no son credenciales ni una anonimización fuerte.
Los diagnósticos no incluyen cuerpos, trazas ni URLs de sesión. Los resultados normales del catálogo
siguen conteniendo títulos y rutas relativas: no publiques una respuesta personal completa.

Si hay incoherencia, sigue [la revisión y reparación explícita de rutas](windows-paths.md).
Después de corregir configuración o actualizar código, reinicia los procesos MCP/visor desde su
host o terminal y vuelve a leer una nota conocida. Un proceso Python antiguo puede
servir archivos estáticos recién actualizados: el visor detecta la falta del nuevo contrato y pide
reiniciar, en lugar de presentar un cero engañoso.

## Regresión local, exclusivamente sintética

```powershell
.\.venv\Scripts\python.exe scripts/check-local.py
.\.venv\Scripts\python.exe -m pytest tests/test_path_coherence.py tests/test_catalog.py tests/test_cli.py tests/test_viewer.py -q
```

La suite compara identidad, IDs y lectura mediante PowerShell/CLI, MCP stdio nuevo y HTTP con
el mismo `--config`, incluso con un `SECOND_BRAIN_CONFIG` ambiental distinto. Cubre el JSON
actual y el esquema anterior mínimo con BOM y nombre con espacios. Conserva bytes de notas,
ledger, anotaciones y configuración; las pruebas de reparación verifican por separado su copia
anterior y el cambio autorizado del JSON. Mantiene rechazos de traversal, symlinks, junctions y escapes.
HTTP comprueba fuentes sintéticas vacías, inválidas, parcialmente legibles y truncadas, así como
fallos persistentes y cambios entre catálogo y lectura.

La aceptación opcional de presentación requiere Node, Playwright y un navegador instalado:

```powershell
# Terminal 1: crea su propio contenido desechable, sin usar la memoria personal.
.\.venv\Scripts\python.exe scripts/demo-viewer.py
# Terminal 2: URL del demo anterior; nunca la URL del despliegue personal.
$env:SB_VIEWER_TEST_URL = $DemoUrl
# Opcional: ruta local a Edge/Chromium si Playwright no tiene uno instalado.
$env:SB_TEST_BROWSER = $BrowserExecutable
node scripts/check-viewer-states.cjs
```

El script controla respuestas del listado para comprobar seis presentaciones en Claro/Oscuro/Café
Latte y anchos 1440/820/390: 54 combinaciones, teclado para actualizar/reintentar/abrir/volver,
compatibilidad con un servidor antiguo y ausencia de errores JS/desbordamiento horizontal.
Cada ancho inicia un documento nuevo y la automatización solicita movimiento reducido;
la revisión visual adicional usa capturas con la presentación habitual.
La apertura usa contenido real del demo. La clasificación de estados se prueba por separado contra
fuentes reales sintéticas mediante HTTP; las respuestas controladas no prueban por sí solas el backend.
Playwright es una herramienta opcional de desarrollo, sin dependencia nueva del producto.

La ejecución del 2026-10-20 se realizó en Windows sin identidad de paquete (API de Windows:
`GetCurrentPackageFamilyName` devolvió 15700). La resolución de raíces/hijos bajo MSIX está
**simulada** de forma determinista: la regresión fallaba con el código anterior. No se afirma una
prueba física desde Codex MSIX, ni se usó el vault del propietario, se reparó su configuración o se
reiniciaron sus procesos. Esta cobertura simulada es la alternativa prevista en #65; la aceptación
física adicional sigue siendo una limitación documentada. No se ejecutó GitHub Actions.
