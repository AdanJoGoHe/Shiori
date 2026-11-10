/* Throwaway UI study for issue #23. Three structures, synthetic data, memory-only mutations. */
'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
const normalize = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const titles = {inicio:'Tu mesa de trabajo', biblioteca:'Biblioteca', fragmentos:'Fragmentos', favoritos:'Favoritos', diario:'Diario', 'agent-log':'Agent log'};
const descriptions = {
  inicio:'Lo que quieres encontrar. Lo que quieres recordar.',
  biblioteca:'Páginas y conocimiento, con su contexto.',
  fragmentos:'El texto que necesitas, sin recorrer toda la página.',
  favoritos:'Las páginas a las que merece la pena volver.',
  diario:'Qué hiciste y por dónde seguir.',
  'agent-log':'Las acciones registradas detrás de cada resultado.'
};
const variants = ['A', 'B', 'C'];
const params = new URLSearchParams(location.search);
const initialTheme = ['light','dark','latte'].includes(params.get('theme')) ? params.get('theme') : 'light';
document.documentElement.dataset.theme = initialTheme;
$('#theme').value = initialTheme;
const state = {
  variant: variants.includes(params.get('variant')) ? params.get('variant') : 'A',
  view: Object.hasOwn(titles, location.hash.slice(1)) ? location.hash.slice(1) : 'inicio',
  query:'', project:'', category:'', day:'today', scenario:'full', limit:12,
  favorites:new Set(['puerto', 'actualizar', 'python-docs']), tasks:new Set()
};
const pages = [
  {id:'puerto', title:'Encontrar qué ocupa un puerto', type:'Comando', project:'laboratorio', tags:['windows','red'], description:'Localiza el proceso antes de decidir qué hacer con él.', date:'30 oct', evidence:'Ejemplo ficticio. El comando no se ha ejecutado en tu equipo.', sections:[
    {title:'Comprobar el puerto', text:'Consulta el puerto y revisa el proceso que devuelve. Esto solo lee el estado de la red.', code:'Get-NetTCPConnection -LocalPort 8080', category:'Comando'},
    {title:'Antes de cerrar un proceso', text:'Comprueba para qué sirve. Que un proceso ocupe un puerto no implica que debas detenerlo.', category:'Información importante'}
  ]},
  {id:'python', title:'Preparar un entorno Python', type:'Guía', project:'apuntes', tags:['python','entornos'], description:'Dependencias separadas y una comprobación fácil de repetir.', date:'29 oct', evidence:'Fixture de diseño; los resultados de las pruebas son simulados.', sections:[
    {title:'Crear el entorno', text:'Usa una carpeta de proyecto y un entorno independiente.', code:'python -m venv .venv', category:'Comando'},
    {title:'Ejecutar las pruebas', text:'Desde el proyecto con sus dependencias instaladas.', code:'python -m pytest -q', category:'Comando'}
  ]},
  {id:'actualizar', title:'Actualizar sin perder tus notas', type:'Conocimiento', project:'laboratorio', tags:['copias','actualizacion'], description:'Conservar datos y comprobar que puedes volver atrás.', date:'30 oct', evidence:'Documento ficticio para probar el recorrido de lectura.', sections:[
    {title:'La copia también se prueba', text:'Una copia de seguridad solo sirve si puedes restaurarla.', category:'Información importante'},
    {title:'Carpeta del ejemplo', text:'Una ruta sintética fuera del código.', code:'D:\\Projects\\demo\\notas', category:'Ruta'}
  ]},
  {id:'red', title:'Datos de la red de pruebas', type:'Nota', project:'laboratorio', tags:['red','ejemplo'], description:'Direcciones reservadas para ejemplos, sin equipos reales.', date:'28 oct', evidence:'Usa una dirección de documentación; no representa un servidor.', sections:[
    {title:'Dirección de ejemplo', text:'Referencia ficticia para el laboratorio.', code:'198.51.100.24', category:'IP'}
  ]},
  {id:'git', title:'Revisar lo que cambió en Git', type:'Comando', project:'apuntes', tags:['git','revision'], description:'Una vista breve antes de abrir el diff completo.', date:'29 oct', evidence:'Comando de solo lectura usado como muestra de interfaz.', sections:[
    {title:'Ver el resumen', text:'Muestra los archivos modificados y el tamaño del cambio.', code:'git diff --stat', category:'Comando'}
  ]},
  {id:'python-docs', title:'Documentación de Python', type:'Enlace', project:'apuntes', tags:['python','referencia'], description:'Referencia web guardada. Sin contenido descargado.', date:'29 oct', url:'https://docs.python.org/3/', evidence:'Enlace de ejemplo; guardarlo no significa que se haya visitado.', sections:[]}
];
const fragments = pages.flatMap(page => page.sections.map((section, index) => ({
  id:page.id + '-' + index, page:page.id, title:section.title, quote:section.code || section.text,
  context:section.code ? section.text : page.description,
  category:section.category, project:page.project
})));
const activity = [
  {id:'avance-lector', day:'today', time:'10:42', title:'La lectura conserva los acentos', text:'Terminada la revisión del ejemplo UTF-8. Queda comprobarlo en el editor.', project:'laboratorio', checks:'3 comprobaciones simuladas', action:'Retomar el lector', session:'lector'},
  {id:'avance-puerto', day:'today', time:'09:35', title:'Guardado el comando para revisar un puerto', text:'Comando y advertencia reunidos en una página fácil de consultar.', project:'laboratorio', checks:'Página y marca de ejemplo', page:'puerto'},
  {id:'avance-entorno', day:'yesterday', time:'17:20', title:'Preparado un entorno independiente', text:'Dependencias separadas y receta de pruebas anotada.', project:'apuntes', checks:'Entorno ficticio', page:'python'},
  {id:'avance-red', day:'earlier', time:'11:10', title:'Organizados los datos del laboratorio', text:'Ruta y dirección de ejemplo clasificadas para encontrarlas después.', project:'laboratorio', checks:'Datos de documentación', page:'red'}
];
const events = [
  {id:'evt-test', day:'today', time:'10:38', title:'Comprobación del lector', type:'Comando ejecutado', status:'Éxito', text:'3 comprobaciones del fixture completadas.', command:'python -m pytest -q', project:'laboratorio', session:'lector', page:'python'},
  {id:'evt-file', day:'today', time:'10:21', title:'Revisado el ejemplo de lectura', type:'Archivo revisado', status:'Registrado', text:'Referencia al cambio, sin guardar el contenido del archivo.', command:'ejemplo/lector.py', project:'laboratorio', session:'lector'},
  {id:'evt-visit', day:'today', time:'09:48', title:'Consultada la referencia de Python', type:'Página visitada', status:'Registrado', text:'El fixture simula una visita; no se ha abierto ahora.', url:'https://docs.python.org/3/', project:'laboratorio', session:'lector', page:'python-docs'},
  {id:'evt-proposal', day:'today', time:'09:30', title:'Comando pendiente de comprobar', type:'Comando propuesto', status:'Sin ejecutar', text:'La propuesta no demuestra ejecución ni resultado.', command:'Get-NetTCPConnection -LocalPort 8080', project:'laboratorio', session:'puerto', page:'puerto'},
  {id:'evt-link', day:'yesterday', time:'17:16', title:'Guardada una referencia para después', type:'Enlace encontrado', status:'Sin visitar', text:'Encontrar y guardar una URL no equivale a leerla.', url:'https://docs.python.org/3/', project:'apuntes', session:'entorno', page:'python-docs'},
  {id:'evt-fail', day:'yesterday', time:'17:02', title:'La comprobación no terminó', type:'Comando intentado', status:'Desconocido', text:'La sesión se interrumpió; no hay un resultado confirmado.', command:'python -m pytest -q', project:'apuntes', session:'entorno', page:'python'}
];
const tasks = [
  {id:'editor', title:'Comprobar el lector en el editor', project:'laboratorio', status:'Abierto', detail:'Retomar desde el último resultado, no desde cero.'},
  {id:'copia', title:'Ensayar una restauración', project:'laboratorio', status:'Bloqueado', detail:'Falta preparar el destino del ejemplo.'},
  {id:'entorno', title:'Anotar la versión del entorno', project:'apuntes', status:'Abierto', detail:'Conservar el dato junto a la receta.'}
];
const dateNames = {today:'Hoy · 30 de octubre', yesterday:'Ayer · 29 de octubre', earlier:'28 de octubre'};
let toastTimer;
function announce(message) {
  $('#announcement').textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#announcement').textContent = ''; }, 4000);
}
function matches(item) {
  return (!state.project || item.project === state.project) &&
    normalize(state.query).split(/\s+/).filter(Boolean).every(word => normalize(JSON.stringify(item)).includes(word));
}
function favoriteButton(id) {
  const active = state.favorites.has(id);
  return '<button class="favorite" data-favorite="' + esc(id) + '" aria-pressed="' + active + '" aria-label="' + (active ? 'Quitar de favoritos: ' : 'Añadir a favoritos: ') + esc(pages.find(page => page.id === id).title) + '"><svg width="19" height="22" viewBox="0 0 20 24" fill="' + (active ? 'currentColor' : 'none') + '" aria-hidden="true"><path d="M4 2h12v20l-6-4-6 4V2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg></button>';
}
function pageRow(page) {
  return '<article class="page-row"><div class="grow"><div class="meta">' + esc(page.type) + ' · ' + esc(page.project) + '</div><button class="page-link" data-open="' + esc(page.id) + '">' + esc(page.title) + '</button><p>' + esc(page.description) + '</p></div>' + favoriteButton(page.sourceId || page.id) + '</article>';
}
function fragmentRow(fragment) {
  const quote = fragment.category === 'Información importante' ? '<blockquote class="important-quote">' + esc(fragment.quote) + '</blockquote>' : '<pre><code>' + esc(fragment.quote) + '</code></pre>';
  return '<article class="fragment"><div class="fragment-head"><h3>' + esc(fragment.title) + '</h3><span class="tag ' + (fragment.category === 'Información importante' ? 'important' : '') + '">' + esc(fragment.category) + '</span></div>' + quote + '<p>' + esc(fragment.context) + '</p><div class="fragment-footer"><button class="copy" data-copy-fragment="' + esc(fragment.id) + '">Copiar texto</button><button class="text-action" data-fragment="' + esc(fragment.id) + '">Abrir en la página</button><span class="meta">' + esc(fragment.project) + '</span></div></article>';
}
function activityRow(item) {
  return '<article class="event"><time>' + item.time + '</time><div><h3>' + esc(item.title) + '</h3><p>' + esc(item.text) + '</p><span class="meta">' + esc(item.project) + ' · ' + esc(item.checks) + '</span>' +
    (item.page ? '<button class="text-action" data-open="' + item.page + '">Abrir página</button>' : '<button class="text-action" data-resume="' + item.project + '">Retomar el proyecto</button>') + '</div></article>';
}
function logRow(item) {
  const unknown = ['Desconocido','Sin ejecutar','Sin visitar'].includes(item.status);
  return '<article class="event"><time>' + item.time + '</time><div><div class="fragment-head"><span class="meta">' + esc(item.type) + '</span><span class="status ' + (unknown ? 'unknown' : '') + '">' + esc(item.status) + '</span></div><h3>' + esc(item.title) + '</h3><p>' + esc(item.text) + '</p>' +
    (item.command || item.url ? '<pre><code>' + esc(item.command || item.url) + '</code></pre>' : '') +
    '<div class="fragment-footer"><span class="meta">' + esc(item.project) + ' · Sesión ' + esc(item.session) + '</span><button class="text-action" data-event="' + item.id + '">Ver detalle</button></div></div></article>';
}
function taskList(limit = tasks.length) {
  const list = tasks.filter(item => !state.project || item.project === state.project).slice(0,limit);
  return list.map(item => '<div class="task"><span class="task-dot" aria-hidden="true"></span><div><p>' + esc(item.title) + '</p><small>' + (state.tasks.has(item.id) ? 'Resuelto en esta simulación' : item.status) + ' · ' + esc(item.project) + '</small></div></div>').join('') || '<p class="muted">Sin pendientes registrados en este proyecto.</p>';
}
function panel(title, href, link, content, size) {
  return '<section class="panel ' + (size || '') + '"><header class="panel-head"><h2>' + title + '</h2><a href="#' + href + '">' + link + '</a></header>' + content + '</section>';
}
function heading(title, description) {
  return '<header class="page-title"><div><h1>' + esc(title) + '</h1><p>' + esc(description) + '</p></div><time datetime="2026-10-30">Viernes, 30 oct · Día de ejemplo</time></header>';
}
function dayBar() {
  return '<div class="day-bar" role="group" aria-label="Día del registro">' + Object.entries(dateNames).map(([id, label]) => '<button data-day="' + id + '" aria-pressed="' + (state.day === id) + '">' + label.split(' · ')[0] + '</button>').join('') + '<span class="day-caption">' + dateNames[state.day] + ' · 2026</span></div>';
}
function home() {
  const important = fragments.filter(matches).filter(item => ['Comando','Información importante'].includes(item.category));
  const favorites = pages.filter(matches).filter(page => state.favorites.has(page.id));
  const today = activity.filter(matches).filter(item => item.day === 'today');
  const notes = important.slice(0,2).map(fragmentRow).join('');
  const saved = favorites.slice(0,2).map(pageRow).join('') || '<p class="muted">Sin favoritos para este proyecto.</p>';
  const daily = today.map(activityRow).join('') || '<p class="muted">Sin actividad registrada hoy.</p>';
  const dailyBrief = today.length ? today.slice(0,1).map(activityRow).join('') + (today.length > 1 ? '<p><a href="#diario">Ver ' + (today.length - 1) + ' avance más de hoy</a></p>' : '') : daily;
  const pendingNext = tasks.find(item => item.status === 'Bloqueado' && !state.tasks.has(item.id) && (!state.project || item.project === state.project));
  const nextPreview = pendingNext ? '<div class="next-preview"><span class="meta">Pendiente actual · Bloqueado</span><p>' + esc(pendingNext.title) + '</p></div>' : '';
  const recent = events.filter(matches).filter(item => state.variant !== 'C' || item.day === state.day).slice(0,1).map(logRow).join('') || '<p class="muted">Sin acciones registradas para este día.</p>';
  if (state.variant === 'B') {
    return heading('Vuelve a lo que aprendiste', 'Tus páginas a un lado. Lo importante, a la vista.') +
      '<div class="shelf"><section><header class="panel-head"><h2>Páginas a mano</h2><a href="#biblioteca">Biblioteca</a></header>' + pages.filter(matches).slice(0,2).map(pageRow).join('') +
      '<header class="panel-head"><h2>Favoritos</h2><a href="#favoritos">Ver todos</a></header>' + favorites.slice(0,1).map(pageRow).join('') + '</section><section>' +
      '<div class="reader-preview"><div class="meta">Fragmentos guardados</div><h2>Lo que no quieres volver a buscar</h2>' + notes + '</div>' +
      '<div class="panel" style="margin-top:20px"><header class="panel-head"><h2>Hoy en tu diario</h2><a href="#diario">Abrir diario</a></header>' + today.slice(0,1).map(activityRow).join('') +
      '<a class="text-action" href="#agent-log">Ver las acciones en Agent log</a></div></section></div>';
  }
  if (state.variant === 'C') {
    const dayTitle = state.day === 'today' ? 'Hoy, paso a paso' : state.day === 'yesterday' ? 'Ayer, paso a paso' : 'El 28 de octubre';
    const dayEntries = activity.filter(matches).filter(item => item.day === state.day).slice(0,1).map(activityRow).join('') || '<p class="muted">Sin actividad registrada para este día.</p>';
    return heading(dayTitle, 'Resultados del día y contexto para continuar.') +
      '<div class="notebook"><section class="day-sheet">' + dayBar() + '<div class="timeline">' + dayEntries +
      '</div><section style="margin-top:24px"><header class="panel-head"><h2>Pendientes actuales</h2><a href="#diario">Retomar</a></header>' + taskList(2) +
      '</section><section style="margin-top:24px"><header class="panel-head"><h2>Acciones del agente</h2><a href="#agent-log">Agent log</a></header>' + recent + '</section></section>' +
      '<div class="side-notes">' + panel('Textos importantes', 'fragmentos', 'Ver todos', notes) + panel('Favoritos', 'favoritos', 'Ver todos', saved) + '</div></div>';
  }
  return heading(titles.inicio, descriptions.inicio) + '<div class="desk">' +
    panel('A mano', 'fragmentos', 'Todos los fragmentos', notes, 'wide') +
    panel('Hoy', 'diario', 'Abrir diario', dailyBrief + nextPreview + '<div style="margin-top:16px"><button class="primary" data-resume="' + (state.project || 'laboratorio') + '">Retomar el proyecto</button></div>', 'narrow') +
    panel('Tus favoritos', 'favoritos', 'Ver todos', saved, 'half') +
    panel('Última acción del agente', 'agent-log', 'Abrir Agent log', recent, 'half') + '</div>';
}
function emptyState(title, text, retry) {
  return '<section class="empty"><h2>' + esc(title) + '</h2><p>' + esc(text) + '</p>' + (retry ? '<button data-retry>Reintentar</button>' : '<button data-reset>Volver al ejemplo completo</button>') + '</section>';
}
function filteredData() {
  let list = pages;
  if (state.scenario === 'dense') list = pages.concat(Array.from({length:36}, (_, index) => ({
    ...pages[index % 5], id:'ensayo-' + index, sourceId:pages[index % 5].id, title:'Ensayo ' + (index + 1) + ' · ' + pages[index % 5].title
  })));
  return list.filter(matches);
}
function render() {
  document.documentElement.dataset.variant = state.variant;
  $('#variant').value = state.variant;
  $('#scenario').value = state.scenario;
  document.querySelectorAll('nav a').forEach(link => {
    if (link.dataset.view === state.view) link.setAttribute('aria-current','page');
    else link.removeAttribute('aria-current');
  });
  $('#search-scope').textContent = state.view === 'inicio' ? 'Todo lo registrado' : titles[state.view];
  $('#query-count').textContent = '';
  let html = '';
  if (state.scenario === 'loading') {
    html = heading(titles[state.view], 'Cargando el ejemplo…') + '<section class="panel" aria-busy="true" aria-label="Contenido cargando"><h2>Preparando el contenido</h2><span class="loading-row"></span><span class="loading-row short"></span><span class="loading-row"></span></section>';
  } else if (state.scenario === 'error') {
    html = heading(titles[state.view], descriptions[state.view]) + emptyState('No se pudo cargar esta vista', 'Error simulado. La búsqueda y la navegación siguen disponibles.', true);
  } else if (state.scenario === 'empty') {
    html = heading(titles[state.view], descriptions[state.view]) + emptyState('Todavía no hay registros aquí', 'Una memoria nueva conserva sus accesos y muestra cómo empezar.');
  } else if (state.view === 'inicio' && !state.query) {
    html = home();
  } else if (state.view === 'diario') {
    const rows = activity.filter(matches).filter(item => item.day === state.day);
    html = heading('Diario', descriptions.diario) + dayBar() + '<div class="desk">' +
      panel('Qué quedó hecho', 'agent-log', 'Ver acciones', rows.length ? rows.map(activityRow).join('') : '<p class="muted">Sin actividad registrada para este día.</p>', 'wide') +
      panel('Por dónde seguir', 'diario', 'Pendientes actuales', taskList() + '<div style="margin-top:16px"><button class="primary" data-resume="' + (state.project || 'laboratorio') + '">Retomar proyecto</button></div>', 'narrow') + '</div>';
    $('#query-count').textContent = rows.length + ' avances registrados';
  } else if (state.view === 'agent-log') {
    const rows = events.filter(matches).filter(item => item.day === state.day);
    html = heading('Agent log', descriptions['agent-log']) + dayBar() +
      '<p class="result-label">Registro simulado por skill · Cobertura parcial · Solo acciones declaradas</p><div class="result-list timeline">' +
      (rows.length ? rows.map(logRow).join('') : emptyState('Sin acciones registradas', 'Eso no demuestra que no se haya trabajado.')) + '</div>';
    $('#query-count').textContent = rows.length + ' acciones';
  } else if (state.view === 'fragmentos') {
    const rows = fragments.filter(matches).filter(item => !state.category || item.category === state.category);
    html = heading('Fragmentos', descriptions.fragmentos) + '<div class="filter-bar" role="group" aria-label="Categoría del fragmento">' +
      ['','Comando','IP','Ruta','Información importante'].map(category => '<button data-category="' + category + '" aria-pressed="' + (state.category === category) + '">' + (category || 'Todos') + '</button>').join('') +
      '</div><div class="result-list">' + (rows.length ? rows.map(fragmentRow).join('') : emptyState('Sin fragmentos con estos filtros', 'Prueba otra categoría o limpia la búsqueda.')) + '</div>';
    $('#query-count').textContent = rows.length + ' fragmentos';
  } else {
    const favoritesOnly = state.view === 'favoritos';
    const rows = filteredData().filter(page => !favoritesOnly || state.favorites.has(page.id));
    const foundFragments = state.view === 'inicio' && state.query ? fragments.filter(matches) : [];
    html = heading(state.view === 'inicio' ? 'Resultados de búsqueda' : titles[state.view], descriptions[state.view]) +
      (favoritesOnly ? '<div class="filter-bar"><button class="primary" data-agent>Consultar como agente</button><span class="meta">Preferencias guardadas en esta simulación, no pruebas de verificación.</span></div>' : '') +
      '<div class="result-list">' + foundFragments.map(fragmentRow).join('') + rows.slice(0,state.limit).map(pageRow).join('') +
      (rows.length || foundFragments.length ? '' : emptyState('No encontramos coincidencias', 'La búsqueda usa el proyecto seleccionado. Puedes limpiar ambos filtros.')) +
      (rows.length > state.limit ? '<button class="load-more" data-more>Mostrar más páginas (' + Math.min(state.limit, rows.length) + ' de ' + rows.length + ')</button>' : '') + '</div>';
    $('#query-count').textContent = rows.length + ' páginas' + (foundFragments.length ? ' · ' + foundFragments.length + ' fragmentos' : '');
  }
  $('#canvas').innerHTML = html;
}
function openDetail(kind, html) {
  $('#detail-kind').textContent = kind;
  $('#detail-body').innerHTML = html;
  if (!$('#detail').open) $('#detail').showModal();
}
function openPage(id, fragmentId) {
  const page = pages.find(item => item.id === id) || filteredData().find(item => item.id === id);
  if (!page) return;
  const sections = page.sections.map((section, index) => '<section><h3>' + esc(section.title) + '</h3><p>' + esc(section.text) + '</p>' +
    (section.code ? '<pre id="mark-' + page.id + '-' + index + '"><code>' + esc(section.code) + '</code></pre>' : '<p id="mark-' + page.id + '-' + index + '"><mark>' + esc(section.text) + '</mark></p>') +
    '<span class="tag">' + esc(section.category) + '</span></section>').join('');
  openDetail('Lector · Datos ficticios', '<div class="reader-tools"><span class="meta">' + esc(page.type) + ' · ' + esc(page.project) + '</span>' + favoriteButton(page.sourceId || page.id) + '</div><h2>' + esc(page.title) + '</h2><p class="muted">' + esc(page.description) + '</p>' +
    (page.url ? '<p><a href="' + esc(page.url) + '" target="_blank" rel="noopener noreferrer">Abrir referencia web</a></p>' : sections) +
    '<h3>Procedencia</h3><p>' + esc(page.evidence) + '</p>');
  if (fragmentId) {
    const mark = document.getElementById('mark-' + fragmentId);
    if (mark) { mark.classList.add('selected-mark'); mark.scrollIntoView({block:'center'}); }
  }
}
function agentPreview() {
  const favorites = pages.filter(matches).filter(page => state.favorites.has(page.id)).map(page => ({
    id:page.id, title:page.title, kind:page.type, project:page.project,
    reference:page.url || 'pagina:' + page.id, excerpt:page.description, verification:'ejemplo-no-verificado'
  }));
  openDetail('Vista para IA · Simulación', '<h2>Los mismos favoritos, con contexto</h2><p>Respuesta de ejemplo acotada a los filtros actuales. No es una llamada MCP real.</p><pre><code>' +
    esc(JSON.stringify({prototype:true, scope:'synthetic', count:favorites.length, items:favorites}, null, 2)) + '</code></pre>');
}
function resume(project) {
  const pending = tasks.filter(item => item.project === project && !state.tasks.has(item.id));
  openDetail('Retomar proyecto · Simulación', '<h2>' + esc(project === 'laboratorio' ? 'Continuar con el lector' : 'Continuar con los apuntes') + '</h2><p>Último resultado: ' +
    esc(activity.find(item => item.project === project).title) + '.</p><h3>Pendientes actuales</h3>' +
    pending.map(item => '<div class="task"><div><h3>' + esc(item.title) + '</h3><p>' + esc(item.detail) + '</p><button data-resolve="' + item.id + '">Marcar resuelto en el ejemplo</button></div></div>').join('') +
    (!pending.length ? '<p>Sin pendientes activos en esta simulación.</p>' : '') + '<p class="meta">Estado de ejemplo. No se ha modificado ningún diario real.</p>');
}
function changeVariant(variant) {
  state.variant = variant;
  const url = new URL(location.href); url.searchParams.set('variant', variant); history.replaceState(null,'',url);
  render();
  announce('Variante ' + variant + '. Los filtros y favoritos de ejemplo se conservan.');
}
document.addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.favorite) {
    const id = button.dataset.favorite;
    if (state.favorites.has(id)) state.favorites.delete(id); else state.favorites.add(id);
    const active = state.favorites.has(id);
    render();
    document.querySelectorAll('[data-favorite="' + id + '"]').forEach(item => {
      item.setAttribute('aria-pressed', String(active));
      item.setAttribute('aria-label', (active ? 'Quitar de favoritos: ' : 'Añadir a favoritos: ') + pages.find(page => page.id === id).title);
      item.querySelector('svg').setAttribute('fill', active ? 'currentColor' : 'none');
    });
    const focusRoot = $('#detail').open ? $('#detail') : $('#canvas');
    (focusRoot.querySelector('[data-favorite="' + id + '"]') || $('#canvas')).focus({preventScroll:true});
    announce(active ? 'Añadido a favoritos de esta pestaña.' : 'Quitado de favoritos del ejemplo.');
  } else if (button.dataset.open) openPage(button.dataset.open);
  else if (button.dataset.fragment) {
    const item = fragments.find(fragment => fragment.id === button.dataset.fragment); openPage(item.page, item.id);
  } else if (button.dataset.copyFragment) {
    const item = fragments.find(fragment => fragment.id === button.dataset.copyFragment);
    try { await navigator.clipboard.writeText(item.quote); announce('Texto copiado, sin añadir contexto.'); }
    catch { openDetail('Copiar texto', '<h2>Selecciona y copia el fragmento</h2><pre><code>' + esc(item.quote) + '</code></pre>'); }
  } else if (button.dataset.day) { state.day = button.dataset.day; render(); }
  else if (Object.hasOwn(button.dataset,'category')) { state.category = button.dataset.category; render(); }
  else if (button.dataset.resume) resume(button.dataset.resume);
  else if (button.dataset.resolve) {
    const task = tasks.find(item => item.id === button.dataset.resolve); state.tasks.add(task.id); render(); resume(task.project);
  } else if (button.dataset.event) {
    const item = events.find(row => row.id === button.dataset.event);
    openDetail('Acción registrada · Simulación', '<h2>' + esc(item.title) + '</h2><p>' + esc(item.type) + ' · ' + esc(item.status) + '</p><p>' + esc(item.text) +
      '</p><pre><code>' + esc(item.command || item.url) + '</code></pre><p class="meta">Declarado por skill de ejemplo · ' + esc(item.project) + ' · Sesión ' + esc(item.session) + '</p>' +
      (item.page ? '<button data-open="' + item.page + '">Abrir página relacionada</button>' : ''));
  } else if (Object.hasOwn(button.dataset,'agent')) agentPreview();
  else if (Object.hasOwn(button.dataset,'more')) { state.limit += 12; render(); }
  else if (Object.hasOwn(button.dataset,'retry') || Object.hasOwn(button.dataset,'reset')) {
    state.scenario = 'full'; state.query = ''; state.project = ''; state.category = ''; $('#query').value = ''; $('#project').value = ''; render();
  }
});
$('#query').addEventListener('input', event => { state.query = event.target.value; state.limit = 12; render(); });
$('#clear-query').addEventListener('click', () => { state.query = ''; $('#query').value = ''; render(); $('#query').focus(); });
$('#project').addEventListener('change', event => { state.project = event.target.value; state.limit = 12; render(); });
$('#theme').addEventListener('change', event => {
  document.documentElement.dataset.theme = event.target.value;
  const url = new URL(location.href); url.searchParams.set('theme', event.target.value); history.replaceState(null,'',url);
});
$('#scenario').addEventListener('change', event => { state.scenario = event.target.value; state.limit = 12; render(); });
$('#variant').addEventListener('change', event => changeVariant(event.target.value));
$('#previous-variant').addEventListener('click', () => changeVariant(variants[(variants.indexOf(state.variant)+2)%3]));
$('#next-variant').addEventListener('click', () => changeVariant(variants[(variants.indexOf(state.variant)+1)%3]));
$('#close-detail').addEventListener('click', () => $('#detail').close());
$('#menu').addEventListener('click', () => {
  const open = $('#navigation').classList.toggle('open'); $('#menu').setAttribute('aria-expanded',String(open));
});
window.addEventListener('hashchange', () => {
  const view = location.hash.slice(1); if (!Object.hasOwn(titles, view)) return;
  state.view = view; state.limit = 12;
  $('#navigation').classList.remove('open'); $('#menu').setAttribute('aria-expanded','false'); render();
  const title = $('#canvas h1'); title.tabIndex = -1; title.focus({preventScroll:true}); window.scrollTo(0,0);
});
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); $('#query').focus(); }
  if (!$('#detail').open && !event.target.closest('input,textarea,select,[contenteditable="true"]') && ['ArrowLeft','ArrowRight'].includes(event.key)) {
    event.preventDefault(); changeVariant(variants[(variants.indexOf(state.variant)+(event.key === 'ArrowRight' ? 1 : 2))%3]);
  }
});
render();
