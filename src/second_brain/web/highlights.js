"use strict";

class ReaderMarks {
  static offsets(text, start, end) {
    const boundary = i => !(i > 0 && i < text.length && /[\uD800-\uDBFF]/.test(text[i - 1]) && /[\uDC00-\uDFFF]/.test(text[i]));
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > text.length || !boundary(start) || !boundary(end)) throw new Error("Selecciona caracteres completos dentro del documento.");
    const quote = text.slice(start, end);
    if (!quote.trim() || Array.from(quote).length > 4000) throw new Error("Selecciona entre 1 y 4.000 caracteres de texto.");
    return {start: Array.from(text.slice(0, start)).length, end: Array.from(text.slice(0, end)).length, quote};
  }

  static segments(items, text) {
    const points = [0];
    for (const char of text) points.push(points[points.length - 1] + char.length);
    const valid = items.filter(item => {
      const a = item.anchor;
      return a?.status === "resolved" && Number.isInteger(a.start) && Number.isInteger(a.end) && a.start >= 0 && a.end > a.start && a.end < points.length && text.slice(points[a.start], points[a.end]) === item.quote;
    }).sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
    const bounds = [...new Set([0, text.length, ...valid.flatMap(item => [points[item.anchor.start], points[item.anchor.end]])])].sort((a, b) => a - b);
    return bounds.slice(0, -1).map((start, i) => ({start, end: bounds[i + 1], items: valid.filter(item => points[item.anchor.start] <= start && points[item.anchor.end] >= bounds[i + 1])}));
  }

  constructor() {
    this.doc = null;
    this.items = [];
    this.categories = [];
    this.busy = false;
    this.editing = null;
    this.pending = null;
    this.undoToken = null;
    document.addEventListener("selectionchange", () => this.capture());
    $("mark-selection").onclick = () => {
      if (!this.pending) return this.message("Selecciona texto dentro del lector o usa el campo de texto exacto.");
      this.prepare(this.pending);
    };
    $("mark-find").onclick = () => this.find();
    $("mark-exact").oninput = () => { this.findAfter = 0; };
    $("mark-form").onsubmit = event => { event.preventDefault(); this.save(); };
    $("mark-cancel").onclick = () => { this.cancel(); $("mark-selection").focus(); };
    $("mark-cancel-relink").onclick = () => { this.cancel(); this.message(""); $("mark-selection").focus(); };
    $("mark-reload").onclick = () => { if (this.doc) openItem(this.doc.item.id); };
    $("mark-undo").onclick = () => this.mutate("api/annotations/undo", "POST", {token: this.undoToken}, "restored");
    $("reader-body").addEventListener("click", event => {
      const node = event.target.closest("mark[data-mark-id]");
      if (!node || event.target.closest("a") || !getSelection().isCollapsed) return;
      this.edit(this.items.find(item => item.id === node.dataset.markId));
    });
    $("reader-body").addEventListener("keydown", event => {
      const node = event.target.closest("mark[data-mark-id]");
      if (node && !event.target.closest("a") && ["Enter", " "].includes(event.key)) {
        event.preventDefault();
        this.edit(this.items.find(item => item.id === node.dataset.markId));
      }
    });
  }

  message(text) { $("mark-message").textContent = text; }
  setBusy(busy) {
    this.busy = busy;
    for (const control of $("marks-panel").querySelectorAll("button, input, select, textarea")) control.disabled = busy;
    $("marks-panel").setAttribute("aria-busy", String(busy));
    if (!busy) $("mark-undo").disabled = !this.undoToken;
    if (!busy && !this.doc?.revision) {
      $("mark-selection").disabled = true;
      $("mark-find").disabled = true;
    }
  }
  reset() {
    this.doc = null;
    this.items = [];
    this.pending = null;
    this.undoToken = null;
    this.findAfter = 0;
    $("marks-panel").hidden = true;
    $("mark-exact").value = "";
    this.cancel();
    this.message("");
    $("mark-selection-hint").textContent = "Selecciona texto dentro del documento.";
    $("mark-count").textContent = "";
    $("mark-list").replaceChildren();
    $("mark-tags").replaceChildren();
    this.setBusy(false);
  }
  cancel() {
    this.editing = null;
    this.metadataOnly = false;
    this.draft = null;
    $("mark-form").hidden = true;
    $("mark-form").reset();
    $("mark-selection-fields").hidden = false;
    $("mark-cancel-relink").hidden = true;
  }
  async open(doc) {
    this.doc = doc;
    $("marks-panel").hidden = false;
    this.setBusy(true);
    try { await this.reload(doc); }
    catch (error) { if (this.doc === doc) this.message(error.message); }
    finally { if (this.doc === doc) this.setBusy(false); }
  }
  async reload(doc) {
    const [marks, categories] = await Promise.all([api("api/annotations?" + new URLSearchParams({document_id: doc.item.id})), api("api/categories")]);
    if (this.doc !== doc) return;
    this.items = marks.items;
    this.categories = categories.items;
    this.render();
  }
  capture() {
    if (!this.doc || this.busy) return;
    const selection = getSelection(), root = $("reader-body");
    if (!selection || selection.isCollapsed || !selection.rangeCount) return;
    const range = selection.getRangeAt(0);
    if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) {
      this.pending = null;
      $("mark-selection-hint").textContent = "La selección debe estar completamente dentro del documento.";
      return;
    }
    try {
      const prefix = range.cloneRange();
      prefix.selectNodeContents(root);
      prefix.setEnd(range.startContainer, range.startOffset);
      this.pending = ReaderMarks.offsets(this.doc.text, prefix.toString().length, prefix.toString().length + range.toString().length);
      if (this.pending.quote !== range.toString()) throw new Error("La selección no coincide con el lector. Actualiza el documento.");
      $("mark-selection-hint").textContent = "Selección lista: " + this.pending.quote.slice(0, 100);
    } catch (error) { this.pending = null; this.message(error.message); }
  }
  find() {
    if (!this.doc || this.busy) return;
    const quote = $("mark-exact").value;
    let start = this.doc.text.indexOf(quote, this.findAfter || 0);
    if (start < 0) start = this.doc.text.indexOf(quote);
    try {
      if (start < 0) throw new Error("Ese texto exacto no aparece en el lector.");
      const selection = ReaderMarks.offsets(this.doc.text, start, start + quote.length);
      this.findAfter = start + 1;
      this.pending = selection;
      this.prepare(selection);
      this.message("Coincidencia en posición " + selection.start + ". Comprueba el contexto; pulsa otra vez para ver la siguiente.");
    } catch (error) { this.message(error.message); }
  }
  prepare(selection) {
    if (!this.doc || this.busy) return;
    this.metadataOnly = false;
    $("mark-selection-fields").hidden = false;
    this.draft = {...selection};
    $("mark-cancel-relink").hidden = true;
    $("mark-form").hidden = false;
    $("mark-form-title").textContent = this.editing ? "Editar / volver a enlazar marca" : "Nueva marca";
    $("mark-quote").textContent = selection.quote;
    const chars = Array.from(this.doc.text);
    $("mark-context").textContent = chars.slice(Math.max(0, selection.start - 60), selection.start).join("") + "【" + selection.quote + "】" + chars.slice(selection.end, selection.end + 60).join("");
    $("mark-color").value = this.editing?.color || "yellow";
    $("mark-title").value = this.editing?.title || "";
    $("mark-description").value = this.editing?.description || "";
    this.tagChoices(this.editing?.tags || []);
    $("mark-color").focus();
  }
  tagChoices(selected) {
    const container = $("mark-tags");
    container.replaceChildren();
    for (const category of this.categories.filter(c => !c.archived || selected.includes(c.id))) {
      const label = element("label"), input = element("input");
      input.type = "checkbox";
      input.value = category.id;
      input.checked = selected.includes(category.id);
      label.append(input, document.createTextNode(category.label + (category.archived ? " (archivada)" : "")));
      container.append(label);
    }
  }
  edit(item) {
    if (!item || this.busy) return;
    this.editing = item;
    if (item.anchor.status === "resolved" && item.anchor.revision === this.doc.revision) {
      this.prepare({start: item.anchor.start, end: item.anchor.end, quote: item.quote});
      const node = Array.from($("reader-body").querySelectorAll("mark")).find(n => n.dataset.markId === item.id);
      node?.scrollIntoView({block: "center"});
    } else {
      this.draft = null;
      $("mark-form").hidden = true;
      $("mark-cancel-relink").hidden = false;
      this.message("Esta marca necesita reparación. Selecciona el texto correcto y pulsa Marcar selección, o usa Texto exacto para marcar.");
      document.querySelector(".mark-lookup").open = true;
      $("mark-exact").focus();
    }
  }
  async save() {
    if (!this.doc || (!this.draft && !this.metadataOnly) || this.busy) return;
    const details = {title: $("mark-title").value, description: $("mark-description").value};
    if (Array.from(details.title).length > 120 || Array.from(details.description).length > 1000) {
      this.message("Usa hasta 120 caracteres para el título y 1.000 para la descripción.");
      return;
    }
    if (this.metadataOnly) {
      this.mutate("api/annotations?" + new URLSearchParams({id: this.editing.id}), "PATCH",
        {...details, version: this.editing.version}, "saved");
      return;
    }
    const payload = {document_id: this.doc.item.id, revision: this.doc.revision, ...this.draft,
      ...details,
      color: $("mark-color").value, tags: Array.from($("mark-tags").querySelectorAll("input:checked")).map(n => n.value)};
    if (this.editing) payload.version = this.editing.version;
    this.mutate("api/annotations" + (this.editing ? "?" + new URLSearchParams({id: this.editing.id}) : ""), this.editing ? "PATCH" : "POST", payload, "saved");
  }
  editDetails(item) {
    if (this.busy) return;
    this.cancel();
    this.editing = item;
    this.metadataOnly = true;
    this.draft = null;
    $("mark-form").hidden = false;
    $("mark-form-title").textContent = "Editar título y descripción";
    $("mark-quote").textContent = item.quote;
    $("mark-context").textContent = "El texto original, el anclaje, el color y las categorías se conservan.";
    $("mark-title").value = item.title || "";
    $("mark-description").value = item.description || "";
    $("mark-selection-fields").hidden = true;
    $("mark-title").focus();
  }
  async mutate(path, method, payload, action) {
    if (!this.doc || this.busy) return;
    const doc = this.doc;
    this.setBusy(true);
    let committed = false;
    try {
      const result = await api(path, method, payload);
      committed = true;
      if (this.doc !== doc) return;
      if (action === "deleted") this.undoToken = result.undo_token;
      if (action === "restored") this.undoToken = null;
      this.cancel();
      this.pending = null;
      $("mark-selection-hint").textContent = "Selecciona texto dentro del documento.";
      await this.reload(doc);
      if (this.doc === doc) this.message(action === "deleted" ? "Marca eliminada. Puedes deshacer la última eliminación durante esta sesión." : action === "restored" ? "Marca recuperada." : "Marca guardada.");
    } catch (error) {
      if (this.doc === doc) this.message((committed ? "Cambio guardado; no se pudo actualizar la lista. " : "") + error.message + (error.status === 409 ? " Recarga las marcas antes de reintentar; copia el borrador si lo necesitas." : ""));
    } finally {
      if (this.doc === doc) {
        this.setBusy(false);
        if (committed) (action === "deleted" ? $("mark-undo") : $("mark-selection")).focus();
      }
    }
  }
  focusMark(id) {
    const item = this.items.find(item => item.id === id);
    if (!item) { this.message("La marca ya no está disponible. Actualiza los resultados."); return; }
    const row = Array.from($("mark-list").children).find(row => row.dataset.markId === id);
    if (item.anchor.revision && item.anchor.revision !== this.doc.revision) {
      this.message("El documento ha cambiado. Recárgalo antes de localizar la marca.");
      return;
    }
    document.querySelector(".saved-marks").open = true;
    if (item.anchor.status !== "resolved") {
      this.message("La cita guardada necesita reparación; no hay un destino exacto confirmado.");
      row?.querySelector("button")?.focus();
      row?.scrollIntoView({block: "center"});
      return;
    }
    // A DOM range also locates marks hidden beneath overlapping, newer highlights.
    const chars = Array.from(this.doc.text);
    const start = chars.slice(0, item.anchor.start).join("").length;
    const end = chars.slice(0, item.anchor.end).join("").length;
    const walker = document.createTreeWalker($("reader-body"), NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let offset = 0, started = false;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (!started && start < offset + node.length) { range.setStart(node, start - offset); started = true; }
      if (started && end <= offset + node.length) {
        range.setEnd(node, end - offset);
        const parent = range.startContainer.parentElement;
        parent.tabIndex = -1;
        parent.focus({preventScroll: true});
        getSelection().removeAllRanges();
        getSelection().addRange(range);
        parent.scrollIntoView({block: "center"});
        this.message("Fragmento localizado. Usa Volver a resultados para conservar la búsqueda.");
        return;
      }
      offset += node.length;
    }
    this.message("El lector ha cambiado. Recarga el documento para comprobar el destino.");
  }
  render() {
    const root = $("reader-body"), doc = this.doc;
    root.innerHTML = doc.html;
    if (root.textContent !== doc.text) throw new Error("El texto del lector ha cambiado. No se aplicaron marcas.");
    const segments = ReaderMarks.segments(this.items.filter(item => item.anchor.revision === doc.revision), doc.text);
    const nodes = [], walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) nodes.push(walker.currentNode);
    let offset = 0, segmentIndex = 0;
    for (const node of nodes) {
      const end = offset + node.length, fragment = document.createDocumentFragment();
      let cursor = offset;
      while (cursor < end) {
        while (segments[segmentIndex].end <= cursor) segmentIndex++;
        const segment = segments[segmentIndex], stop = Math.min(end, segment.end);
        const text = node.data.slice(cursor - offset, stop - offset), item = segment.items.at(-1);
        if (item) {
          const mark = element("mark", text, "reader-mark");
          mark.dataset.color = item.color;
          mark.dataset.markId = item.id;
          mark.title = `${colorNames[item.color]} · ${item.tags.map(id => this.categories.find(c => c.id === id)?.label || id).join(" / ") || "Sin etiquetas"}`;
          if (!node.parentElement.closest("a")) {
            mark.tabIndex = 0;
            mark.setAttribute("role", "button");
            mark.setAttribute("aria-label", "Editar marca: " + item.quote);
          }
          fragment.append(mark);
        } else fragment.append(document.createTextNode(text));
        cursor = stop;
      }
      offset = end;
      node.replaceWith(fragment);
    }
    const list = $("mark-list");
    list.replaceChildren();
    const reasons = {current: "Enlazada", reattached: "Reenlazada tras cambios", missing: "Texto desaparecido", ambiguous: "Texto ambiguo", "context-changed": "Contexto cambiado", unavailable: "Documento no disponible"};
    for (const item of this.items) {
      const outOfDate = doc.revision && item.anchor.revision && item.anchor.revision !== doc.revision;
      const row = element("div", undefined, "saved-mark");
      row.dataset.markId = item.id;
      row.setAttribute("role", "group");
      row.setAttribute("aria-label", "Marca: " + item.quote);
      if (item.title) row.append(element("h4", item.title));
      if (item.description) row.append(element("p", item.description, "mark-description"));
      row.append(element("blockquote", item.quote), element("p", [outOfDate ? "Documento cambiado; recarga para comprobar el destino" : reasons[item.anchor.reason], colorNames[item.color], ...item.tags.map(id => {const c = this.categories.find(c => c.id === id); return (c?.label || id) + (c?.archived ? " (archivada)" : "");})].join(" · ")));
      const edit = element("button", outOfDate ? "Recargar documento" : item.anchor.status === "resolved" ? "Ver / editar" : "Volver a enlazar", "quiet");
      edit.onclick = () => outOfDate ? openItem(doc.item.id) : this.edit(item);
      const remove = element("button", "Eliminar marca", "quiet");
      remove.onclick = () => this.mutate("api/annotations?" + new URLSearchParams({id: item.id}), "DELETE", {version: item.version}, "deleted");
      const details = element("button", "Editar detalles", "quiet");
      details.onclick = () => this.editDetails(item);
      row.append(edit, details, remove);
      list.append(row);
    }
    if (!this.items.length) list.append(element("p", "Este documento aún no tiene marcas."));
    $("mark-count").textContent = this.items.length + " marcas";
  }
}
