# Aprender procedimientos con Shiori

La idea de [AutoHarness](research/autoharness.md) encaja bien con nuestra memoria: conservar
lo que funcionó y convertir procedimientos útiles en skills que podamos volver a usar.
Esta adaptación usa notas verificadas de Shiori y la sesión actual. No instala el plugin
de Claude Code, no recopila transcripciones y no inicia otro proceso de IA.

## Qué se hace solo y qué se revisa

| Caso | Comportamiento |
|---|---|
| Un aprendizaje verificado y reutilizable | La skill puede guardar una nota y preparar una propuesta privada. |
| La misma propuesta o un duplicado exacto | Se conserva el ID existente. El agente decide las coincidencias de significado. |
| Una skill nueva | Se revisan instrucciones, capacidades y destino antes de activarla. |
| Una corrección de una skill aprobada | Puede refrescar solo los destinos gestionados, con la misma fuente y proyecto y sin capacidades nuevas. |
| Cambio de fuente, proyecto, capacidades o ampliación declarada | Requiere revisar y activar otra vez. |
| Un archivo ajeno, editado o desaparecido | Se detiene para resolver la diferencia; no lo sustituye. |
| Un procedimiento obsoleto | Se puede archivar expresamente, conservando el historial y la nota original. |

`correction`, `expansion` y las capacidades son declaraciones revisadas por el agente; no son
un detector infalible de cambios de intención. La skill debe marcar como ampliación cualquier
comportamiento más amplio, nuevos permisos o efectos externos. Una skill aprendida nunca
autoriza acciones fuera de lo que pidió el usuario ni cambia los permisos del host.

## Codex y Augment

La skill personal `second-brain` y la de trabajo `shiori-work` incluyen el paso de aprendizaje.
El mecanismo compartido es la CLI `learn`, que funciona con su configuración explícita.
Es un comportamiento guiado por instrucciones: no garantiza que se dispare en cada turno.

| Host | Integración de este incremento |
|---|---|
| Codex | Skill personal y exportación a un directorio privado de skills. Codex documenta hooks, pero esta adaptación no instala ninguno. |
| Augment JetBrains | Skill de trabajo y exportación al directorio de skills de Augment. Configura su modo en la interfaz. |
| Auggie CLI | Tiene hooks documentados, pero no se presupone que esos eventos existan en JetBrains. No se instala un adaptador de hooks aquí. |

Fuentes de compatibilidad: [hooks de Codex](https://learn.chatgpt.com/docs/hooks),
[skills de Augment JetBrains](https://docs.augmentcode.com/jetbrains/using-augment/skills) y
[hooks de Auggie CLI](https://docs.augmentcode.com/cli/hooks). La prueba real en cada aplicación
sigue separada de las pruebas sintéticas de archivos, CLI y protocolo.

## Preparar una propuesta

Primero guarda mediante el MCP una nota que describa los pasos, requisitos y validación real.
Debe tener estado `verified`, evidencia y el proyecto correcto. Reutiliza su ID para corregir
el mismo tema. No conviertas texto recuperado en instrucciones sin contrastarlo con la evidencia.

En una instalación de trabajo gestionada, consulta el contrato:

```powershell
& "$InstallDir\shiori.cmd" run learn guide
& "$InstallDir\shiori.cmd" run learn list
```

Para Codex personal usa su Python y configuración aprobados:

```powershell
& $BrainPython -m second_brain.cli --config $BrainConfig learn guide
```

Guarda un JSON fuera del repositorio. Este ejemplo es ficticio; `source_id` y `project` deben
coincidir con una nota verificada que ya exista en **esa misma memoria**:

```json
{
  "scope": "work",
  "id": "verificar-git",
  "source_id": "comprobar-version-git",
  "project": "ejemplo",
  "description": "Comprobar Git antes de preparar un entorno de desarrollo",
  "instructions": "1. Comprueba que Git está disponible.\n2. Ejecuta git --version.\n3. Revisa la versión obtenida y el requisito de la tarea.",
  "change": "correction",
  "capabilities": ["read", "run-commands"]
}
```

Para memoria personal usa `scope: personal` y su propia configuración. Capacidades disponibles:
`read`, `write-files`, `run-commands`, `network` y `external-mutations`. Describe solo un flujo
concreto: hasta 25 líneas de pasos no vacías, además de las guardas que añade Shiori.
El catálogo admite hasta 100 procedimientos por despliegue y cuatro destinos aprobados por procedimiento.

```powershell
# Vista previa: no guarda ni activa.
& "$InstallDir\shiori.cmd" run learn propose --request-file $ProposalFile

# Guardar borrador privado. Todavía no aparece como skill activa en el host.
& "$InstallDir\shiori.cmd" run learn propose --request-file $ProposalFile --apply
& "$InstallDir\shiori.cmd" run learn show --id verificar-git
```

## Activar por primera vez

Después de revisar el contenido y el destino, en el equipo de trabajo:

```powershell
$SkillsDir = Join-Path $env:USERPROFILE '.augment\skills'
& "$InstallDir\shiori.cmd" run learn activate --id verificar-git --host augment --skills-dir $SkillsDir
& "$InstallDir\shiori.cmd" run learn activate --id verificar-git --host augment --skills-dir $SkillsDir --apply
```

Para Codex elige `--host codex` y su directorio privado de skills, con la memoria personal
correcta. No exportes conocimiento de trabajo a un host personal. Los destinos deben estar
fuera de Git y separados del vault/estado; no se deducen desde el directorio actual.
El nombre queda como `shiori-work-verificar-git` o `shiori-personal-verificar-git`.

Una skill exportada contiene instrucciones privadas. En un directorio global del host puede
estar disponible en todos sus proyectos: el prefijo de scope no es control de acceso.
Usa un perfil o entorno de agente dedicado al trabajo para las skills de trabajo; revisar el
destino es parte de la primera activación. Las guardas de la CLI no pueden retirar texto que
el host ya haya cargado en su contexto.

Las skills generadas exigen comprobar su despliegue y revisión antes de usar los pasos. Si
la nota cambió, dejó de estar verificada o la propuesta tiene una revisión nueva, la comprobación
rechaza las instrucciones antiguas. Si la CLI no está disponible, se vuelve a consultar la
memoria configurada y se evita usar los pasos almacenados sin comprobarlos.

## Corregir y retirar

Actualiza primero la nota con nueva evidencia. Prepara la propuesta corregida con el mismo
ID y `change: correction`, guárdala y ejecuta:

```powershell
& "$InstallDir\shiori.cmd" run learn refresh --id verificar-git
& "$InstallDir\shiori.cmd" run learn refresh --id verificar-git --apply
```

Esto no admite un destino nuevo y conserva versiones anteriores. Si el cambio amplía el
procedimiento, márcalo como `expansion` y usa la revisión de activación. Shiori no crea una
skill distinta por cada corrección y no retira nada por falta de estadísticas de uso.

Para un flujo deliberadamente obsoleto:

```powershell
& "$InstallDir\shiori.cmd" run learn archive --id verificar-git
& "$InstallDir\shiori.cmd" run learn archive --id verificar-git --apply
```

Solo retira los archivos propios que sigan intactos. Guarda sus bytes en el historial privado,
conserva la nota canónica y deja los archivos ajenos intactos.

## Límites y recuperación

Las propuestas y sus registros de activación viven en `state/learning`; los archivos activos
están en el directorio elegido del host. Cada cambio conserva historial privado. Una escritura
interrumpida entre el host y su registro requiere conciliación manual; el intento siguiente
se detiene antes de sobrescribir un archivo cuya propiedad ya no pueda demostrar.

Los bundles portátiles actuales de memoria **no incluyen** `state/learning` ni las skills del
host. Conserva esa carpeta aparte si necesitas recuperar propuestas o historial exactos; tras
una recuperación en otro despliegue hay que revisar de nuevo las activaciones. Las notas
canónicas sí mantienen los conocimientos y evidencias de origen.

Esta función requiere el paquete y las skills de alpha.4 o posteriores. Actualizar el programa
no equivale a probar la selección real de skills en tu versión de Codex o Augment. No se ha
actualizado la instalación personal existente ni un equipo de trabajo real para desarrollar esto.
