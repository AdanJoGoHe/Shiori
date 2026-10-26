# Rutas coherentes entre Windows, PowerShell y Codex

Una ruta nominal de AppData y su ubicación física pueden diferir en una aplicación empaquetada.
El código compara ahora raíz y archivo resueltos en el mismo momento y rechaza symlinks/junctions,
incluidos los de ancestros. No acepta como válida cualquier ruta que apunte fuera de la raíz.
La carga de configuración normaliza las raíces en memoria; no reescribe el JSON silenciosamente.
El inicializador resuelve otra vez los directorios después de crearlos y usa un archivo temporal
vacío propio para verificar la ubicación física de las escrituras. Lo elimina y persiste esa raíz.
Esto solo ocurre al inicializar, no en `paths` ni en una vista previa de reparación.

Microsoft documenta la [redirección de AppData de aplicaciones empaquetadas](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes).
Esto no identifica automáticamente la causa de cualquier error de rutas. No se fija el identificador
de paquete de Codex ni se buscan almacenes alternativos entre carpetas de otros hosts.

## Diagnosticar sin inicializar otro almacén

Selecciona el archivo **existente** del despliegue. El inicializador imprime `config_path`; usa esa
misma ruta física desde PowerShell, Codex y el visor. Un `--config` explícito prevalece sobre
`SECOND_BRAIN_CONFIG`; no se deduce el despliegue a partir del directorio de trabajo.

```powershell
$BrainConfigPath = 'D:\SecondBrain-Private\config.json'
.\.venv\Scripts\python.exe -m second_brain.cli --config $BrainConfigPath paths
```

`paths` solo lee configuración/metadatos: no crea directorios, ledger ni índices. Devuelve revisión
SHA256 del JSON, IDs opacos de raíces y códigos, sin cuerpos de notas, URLs de sesión ni rutas
completas. `ok` sale con0; `attention`/`unavailable` con1. Los códigos distinguen raíz ausente,
normalización pendiente, resolución incoherente y raíz inválida/inaccesible. Es diagnóstico de
rutas, no prueba de frescura del proveedor ni de que el host haya recargado el MCP.

## Vista previa y reparación explícita del mismo almacén

```powershell
$PathPreview = .\.venv\Scripts\python.exe -m second_brain.cli --config $BrainConfigPath repair-paths
if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar la reparación; revisa su código de bloqueo.' }
$PathPlan = $PathPreview | ConvertFrom-Json
$PathPlan
```

La vista previa no escribe. Muestra las rutas antes/después y la ruta física del JSON para que se
pueda revisar: su salida es privada, a diferencia del diagnóstico seguro `paths`. Los campos ajenos
se conservan. Solo normaliza `vault_path`, `state_path` y el directorio del proveedor si ya existe
como campo. No mueve ni copia datos ni busca un almacén vacío de repuesto.

Cuando la redirección mantiene incoherentes raíz e hijos, la vista previa sin parámetros puede
bloquearse. Solo si conoces las ubicaciones físicas del **mismo** almacén existente, puedes repetir
`repair-paths` con `--vault-path`, `--state-path` o `--basic-memory-config-dir`. La comprobación usa
resolución y `samefile`: directorios equivalentes o los mismos objetos de archivos registrados.
No basta con que dos carpetas tengan notas con el mismo texto. Si no se puede probar la identidad,
se rechaza la reparación en vez de cambiar de despliegue. Raíces ausentes, solapadas, enlaces,
escapes, errores de acceso y límites de inspección también bloquean sin crear un sustituto.

Tras revisar el plan, detén las capturas/procesos que utilicen esa configuración y aplica:

```powershell
$PhysicalRootArgs = @()
foreach ($RootField in $PathPlan.proposed_roots.PSObject.Properties) {
    $PhysicalRootArgs += @(('--' + $RootField.Name.Replace('_', '-')), [string]$RootField.Value)
}
.\.venv\Scripts\python.exe -m second_brain.cli --config $BrainConfigPath repair-paths @PhysicalRootArgs --apply --expect-revision $PathPlan.configuration_revision
```

Repetir todas las raíces físicas revisadas evita recalcular el destino en otro contexto de host.
Si el contexto actual apunta a otro almacén, la identidad no coincide y se bloquea la operación.
No elimines ese control para forzar la reparación; utiliza el contexto original del almacén. `--expect-revision` rechaza
un JSON cambiado desde la revisión; es recomendable para evitar aplicar sobre cambios ajenos.
Antes de sustituir el JSON se guarda una copia exacta con nombre único al lado del archivo físico.
La sustitución es atómica y la operación usa un lock; los editores externos que ignoren ese lock
no ofrecen una transacción conjunta. Si falla la escritura, el JSON anterior y la copia quedan
disponibles. No se cambian bytes de notas, ledger o anotaciones. `no-change` no crea una copia.
La reparación limita el JSON a128KB, el ledger a8MB y los anclajes/notas inspeccionados a5000.

Un despliegue con ledger existente y vault ausente, o notas gestionadas sin su ledger, se rechaza
antes de inicializar directorios de repuesto. Conserva la configuración/estado original y usa el
diagnóstico. La inicialización legítima de un despliegue nuevo sigue disponible.

## Reabrir el mismo despliegue

Usa el `config_path` físico del plan/instalador. Revisa `upgrade-codex` antes de actualizar sus
bloques gestionados; no sobrescribas ajustes propios. Usa la misma configuración al abrir el visor.
La reparación no modifica automáticamente la integración de Codex ni el registro del proveedor:
ambos se revisan por separado.

Reinicia el MCP y un visor ya arrancado para cargar la nueva configuración/código. Comprueba
`doctor`, `catalog --kind note` y una lectura conocida, además de abrir una nota en el visor.
Si la configuración del proveedor sigue enlazada a una ruta anterior, revisa su diagnóstico por
separado; no reindexar o recrear proyectos como sustituto de recuperar el almacén correcto.
No publiques salidas privadas, citas personales ni la capacidad de sesión del visor.

Los scripts `install-personal.ps1 -ConfigPath <archivo>` y `secure-personal.ps1 -ConfigPath <archivo>`
aceptan selección explícita; el instalador pasa a endurecimiento y registro el archivo físico que
devuelve el inicializador. También respetan `SECOND_BRAIN_CONFIG`. Un JSON existente se conserva
sin bootstrap del proveedor; el inicializador exige raíces gestionadas coherentes antes de seguir.
El instalador y `upgrade-codex` rechazan la resolución incoherente antes de escribir en el host. Raíces amplias (unidad, perfil/AppData o repositorio) se rechazan antes
de endurecer ACLs; utiliza subdirectorios privados aprobados.

## Evidencia y alcance

La regresión determinista produce ledger con1 nota y catálogo vacío/`invalid-content` en el código
anterior; al normalizar ambos lados recupera el ID y cuerpo exactos. Otras pruebas simulan raíz
estable/hijos redirigidos y verifican diagnóstico, reparación explícita, copia anterior, rechazo
de otro almacén y preservación de bytes. Hay prueba real de lectura con selección explícita por
PowerShell/CLI, MCP stdio y HTTP sobre una instalación sintética. El proceso local devolvió15700
([`APPMODEL_ERROR_NO_PACKAGE`](https://learn.microsoft.com/en-us/windows/win32/api/appmodel/nf-appmodel-getcurrentpackagefamilyname)): es Windows sin identidad de paquete, no evidencia física de MSIX.
La creación posterior a redirección se simula y el proveedor de ese test se sustituye por un fixture.
No se usó el vault real ni se reinició el host del propietario. La aceptación física empaquetada
es una limitación documentada. #64/#65 añaden [estados del visor y paridad de lectura](catalog-diagnostics.md),
con cobertura MSIX simulada explícita; no se afirma aceptación física empaquetada. No se ejecutó GitHub Actions.
