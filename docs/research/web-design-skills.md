# Skills de diseño web para el visor de escritorio

Revisión: **2026-10-30**. Alcance: una aplicación local en HTML, CSS y JavaScript para PC,
con biblioteca técnica, fragmentos y comandos marcados, favoritos, diario Hoy/Ayer y Agent log.
Se consultaron repositorios, instrucciones y código públicos. La comparación no ejecutó scripts
de esas candidatas ni comprobó su integración automática en el host. Las valoraciones de
encaje son propuestas para este producto, no resultados de una comparativa de eficacia.

**Recomendación:** conservar Taste como única dirección visual y usar Vercel
`web-design-guidelines` como revisión técnica complementaria. Consultar Interface Design para
documentar patrones cuando haga falta. Dejar Impeccable y UI/UX Pro Max para necesidades concretas;
añadir ahora otra dirección visual completa aportaría más solapamiento que valor.

## Base: Taste ya cubre las pantallas de aplicación

Taste v2.1.5 distingue páginas de marketing de pantallas donde se trabaja. Para estas últimas
prescribe un recorrido propio: inventario de datos y tareas, una pregunta principal por pantalla,
estilo de aplicación, tokens y comprobación visual. Admite bordes discretos, etiquetas pequeñas y
paneles repetidos; por tanto, no procede aplicar al visor las prohibiciones de su recorrido de
marketing. También incluye listas, detalles, estados vacíos y errores. Su inspector requiere
Node 22+ y Chrome, Edge o Chromium; ofrece una alternativa de lint y capturas cuando ese entorno
no está disponible. [Instrucciones de Taste][taste-skill], [pantallas de aplicación][taste-app].

La propuesta para Shiori es usar ese recorrido con el alcance PC del producto. Una biblioteca
necesita lectura y recuperación; favoritos y fragmentos, acceso rápido; Hoy/Ayer, orientación
temporal; Agent log, evidencia legible. No hace falta convertir esas tareas en un dashboard de
métricas ni añadir gráficos para justificar una skill.

## Comparación por función

| Candidata | Valor propuesto para este visor | Solapamiento o conflicto | Decisión propuesta |
|---|---|---|---|
| Vercel `web-design-guidelines` | Revisar semántica, teclado, foco, nombres accesibles, desbordamientos, fechas y listas largas. | Comparte estados y accesibilidad con Taste, pero actúa como lista de revisión del código. Algunas reglas de estilo editorial requieren adaptación al español. | Complemento principal para revisar la implementación. |
| `pbakaus/impeccable` | Revisión más amplia; `harden` para textos largos, errores y zoom; modos Operate y Read para herramientas y lectura. | También dirige diseño, tokens, crítica visual y verificación; incorpora motor, contexto y hooks propios. | Reservar para una auditoría o endurecimiento con alcance definido. |
| `Dammyjay93/interface-design` | Mantener densidad, tokens y componentes consistentes entre las áreas del visor. | Su exploración visual y jerarquía repiten parte de Taste; propone otro archivo de sistema y algunas elecciones visuales diferentes. | Referencia puntual; no instalar como segunda dirección automática. |
| Anthropic `frontend-design` | Redacción de acciones y errores; claridad tipográfica y crítica del resultado. | Repite dirección basada en el tema, tokens, rechazo de plantillas y autocrítica; contiene orientación de hero y móvil ajena al alcance PC. | No añadir ahora. |
| `nextlevelbuilder/ui-ux-pro-max-skill` | Consultas específicas sobre foco, navegación, estados o rendimiento de listas. | Su generación de sistema visual y catálogos de estilos duplican Taste; mezcla criterios web, móviles y nativos. | Referencia de consulta si aparece una carencia concreta. |

La tabla resume juicios de encaje basados en los archivos revisados a continuación; no ordena
proyectos por estrellas, instalaciones ni popularidad.

## Qué se comprobó en cada candidata

### Vercel: revisión técnica ligera

La skill lee archivos y devuelve hallazgos con ubicación `file:line`. Antes de cada revisión pide
descargar `command.md` desde la rama mutable `main` de otro repositorio, mediante una herramienta
llamada `WebFetch`. Las reglas incluyen HTML semántico, foco visible y no tapado, etiquetas de
controles, anuncios de cambios asíncronos, estados vacíos, contenido largo, estado en la URL,
`Intl.DateTimeFormat` y estilos de controles nativos en Windows oscuro. También menciona
virtualización para listas grandes. [Skill][vercel-skill], [reglas][vercel-rules].

Aplicación propuesta: comprobar el botón de favorito y el de copiar, restauración del foco al
cerrar un detalle, filtros navegables, nombres técnicos extensos y fechas de Hoy/Ayer. Las pautas
de comillas, mayúsculas o elipsis se aplicarían al texto de interfaz, preservando el contenido
literal de los comandos. La virtualización se decidiría por medición y comportamiento de búsqueda,
selección y teclado, sin introducir una dependencia solo por superar un umbral orientativo.

No incluye aquí un motor de ejecución ni obliga a usar React o Tailwind: las reglas también
expresan equivalentes de HTML/CSS. Sin embargo, que un agente entienda `SKILL.md` no demuestra que
disponga de una herramienta denominada `WebFetch`. Para Codex hay que usar su capacidad real de
lectura web y registrar la revisión de las reglas consultadas. Fijar únicamente la SHA de la skill
no fija esas reglas remotas. [Skill][vercel-skill], [reglas][vercel-rules].

### Impeccable: más capacidad, más integración

La versión declarada es 4.8.0. Sus modos separan Operate, para completar tareas, de Read, para
comprender documentos. Incluye `audit`, `critique`, `harden`, `clarify`, `polish` y otras acciones;
`harden` contempla desbordamiento, estados, teclado y zoom al 200%. La documentación de Operate
prioriza consistencia y densidad útil sobre sorpresa visual. [Skill][impeccable-skill],
[Operate/Read][impeccable-operate], [harden][impeccable-harden].

El arranque pide ejecutar un launcher que usa un binario autocontenido, incluido o descargado en
su primera ejecución. Node se requiere para la vía de instalación con `npx`, no para ese motor.
La inspección de una URL usa Chrome o Edge instalado. Hay artefactos específicos para Codex y
comandos Windows, además de hooks; el README indica un paso adicional de aprobación del hook en
Codex. Es evidencia de integración prevista por el autor, no de funcionamiento comprobado en
este entorno. [Arranque][impeccable-skill], [instalación y requisitos][impeccable-readme],
[hooks Codex][impeccable-hooks].

El README también documenta consultas al catálogo remoto para nuevas direcciones y distingue
esas peticiones de su telemetría. No conviene describir el conjunto como una skill exclusivamente
Markdown ni totalmente local. [README][impeccable-readme].

Para Shiori, su valor diferencial sería una revisión delimitada de casos difíciles de lectura y
operación. Su sistema PRODUCT.md/DESIGN.md, detector y dirección visual se superponen con Taste;
no se propone incorporar el motor ni sus hooks para este prototipo. Además, la puntuación de
responsive en `audit` contempla móvil: habría que evaluar el alcance PC acordado y registrar esa
adaptación, sin presentar la puntuación original como certificación. [Skill][impeccable-skill],
[auditoría][impeccable-audit].

### Interface Design: consistencia de producto

Su alcance explícito son aplicaciones, herramientas y paneles, excluyendo marketing. Propone
reutilizar controles nativos y patrones existentes, definir tokens semánticos, elegir densidad
concreta y cubrir estados interactivos y de datos. Conserva decisiones en
`.interface-design/system.md`. El README ofrece instalación dirigida a Codex y copia manual del
directorio de la skill; el núcleo revisado es Markdown y no exige un motor propio. La generación
de referencias visuales es condicional a disponer de una herramienta de imágenes.
[Skill][interface-skill], [README][interface-readme].

Aplicación propuesta: registrar una vez altura de filas, escala de texto, ancho de lectura,
tratamiento de comandos, selección y estados de favorito; reutilizarlos en biblioteca, diario y
Agent log. No crear otro registro visual paralelo si esos acuerdos ya están en los tokens y
documentación del proyecto.

Hay diferencias que impiden mezclar reglas mecánicamente: su ejemplo de métrica usa etiqueta en
mayúsculas y su apartado de elevación propone sombras para algunos contenedores, mientras Taste
mantiene reglas propias para etiquetas y superficies de aplicación. También pide confirmar
dirección y ofrecer guardar patrones. Usar ambas como autoridades completas duplicaría decisiones
y pasos de interacción. La propuesta es conservar Taste como autoridad visual y consultar los
principios de reutilización y consistencia. [Skill][interface-skill], [Taste para apps][taste-app].

### Anthropic frontend-design: buen criterio, poco incremento

El archivo revisado propone una identidad nacida del tema, un plan compacto de color, tipografía
y composición, revisión contra el brief y autocrítica visual. Incluye vocabulario consistente
para acciones, errores que expliquen cómo continuar y estados vacíos que orienten. No prescribe
scripts ni dependencias de ejecución; las capturas se condicionan a las herramientas disponibles.
Su propia base de calidad incluye móvil. [Skill][anthropic-skill].

Para Shiori son útiles sus criterios de texto y legibilidad, pero el trabajo de dirección y
crítica ya está en Taste. No se observó en este archivo un adaptador o requisito específico de
Codex: poder leer sus instrucciones no equivale a haber probado una integración. Añadirla ahora
no resuelve una carencia identificada del visor. [Skill][anthropic-skill], [Taste][taste-skill].

### UI/UX Pro Max: catálogo consultable, no cambio de stack

El núcleo ofrece búsqueda por dominios, como UX, tipografía, iconos o gráficos, y por stack.
Distingue una consulta puntual de generar un sistema completo; permite persistir este último en
`design-system/<project-slug>/MASTER.md` y excepciones por página. Sus scripts requieren Python 3;
la plantilla declara biblioteca estándar y búsquedas locales sin red. Se revisaron las
instrucciones y la entrada del buscador, sin ejecutar ni auditar íntegramente ese código.
[Skill][uipro-skill], [plantilla][uipro-template], [buscador][uipro-search].

Hay una plantilla Codex explícita que genera `.agents/skills/ui-ux-pro-max` y configura el camino
del buscador. Esto concreta mejor la compatibilidad que una lista publicitaria de plataformas,
pero sigue sin constituir una prueba de ejecución. [Plantilla Codex][uipro-codex].

Para HTML/CSS/JS sin framework, las consultas genéricas de UX pueden servir. El inventario de
stacks incluye `html-tailwind`, pero no una opción llamada HTML/CSS/JS puro; las opciones WPF,
WinUI o JavaFX describen aplicaciones nativas, no convierten un visor web en una de ellas.
No se propone introducir Tailwind, GSAP ni un framework para aprovechar el catálogo.
[Stacks y dominios][uipro-skill].

Su generación de paletas, fuentes y estilos competiría con la dirección ya elegida. Las reglas
generales de móvil, objetivos táctiles y ausencia de desplazamiento horizontal tampoco deben
aplicarse sin contexto a un visor de PC con comandos extensos. La propuesta es consultar solo
una necesidad verificable, mantener los tokens actuales y validar el resultado en el navegador.
[Flujo y prioridades][uipro-skill].

## Uso propuesto y aceptación de escritorio

Se ha elegido instalar únicamente `web-design-guidelines`, fijada a la revisión
`1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62`. Sus instrucciones y las reglas se han leído para
la revisión del prototipo; esto no instala el motor de Impeccable ni otra dirección visual.
La disponibilidad automática de la skill corresponde al siguiente turno del host.

1. Diseñar con el recorrido de aplicación de Taste y una única fuente de tokens.
2. Revisar el código con Vercel, anotando tanto la SHA de la skill como la de `command.md`.
3. Validar a **1280, 1440 y 1920 px**, con teclado y zoom al **200%**. Estos son criterios
   propuestos para el producto PC, no una afirmación de cobertura realizada por estas skills.
4. Ejercitar búsqueda, filtros, apertura y vuelta al listado, favoritos, copia de fragmentos,
   Hoy/Ayer y Agent log; comprobar foco visible, orden de tabulación, estados vacíos/error y texto
   largo con ejemplos sintéticos. Una línea de código puede necesitar desplazamiento propio sin
   provocar desbordamiento de toda la página.
5. Consultar otra candidata solo para una carencia concreta. Revisar sus instrucciones, archivos
   que escribe, herramientas y conexiones antes de incorporarla; una licencia o una revisión del
   código no demuestra seguridad ni calidad efectiva.

Esta aceptación es una propuesta de trabajo. Leer instrucciones, ejecutar un detector y verificar
la interfaz son evidencias distintas; ninguna sustituye por sí sola las demás.

## Revisiones y licencias observadas

Los enlaces del documento fijan las revisiones consultadas, no prometen que sean las últimas
cuando se vuelva a leer. Las licencias indicadas describen los archivos observados; no extienden
automáticamente permisos a fuentes, imágenes u otros recursos recomendados.

| Fuente | Revisión consultada | Licencia observada |
|---|---|---|
| Vercel agent-skills | [`1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62`](https://github.com/vercel-labs/agent-skills/tree/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62) | El [README][vercel-readme] declara MIT; no se encontró archivo LICENSE en el [árbol de esa revisión][vercel-tree]. |
| Vercel web-interface-guidelines | [`434b7f91364665f2f733b310ec54809bf8f37937`](https://github.com/vercel-labs/web-interface-guidelines/tree/434b7f91364665f2f733b310ec54809bf8f37937) | [MIT][vercel-license]. |
| Impeccable | [`df3a4abe7d0840d5f60324812c432e00b66a4e75`](https://github.com/pbakaus/impeccable/tree/df3a4abe7d0840d5f60324812c432e00b66a4e75) | [Apache-2.0][impeccable-license]; conserva [avisos de terceros][impeccable-notice]. |
| Interface Design | [`2f9be3206855bcb2d1d0af262c8bae25cba6658d`](https://github.com/Dammyjay93/interface-design/tree/2f9be3206855bcb2d1d0af262c8bae25cba6658d) | [MIT][interface-license]. |
| Anthropic frontend-design | [`ca45fc496a3436251f191354091d557da31c15b5`](https://github.com/anthropics/skills/tree/ca45fc496a3436251f191354091d557da31c15b5/skills/frontend-design) | [Apache-2.0 en el directorio de la skill][anthropic-license]. |
| UI/UX Pro Max | [`28b3b8dee8c976df4fa3e94aed4e092ad43fcb03`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/28b3b8dee8c976df4fa3e94aed4e092ad43fcb03) | [MIT en raíz][uipro-license]; no confundirla con las licencias de otras skills del mismo repositorio. |
| Taste, base de comparación | tag v2.1.5, [`12af471f627f866411b4bd785b19646d3672784c`](https://github.com/Leonxlnx/taste-skill/tree/12af471f627f866411b4bd785b19646d3672784c) | Se consultó como referencia visual existente; no se redistribuye su contenido aquí. |

[taste-skill]: https://github.com/Leonxlnx/taste-skill/blob/12af471f627f866411b4bd785b19646d3672784c/skills/taste-skill/SKILL.md
[taste-app]: https://github.com/Leonxlnx/taste-skill/blob/12af471f627f866411b4bd785b19646d3672784c/skills/taste-skill/references/app-screens.md
[vercel-skill]: https://github.com/vercel-labs/agent-skills/blob/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62/skills/web-design-guidelines/SKILL.md
[vercel-rules]: https://github.com/vercel-labs/web-interface-guidelines/blob/434b7f91364665f2f733b310ec54809bf8f37937/command.md
[vercel-readme]: https://github.com/vercel-labs/agent-skills/blob/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62/README.md
[vercel-tree]: https://api.github.com/repos/vercel-labs/agent-skills/git/trees/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62?recursive=1
[vercel-license]: https://github.com/vercel-labs/web-interface-guidelines/blob/434b7f91364665f2f733b310ec54809bf8f37937/LICENSE
[impeccable-skill]: https://github.com/pbakaus/impeccable/blob/df3a4abe7d0840d5f60324812c432e00b66a4e75/.agents/skills/impeccable/SKILL.md
[impeccable-operate]: https://github.com/pbakaus/impeccable/blob/df3a4abe7d0840d5f60324812c432e00b66a4e75/.agents/skills/impeccable/reference/operate.md
[impeccable-harden]: https://github.com/pbakaus/impeccable/blob/df3a4abe7d0840d5f60324812c432e00b66a4e75/.agents/skills/impeccable/reference/harden.md
[impeccable-audit]: https://github.com/pbakaus/impeccable/blob/df3a4abe7d0840d5f60324812c432e00b66a4e75/.agents/skills/impeccable/reference/audit.md
[impeccable-readme]: https://github.com/pbakaus/impeccable/blob/df3a4abe7d0840d5f60324812c432e00b66a4e75/README.md
[impeccable-hooks]: https://github.com/pbakaus/impeccable/blob/df3a4abe7d0840d5f60324812c432e00b66a4e75/.codex/hooks.json
[impeccable-license]: https://github.com/pbakaus/impeccable/blob/df3a4abe7d0840d5f60324812c432e00b66a4e75/LICENSE
[impeccable-notice]: https://github.com/pbakaus/impeccable/blob/df3a4abe7d0840d5f60324812c432e00b66a4e75/NOTICE.md
[interface-skill]: https://github.com/Dammyjay93/interface-design/blob/2f9be3206855bcb2d1d0af262c8bae25cba6658d/.claude/skills/interface-design/SKILL.md
[interface-readme]: https://github.com/Dammyjay93/interface-design/blob/2f9be3206855bcb2d1d0af262c8bae25cba6658d/README.md
[interface-license]: https://github.com/Dammyjay93/interface-design/blob/2f9be3206855bcb2d1d0af262c8bae25cba6658d/LICENSE
[anthropic-skill]: https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/frontend-design/SKILL.md
[anthropic-license]: https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/frontend-design/LICENSE.txt
[uipro-skill]: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/28b3b8dee8c976df4fa3e94aed4e092ad43fcb03/.claude/skills/ui-ux-pro-max/SKILL.md
[uipro-template]: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/28b3b8dee8c976df4fa3e94aed4e092ad43fcb03/src/ui-ux-pro-max/templates/base/skill-content.md
[uipro-search]: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/28b3b8dee8c976df4fa3e94aed4e092ad43fcb03/src/ui-ux-pro-max/scripts/search.py
[uipro-codex]: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/28b3b8dee8c976df4fa3e94aed4e092ad43fcb03/src/ui-ux-pro-max/templates/platforms/codex.json
[uipro-license]: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/28b3b8dee8c976df4fa3e94aed4e092ad43fcb03/LICENSE
