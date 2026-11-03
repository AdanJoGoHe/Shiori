"use strict";
window.AgentLogUI = (() => {
  const get = key => document.getElementById(key);
  const fields = ["log-from", "log-to", "log-project", "log-session", "log-agent", "log-kind", "log-outcome", "log-journal-event", "log-selected", "log-mode"];
  const kinds = {"command-proposed":"Comando propuesto", "command-attempted":"Comando intentado", "command-executed":"Comando ejecutado", check:"Comprobación", "file-changed":"Archivo cambiado", "link-found":"Enlace encontrado", "page-visited":"Página visitada"};
  const outcomes = {success:"Éxito", failure:"Fallo", cancelled:"Cancelado", unknown:"Desconocido"};
  let sequence = 0, detailSequence = 0, offsets = [0], pageIndex = 0, next = null, enabled = false, revision = 0, timezone, lastQuery;
  const node = (tag, text, cls) => {const value = document.createElement(tag); if (text !== undefined) value.textContent = text; if (cls) value.className = cls; return value;};
  const message = text => { get("log-message").textContent = text; };
  const button = (text, run) => {const value = node("button",text,"quiet"); value.type="button"; value.onclick=run; return value;};
  const when = at => new Date(at).toLocaleString("es-ES", {dateStyle:"medium",timeStyle:"short",timeZone:timezone});
  const shift = (day, count) => {const value=new Date(day+"T12:00:00Z");value.setUTCDate(value.getUTCDate()+count);return value.toISOString().slice(0,10);};
  const snapshot = () => ({values:Object.fromEntries(fields.map(key=>[key,get(key).value])), offsets:[...offsets], pageIndex});
  function restore(saved) {
    if (!saved) return;
    for (const [key,value] of Object.entries(saved.values)) if (fields.includes(key)) get(key).value=value;
    offsets=[...saved.offsets]; pageIndex=saved.pageIndex;
  }
  function emptyDetail() {get("log-detail").replaceChildren(node("h2","Detalle de la acción"),node("p","Abre una acción para ver el comando completo, las referencias y su procedencia."));}
  async function copy(text) {
    try {await navigator.clipboard.writeText(text);message("Texto exacto copiado.");}
    catch {message("No se pudo copiar. Selecciona el texto de la acción para copiarlo manualmente.");}
  }
  function badge(kind, outcome) {const value=node("p", kinds[kind]+" · "+outcomes[outcome],"log-status");value.dataset.outcome=outcome;return value;}
  async function detail(eventId, record = true) {
    const current=++detailSequence, pane=get("log-detail");
    pane.setAttribute("aria-busy","true");
    pane.inert=true;pane.replaceChildren(node("h2","Detalle de la acción"),node("p","Leyendo la acción…"));
    try {
      const data=await api("api/agent-log?"+new URLSearchParams({event_id:eventId}));
      if(current!==detailSequence || state.screen!=="agent-log") return;
      get("log-selected").value=eventId;
      const item=data.item;
      const heading=node("h2","Detalle de la acción");heading.tabIndex=-1;
      pane.replaceChildren(heading,badge(item.kind,item.outcome),node("p",item.summary,"log-full-summary"));
      pane.append(node("p",item.agent+" · "+item.session+" · "+(item.project||"Sin proyecto"),"log-meta"));
      pane.append(node("p",item.occurred_at?"Acción: "+when(item.occurred_at):"Hora de la acción no indicada.","log-meta"),node("p","Registrado: "+when(item.recorded_at)+" · Registro informado", "log-meta"));
      if (item.command) {const pre=node("pre"),code=node("code",item.command);pre.append(code);pane.append(node("h3","Comando"),pre,button("Copiar comando",()=>copy(item.command)));}
      if (item.context) pane.append(node("h3","Contexto"),node("p",item.context,"log-context"));
      if (item.corrects) pane.append(node("p","Corrección: "+item.correction_reason),button("Ver registro original",()=>detail(item.corrects)));
      if (data.corrected_by) pane.append(node("p","Este registro tiene una corrección posterior."),button("Ver corrección",()=>detail(data.corrected_by)));
      if (data.references.length) pane.append(node("h3","Referencias"));
      for (const ref of data.references) {
        const row=node("div",undefined,"log-reference");
        row.append(node("p",ref.label),node("p",ref.target,"log-target"));
        if (ref.kind==="file") row.append(node("p","Ruta informada; se conserva como texto.","log-meta"),button("Copiar ruta",()=>copy(ref.target)));
        else if (!ref.available) row.append(node("p","Referencia no disponible en las fuentes autorizadas.","log-meta"));
        else if (ref.kind==="url") {const a=node("a","Abrir enlace");a.href=ref.target;a.target="_blank";a.rel="noopener noreferrer";row.append(a);}
        else row.append(button(ref.kind==="journal-event"?"Abrir día del avance":"Abrir página",()=>openReference(ref.content_id)));
        pane.append(row);
      }
      for(const row of document.querySelectorAll(".log-event")) {
        row.dataset.selected=String(row.dataset.eventId===eventId);
        row.querySelector('[data-log-open]').setAttribute("aria-pressed",row.dataset.selected);
      }
      if(record) {remember();heading.focus({preventScroll:true});}
    } catch {if(current===detailSequence){message("No se pudo leer esta acción. Actualiza para reintentar.");emptyDetail();}}
    finally {if(current===detailSequence){pane.setAttribute("aria-busy","false");pane.inert=false;}}
  }
  function render(data) {
    const list=get("log-list");list.replaceChildren();
    const groups=new Map();
    for(const item of data.items) {
      const key=item.day+":"+item.session+":"+item.project;
      if(!groups.has(key)) {
        const group=node("section",undefined,"log-session-group");
        const day=new Date(item.day+"T12:00:00Z").toLocaleDateString("es-ES",{dateStyle:"full",timeZone:"UTC"});
        group.append(node("h3",day),node("p",item.session+" · "+(item.project||"Sin proyecto"),"log-session-meta"));groups.set(key,group);list.append(group);
      }
      const row=node("article",undefined,"log-event");row.dataset.eventId=item.event_id;
      const summary=node("p",item.summary,"log-summary");summary.id="log-summary-"+item.event_id;
      row.append(badge(item.kind,item.outcome),summary,node("p",item.agent+" · "+(item.occurred_at?when(item.occurred_at):"Hora no indicada · registrado "+when(item.recorded_at)),"log-meta"));
      if(item.command_preview) {const pre=node("pre"),code=node("code",item.command_preview);pre.append(code);row.append(pre);}
      else if(item.reference_preview) row.append(node("p",item.reference_preview,"log-target"));
      if(item.corrected_by) row.append(node("p","Registro corregido; abre el detalle para ver la corrección.","log-meta"));
      if(item.preview_truncated) row.append(node("p","Vista abreviada; abre el detalle para ver el texto completo.","log-meta"));
      const open=button("Ver acción",()=>detail(item.event_id));open.dataset.logOpen="";open.setAttribute("aria-describedby",summary.id);open.setAttribute("aria-pressed","false");row.append(open);
      if(item.command_preview) row.append(button("Copiar comando",async()=>{try {const full=await api("api/agent-log?"+new URLSearchParams({event_id:item.event_id}));await copy(full.item.command);}catch{message("No se pudo recuperar el comando completo. Abre la acción para reintentar.");}}));
      groups.get(key).append(row);
    }
    if(!data.items.length) list.append(node("p","Sin acciones registradas que coincidan. Esto no significa que el agente no haya trabajado.","log-empty"));
    get("log-count").textContent=data.items.length+" de "+data.total+" acciones";
    get("log-period").textContent=data.start_date+" — "+data.end_date+" · "+data.timezone+" · Más recientes primero"+(get("log-journal-event").value?" · Vinculadas al avance seleccionado":"");
    next=data.next_offset;
    get("log-prev").disabled=pageIndex===0;get("log-next").disabled=next===null;
    get("log-page").textContent=data.total?"Página "+(pageIndex+1):"";
  }
  function hide(){sequence++;detailSequence++;}
  async function load(reset=false) {
    const current=++sequence;detailSequence++;
    get("log-list").setAttribute("aria-busy","true");get("log-detail").inert=true;get("log-toggle").disabled=true;
    message("Leyendo acciones…");
    try {
      const info=await viewerInfo(true);
      if(current!==sequence||state.screen!=="agent-log")return;
      if(get("log-mode").value!=="custom") {const day=shift(info.today,get("log-mode").value==="yesterday"?-1:0);get("log-from").value=day;get("log-to").value=day;}
      const params=new URLSearchParams({query:get("search").value,start_date:get("log-from").value,end_date:get("log-to").value});
      for(const key of ["project","session","agent","kind","outcome","journal-event"]) if(get("log-"+key).value)params.set(key.replaceAll("-","_"),get("log-"+key).value);
      const signature=params.toString();
      if(reset||(!restoring&&lastQuery!==undefined&&lastQuery!==signature)) {offsets=[0];pageIndex=0;get("log-selected").value="";emptyDetail();}
      lastQuery=signature;params.set("offset",String(offsets[pageIndex]));
      const data=await api("api/agent-log?"+params);
      if(current!==sequence||state.screen!=="agent-log")return;
      timezone=data.timezone;revision=data.revision;enabled=data.enabled;
      get("log-activation").textContent=enabled?"Registro activado en este perfil":"Registro desactivado en este perfil";
      get("log-toggle").textContent=enabled?"Desactivar registro":"Activar registro";get("log-toggle").disabled=false;
      get("log-today").setAttribute("aria-pressed",String(get("log-mode").value==="today"));get("log-yesterday").setAttribute("aria-pressed",String(get("log-mode").value==="yesterday"));
      render(data);message(data.truncated?"Página acotada por presupuesto. Carga la siguiente para continuar.":"");
      if(!get("log-selected").value && data.items.length) get("log-selected").value=data.items[0].event_id;
      if(get("log-selected").value) await detail(get("log-selected").value,false);
      else emptyDetail();
      if(current===sequence) {get("log-detail").inert=false;remember();}
    } catch {if(current===sequence)message("No se pudo leer Agent log. El registro puede estar incompleto o no disponible. Pulsa Actualizar para reintentar.");}
    finally {if(current===sequence)get("log-list").setAttribute("aria-busy","false");}
  }
  async function openJournal(eventId,day,project) {
    get("log-mode").value="custom";get("log-from").value=day;get("log-to").value=day;get("log-journal-event").value=eventId;
    get("log-project").value=project||"";get("log-session").value="";get("log-agent").value="";get("log-kind").value="";get("log-outcome").value="";get("search").value="";
    offsets=[0];pageIndex=0;get("log-selected").value="";
    await navigate("agent-log");
  }
  document.addEventListener("DOMContentLoaded",()=>{
    get("log-filter-form").onsubmit=event=>{event.preventDefault();get("log-mode").value="custom";load(true);};
    for(const mode of ["today","yesterday"])get("log-"+mode).onclick=()=>{get("log-mode").value=mode;load(true);};
    get("log-clear").onclick=()=>{for(const key of ["project","session","agent","kind","outcome","journal-event"])get("log-"+key).value="";get("search").value="";get("log-mode").value="today";load(true);};
    get("log-next").onclick=()=>{offsets=offsets.slice(0,pageIndex+1);offsets.push(next);pageIndex++;get("log-selected").value="";load();};
    get("log-prev").onclick=()=>{pageIndex--;get("log-selected").value="";load();};
    get("log-toggle").onclick=async()=>{
      get("log-toggle").disabled=true;
      try {const requested=!enabled;await api("api/agent-log/config","POST",{enabled:requested,revision});await load();message(requested?"Registro activado para recibir acciones informadas en este perfil.":"Registro desactivado. Las acciones anteriores se conservan.");}
      catch(error){message(error.status===409?"El registro cambió. Actualiza antes de cambiar su activación.":"No se pudo cambiar la activación. Actualiza para reintentar.");}
    };
  });
  return {snapshot,restore,hide,load,openJournal};
})();
