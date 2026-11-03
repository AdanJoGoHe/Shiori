"use strict";
// All captured prose is textContent; only the existing authorized reader renders Markdown.
window.JournalUI = (() => {
  const id = name => document.getElementById(name);
  let scope, sequence = 0, entries = [], tasks = [], next = null, taskNext = null;
  let taskTotal = 0, activeTotal = 0, today, timezone;
  const statusNames = {open: "Abierto", blocked: "Bloqueado", done: "Resuelto", discarded: "Descartado"};
  const sectionNames = {completed: "Resultados", checks: "Comprobaciones", decisions: "Decisiones", blockers: "Bloqueos", next_steps: "Próximos pasos"};
  const date = value => new Date(value).toLocaleString("es-ES", {dateStyle: "medium", timeStyle: "short", timeZone: timezone});
  // Calendar arithmetic stays independent of browser timezone and 23/25-hour DST days.
  const dayShift = (day, count) => {
    const value = new Date(day + "T12:00:00Z");
    value.setUTCDate(value.getUTCDate() + count);
    return value.toISOString().slice(0, 10);
  };
  const fullDay = day => new Date(day + "T12:00:00Z").toLocaleDateString("es-ES", {dateStyle: "full", timeZone: "UTC"});
  const monthRange = month => {
    const start = month + "-01", next = new Date(start + "T12:00:00Z");
    next.setUTCMonth(next.getUTCMonth() + 1);
    return [start, dayShift(next.toISOString().slice(0, 10), -1)];
  };
  const dayName = day => (day === today ? "Hoy · " : day === dayShift(today, -1) ? "Ayer · " : "") + fullDay(day);
  const node = (tag, text, className) => {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;
    return result;
  };
  const message = text => { id("journal-message").textContent = text; };
  const action = (text, callback) => {
    const button = node("button", text, "quiet");
    button.type = "button";
    button.onclick = callback;
    return button;
  };
  function periodHeading(feed) {
    const single = feed.start_date === feed.end_date;
    id("journal-period-title").textContent = single ? dayName(feed.start_date) : fullDay(feed.start_date) + " — " + fullDay(feed.end_date);
    id("journal-timezone").textContent = "Zona horaria · " + timezone;
    for (const button of document.querySelectorAll("[data-journal-period]")) button.setAttribute("aria-pressed", String(button.dataset.journalPeriod === id("journal-period").value));
    id("journal-next-day").disabled = feed.end_date >= today;
    id("journal-month").value = feed.start_date.slice(0, 7);
    id("journal-next-month").disabled = feed.end_date.slice(0, 7) >= today.slice(0, 7);
    id("journal-dates").querySelector("summary").textContent = "Histórico · elegir fecha o mes";
  }
  function selectPeriod(mode, start, end) {
    id("journal-period").value = mode;
    if (start) id("journal-from").value = start;
    if (end) id("journal-to").value = end;
    id("journal-dates").open = false;
    load();
  }
  function query(extra = {}, dates = false) {
    const params = new URLSearchParams(extra);
    if (id("journal-project").value) params.set("project", id("journal-project").value);
    if (dates) {
      if (id("journal-from").value) params.set("start_date", id("journal-from").value);
      if (id("journal-to").value) params.set("end_date", id("journal-to").value);
    }
    return params;
  }
  function show() {
    document.body.classList.add("journal-active");
    id("journal-panel").hidden = false;
    for (const selector of [".toolbar", "#category-manager", ".workspace"]) document.querySelector(selector).hidden = true;
    document.querySelector(".masthead h1").textContent = "Diario";
    document.querySelector(".masthead .subtitle").textContent = "Lo que avanzaste y el siguiente paso para retomarlo.";
  }
  function hide() {
    sequence++;
    if (!document.body.classList.contains("journal-active")) return;
    document.body.classList.remove("journal-active");
    id("journal-panel").hidden = true;
    for (const selector of [".toolbar", "#category-manager", ".workspace"]) document.querySelector(selector).hidden = false;
    document.querySelector(".masthead h1").textContent = "Biblioteca";
    document.querySelector(".masthead .subtitle").textContent = "Documentación, conocimiento y avances, en un mismo lugar.";
  }
  async function save(candidate, button) {
    button.disabled = true;
    message("Guardando en el diario…");
    try {
      const result = await api("api/journal", "POST", candidate);
      if (!["saved", "duplicate"].includes(result.status)) throw new Error("No se guardó: " + (result.reason || result.status));
      await load();
      message("Guardado en el diario. El historial anterior se conserva.");
      return true;
    } catch (error) {
      message(error.status === 409 ? "Los datos cambiaron. Actualiza antes de guardar; conserva tu texto si quieres reutilizarlo." : error.message);
      return false;
    } finally { button.disabled = false; }
  }
  function candidate(project, title, summary) {
    return {scope, mode: "journal-only", event_id: "viewer-" + crypto.randomUUID(), source_agent: "manual", project, title, summary};
  }
  async function taskActivity(taskId) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(taskId));
    return "task-" + Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  }
  function field(label, tag = "input", value = "", maximum = 500) {
    const wrap = node("label", label), input = node(tag);
    input.value = value;
    input.maxLength = maximum;
    if (tag === "textarea") input.rows = 2;
    wrap.append(input);
    return {wrap, input};
  }
  function sourceButton(row) {
    return action("Abrir día completo", () => openReference("journal:" + scope + ":" + row.path.replace(/^journal\//, "")));
  }
  function taskChanges(row) {
    const details = node("details", undefined, "journal-recorded-tasks");
    details.append(node("summary", "Pendientes registrados en esta captura · " + row.task_changes.length));
    for (const task of row.task_changes) {
      const change = node("div", undefined, "journal-task-comparison");
      change.append(node("p", task.title), node("p", "Registrado entonces: " + statusNames[task.status] + " · v" + task.version, "journal-meta"),
        node("p", task.current_status ? "Estado actual registrado: " + statusNames[task.current_status] + " · v" + task.current_version : "Estado actual no disponible: historial incompleto.", "journal-meta"));
      if (task.current_at) change.append(action("Ver último cambio", () => selectPeriod("custom", task.current_at.slice(0, 10), task.current_at.slice(0, 10))));
      details.append(change);
    }
    return details;
  }
  function correction(row) {
    const details = node("details", undefined, "journal-correction");
    details.append(node("summary", "Corregir o agrupar esta captura"));
    const form = node("form");
    const title = field("Título", "input", row.title, 200);
    const summary = field("Resultado corregido", "textarea", row.summary, 1000);
    const reason = field("Qué cambia y por qué", "textarea");
    const activity = field("Actividad compartida (ID opcional)", "input", row.activity || "", 100);
    for (const input of [title.input, summary.input, reason.input]) input.required = true;
    activity.input.pattern = "[a-z0-9][a-z0-9-]{0,99}";
    const button = node("button", "Guardar corrección");
    button.type = "submit";
    form.append(title.wrap, summary.wrap, reason.wrap, activity.wrap,
      node("p", "Comparte el ID de actividad para agrupar avances. La corrección conserva el original y no modifica estados de pendientes."), button);
    let pending;
    form.onsubmit = async event => {
      event.preventDefault();
      // Keep the same payload for a retry; edited input creates a new event.
      const values = JSON.stringify([title.input.value, summary.input.value, reason.input.value, activity.input.value]);
      if (!pending || pending.values !== values) pending = {values, data: {
        ...candidate(row.project, title.input.value, summary.input.value),
        progress: row.progress, activity: activity.input.value || null,
        supersedes: [row.event_id], change_reason: reason.input.value
      }};
      await save(pending.data, button);
    };
    details.append(form);
    return details;
  }
  function entry(row, historical = false) {
    const article = node("article", undefined, "journal-entry");
    article.dataset.eventId = row.event_id;
    article.append(node(historical ? "h5" : "h4", row.title), node("p", row.summary, "journal-outcome"));
    if (row.superseded_by) article.append(node("p", "Captura corregida posteriormente; se conserva el original.", "journal-meta"));
    if (row.change_reason) article.append(node("p", "Corrección: " + row.change_reason, "journal-meta"));
    const extra = node("details", undefined, "journal-entry-detail");
    extra.append(node("summary", "Detalle de la captura"), node("p", date(row.at) + " · " + row.source_agent, "journal-meta"));
    for (const key of ["completed", "checks", "blockers", "decisions", "next_steps"]) {
      const values = row.progress[key] || [];
      if (!values.length) continue;
      const block = node("div", undefined, "journal-progress");
      block.dataset.progress = key;
      block.append(node("h5", sectionNames[key]));
      const list = node("ul");
      for (const value of values) list.append(node("li", value));
      block.append(list);
      (["completed", "checks", "blockers"].includes(key) && !historical ? article : extra).append(block);
    }
    if (row.task_changes?.length) article.append(taskChanges(row));
    if (row.entry_truncated) article.append(node("p", "Vista abreviada. Abre el día completo para ver todo el texto.", "journal-meta"));
    const links = node("div", undefined, "journal-entry-links");
    links.append(sourceButton(row));
    links.append(action("Ver acciones asociadas", () => AgentLogUI.openJournal(row.event_id, row.day, row.project)));
    if (row.note_id) links.append(action("Abrir nota vinculada", () => openReference("note:" + scope + ":" + row.note_id, "note")));
    article.append(links);
    if (!historical && row.project && !row.superseded_by && !row.entry_truncated) extra.append(correction(row));
    article.append(extra);
    return article;
  }
  function renderEntries(total, incomplete) {
    const target = id("journal-entries"); target.replaceChildren();
    id("journal-count").textContent = entries.length + " de " + total + " capturas";
    const known = new Map(entries.map(row => [row.event_id, row])), groups = new Map();
    for (const row of entries) {
      let current = row, seen = new Set();
      while (known.has(current.superseded_by) && !seen.has(current.event_id)) {
        seen.add(current.event_id); current = known.get(current.superseded_by);
      }
      const key = row.day + ":" + row.project + ":" + (current.day === row.day ? current.activity || current.event_id : row.activity || row.event_id);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }
    const days = new Map();
    for (const rows of groups.values()) {
      const lead = rows.find(row => !row.superseded_by) || rows[0];
      const thread = node("div", undefined, "journal-thread");
      if (lead.activity) thread.append(node("p", lead.activity.startsWith("task-") ? "Seguimiento de pendiente" : "Actividad · " + lead.activity, "journal-meta"));
      thread.append(entry(lead));
      const history = rows.filter(row => row !== lead);
      if (history.length) {
        const detail = node("details"); detail.append(node("summary", "Historial · " + history.length + " capturas anteriores en este periodo"));
        for (const row of history) detail.append(entry(row, true));
        thread.append(detail);
      }
      if (!days.has(lead.day)) days.set(lead.day, new Map());
      const projects = days.get(lead.day), project = lead.project || "Sin proyecto";
      if (!projects.has(project)) projects.set(project, []);
      const priority = ["completed", "checks", "blockers"].some(key => lead.progress[key]?.length) ? 0 : lead.task_changes?.length ? 2 : 1;
      projects.get(project).push({thread, priority});
    }
    for (const day of [...days.keys()].sort().reverse()) {
      const section = node("section", undefined, "journal-day"); section.dataset.day = day;
      const heading = node("div", undefined, "journal-day-title");
      const time = node("time", dayName(day)); time.dateTime = day;
      heading.append(time, action("Ver este día", () => selectPeriod("custom", day, day)));
      if (id("journal-from").value !== id("journal-to").value) section.append(heading);
      for (const [project, threads] of days.get(day)) {
        const group = node("section", undefined, "journal-project-group");
        group.append(node("h3", project), ...threads.sort((a, b) => a.priority - b.priority).map(row => row.thread)); section.append(group);
      }
      target.append(section);
    }
    if (!entries.length) target.append(node("p", incomplete ? "No se han recuperado avances. La lectura está incompleta; revisa los archivos del diario." : "Sin actividad registrada para este proyecto y periodo.", "journal-empty"));
    id("journal-more").hidden = next === null;
  }
  function renderTasks(total, active) {
    taskTotal = total; activeTotal = active;
    document.querySelector('[data-journal-pane="tasks"]').textContent = "Pendientes · " + active;
    const target = id("journal-task-list"); target.replaceChildren();
    id("journal-task-count").textContent = active + " activos · " + total + " en total";
    const visible = tasks.filter(task => id("journal-task-filter").value === "all" || ["open", "blocked"].includes(task.status));
    for (const task of visible) {
      const row = node("article", undefined, "journal-task"); row.dataset.taskId = task.id;
      const badge = node("span", statusNames[task.status], "journal-status"); badge.dataset.status = task.status;
      row.append(badge, node("h3", task.title), node("p", task.details), node("p", task.project + " · Estado actual · v" + task.version + " · " + date(task.at), "journal-meta"));
      const edit = node("details"); edit.append(node("summary", "Cambiar estado"));
      const form = node("form"), select = node("select"), label = node("label", "Nuevo estado");
      for (const [value, text] of Object.entries(statusNames)) { const option = node("option", text); option.value = value; select.append(option); }
      select.value = task.status; label.append(select);
      const context = field("Contexto del cambio", "textarea", task.details);
      const button = node("button", "Guardar estado"); button.type = "submit";
      form.append(label, context.wrap, button);
      let pending;
      form.onsubmit = async event => {
        event.preventDefault();
        const values = JSON.stringify([select.value, context.input.value]);
        if (!pending || pending.values !== values) pending = {values, data: {
          ...candidate(task.project, "Pendiente actualizado: " + task.title.slice(0, 170), statusNames[select.value] + ": " + task.title),
          activity: await taskActivity(task.id),
          tasks: [{id: task.id, title: task.title, status: select.value, details: context.input.value, version: task.version}]
        }};
        await save(pending.data, button);
      };
      edit.append(form); row.append(edit);
      const history = node("details"); history.append(node("summary", "Historial · " + task.history_total + " cambios"));
      for (const item of task.history.slice().reverse()) {
        const change = node("p", date(item.at) + " · " + statusNames[item.status] + " · v" + item.version + (item.details ? " — " + item.details : ""));
        change.append(" ", sourceButton(item)); history.append(change);
      }
      if (task.history_truncated) history.append(node("p", "Mostrando solo los cambios recientes. Los anteriores siguen en el diario."));
      row.append(history); target.append(row);
    }
    if (!visible.length) target.append(node("p", taskNext !== null ? "No hay pendientes de este estado en esta página. Carga más para continuar." : "No hay pendientes de este estado.", "journal-empty"));
    id("journal-tasks-more").hidden = taskNext === null;
  }
  async function load(more = false, moreTasks = false) {
    const current = ++sequence;
    document.querySelector(".journal-grid").inert = true;
    id("journal-resume").disabled = true;
    id("journal-entries").setAttribute("aria-busy", "true");
    message("Leyendo diario…");
    id("journal-resume-result").hidden = true;
    try {
      const info = await viewerInfo(true);
      if (current !== sequence || !document.body.classList.contains("journal-active")) return;
      today = info.today;
      const mode = id("journal-period").value;
      if (mode !== "custom") {
        id("journal-from").value = dayShift(today, mode === "week" ? -6 : mode === "yesterday" ? -1 : 0);
        id("journal-to").value = dayShift(today, mode === "yesterday" ? -1 : 0);
      }
      const [feed, board] = await Promise.all([
        api("api/journal?" + query({offset: String(more ? next || 0 : 0)}, true)),
        api("api/journal-state?" + query({offset: String(moreTasks ? taskNext || 0 : 0)}))
      ]);
      if (current !== sequence || !document.body.classList.contains("journal-active")) return;
      scope = feed.scope;
      timezone = feed.timezone; today = feed.today;
      document.querySelector("footer span").textContent = "Markdown · Local · " + (scope === "work" ? "Trabajo" : "Personal");
      entries = more ? entries.concat(feed.items) : moreTasks ? entries : feed.items;
      tasks = moreTasks ? tasks.concat(board.tasks) : more ? tasks : board.tasks;
      if (!moreTasks) next = feed.next_offset;
      if (!more) taskNext = board.next_offset;
      const selected = id("journal-project").value;
      id("journal-projects").replaceChildren();
      for (const project of board.projects) id("journal-projects").append(new Option(project, project));
      id("journal-resume").disabled = !selected;
      id("journal-from").value = feed.start_date; id("journal-to").value = feed.end_date;
      id("journal-range-from").value = feed.start_date; id("journal-range-to").value = feed.end_date;
      periodHeading(feed);
      renderEntries(feed.total, feed.error_count); renderTasks(board.task_total, board.active_total);
      document.querySelector(".journal-grid").inert = false;
      message(
        (feed.error_count || board.error_count ? "Lectura incompleta: las correcciones o los estados actuales pueden estar incompletos. Revisa el diario antes de actualizar pendientes." : "") +
        (board.truncated || feed.truncated ? " Se alcanzó un límite de lectura; carga más cuando esté disponible." : ""));
      remember();
    } catch (error) { if (current === sequence) message("No se pudo leer el diario. " + error.message + " Pulsa Actualizar para reintentar."); }
    finally { if (current === sequence) id("journal-entries").setAttribute("aria-busy", "false"); }
  }
  document.addEventListener("DOMContentLoaded", () => {
    id("journal-panel").dataset.pane = "feed";
    for (const button of document.querySelectorAll("[data-journal-pane]")) button.onclick = () => {
      id("journal-panel").dataset.pane = button.dataset.journalPane;
      for (const peer of document.querySelectorAll("[data-journal-pane]")) peer.setAttribute("aria-pressed", String(peer === button));
    };
    id("journal-project").onchange = () => { id("journal-resume-result").hidden = true; load(); };
    for (const button of document.querySelectorAll("[data-journal-period]")) button.onclick = () => selectPeriod(button.dataset.journalPeriod);
    id("journal-previous").onclick = () => selectPeriod("custom", dayShift(id("journal-from").value, -1), dayShift(id("journal-from").value, -1));
    id("journal-next-day").onclick = () => selectPeriod("custom", dayShift(id("journal-to").value, 1), dayShift(id("journal-to").value, 1));
    id("journal-period-form").onsubmit = event => {
      event.preventDefault();
      const start = id("journal-range-from").value, end = id("journal-range-to").value;
      if (start > end || dayShift(start, 30) < end) { message("Elige un periodo de 1 a 31 días, con inicio anterior o igual al fin."); return; }
      selectPeriod("custom", start, end);
    };
    id("journal-month-form").onsubmit = event => {
      event.preventDefault();
      selectPeriod("custom", ...monthRange(id("journal-month").value));
    };
    for (const [name, step] of [["journal-previous-month", -1], ["journal-next-month", 1]]) id(name).onclick = () => {
      if (!id("journal-month").reportValidity()) return;
      const month = new Date(id("journal-month").value + "-01T12:00:00Z");
      month.setUTCMonth(month.getUTCMonth() + step);
      selectPeriod("custom", ...monthRange(month.toISOString().slice(0, 7)));
      id("journal-dates").open = true;
    };
    id("journal-task-filter").onchange = () => { renderTasks(taskTotal, activeTotal); remember(); };
    id("journal-more").onclick = () => load(true);
    id("journal-tasks-more").onclick = () => load(false, true);
    id("journal-resume").onclick = async () => {
      const project = id("journal-project").value, current = sequence;
      try {
        const pack = await api("api/project-resume?" + new URLSearchParams({project}));
        if (current !== sequence) return;
        const target = id("journal-resume-result"); target.replaceChildren(node("h2", "Por dónde retomar · " + project)); target.hidden = false;
        if (pack.latest) target.append(node("p", pack.latest.summary), sourceButton(pack.latest));
        else target.append(node("p", "Este proyecto todavía no tiene avances guardados."));
        const list = node("ul");
        for (const task of pack.active_tasks) list.append(node("li", statusNames[task.status] + " · " + task.title + (task.details ? " — " + task.details : "")));
        if (!pack.active_total) target.append(node("p", "No hay pendientes activos registrados."));
        target.append(list);
        if (pack.suggested_next_steps.length) { target.append(node("h3", "Sugerencias históricas")); for (const step of pack.suggested_next_steps) target.append(node("p", step)); }
        if (pack.truncated || pack.error_count) target.append(node("p", "Contexto parcial. Revisa el diario completo y sus pendientes antes de continuar."));
      } catch (error) { message(error.message); }
    };
    let pendingTask;
    id("journal-task-form").onsubmit = async event => {
      event.preventDefault();
      const project = id("journal-project").value;
      if (!project) { message("Selecciona un proyecto antes de crear el pendiente."); return; }
      const title = id("journal-task-title").value, details = id("journal-task-details").value;
      const values = JSON.stringify([project, title, details]);
      if (!pendingTask || pendingTask.values !== values) pendingTask = {values, data: {
        ...candidate(project, "Nuevo pendiente: " + title.slice(0, 180), title),
        tasks: [{id: "task-" + crypto.randomUUID(), title, details, status: "open", version: 0}]
      }};
      if (await save(pendingTask.data, event.submitter)) {
        pendingTask = null; id("journal-task-form").reset(); id("journal-new-task").open = false;
      }
    };
  });
  return {show, hide, load};
})();
