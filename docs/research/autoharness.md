# AutoHarness y una adaptación para Shiori

Revisión del 2026-10-27. Referencia: **Tigerless Labs AutoHarness**, versión declarada 0.5.3,
commit [`69deaeabd147a8a73e9f7e4583a2b70d1785a437`](https://github.com/tigerless-labs/autoharness/tree/69deaeabd147a8a73e9f7e4583a2b70d1785a437).
Se revisaron documentos y código público; no se instaló ni ejecutó el plugin y no se usaron
sesiones, configuraciones o información de un entorno de trabajo real.

## Qué aporta

Es un plugin de Claude Code que convierte experiencias de una sesión en skills, propone
correcciones y consolidaciones y archiva parte de su biblioteca según señales de uso. No es
entrenamiento de los pesos del modelo. Su objetivo encaja con Shiori, pero la memoria canónica
y las instrucciones ejecutables deben seguir siendo capas distintas. La primera parte es la
descripción del proyecto; la separación para Shiori es nuestra propuesta.
[README](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/README.md),
[manifiesto](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/.claude-plugin/plugin.json).

## Flujo comprobado en el código

| Etapa | Comportamiento del upstream |
|---|---|
| Eventos | Registra `SessionStart`, `PreToolUse`, `Stop` y `SessionEnd` de Claude Code. |
| Captura | Lee un tramo del log JSONL del host desde un offset; aplica reglas de redacción y prepara una ventana y un resumen previo. |
| Reflexión | Otro proceso de Claude recibe la ventana y el índice de skills. Propone crear, actualizar, parchear, retirar un subarchivo o archivar una skill. |
| Propuesta | La herramienta MCP `stage_skill` valida campos y añade una intención a una cola; no publica la skill. |
| Publicación | Un promotor separado vuelve a validar, escribe archivos de soporte y evidencia y reemplaza `SKILL.md` al final. |
| Recuperación de contexto | Al empezar una sesión inyecta un índice agrupado de su biblioteca gestionada. |
| Ciclo de vida | Separa invocaciones de una skill, lecturas de sus archivos y modificaciones. Puede archivarla, conservando su directorio e historial. |

Fuentes de las etapas: [hooks](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/hooks/hooks.json),
[captura](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/capture.py),
[lanzamiento](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/spawn.py),
[MCP](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/stage_skill/server.py),
[promotor](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/promoter.py),
[inicio de sesión](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/on_session_start.py).

La reflexión se activa por defecto al alcanzar 50 llamadas de herramientas; `Stop` comprueba
el contador al terminar el turno. `SessionEnd` también intenta procesar el resto pendiente.
La consolidación usa realmente el contador de requests incrementado en `Stop`: su valor por
defecto es 250. No conviene interpretar ambas cadencias como la misma unidad, aunque algún
comentario las describa así. Hay una variable de entorno para evitar la recursión de los hijos.
[Dispatcher](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/dispatch.py),
[Stop](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/on_stop.py),
[fin](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/on_session_end.py).

## Qué guarda y qué cuesta

La biblioteca usa `SKILL.md`, archivos de soporte, un registro `.ledger.jsonl` y un sidecar
con propiedad y contadores. El promotor materializa evidencia redactada de la sesión en
`references/evidence-<hash>.md`. Estado adicional conserva offsets, colas, resultados de cada
ejecución y snapshots antes de consolidar. Desinstalar el plugin no equivale a borrar estos
datos. El alcance puede ser de proyecto o global; el global se puede deshabilitar.
[Evidencia y publicación](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/promoter.py),
[registro](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/lib/ledger.py),
[sidecar](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/lib/sidecar.py),
[configuración](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/config.py).

El modo `bundle`, predeterminado, envía una ventana redactada a una sesión nueva; existe un
modo alternativo que reanuda y bifurca la sesión. Los agentes reflector y curator declaran
`model: haiku`. Que no haya un daemon residente no elimina esas invocaciones adicionales ni
su consumo de contexto/modelo. El código de lanzamiento no fija un presupuesto total de tokens
ni un timeout para la ejecución del hijo.
[Reflector](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/agents/reflector.md),
[curator](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/agents/curator.md),
[spawn](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/spawn.py).

Los límites nominales de salida son 4.000 bytes por registro, 200.000 por ventana y 20.000
por resumen. La captura lee el tramo del archivo antes de truncarlo: esos límites de contexto
no son un límite estricto de lectura o memoria del proceso. Las propuestas también tienen
límites de cuerpo y subarchivos. `create/update` limita el cuerpo a 25 líneas no vacías y la
descripción al presupuesto del índice, 60 caracteres por defecto; `patch` tiene excepciones.
Son políticas del plugin, no requisitos universales de las skills.
[Captura](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/capture.py),
[límites](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/config.py),
[validador](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/lib/validate.py).

## Propiedad, recuperación y límites

Las modificaciones ordinarias requieren `created_by: agent`. Un merge debe nombrar una skill
gestionada que absorba el contenido. La retirada mueve el directorio a un archivo reversible.
Las tasas usan oportunidades de uso desde la creación; una lectura no se cuenta como una
invocación, aunque evita ciertas retiradas por falta de uso. Estos contadores no demuestran
que una instrucción mejorara el resultado. El índice incluye miembros en periodo de prueba,
por lo que el límite de skills maduras no limita por sí solo todo el contexto inyectado.
[Admisión](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/promoter.py),
[ciclo de vida](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/lib/lifecycle.py),
[contadores observados](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/on_skill_call.py),
[índice](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/on_session_start.py).

Hay filtros de secretos e instrucciones peligrosas mediante expresiones regulares, validación
de rutas y sintaxis de Python. Son comprobaciones deterministas de patrones, no un sandbox ni
una prueba de ausencia de datos sensibles. El reflector propone con herramientas limitadas,
pero el lanzador utiliza `--dangerously-skip-permissions`; no debe trasladarse ese patrón a
otros hosts. El modo fork hereda contexto y herramientas, por lo que merece una revisión
separada antes de usarlo. Los snapshots de consolidación son recuperación manual y el código
puede continuar si no consigue crearlos.
[Filtros](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/lib/skills_guard.py),
[redacción](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/lib/redact.py),
[herramientas del reflector](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/agents/reflector.md),
[lanzamiento y snapshots](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/spawn.py).

El snapshot de consolidación añade el árbol de skills completo de cada capa activa al tar,
sin filtrar ahí por propiedad. Aunque la consolidación se dirija a skills gestionadas, la
copia puede contener también skills del usuario. En Shiori una copia de seguridad de este
tipo debe tener un alcance explícito y permanecer fuera del código público.
[Selección del snapshot](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/spawn.py).

**Punto pendiente de confirmar mediante pruebas aisladas:** en la lectura estática, `create`
comprueba colisiones en la otra capa, pero no se aprecia una negativa equivalente ante un
destino ya existente de la misma capa. Esa acción está exenta del control de propiedad usado
por modificaciones, y la escritura utiliza reemplazo. Esto impide tomar la promesa de proteger
skills ajenas como una garantía demostrada para todos los caminos. No se ejecutó una prueba
contra el upstream. Nuestra implementación debe exigir un destino nuevo o una propiedad
verificada incluso al crear.
[Promoción](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/hook/promoter.py),
[exención de create](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/lib/validate.py),
[almacén](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/lib/skill_store.py).

## Portabilidad y licencia

El plugin requiere Python 3.11 o posterior y no declara dependencias Python de terceros.
Su manifiesto y sus hooks invocan `python3`; los comandos de hook usan asignación de entorno
POSIX. Hay primitivas de bloqueo para Windows y restricciones sobre nombres reservados,
pero el workflow revisado prueba Ubuntu con Python 3.11/3.12. No establece una instalación
Windows validada, ni soporte para Codex o Augment.
[Manifiesto](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/.claude-plugin/plugin.json),
[hooks](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/hooks/hooks.json),
[bloqueo](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/src/autoharness/lib/lock.py),
[CI](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/.github/workflows/ci.yml).

La licencia es MIT; si se copia código o una parte sustancial, se debe conservar su aviso
de copyright y licencia. La investigación y las recomendaciones de este documento son una
síntesis propia; no incluyen código del plugin.
[LICENSE](https://github.com/tigerless-labs/autoharness/blob/69deaeabd147a8a73e9f7e4583a2b70d1785a437/LICENSE).

## Propuesta para Shiori

Estas son recomendaciones de diseño, no capacidades comprobadas de Codex o Augment:

1. Mantener las notas verificadas de Shiori como fuente canónica. Una skill derivada debe
   referenciar IDs y revisiones de notas curadas; no necesita almacenar conversaciones crudas.
2. Separar **proponer**, **validar** y **publicar**. Empezar con una revisión explícita o una
   skill de cierre compatible con el host, antes de depender de hooks automáticos.
3. Buscar una nota o skill equivalente antes de crear otra. Las correcciones deben actualizar
   el mismo tema; los cambios de instrucciones necesitan evidencia y un diff revisable.
4. Limitar la primera versión a Markdown. No generar scripts ejecutables ni cambios globales
   automáticamente. Usar un manifiesto de propiedad y hashes; conservar los archivos ajenos o
   editados y tomar una copia antes de publicar un cambio propio.
5. Llevar personal y trabajo por el scope y almacén ya seleccionados. La capa global de
   instrucciones no puede ser un puente entre ambas memorias.
6. Si el host no ofrece eventos fiables, registrar el uso como **desconocido**, no como cero.
   En esa situación el archivado debe ser explícito; una ausencia de telemetría no demuestra
   que una skill sea inútil.
7. Mantener presupuesto de contexto, límites de propuestas y resultados visibles. Usar el
   modelo de la conversación actual para una primera reflexión evita añadir llamadas ocultas.
8. Validar cada integración con datos ficticios: deduplicación, corrección, destino ajeno,
   archivo editado, scope incorrecto, interrupción y recuperación. Las pruebas del núcleo no
   sustituyen comprobar descubrimiento y uso real en cada host.

La comprobación de los eventos y formatos disponibles en Codex y Augment es una investigación
separada. No se ha asumido que acepten los hooks, agentes o nombres MCP de Claude Code.

## Adaptación preparada en Shiori

La primera adaptación está implementada en la CLI `learn` y en las skills personal y de
trabajo: borradores privados desde notas verificadas, activación revisada y correcciones
acotadas a destinos propios. Conserva versiones y rechaza archivos ajenos, cambios de fuente,
proyecto o capacidades en el refresco automático. Las declaraciones de cambio siguen siendo
juicios del agente, no un clasificador semántico independiente.

La [guía de uso](../learning.md) diferencia la comprobación de archivos/CLI de la aceptación
real en los hosts. Codex tiene [hooks documentados](https://learn.chatgpt.com/docs/hooks),
pero esta implementación no instala ninguno. Augment JetBrains dispone de
[skills](https://docs.augmentcode.com/jetbrains/using-augment/skills); los
[hooks de Auggie CLI](https://docs.augmentcode.com/cli/hooks) no acreditan eventos de JetBrains.
La adaptación no recoge transcripciones ni lanza el reflector de Claude.
