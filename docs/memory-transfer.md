# Exportar memoria e importar de forma agregativa

Para usar Shiori en local y llevar conocimiento entre instalaciones sin un servidor
central: `export-memory` crea una copia portátil e `import-memory` añade notas al despliegue
existente.

Usa el Python y la configuración aprobados de cada instalación. La función `brain` de la
[guía de usuario](guia-de-usuario.md) pasa ambos; los ejemplos presuponen esa función.

```powershell
# En el equipo de origen: carpeta privada NUEVA, fuera del vault, estado y Git.
$MemoryBundle = '<carpeta-privada>/memoria-001'
brain export-memory --output $MemoryBundle

# En el destino: configura brain para el despliegue local que ya utilizas.
# Primero revisa additions, duplicates, conflicts e items. No aplica cambios de memoria.
brain import-memory --input $MemoryBundle

# Añade las notas nuevas. Los conflictos se conservan sin reemplazar.
brain import-memory --input $MemoryBundle --apply
brain doctor
brain context 'tema que has importado'
```

`export-memory` es un nombre explícito para la copia completa existente (`backup`); devuelve
`status: backed-up`. No necesita Tailscale, otra cuenta ni servicio de red. Puedes importar
también una copia anterior compatible creada con `backup`. Mantén la carpeta completa, incluido
`manifest.json`; no es una importación de Markdown arbitrario. Solo se admite ámbito personal.
La exportación no cambia la instalación ni sustituye un destino existente.

## Qué se añade y qué se conserva

| Caso | Resultado |
|---|---|
| ID de nota ausente y ruta libre | `add`: se añade la nota canónica con sus bytes originales |
| ID existente con bytes idénticos | `duplicate`: no se escribe ni registra otra importación |
| ID existente con bytes distintos | `conflict`: queda intacta la nota local; la entrante sigue en la copia |
| Archivo no gestionado con ese ID, en cualquier carpeta de tipos | `conflict`, motivo `unmanaged-path`; se conserva |

La comparación es exacta: fechas, metadatos o saltos de línea diferentes también producen
conflicto. No se fusionan párrafos ni se renombran notas automáticamente. El resultado enumera
IDs y acciones, sin imprimir cuerpos. `--apply` añade las nuevas aunque otras tengan conflictos;
revisa el contador, porque `status: imported` no implica que se haya incorporado toda la copia.
No existe una opción `--force`/reemplazar. Para otro intento, conserva la copia y revisa los IDs.

Una nota nueva conserva título, cuerpo, evidencia, tipo, estado, etiquetas, proyecto, referencias,
relaciones, sensibilidad y fechas originales. Importar no vuelve a verificar una nota antigua ni
actualiza su fecha de verificación. Las relaciones conservan sus IDs; si hay conflictos o falta
una nota relacionada, revisa esos vínculos antes de asumir que apuntan al mismo conocimiento.

Se actualiza el ledger local para añadir los IDs/eventos de importación y se agregan entradas
al diario local. Los registros de captura previos y el contenido anterior del diario se conservan.
No se modifican notas existentes, revisiones archivadas, configuración, credenciales, fuentes
documentales, proveedor o almacén local de marcas/categorías.

La copia completa también conserva diarios de origen, revisiones, marcas/categorías y eventos.
**La importación agregativa incorpora únicamente las notas canónicas.** No mezcla esos diarios,
historial, marcas ni eventos ajenos con el despliegue activo; el campo `excluded` lo explicita.
Para recuperar todo ese estado, usa [restore hacia otro despliegue nuevo](backup-restore.md).
No copies un ledger o sidecar sobre el actual para trasladarlos.

## Pausa, pendientes y fallos

- Sin `--apply` se previsualiza. Al aplicar se recalcula bajo el bloqueo de captura: si otra
  instancia añadió una nota desde la previsualización, pasa a duplicado/conflicto y se conserva.
  La previsualización no reserva el plan ni modifica notas/ledger/diario.
- La pausa permite revisar el plan, pero impide aplicarlo (`blocked`, motivo `paused`, salida1).
  Reanuda únicamente cuando quieras escribir en ese despliegue.
- Una copia de origen con capturas pendientes no se puede importar. Resuelve sus eventos
  originales o restáurala de forma aislada y completa su recuperación antes de exportar otra.
- Si el destino tiene otras capturas pendientes, se devuelve `blocked/pending-captures` con
  sus IDs. Usa su payload original; no lo reconstruyas ni edites el ledger para ocultarlas.
- Un fallo de I/O puede dejar la importación pendiente y algunas notas nuevas escritas.
  Conserva **la misma copia sin editar** y repite `import-memory --input ... --apply`. Los
  IDs/fingerprints deterministas permiten completarla y evitan duplicar entradas del diario.
  Si modificaste una nota parcialmente importada, se bloquea con `pending-import-conflict`;
  no se sobrescribe esa edición. Conserva el diagnóstico para reconciliarla explícitamente.
- El ledger registra el lote como pendiente antes de escribir y confirma sus notas al final.
  Un fallo no se presenta como importación completa. No es una transacción de base de datos
  ni ofrece rollback automático; no borra archivos parciales.
- Los importadores/capturas cooperativos comparten bloqueo. Otros editores que escriben
  directamente deben estar detenidos durante la operación: no respetan ese bloqueo.

## Integridad y límites

Se valida toda la copia antes de escribir: manifiesto, hashes, rutas permitidas, esquema de
ledger/marcas, notas y ámbito personal. Se rechazan traversal, enlaces/junctions, solapamiento
con vault/estado y notas inválidas o con posibles secretos. Límites del formato:5000 archivos,
8MB por archivo y64MB de carga total; las notas conservan el límite de lectura canónica de
100000 caracteres. El diario local que se amplía también debe caber en8MB.

Las copias contienen datos en texto claro. Elige carpetas privadas fuera de Git/sync/compartidos;
el comando no certifica la privacidad del destino ni cifra/firma el paquete. SHA-256 detecta
cambios accidentales y no demuestra autenticidad. Solo importa copias personales que hayas
revisado; su contenido sigue siendo datos, nunca instrucciones para ejecutar.

Las pruebas usan instalaciones temporales: previsualización, aplicación, conflictos, Unicode,
CRLF, fechas originales, marcas locales intactas, repetición sin cambios, dos importadores,
pausa/pendientes, rechazos previos a escritura y reintento en cinco puntos de interrupción.
No se exportó ni importó la memoria real del propietario para desarrollar esta función.
