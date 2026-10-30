"use strict";
const $ = id => document.getElementById(id);
$("theme").value = document.documentElement.dataset.theme || "light";
$("theme").onchange = () => {
  document.documentElement.dataset.theme = $("theme").value;
  try {
    localStorage.setItem("second-brain-theme", $("theme").value);
  } catch { /* A temporary choice still applies when storage is blocked. */ }
};
const names = {
  documentation: "Documentación",
  note: "Conocimiento",
  journal: "Diario"
};
const labels = {
  verified: "Verificado",
  unverified: "Sin verificar",
  draft: "Borrador",
  obsolete: "Obsoleto",
  superseded: "Sustituido",
  command: "Comando",
  knowledge: "Conocimiento",
  troubleshooting: "Resolución de problemas",
  decision: "Decisión",
  lesson: "Lección",
  preference: "Preferencia",
  profile: "Perfil"
};
const state = {
  screen: "inicio",
  kind: "",
  categories: [],
  tags: [],
  offset: 0,
  next: null,
  selected: null
};
let readerMarks;
let requestNumber = 0,
  readerNumber = 0,
  timer;
const filterKeys = ["source", "project", "type", "status", "source_agent", "from", "to", "sort"];
const dateText = value => value ? new Date(value).toLocaleDateString("es-ES") : "Fecha desconocida";

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

// Identity describes destinations/content, independently of verification or highlight colors.
const identities = {
  inicio: ["🗂", "inicio"], biblioteca: ["📚", "biblioteca"], fragmentos: ["🏷", "fragmentos"], // taste-skill-ignore: owner-requested identity symbols.
  favoritos: ["🔖", "favoritos"], diario: ["📓", "diario"], "agent-log": ["📋", "agent-log"], // taste-skill-ignore: owner-requested identity symbols.
  documentation: ["📄", "biblioteca"], note: ["📘", "biblioteca"], journal: ["📓", "diario"], // taste-skill-ignore: owner-requested identity symbols.
  comando: ["⌨", "inicio"], "direccion-ip": ["🌐", "biblioteca"], ruta: ["📂", "diario"], // taste-skill-ignore: owner-requested identity symbols.
  "informacion-importante": ["📌", "fragmentos"] // taste-skill-ignore: owner-requested identity symbols.
};
function identify(node, key) {
  const identity = identities[key];
  if (!identity) return;
  node.dataset.identity = identity[1];
  const symbol = element("span", identity[0], "identity-symbol");
  symbol.setAttribute("aria-hidden", "true");
  node.prepend(symbol);
}
// Keep queries in this tab's history state, never in shareable URLs or localStorage.
const screens = {
  inicio: ["Inicio", "Lo que quieres tener a mano."],
  biblioteca: ["Biblioteca", "Documentación y conocimiento, con su contexto."],
  fragmentos: ["Fragmentos", "Comandos, IPs, rutas y textos importantes, listos para recuperar."],
  diario: ["Diario", "Lo que avanzaste y el siguiente paso para retomarlo."],
  favoritos: ["Favoritos", "Tus páginas a mano."],
  "agent-log": ["Agent log", "Las acciones del agente, con su resultado."]
};
let deployment, restoring = false, routeSequence = 0, fragmentCategories = [];
function snapshot() {
  return {viewer: true, screen: state.screen, kind: state.kind, tags: [...state.tags], categories: [...state.categories],
    offset: state.offset, selected: state.selected, markId: state.markId || null,
    query: $("search").value, view: $("view").value, color: $("fragment-color").value,
    filters: Object.fromEntries(filterKeys.map(key => [key, $(key).value])),
    journal: Object.fromEntries(["journal-project", "journal-from", "journal-to", "journal-task-filter"].map(key => [key, $(key).value])),
    focusId: document.activeElement.closest?.(".result")?.dataset.id, focusMark: document.activeElement.closest?.(".fragment-result")?.dataset.markId,
    y: window.scrollY, resultsScroll: $("results").scrollTop};
}
function remember() { if (!restoring) history.replaceState(snapshot(), ""); }
function resetReader() {
  readerNumber++;
  readerMarks?.reset();
  state.selected = null; state.markId = null;
  document.body.classList.remove("reading");
  $("reader-empty").hidden = false; $("reader-content").hidden = true;
}
function showScreen() {
  const screen = state.screen, library = ["biblioteca", "fragmentos"].includes(screen);
  document.body.dataset.screen = screen;
  document.querySelector(".masthead").dataset.identity = screen;
  $("screen-symbol").textContent = identities[screen][0];
  document.querySelector(".masthead h1").textContent = screens[screen][0];
  document.querySelector(".subtitle").textContent = screens[screen][1];
  document.title = "Shiori · " + screens[screen][0];
  $("home-panel").hidden = screen !== "inicio";
  $("upcoming-panel").hidden = !["favoritos", "agent-log"].includes(screen);
  document.querySelector(".toolbar").hidden = !library;
  $("category-manager").hidden = !library;
  document.querySelector(".workspace").hidden = !library && !(screen === "inicio" && state.selected);
  const fragments = $("view").value === "fragments";
  $("fragment-filters").hidden = !fragments;
  $("fragment-color-wrap").hidden = !fragments;
  $("fragment-shortcuts").hidden = !fragments;
  $("search-context").textContent = fragments ? "Texto marcado y categorías" : "Documentación y conocimiento";
  for (const button of document.querySelectorAll(".destination")) {
    button.classList.toggle("active", button.dataset.screen === screen);
    if (button.dataset.screen === screen) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  for (const button of document.querySelectorAll(".collection")) button.setAttribute("aria-pressed", String(button.dataset.kind === state.kind && library));
}
async function navigate(screen, kind = "", record = true) {
  const route = ++routeSequence;
  restoring = false;
  clearTimeout(timer);
  if (record) remember();
  resetReader();
  state.screen = screen; state.kind = screen === "diario" ? "journal" : kind;
  state.offset = 0; state.tags = []; state.categories = [];
  $("fragment-color").value = "";
  for (const key of filterKeys) $(key).value = key === "sort" ? "relevance" : "";
  $("view").value = screen === "fragmentos" ? "fragments" : "documents";
  if (record) history.pushState(snapshot(), "", "#" + screen);
  await load();
  if (route !== routeSequence) return;
  window.scrollTo(0, 0);
  document.querySelector(".masthead h1").focus({preventScroll: true});
}
function pageResult(item) {
  const button = element("button", undefined, "result" + (state.selected === item.id ? " active" : ""));
  button.setAttribute("aria-pressed", String(state.selected === item.id));
  button.dataset.id = item.id;
  const kind = element("span", names[item.kind] + " / " + item.source, "kind identity-label");
  identify(kind, item.kind);
  button.append(kind, element("h3", item.title),
    element("p", item.preview), element("div", dateText(item.updated_at) + (item.metadata.tags?.length ? " · " + item.metadata.tags.join(" / ") : ""), "result-foot"));
  button.onclick = () => openItem(item.id);
  return button;
}
function shortcuts(container, categories, home = false) {
  container.replaceChildren();
  for (const key of ["comando", "direccion-ip", "ruta", "informacion-importante"]) {
    const category = categories.find(row => row.id === key && !row.archived);
    if (!category) continue;
    const button = element("button", category.label, "shortcut");
    identify(button, key);
    button.type = "button";
    button.setAttribute("aria-pressed", String(!home && state.categories.includes(key)));
    button.onclick = async () => {
      if (home) await navigate("fragmentos");
      state.categories = [key]; state.offset = 0;
      load();
    };
    container.append(button);
  }
}
function activeFilters() {
  const target = $("active-filters"); target.replaceChildren();
  const chip = (label, remove) => {
    const button = element("button", label + " ×", "tag");
    button.type = "button"; button.setAttribute("aria-label", "Quitar filtro: " + label);
    button.onclick = () => { remove(); state.offset = 0; load(); };
    target.append(button);
  };
  if (state.kind) chip(names[state.kind], () => { state.kind = ""; });
  if ($("search").value) chip("Texto: " + $("search").value, () => { $("search").value = ""; });
  for (const key of filterKeys) {
    const input = $(key);
    if (input.value && !(key === "sort" && input.value === "relevance"))
      chip(input.closest("label").firstChild.textContent + ": " + (input.selectedOptions?.[0]?.textContent || input.value), () => { input.value = key === "sort" ? "relevance" : ""; });
  }
  for (const tag of state.tags) chip("Etiqueta: " + (tag === "__none__" ? "Sin etiquetas" : tag), () => { state.tags = state.tags.filter(value => value !== tag); });
  if ($("view").value === "fragments") {
    for (const category of state.categories) chip("Categoría: " + (fragmentCategories.find(row => row.id === category)?.label || (category === "__none__" ? "Sin categoría" : category)), () => { state.categories = state.categories.filter(value => value !== category); });
    if ($("fragment-color").value) chip(colorNames[$("fragment-color").value], () => { $("fragment-color").value = ""; });
  }
}
async function viewerInfo(refresh = false) {
  if (!deployment || refresh) deployment = await api("api/viewer-info");
  const scope = deployment.scope === "work" ? "de trabajo" : "personal";
  $("memory-scope").textContent = "Memoria " + scope;
  $("deployment-label").textContent = "Markdown · Local · " + (deployment.scope === "work" ? "Trabajo" : "Personal");
  return deployment;
}
async function loadHome(number) {
  const sections = ["home-fragments", "home-pages", "home-journal"];
  for (const name of sections) { $(name).replaceChildren(element("p", "Leyendo…", "home-message")); $(name).setAttribute("aria-busy", "true"); }
  const requests = [
    api("api/items?view=fragments&sort=updated"),
    api("api/items?sort=updated"),
    viewerInfo(true).then(info => api("api/journal?" + new URLSearchParams({start_date: info.today, end_date: info.today})))
  ];
  await Promise.all(requests.map(async (request, index) => {
    const target = $(sections[index]);
    try {
      const data = await request;
      if (number !== requestNumber) return;
      target.replaceChildren();
      if (index === 0) {
        shortcuts($("home-shortcuts"), data.facets.category || [], true);
        for (const item of data.items.slice(0, 2)) target.append(fragmentResult(item, data.facets.category, true));
        if (!data.items.length) target.append(element("p", ["partial", "limited", "unavailable"].includes(data.diagnostics?.status) ? "No se pudo confirmar qué textos están disponibles. Abre Fragmentos para revisar el diagnóstico." : "Todavía no hay textos marcados. Abre una página y guarda sus partes útiles.", "home-message"));
      } else if (index === 1) {
        for (const item of data.items.slice(0, 2)) target.append(pageResult(item));
        if (!data.items.length) target.append(element("p", ["partial", "limited", "unavailable"].includes(data.diagnostics?.status) ? "No se pudo confirmar qué páginas están disponibles. Abre Biblioteca para revisar el diagnóstico." : "Todavía no hay páginas disponibles. Añade notas o una fuente de documentación.", "home-message"));
      } else {
        target.append(element("p", data.start_date, "home-date"));
        for (const item of data.items.filter(row => !row.superseded_by).slice(0, 2)) {
          const row = element("div", undefined, "home-advance");
          row.append(element("h3", item.title));
          if (item.summary !== item.title) row.append(element("p", item.summary));
          if (item.project) row.append(element("span", item.project, "result-foot"));
          target.append(row);
        }
        if (!target.querySelector(".home-advance")) target.append(element("p", "Sin actividad registrada hoy.", "home-message"));
      }
      if (data.truncated || data.next_offset !== null || data.error_count || ["partial", "limited", "unavailable"].includes(data.diagnostics?.status))
        target.append(element("p", "Vista resumida o incompleta. Abre la sección para consultar más y revisar sus avisos.", "home-message"));
    } catch {
      if (number !== requestNumber) return;
      target.replaceChildren(element("p", "No se pudo leer esta sección.", "home-message"));
      const retry = element("button", "Reintentar", "quiet"); retry.onclick = () => load(); target.append(retry);
    } finally { if (number === requestNumber) target.setAttribute("aria-busy", "false"); }
  }));
}
function warning(text) {
  $("warning").textContent = text;
  $("warning").hidden = !text;
}
function catalogWarning(diagnosis) {
  const messages = {
    unavailable: "No se pueden leer las fuentes seleccionadas.",
    partial: "Lectura parcial: los resultados disponibles siguen accesibles; la búsqueda está incompleta.",
    limited: "Catálogo incompleto: se alcanzó el límite de escaneo. Selecciona una colección u origen más pequeño."
  };
  let text = messages[diagnosis.status] || "";
  if (text) {
    text += " Códigos: " + diagnosis.codes.join(", ") + ".";
    if (diagnosis.codes.some(code => code !== "scan-limit"))
      text += " Si persiste, revisa la configuración seleccionada con doctor --catalog y paths; tras corregirla o actualizar el programa, reinicia el visor desde su terminal.";
  }
  warning(text);
  if (text) {
    const retry = element("button", "Reintentar lectura", "quiet");
    retry.type = "button";
    retry.onclick = () => $("refresh").click();
    $("warning").append(" ", retry);
  }
}
async function api(path, method = "GET", payload) {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "omit",
    method,
    ...(payload === undefined ? {} : {headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)})
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "No se pudo cargar el contenido.");
    error.status = response.status;
    throw error;
  }
  return data;
}

let editingCategory = null, categoriesBusy = false;
const colorNames = {yellow: "Amarillo", green: "Verde", blue: "Azul", pink: "Rosa", orange: "Naranja", violet: "Violeta"};

function categoryMessage(text) {
  $("category-message").textContent = text;
}
function resetCategoryForm() {
  editingCategory = null;
  $("category-form").reset();
  $("category-form-title").textContent = "Nueva categoría";
  $("category-save").textContent = "Crear categoría";
  $("category-cancel").hidden = true;
}
function categoryBusy(busy) {
  categoriesBusy = busy;
  for (const control of $("category-manager").querySelectorAll("button, input, select")) control.disabled = busy;
  $("category-manager").setAttribute("aria-busy", String(busy));
}
async function loadCategories() {
  const data = await api("api/categories");
  const list = $("category-list");
  list.replaceChildren();
  for (const item of data.items) {
    const row = element("div", undefined, "category-row");
    const badge = element("span", item.label, "category-badge");
    badge.dataset.color = item.color;
    row.append(badge, element("span", `${colorNames[item.color]} · ${item.uses} marcas${item.archived ? " · Archivada" : ""}`, "category-description"));
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", item.label);
    const edit = element("button", "Editar", "quiet");
    edit.type = "button";
    edit.onclick = () => {
      editingCategory = item;
      $("category-name").value = item.label;
      $("category-color").value = item.color;
      $("category-form-title").textContent = "Editar categoría";
      $("category-save").textContent = "Guardar cambios";
      $("category-cancel").hidden = false;
      categoryMessage("");
      $("category-name").focus();
    };
    const archive = element("button", item.archived ? "Restaurar" : "Archivar", "quiet");
    archive.type = "button";
    archive.onclick = () => mutateCategory({...item, archived: !item.archived});
    row.append(edit, archive);
    list.append(row);
  }
  if (!data.items.length) list.append(element("p", "Aún no hay categorías."));
  if (readerMarks?.doc) {
    const selected = Array.from($("mark-tags").querySelectorAll("input:checked")).map(n => n.value);
    readerMarks.categories = data.items;
    readerMarks.render();
    if (readerMarks.draft) readerMarks.tagChoices(selected);
  }
}
async function mutateCategory(item, create = false) {
  if (categoriesBusy) return;
  categoryBusy(true);
  categoryMessage("Guardando…");
  let saved = false;
  try {
    const payload = {label: item.label, color: item.color};
    if (!create) Object.assign(payload, {version: item.version, archived: item.archived});
    await api("api/categories" + (create ? "" : "?" + new URLSearchParams({id: item.id})), create ? "POST" : "PATCH", payload);
    saved = true;
    resetCategoryForm();
    await loadCategories();
    categoryMessage(item.archived ? "Categoría archivada. Las marcas existentes se conservan." : "Categoría guardada.");
  } catch (error) {
    categoryMessage((saved ? "Guardado, pero no se pudo actualizar la lista. " : "") + error.message + (error.status === 409 ? " Cancela la edición y vuelve a abrir la categoría para revisar la versión actual." : ""));
  } finally {
    categoryBusy(false);
    if (saved) $("category-name").focus();
  }
}
$("category-form").onsubmit = event => {
  event.preventDefault();
  mutateCategory({...editingCategory, label: $("category-name").value, color: $("category-color").value}, !editingCategory);
};
$("category-cancel").onclick = () => { resetCategoryForm(); $("category-name").focus(); };
$("category-refresh").onclick = async () => {
  if (categoriesBusy) return;
  categoryBusy(true);
  try { await loadCategories(); categoryMessage("Categorías actualizadas. El formulario conserva tus cambios."); }
  catch (error) { categoryMessage(error.message); }
  finally { categoryBusy(false); }
};
$("category-manager").ontoggle = () => {
  if ($("category-manager").open && !$("category-list").children.length) $("category-refresh").click();
};

function options(key, values) {
  const select = $(key),
    current = select.value,
    first = select.options[0].textContent;
  select.replaceChildren(new Option(first, ""));
  if (key !== "source") select.add(new Option("Sin dato", "__none__"));
  for (const value of values || []) select.add(new Option(labels[value] || value, value));
  select.value = Array.from(select.options).some(o => o.value === current) ? current : "";
}

function renderTags(values) {
  const container = $("tags");
  container.replaceChildren();
  for (const value of [...new Set([...(values || []), ...state.tags])]) {
    const button = element("button", value === "__none__" ? "Sin etiquetas" : value, "tag" + (state.tags.includes(value) ? " selected" : ""));
    button.type = "button";
    button.setAttribute("aria-pressed", String(state.tags.includes(value)));
    button.onclick = () => {
      state.tags = state.tags.includes(value) ? state.tags.filter(t => t !== value) : [...state.tags, value];
      state.offset = 0;
      load();
    };
    container.append(button);
  }
  if (!(values || []).includes("__none__") && !state.tags.includes("__none__")) {
    const button = element("button", "Sin etiquetas", "tag");
    button.onclick = () => {
      state.tags.push("__none__");
      state.offset = 0;
      load();
    };
    container.append(button);
  }
}
function renderFragmentCategories(values) {
  const container = $("fragment-categories");
  const focused = container.contains(document.activeElement) ? document.activeElement.dataset.category : null;
  container.replaceChildren();
  for (const category of [...values, {id: "__none__", label: "Sin categoría"}]) {
    const button = element("button", category.label + (category.archived ? " (archivada)" : ""), "tag" + (state.categories.includes(category.id) ? " selected" : ""));
    button.type = "button";
    button.dataset.category = category.id;
    button.setAttribute("aria-pressed", String(state.categories.includes(category.id)));
    button.onclick = () => {
      state.categories = state.categories.includes(category.id) ? state.categories.filter(id => id !== category.id) : [...state.categories, category.id];
      state.offset = 0;
      load();
    };
    container.append(button);
    if (focused === category.id) button.focus({preventScroll: true});
  }
}
function fragmentResult(item, categories, compact = false) {
  const mark = item.annotation, row = element("article", undefined, "fragment-result");
  row.dataset.markId = mark.id;
  if (mark.title) row.append(element("h3", mark.title));
  if (mark.description) row.append(element("p", mark.description, "mark-description"));
  row.append(element("p", item.context_before, "fragment-context"));
  const quote = element(mark.tags.includes("comando") || mark.tags.includes("ruta") || mark.tags.includes("direccion-ip") ? "pre" : "blockquote", undefined, "fragment-quote");
  const text = element("mark", mark.quote, "reader-mark");
  text.dataset.color = mark.color;
  quote.append(text);
  row.append(quote);
  if (!compact) row.append(element("p", item.context_after, "fragment-context"));
  const categoryText = mark.tags.map(id => { const c = categories.find(c => c.id === id); return (c?.label || id) + (c?.archived ? " (archivada)" : ""); }).join(" / ") || "Sin categoría";
  row.append(element("p", categoryText + (compact ? " · " + item.title : ""), "result-foot"));
  if (!compact) row.append(element("p", `${item.title} · ${names[item.kind]} · ${colorNames[mark.color]} · Marca: ${dateText(mark.updated_at)}`, "result-foot"));
  if (mark.anchor.status !== "resolved") {
    const reasons = {missing: "texto desaparecido", ambiguous: "texto ambiguo", "context-changed": "contexto cambiado", unavailable: "documento no disponible"};
    row.append(element("p", "Cita y contexto guardados. Anclaje pendiente de reparación: " + (reasons[mark.anchor.reason] || "destino sin confirmar"), "fragment-context"));
  }
  const copy = element("button", "Copiar fragmento", "quiet");
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(mark.quote); $("copy-message").textContent = "Fragmento copiado."; }
    catch { $("copy-message").textContent = "No se pudo copiar. Selecciona el texto del fragmento y cópialo con el teclado."; }
  };
  const open = element("button", mark.anchor.status === "resolved" ? "Abrir ubicación" : "Revisar marca", "quiet");
  open.onclick = () => openItem(item.id, mark.id);
  row.append(copy, open);
  return row;
}
async function load() {
  const number = ++requestNumber;
  JournalUI.hide();
  showScreen();
  remember();
  if (state.screen === "inicio") { warning(""); return loadHome(number); }
  if (["favoritos", "agent-log"].includes(state.screen)) {
    warning("");
    $("upcoming-title").textContent = state.screen === "favoritos" ? "Favoritos persistentes · pendiente" : "Registro de acciones · pendiente";
    $("upcoming-description").textContent = state.screen === "favoritos" ? "Guardar y recuperar páginas desde el visor y la IA llegará con el sistema de favoritos. Aún no se guardan favoritos aquí." : "Aquí podrás consultar comandos, visitas y enlaces registrados por el agente. El registro y sus consultas todavía no están implementados.";
    return;
  }
  if (state.kind === "journal") {
    warning("");
    JournalUI.show();
    return JournalUI.load();
  }
  $("results").setAttribute("aria-busy", "true");
  $("count").textContent = "Buscando…";
  const params = new URLSearchParams();
  const fragments = $("view").value === "fragments";
  params.set("view", $("view").value);
  if (fragments) {
    for (const id of state.categories) params.append("category", id);
    if ($("fragment-color").value) params.set("color", $("fragment-color").value);
  }
  if ($("search").value) params.set("q", $("search").value);
  if (state.kind) params.set("kind", state.kind);
  for (const key of filterKeys)
    if ($(key).value) params.set(key, $(key).value);
  for (const tag of state.tags) params.append("tag", tag);
  params.set("offset", String(state.offset));
  try {
    const data = await api("api/items?" + params);
    if (number !== requestNumber) return;
    if (!data.diagnostics) throw new Error("Reinicia el visor para cargar la versión actual del servidor y vuelve a actualizar.");
    for (const key of ["source", "project", "type", "status", "source_agent"]) options(key, data.facets[key]);
    renderTags(data.facets.tag);
    fragmentCategories = data.facets.category || [];
    renderFragmentCategories(fragmentCategories);
    shortcuts($("fragment-shortcuts"), fragmentCategories);
    activeFilters();
    state.next = data.next_offset;
    const incomplete = ["partial", "limited", "unavailable"].includes(data.diagnostics.status);
    $("count").textContent = data.result_state === "unavailable" ? "No disponible" :
      data.total + " resultado" + (data.total === 1 ? "" : "s") + (incomplete ? " · incompletos" : "");
    $("collection-title").textContent = fragments ? "Fragmentos marcados" : names[state.kind] || "Todo el contenido";
    $("page").textContent = data.total ? `${state.offset+1}–${Math.min(state.offset+20,data.total)}` : "";
    $("prev").disabled = state.offset === 0;
    $("next").disabled = state.next === null;
    const results = $("results");
    results.replaceChildren();
    if (!data.items.length) {
      const messages = {
        "empty-catalog": "La colección seleccionada está vacía. Añade notas o configura una fuente de documentación.",
        "no-matches": fragments ? "No hay fragmentos marcados con estos filtros. Marca texto en un documento o cambia la selección." : "No hay resultados con estos filtros. Prueba otro término o limpia la selección.",
        unavailable: "No se pudo leer el contenido. Consulta el aviso de diagnóstico y reintenta la lectura.",
        partial: "No hay coincidencias entre el contenido que se pudo leer. La búsqueda está incompleta.",
        limited: "No hay coincidencias en la parte examinada. El límite de escaneo impide confirmar el resultado."
      };
      results.append(element("p", messages[data.result_state] || "No se pudo completar la lectura.", "no-results"));
    }
    for (const item of data.items) {
      if (fragments) { results.append(fragmentResult(item, data.facets.category)); continue; }
      results.append(pageResult(item));
    }
    catalogWarning(data.diagnostics);
    remember();
  } catch (error) {
    if (number !== requestNumber) return;
    warning(error.message);
    $("count").textContent = "No disponible";
    $("results").replaceChildren(element("p", "No se pudieron cargar los resultados. Vuelve a actualizar; si persiste, revisa la configuración y reinicia el visor.", "no-results"));
  } finally {
    if (number === requestNumber) $("results").setAttribute("aria-busy", "false");
  }
}
async function openItem(id, markId = null, record = true) {
  if (record) { routeSequence++; restoring = false; remember(); }
  state.selected = id; state.markId = markId;
  if (record) history.pushState(snapshot(), "");
  document.querySelector(".workspace").hidden = false;
  const number = ++readerNumber;
  readerMarks.reset();
  state.selected = id;
  document.body.classList.add("reading");
  $("reader-empty").hidden = true;
  $("reader-content").hidden = false;
  $("reader-title").textContent = "Cargando documento…";
  $("reader-body").replaceChildren();
  try {
    const data = await api("api/content?" + new URLSearchParams({
      id
    }));
    if (number !== readerNumber) return;
    const item = data.item;
    $("reader-source").textContent = names[item.kind] + " / " + item.source + " / " + item.path;
    $("reader-title").textContent = item.title;
    const meta = $("reader-meta");
    meta.replaceChildren(element("div", dateText(item.updated_at) + (item.metadata.status ? " · " + (labels[item.metadata.status] || item.metadata.status) : "") + (item.metadata.project ? " · " + item.metadata.project : "")));
    for (const tag of item.metadata.tags || []) {
      const button = element("button", tag, "tag");
      button.onclick = () => {
        state.tags = [tag];
        state.offset = 0;
        document.body.classList.remove("reading");
        load();
      };
      meta.append(button);
    }
    if (item.metadata.source_agent) meta.append(element("div", "Agente: " + item.metadata.source_agent));
    if (item.metadata.source_refs?.length) meta.append(element("div", "Referencias: " + item.metadata.source_refs.join(" · ")));
    $("reader-body").innerHTML = data.html;
    const toc = $("toc");
    toc.replaceChildren();
    for (const heading of data.headings) {
      const link = element("a", heading.title);
      link.href = "#" + heading.id;
      toc.append(link);
    }
    $("toc-wrap").hidden = !data.headings.length;
    const related = $("related");
    related.replaceChildren();
    for (const note of data.related) {
      const button = element("button", note.title);
      button.onclick = () => openItem(note.id);
      related.append(button);
    }
    $("related-wrap").hidden = !data.related.length;
    await readerMarks.open(data);
    if (number !== readerNumber) return;
    for (const button of document.querySelectorAll(".result")) {
      button.classList.toggle("active", button.dataset.id === id);
      button.setAttribute("aria-pressed", String(button.dataset.id === id));
    }
    if (markId) readerMarks.focusMark(markId);
    else $("reader-title").focus();
  } catch (error) {
    if (number !== readerNumber) return;
    $("reader-title").textContent = "Documento no disponible";
    $("reader-body").replaceChildren(element("p", error.message));
    await readerMarks.open({item: {id}, html: "", text: "", revision: null});
    if (markId) readerMarks.focusMark(markId);
  }
}
$("reader-body").addEventListener("click", event => {
  const link = event.target.closest("a");
  if (!link) return;
  if (link.dataset.contentId) {
    event.preventDefault();
    openItem(link.dataset.contentId);
  } else if (link.dataset.unavailable) {
    event.preventDefault();
    warning("Ese enlace no está disponible dentro de las fuentes autorizadas.");
  }
});
for (const button of document.querySelectorAll(".destination")) {
  identify(button, button.dataset.screen);
  button.onclick = () => navigate(button.dataset.screen);
}
for (const heading of document.querySelectorAll("[data-identity-key]")) identify(heading, heading.dataset.identityKey);
for (const button of document.querySelectorAll(".collections .collection")) button.onclick = () => navigate("biblioteca", button.dataset.kind);
for (const button of document.querySelectorAll("[data-go]")) button.onclick = () => navigate(button.dataset.go);
window.addEventListener("popstate", async () => {
  const saved = history.state;
  if (!saved?.viewer) {
    const screen = location.hash.slice(1);
    if (screens[screen]) await navigate(screen, "", false);
    return;
  }
  const route = ++routeSequence;
  restoring = true;
  try {
    resetReader();
    Object.assign(state, {screen: saved.screen, kind: saved.kind, categories: saved.categories, tags: saved.tags, offset: saved.offset});
    $("search").value = saved.query; $("view").value = saved.view; $("fragment-color").value = saved.color;
    for (const key of filterKeys) {
      if (saved.filters[key] && $(key).tagName === "SELECT" && !Array.from($(key).options).some(option => option.value === saved.filters[key])) $(key).add(new Option(saved.filters[key], saved.filters[key]));
      $(key).value = saved.filters[key];
    }
    for (const [key, value] of Object.entries(saved.journal || {})) $(key).value = value;
    const pending = load(), request = requestNumber;
    await pending;
    if (route !== routeSequence || request !== requestNumber) return;
    if (saved.selected) await openItem(saved.selected, saved.markId, false);
    if (route !== routeSequence) return;
    $("results").scrollTop = saved.resultsScroll;
    window.scrollTo(0, saved.y);
    if (!saved.selected) {
      const focus = Array.from(document.querySelectorAll(".result")).find(node => node.dataset.id === saved.focusId) ||
        Array.from(document.querySelectorAll(".fragment-result")).find(node => node.dataset.markId === saved.focusMark)?.querySelector("button");
      (focus || document.querySelector(".masthead h1")).focus({preventScroll: true});
    }
  } finally { if (route === routeSequence) restoring = false; }
});
document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); $("search").focus(); }
});
$("search").oninput = () => {
  clearTimeout(timer);
  state.offset = 0;
  timer = setTimeout(() => {
    if (!["biblioteca", "fragmentos"].includes(state.screen)) navigate($("view").value === "fragments" ? "fragmentos" : "biblioteca");
    else load();
  }, 250);
};
for (const key of filterKeys) $(key).onchange = () => {
  state.offset = 0;
  load();
};
$("view").onchange = () => {
  const target = $("view").value === "fragments" ? "fragmentos" : "biblioteca";
  $("view").value = state.screen === "fragmentos" ? "fragments" : "documents";
  navigate(target, state.kind === "journal" ? "" : state.kind);
};
$("fragment-color").onchange = () => { state.offset = 0; load(); };
$("clear").onclick = () => {
  state.categories = [];
  $("fragment-color").value = "";
  clearTimeout(timer);
  $("search").value = "";
  for (const key of filterKeys) $(key).value = key === "sort" ? "relevance" : "";
  state.tags = [];
  state.offset = 0;
  load();
};
$("refresh").onclick = () => {
  routeSequence++; restoring = false;
  state.offset = 0;
  load();
  deployment = null; viewerInfo().catch(() => {});
  if (state.selected && (document.body.classList.contains("reading") || window.matchMedia("(min-width: 1001px)").matches)) openItem(state.selected, state.markId, false);
};
$("prev").onclick = () => {
  state.offset = Math.max(0, state.offset - 20);
  load();
};
$("next").onclick = () => {
  if (state.next !== null) {
    state.offset = state.next;
    load();
  }
};
$("back").onclick = () => {
  history.back();
};
readerMarks = new ReaderMarks();
const initialScreen = location.hash.slice(1);
state.screen = screens[initialScreen] ? initialScreen : "inicio";
state.kind = state.screen === "diario" ? "journal" : "";
$("view").value = state.screen === "fragmentos" ? "fragments" : "documents";
viewerInfo().catch(() => { $("memory-scope").textContent = "Ámbito no disponible"; });
load();
