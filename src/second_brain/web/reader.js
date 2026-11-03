"use strict";
// Temporary search ranges never wrap text or change the annotation text contract.
window.ReaderUI = (() => {
  let doc = null, ranges = [], index = 0, limited = false;
  const fold = text => text.toLowerCase().replaceAll("ß", "ss").replaceAll("ς", "σ").normalize("NFKD").replace(/\p{M}/gu, "");
  const native = () => Boolean(window.Highlight && window.CSS?.highlights);
  const snapshot = () => ({query:$("reader-find").value, index, focused:document.body.classList.contains("reading-focus")});
  function reset() {
    doc = null; ranges = []; index = 0;
    if (native()) { CSS.highlights.delete("shiori-search"); CSS.highlights.delete("shiori-current"); }
    document.body.classList.remove("reading-focus");
    $("reader-tools").hidden = true; $("reader-fragments").hidden = true;
  }
  function range(root, start, end) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), result = document.createRange();
    let position = 0, started = false;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (!started && start < position + node.length) { result.setStart(node, start - position); started = true; }
      if (started && end <= position + node.length) { result.setEnd(node, end - position); return result; }
      position += node.length;
    }
    return null;
  }
  function find(root, terms) {
    let folded = "", position = 0;
    const starts = [], ends = [];
    for (const char of root.textContent) {
      const value = fold(char); folded += value;
      for (let i = 0; i < value.length; i++) { starts.push(position); ends.push(position + char.length); }
      position += char.length;
    }
    const matches = new Map();
    for (const term of terms) {
      let at = folded.indexOf(term);
      while (at >= 0) {
        const start = starts[at], end = ends[at + term.length - 1];
        matches.set(start + ":" + end, {start, end});
        if (matches.size > 500) { limited = true; break; }
        at = folded.indexOf(term, at + Math.max(1, term.length));
      }
    }
    return [...matches.values()].sort((a,b) => a.start - b.start || a.end - b.end).slice(0,500).map(m => range(root,m.start,m.end)).filter(Boolean);
  }
  function paint() {
    index = ranges.length ? Math.max(0, Math.min(index, ranges.length - 1)) : 0;
    if (native()) {
      CSS.highlights.set("shiori-search", new Highlight(...ranges));
      CSS.highlights.set("shiori-current", new Highlight(...(ranges[index] ? [ranges[index]] : [])));
    }
    $("reader-match-count").textContent = !$("reader-find").value.trim() ? "Busca en el texto visible de esta página." :
      ranges.length ? `${index+1} de ${ranges.length}${limited ? "+ (primeras 500)" : ""} coincidencias temporales` : "Sin coincidencias en el título o texto visible.";
    $("reader-match-prev").disabled = !ranges.length; $("reader-match-next").disabled = !ranges.length;
  }
  function refresh() {
    if (!doc || doc.item.id !== state.selected) return;
    limited = false;
    const terms = [...new Set(fold($("reader-find").value.trim()).split(/\s+/).filter(Boolean))];
    ranges = terms.length ? [...find($("reader-title"),terms), ...find($("reader-body"),terms)] : [];
    if (ranges.length > 500) { limited = true; ranges = ranges.slice(0,500); }
    paint(); fragments();
  }
  function move(delta) {
    if (!ranges.length) return;
    index = (index + delta + ranges.length) % ranges.length; paint();
    const current = ranges[index], parent = current.startContainer.parentElement;
    parent.scrollIntoView({block:"center", inline:"nearest"});
    const pre = parent.closest("pre");
    if (pre) { const hit = current.getBoundingClientRect(), box = pre.getBoundingClientRect(); pre.scrollLeft += hit.left - box.left - 20; }
    if (!native()) { getSelection().removeAllRanges(); getSelection().addRange(current); }
    remember();
  }
  function fragments() {
    const root = $("reader-fragment-list"); root.replaceChildren();
    const items = readerMarks?.items || [];
    $("reader-fragments").hidden = !items.length;
    $("reader-fragment-count").textContent = items.length + " textos marcados";
    for (const item of items) {
      const row = element("div", undefined, "reader-fragment"); row.dataset.fragmentId = item.id;
      if (item.title) row.append(element("h4", item.title));
      const categories = item.tags.map(key => readerMarks.categories.find(c => c.id === key)?.label || key);
      row.append(element("p", categories.join(" · ") || "Sin categoría", "reader-fragment-category"));
      row.append(element(item.tags.some(key => ["comando", "direccion-ip", "ruta"].includes(key)) ? "pre" : "blockquote", item.quote));
      if (item.description) row.append(element("p", item.description));
      const copy = element("button", "Copiar texto exacto", "quiet"); copy.type = "button";
      copy.onclick = async () => { try { await navigator.clipboard.writeText(item.quote); $("copy-message").textContent = "Texto exacto copiado."; } catch { $("copy-message").textContent = "No se pudo copiar. Selecciona el texto para copiarlo manualmente."; } };
      const locate = element("button", item.anchor.status === "resolved" ? "Ir al fragmento" : "Revisar anclaje", "quiet");
      locate.type = "button"; locate.onclick = () => readerMarks.focusMark(item.id);
      row.append(copy,locate); root.append(row);
    }
  }
  function focused(value) {
    document.body.classList.toggle("reading-focus", value);
    $("reader-focus").textContent = value ? "Ver resultados y lector" : "Centrar lectura";
    $("reader-focus").setAttribute("aria-pressed", String(value));
  }
  function open(value, saved) {
    doc = value; $("reader-tools").hidden = false;
    $("reader-find").disabled = false; $("reader-focus").disabled = false;
    $("reader-find").value = saved?.query ?? $("search").value;
    index = saved?.index || 0; focused(saved?.focused || false); refresh();
    const evidence = value.headings.find(h => /^(evidence|evidencia)$/i.test(h.title));
    $("reader-evidence").hidden = !evidence;
    $("reader-evidence").onclick = () => { const heading = $(evidence.id); heading.tabIndex = -1; heading.focus(); heading.scrollIntoView({block:"center"}); };
  }
  document.addEventListener("DOMContentLoaded", () => {
    $("reader-find").oninput = () => { index = 0; refresh(); remember(); };
    $("reader-match-prev").onclick = () => move(-1);
    $("reader-match-next").onclick = () => move(1);
    $("reader-focus").onclick = () => { focused(!document.body.classList.contains("reading-focus")); remember(); };
    $("reader-find").onkeydown = event => { if (event.key === "Enter") { event.preventDefault(); move(event.shiftKey ? -1 : 1); } };
  });
  return {snapshot, reset, refresh, open, locate:() => move(0), loading:() => {
    reset(); $("reader-tools").hidden = false; $("reader-find").value = ""; $("reader-find").disabled = true;
    $("reader-focus").disabled = true; $("reader-match-prev").disabled = true; $("reader-match-next").disabled = true;
    $("reader-evidence").hidden = true; $("reader-match-count").textContent = "Leyendo página…";
  }, unavailable:() => { $("reader-match-count").textContent = "Página no disponible. Puedes volver a tus resultados."; }};
})();
