# Prototipo de escritorio del visor

Estudio de la [tarea #23](https://github.com/AdanJoGoHe/Shiori/issues/23), dentro de la
[épica #22](https://github.com/AdanJoGoHe/Shiori/issues/22). Es código desechable para comparar
recorridos, conservado en la rama **codex/viewer-prototype**. No es el visor publicado ni una
implementación de favoritos, Agent log o sus APIs. No se debe integrar esta carpeta en main
como producto: la opción elegida se implementará sobre los contratos existentes.

## Abrirlo

Desde el checkout de esa rama:

    python scripts/demo-viewer-prototype.py

Abre la dirección local que imprime. Ctrl+C detiene el servidor. Solo sirve tres recursos
del prototipo y no carga configuración, notas, índice o credenciales de ninguna memoria.
No requiere instalar dependencias de frontend ni descargar fuentes.

La barra inferior permite comparar las opciones, elegir tema y simular carga, error, ausencia
de datos o una biblioteca más abundante. Está separada del diseño que se está evaluando.
Los favoritos y pendientes cambiados duran solo esta pestaña; recargar reinicia el ejemplo.

## Tres maneras de organizarlo

| Opción | Qué pone primero | Diferencia de estructura |
|---|---|---|
| A · Mesa de trabajo | Recuperar un fragmento y retomar el día. | Navegación lateral, búsqueda fija y mesa con comandos, Hoy, favoritos y última acción. |
| B · Biblioteca abierta | Encontrar una página y leer lo importante. | Navegación superior, lista de páginas frente a extractos y acceso al diario. |
| C · Cuaderno diario | Entender qué quedó hecho y qué sigue pendiente. | Navegación superior y cronología del día, con textos/favoritos al lado. |

Las opciones se enlazan con ?variant=A, ?variant=B o ?variant=C; el tema usa
&theme=light, &theme=dark o &theme=latte. Las flechas del comparador cambian de opción;
las del teclado también, excepto al escribir o usar un selector. Ctrl+K enfoca la búsqueda.

**Recomendación inicial: A.** La recuperación de un comando o texto marcado es el trabajo más
frecuente señalado por el propietario. El diario y la siguiente acción quedan cerca, sin
convertir toda la biblioteca en una cronología. B y C sirven para contrastar prioridades,
no son tres productos que mantener. La elección final sigue abierta a revisión.

## Los recorridos que se pueden probar

1. Abrir Fragmentos, elegir Comando, copiar el texto y abrir su marca en el lector.
2. Añadir una página a Favoritos desde Biblioteca o lector y encontrarla en esa vista.
3. Usar «Consultar como agente»: muestra una respuesta ficticia calculada con los mismos
   favoritos y filtros. No llama a MCP ni define todavía su contrato definitivo.
4. Abrir Agent log y distinguir ejecutado, propuesto, encontrado, visitado y desconocido.
5. Consultar Hoy/Ayer, retomar un proyecto y resolver un pendiente del ejemplo.
6. Combinar búsqueda y proyecto, probar una consulta sin resultados, escenarios y temas.

Las páginas web solo se abren por un clic explícito en el lector. Nada ejecuta los comandos.
Los datos del ejemplo no acreditan resultados o visitas reales.

## Inventario y preguntas de diseño

- Seis páginas de muestra: cinco locales y una referencia web.
- Ocho fragmentos: cuatro comandos, dos avisos importantes, una ruta y una IP de documentación.
- Cuatro avances repartidos en tres días; seis acciones de agente en tres sesiones.
- Tres pendientes y tres favoritos iniciales, en dos proyectos ficticios.
- Biblioteca: «¿Dónde está la página o el texto que necesito?».
- Fragmentos: «¿Qué puedo copiar y de dónde salió?».
- Favoritos: «¿A qué páginas quiero volver yo o mi agente?».
- Diario: «¿Qué quedó hecho ese día y qué sigue pendiente ahora?».
- Agent log: «¿Qué acciones se registraron y cuál fue su resultado?».

El día ancla es el 30 de octubre de 2026. Es un escenario fijo y marcado como ficticio; el
producto final calculará los días según la zona horaria del despliegue. El escenario abundante
añade 36 páginas de ensayo y pagina en grupos de 12; no simula una memoria personal.

## Criterio visual

Se usó Taste para pantallas de aplicación: dirección **Editorial greeting**, seed **911640397**,
con paleta y familias del producto conservadas. Su cara es el marcapáginas de Shiori y la
organización de textos que merecen recuperarse. La primera propuesta se adapta al trabajo con
conocimiento: sustituye contadores genéricos por fragmentos y resultados, sin gráficos inventados.
Las otras dos opciones son comparaciones estructurales exigidas por el estudio, no cambios de color.

El contenido importante usa la superficie de marca; los comandos conservan texto monoespaciado
y copia literal. Los títulos, navegación y texto normal no compiten con esos fragmentos.
La búsqueda queda arriba, con proyecto y alcance visibles; los controles de simulación van aparte.

La [comparación de skills](research/web-design-skills.md) explica por qué se complementó Taste
con Vercel para revisar etiquetas, foco, teclado, textos extensos y estados. No se siguió su pauta
de poner toda consulta en la URL: la memoria puede contener búsquedas privadas. En el prototipo
solo se enlazan opción, tema y sección, todos valores de demostración.

## Qué se observó y qué queda pendiente

El antes se registró desde scripts/demo-viewer.py, sobre su memoria temporal ficticia.
El inspector detectó texto menor de 11 px y un título de 46 px; el listado quedaba después de
una zona grande de controles. Es evidencia de esa muestra, no una medición de un vault real.

La revisión de escritorio usa 1280, 1440 y 1920 px, teclado y tres temas. Una emulación de
reflow a 720 píxeles CSS aproxima el espacio de un escritorio de 1440 px al 200%; no acredita
zoom nativo del navegador ni aceptación con lector de pantalla. Móvil queda fuera del alcance.

Los recorridos del prototipo se comprobaron en Chromium con datos ficticios, incluidos copiar
al portapapeles, favoritos compartidos entre vistas, historial de días, propuesta sin ejecutar,
URL sin visitar, error recuperable y lista abundante. Capturas e informes privados se mantienen
fuera del repositorio. Estos ensayos no prueban persistencia, APIs, actualización ni recuperación
de las funcionalidades futuras.

Antes de migrar pantallas hay que revisar la opción elegida y fijar los componentes compartidos:
búsqueda/alcance, navegación, fila de página/favorito, fragmento/contexto/copia, entrada de avance,
entrada de acción, estado de pendiente y lector. Las tareas #24–#36 implementan sus contratos
reales, respaldo y aceptación. El prototipo no sustituye esas tareas.
