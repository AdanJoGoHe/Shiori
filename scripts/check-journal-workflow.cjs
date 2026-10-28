// Only the disposable viewer created by check-journal-workflow.py.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

async function main() {
  assert.equal(new URL(input.url).hostname, '127.0.0.1');
  const browser = await chromium.launch({headless:true, ...(process.env.SB_TEST_BROWSER ? {executablePath:process.env.SB_TEST_BROWSER} : {})});
  const context = await browser.newContext({viewport:{width:1440,height:1000}, reducedMotion:'reduce'});
  const page = await context.newPage(), errors = [], checks = [];
  page.setDefaultTimeout(9000);
  page.on('pageerror', error => errors.push(error.message));
  const check = value => checks.push(value);
  const project = page.locator('#journal-project');
  const api = async suffix => (await page.request.get(input.url+suffix)).json();
  async function selectProject(value) {
    await project.fill(value); await project.press('Tab');
    await page.waitForFunction(() => !document.getElementById('journal-message').textContent.includes('Leyendo'));
  }
  await page.goto(input.url);
  await page.locator('.collection[data-kind="journal"]').click();
  await page.locator('#journal-count').getByText(/capturas/).waitFor();
  await selectProject('diario-demo');
  assert.equal(await page.locator('.journal-thread').count(), 2);
  assert.match(await page.locator('#journal-task-count').innerText(), /2 activos/);
  await page.locator('#journal-resume').click();
  await page.locator('#journal-resume-result').waitFor({state:'visible'});
  assert.match(await page.locator('#journal-resume-result').innerText(), /Validar el lector/);
  check('project-filter-grouped-timeline-and-resume');
  let releaseRequest;
  const hold = new Promise(resolve => { releaseRequest = resolve; });
  await page.route('**/api/journal?*',async route=>{await hold;await route.continue();});
  await project.fill('otro-demo'); await project.press('Tab');
  assert.equal(await page.locator('.journal-grid').evaluate(el=>el.inert),true);
  await assert.rejects(page.locator('.journal-task[data-task-id="editor"] summary').first().click({timeout:200}),/Timeout/);
  releaseRequest();
  await page.waitForFunction(() => !document.getElementById('journal-message').textContent.includes('Leyendo'));
  await page.unroute('**/api/journal?*');
  await selectProject('diario-demo');
  check('loading-another-project-blocks-stale-task-actions');
  const task = page.locator('.journal-task[data-task-id="editor"]');
  await task.locator('summary').filter({hasText:'Cambiar estado'}).click();
  await task.locator('select').selectOption('done');
  await task.locator('textarea').fill('Comprobado con un documento ficticio.');
  await task.getByRole('button',{name:'Guardar estado',exact:true}).click();
  await page.waitForFunction(() => document.getElementById('journal-message').textContent.startsWith('Guardado'));
  assert.equal(await page.locator('.journal-task[data-task-id="editor"]').count(), 0);
  await page.locator('#journal-task-filter').selectOption('all');
  assert.match(await task.innerText(), /Resuelto/);
  assert.match(await task.innerText(), /v3/);
  assert.match(await task.innerText(), /3 cambios/);
  check('state-change-history-and-active-filter');
  const original = page.locator('.journal-entry[data-event-id="lector-final"]');
  await original.locator('summary').filter({hasText:'Corregir o agrupar'}).click();
  await original.getByLabel('Resultado corregido').fill('Lectura verificada con cuatro ejemplos sintéticos.');
  await original.getByLabel('Qué cambia y por qué').fill('Añadida la cuarta comprobación.');
  await original.getByRole('button',{name:'Guardar corrección'}).click();
  await page.waitForFunction(() => document.getElementById('journal-message').textContent.startsWith('Guardado'));
  assert.match(await page.locator('#journal-entries').innerText(), /cuatro ejemplos sintéticos/);
  assert.match(await page.locator('#journal-entries').innerText(), /capturas anteriores/);
  check('linked-correction-preserves-original');
  await page.locator('#journal-new-task>summary').click();
  await page.locator('#journal-task-title').fill('Revisar navegación móvil');
  await page.locator('#journal-task-details').fill('<img src=x onerror="globalThis.journalInjected=true">');
  await page.locator('#journal-task-form button').click();
  await page.waitForFunction(() => document.getElementById('journal-message').textContent.startsWith('Guardado'));
  assert.equal(await page.evaluate(() => globalThis.journalInjected), undefined);
  assert.equal(await page.locator('#journal-task-list img').count(), 0);
  check('new-task-and-inert-captured-text');
  // A second session changes the task while the visible form retains the old version.
  const board = await api('api/journal-state?project=diario-demo');
  const current = board.tasks.find(row=>row.id==='editor');
  const update = {scope:'personal',mode:'journal-only',source_agent:'manual',project:'diario-demo',event_id:'browser-concurrent',title:'Estado externo',summary:'Cambio sintético de otra sesión.',tasks:[{id:current.id,title:current.title,details:current.details,status:'blocked',version:current.version}]};
  const result = await page.request.post(input.url+'api/journal',{data:update,headers:{Origin:new URL(input.url).origin}});
  assert.equal(result.status(),201);
  await task.locator('summary').filter({hasText:'Cambiar estado'}).click();
  await task.locator('select').selectOption('open');
  await task.getByRole('button',{name:'Guardar estado',exact:true}).click();
  await page.waitForFunction(() => document.getElementById('journal-message').textContent.includes('Los datos cambiaron'));
  check('concurrent-stale-version-is-rejected');
  await page.locator('.journal-entry').first().getByRole('button',{name:'Abrir día completo'}).click();
  await page.locator('#reader-content').waitFor({state:'visible'});
  assert.ok(!(await page.locator('#reader-body').innerText()).includes('shiori-data:'));
  await page.locator('.collection[data-kind="journal"]').click();
  await page.waitForFunction(() => !document.getElementById('journal-message').textContent.includes('Leyendo'));
  check('full-day-reader-hides-internal-metadata');
  await page.locator('#refresh').click();
  await page.waitForFunction(() => !document.getElementById('journal-message').textContent.includes('Leyendo'));
  await page.locator('#journal-task-filter').selectOption('active');
  const screenshots=[];
  for(const [width,theme] of [[1440,'light'],[768,'dark'],[390,'latte']]) {
    await page.setViewportSize({width,height:1000});
    await page.locator('#theme').selectOption(theme);
    await page.screenshot({path:path.join(input.screenshots,`journal-${width}-${theme}.png`),fullPage:true});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1), `horizontal overflow at ${width}`);
    screenshots.push(path.join(input.screenshots,`journal-${width}-${theme}.png`));
    if(width===390) {
      await page.locator('[data-journal-pane="tasks"]').click();
      assert.ok(await page.locator('#journal-task-list').isVisible());
      assert.ok(!(await page.locator('#journal-entries').isVisible()));
      await page.locator('[data-journal-pane="feed"]').click();
    }
  }
  check('three-widths-and-themes-without-overflow');
  await selectProject('empty-demo');
  assert.match(await page.locator('#journal-entries').innerText(),/No hay avances/);
  assert.match(await page.locator('#journal-task-list').innerText(),/No hay pendientes/);
  await page.route('**/api/journal?*',route=>route.abort());
  await page.locator('#refresh').click();
  await page.waitForFunction(() => document.getElementById('journal-message').textContent.includes('No se pudo leer'));
  check('empty-and-error-states');
  assert.deepEqual(errors,[]);
  await browser.close();
  console.log(JSON.stringify({status:'passed',data:'synthetic-only',checks,screenshots}));
}
main().catch(error=>{console.error(error);process.exit(1);});
