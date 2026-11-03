"use strict";
window.FavoritesUI = (() => {
  const fields = ["favorite-project", "favorite-tags", "favorite-kind", "favorite-order"];
  let sequence = 0, offsets = [0], pageIndex = 0, next = null, editing = null, editorSequence = 0, lastQuery;
  const message = text => { $("copy-message").textContent = text; };
  const snapshot = () => ({values:Object.fromEntries(fields.map(key => [key, $(key).value])), offsets:[...offsets], pageIndex});
  function restore(saved) {
    if (!saved) return;
    for (const key of fields) $(key).value = saved.values[key] || "";
    offsets = [...saved.offsets]; pageIndex = saved.pageIndex;
  }
  function draw(button, favorite, version = favorite?.version || 0) {
    button.favoriteRecord = favorite;
    button.favoriteVersion = version;
    button.textContent = favorite ? "Quitar de favoritos" : "Añadir a favoritos";
    button.setAttribute("aria-pressed", String(Boolean(favorite)));
    button.disabled = false;
  }
  function sync(target, favorite, version) {
    for (const button of document.querySelectorAll("[data-favorite-target]"))
      if (button.dataset.favoriteTarget === target) draw(button, favorite, version);
  }
  function toggle(target, title, metadata = {}, initial, version) {
    const button = element("button", "Leyendo favorito…", "quiet favorite-toggle");
    button.type = "button"; button.dataset.favoriteTarget = target; button.disabled = true;
    if (initial !== undefined) draw(button, initial, version);
    else api("api/favorites?" + new URLSearchParams({target})).then(data => draw(button, data.items[0] || null, data.items[0]?.version || data.removed_version || 0))
      .catch(() => { button.textContent = "Favoritos no disponibles"; });
    button.onclick = async () => {
      button.disabled = true;
      const previous = button.favoriteRecord;
      try {
        const saved = previous ? await api("api/favorites?" + new URLSearchParams({id:previous.id}), "DELETE", {version:previous.version}) :
          await api("api/favorites", "POST", {target, title:title.slice(0,160), project:metadata.project || null, tags:metadata.tags || [], version:button.favoriteVersion});
        sync(target, previous ? null : saved, saved.version);
        message(previous ? "Favorito quitado. La página sigue intacta." : "Guardado en favoritos de este perfil.");
        if (state.screen === "favoritos") await load();
      } catch (error) {
        message(error.status === 409 ? "Este favorito cambió en otra pestaña. Actualiza antes de volver a guardarlo o quitarlo." : "No se pudo cambiar el favorito. Actualiza para comprobar su estado y reintentar.");
        button.disabled = false;
      }
    };
    return button;
  }
  function pageButton(item) {
    if (item.favorite_available === false) {
      const button = element("button", "Favoritos no disponibles", "quiet favorite-toggle");
      button.disabled = true; return button;
    }
    return toggle(item.id, item.title, item.metadata, item.favorite || null, item.favorite_version);
  }
  function openButton(item) {
    if (!item.available) return element("span", "No disponible · revisa el destino", "favorite-unavailable");
    if (item.kind === "web") {
      const link = element("a", "Abrir enlace", "quiet");
      link.href = item.target; link.target = "_blank"; link.rel = "noopener noreferrer";
      return link;
    }
    const button = element("button", "Abrir página", "quiet");
    button.onclick = () => openReference(item.content_id); return button;
  }
  function row(item, compact = false) {
    const node = element("article", undefined, compact ? "favorite-row favorite-compact" : "favorite-row");
    node.dataset.favoriteId = item.id;
    const type = element("p", (names[item.kind] || "Enlace web") + " / " + item.source, "kind identity-label");
    identify(type, "favoritos");
    node.append(type, element("h3", item.title));
    if (!compact) {
      node.append(element("p", item.target, "favorite-target"));
      if (item.excerpt) node.append(element("p", item.excerpt, "favorite-excerpt"));
      node.append(element("p", [item.project, ...item.tags].filter(Boolean).join(" · ") || "Sin proyecto ni etiquetas", "result-foot"));
      if (item.kind === "web") node.append(element("p", "Referencia guardada · contenido sin descargar", "result-foot"));
    }
    const actions = element("div", undefined, "favorite-actions");
    actions.append(openButton(item));
    if (!compact) {
      actions.append(toggle(item.target, item.title, item, item));
      const edit = element("button", item.available ? "Editar favorito" : "Reparar favorito", "quiet");
      edit.onclick = () => editForm(item); actions.append(edit);
    }
    node.append(actions); return node;
  }
  function editForm(item = null) {
    editorSequence++;
    editing = item;
    $("favorite-editor").hidden = false;
    $("favorite-editor-title").textContent = item ? "Editar favorito" : "Guardar enlace web";
    $("favorite-target").value = item?.target || "";
    $("favorite-target").readOnly = Boolean(item?.available);
    $("favorite-title").value = item?.title || "";
    $("favorite-edit-project").value = item?.project || "";
    $("favorite-edit-tags").value = (item?.tags || []).join(", ");
    $("favorite-editor-help").textContent = item && !item.available ? "Indica una URL o el ID exacto de una página autorizada. Se guardará el nuevo destino antes de quitar el antiguo." : "Solo guardamos la referencia. Puedes revisar su título, proyecto y etiquetas.";
    $("favorite-target").focus();
  }
  async function load(reset = false) {
    const number = ++sequence;
    if (reset) { offsets = [0]; pageIndex = 0; }
    const target = $("favorite-list"); target.setAttribute("aria-busy", "true");
    $("favorite-prev").disabled = true; $("favorite-next").disabled = true;
    $("favorite-status").textContent = "Leyendo favoritos…";
    const params = new URLSearchParams({query:$("search").value, order:$("favorite-order").value});
    if ($("favorite-project").value) params.set("project", $("favorite-project").value);
    if ($("favorite-kind").value) params.set("kind", $("favorite-kind").value);
    for (const tag of $("favorite-tags").value.split(",").map(s => s.trim()).filter(Boolean)) params.append("tag", tag);
    if (!restoring && lastQuery !== undefined && lastQuery !== params.toString()) { offsets = [0]; pageIndex = 0; }
    lastQuery = params.toString(); params.set("offset", String(offsets[pageIndex]));
    try {
      const data = await api("api/favorites?" + params);
      if (number !== sequence || state.screen !== "favoritos") return;
      target.replaceChildren(...data.items.map(item => row(item)));
      if (!data.items.length) target.append(element("p", "No hay favoritos con estos filtros. Guarda una página desde Biblioteca o añade un enlace web.", "favorite-empty"));
      next = data.next_offset;
      $("favorite-count").textContent = data.total + " favoritos";
      $("favorite-status").textContent = data.errors.length || data.catalog_truncated ? "Algunas páginas no se pudieron comprobar. Actualiza para reintentar; no se abrirán destinos parecidos." : data.truncated ? "Página acotada. Pulsa Siguiente para continuar." : "";
      $("favorite-page").textContent = data.total ? "Página " + (pageIndex + 1) : "";
      $("favorite-prev").disabled = pageIndex === 0; $("favorite-next").disabled = next === null;
      remember();
    } catch {
      if (number === sequence) $("favorite-status").textContent = "No se pudieron leer los favoritos. Los resultados anteriores pueden estar desactualizados. Pulsa Actualizar para reintentar.";
    } finally { if (number === sequence) target.setAttribute("aria-busy", "false"); }
  }
  document.addEventListener("DOMContentLoaded", () => {
    $("favorite-filter-form").onsubmit = event => { event.preventDefault(); load(true); };
    $("favorite-add").onclick = () => editForm();
    $("favorite-cancel").onclick = () => { editorSequence++; $("favorite-editor").hidden = true; editing = null; };
    $("favorite-prev").onclick = () => { pageIndex--; load(); };
    $("favorite-next").onclick = () => { offsets = offsets.slice(0,pageIndex+1); offsets.push(next); pageIndex++; load(); };
    $("favorite-editor").onsubmit = async event => {
      event.preventDefault();
      const editRequest = editorSequence, original = editing, target = $("favorite-target").value, replacing = original && original.target !== target;
      const payload = {target, title:$("favorite-title").value, project:$("favorite-edit-project").value || null,
        tags:$("favorite-edit-tags").value.split(",").map(s => s.trim()).filter(Boolean), version:replacing ? 0 : original?.version || 0};
      const submit = $("favorite-save"); submit.disabled = true;
      let saved;
      try {
        if (!original || replacing) {
          const current = await api("api/favorites?" + new URLSearchParams({target}));
          if (current.items.length) throw new Error("Already saved; edit the existing favorite instead");
          payload.version = current.removed_version || 0;
        }
        saved = await api("api/favorites", "POST", payload); sync(target, saved);
        if (replacing) { const removed = await api("api/favorites?" + new URLSearchParams({id:original.id}), "DELETE", {version:original.version}); sync(original.target,null,removed.version); }
        if (editorSequence === editRequest) { $("favorite-editor").hidden = true; editing = null; }
        message("Favorito guardado.");
      } catch (error) {
        message(saved ? "El nuevo favorito se guardó, pero no se pudo quitar el antiguo. Actualiza y revisa ambos." : error.status === 409 ? "Este favorito cambió. Actualiza y abre su edición de nuevo." : "No se pudo guardar. Revisa el destino, las etiquetas y el proyecto, y vuelve a intentarlo.");
      } finally {
        submit.disabled = false;
        if (state.screen === "favoritos") await load();
      }
    };
  });
  return {snapshot, restore, toggle, pageButton, row, load, hide:() => { sequence++; }, clear:() => {
    for (const key of fields) $(key).value = key === "favorite-order" ? "recent" : "";
    $("search").value = ""; load(true);
  }};
})();
