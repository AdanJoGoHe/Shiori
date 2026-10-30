// Only the disposable profiles created by check-workspace-workflow.py --task-pages.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

async function main() {
  assert.equal(new URL(input.url).hostname, '127.0.0.1');
  const browser = await chromium.launch({headless:true,
    ...(process.env.SB_TEST_BROWSER ? {executablePath:process.env.SB_TEST_BROWSER} : {})});
  const context = await browser.newContext({viewport:{width:1440,height:1000}, reducedMotion:'reduce',
    permissions:['clipboard-read', 'clipboard-write']});
  const page = await context.newPage(), errors = [], externalRequests = [];
  page.setDefaultTimeout(10000);
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if(new URL(request.url()).hostname !== '127.0.0.1') externalRequests.push(request.url()); });
  const api = async suffix => (await page.request.get(input.url+suffix)).json();
  const idle = () => page.locator('#marks-panel[aria-busy="false"]').waitFor();
  const data = () => api('api/tasks?key=DEMO-1234');
  const body = '## Comprobar\n\n```sh\n'+input.command+'\n```\n\nIP de documentación: `192.0.2.20`.\n\n<script>globalThis.fixtureExecuted=true</script>';
  try {
    await page.goto(input.url+'#tareas');
    await page.locator('#results[aria-busy="false"]').waitFor();
    assert.equal(await page.locator('h1').innerText(), 'Tareas');
    await page.locator('#task-new').click();
    await page.locator('#task-key').fill('demo-1234');
    await page.locator('#task-title').fill('Contexto de la incidencia ficticia');
    await page.locator('#task-project').fill('demo');
    await page.locator('#task-tags').fill('ejemplo, comandos');
    await page.locator('#task-body').fill(body);
    await page.locator('#task-editor button[type="submit"]').click();
    await page.locator('#task-context').waitFor(); await idle();
    assert.equal((await data()).item.key, 'DEMO-1234');
    assert.equal((await data()).item.body, body);
    assert.equal(await page.evaluate(()=>globalThis.fixtureExecuted), undefined);
    await page.locator('.mark-lookup summary').click();
    await page.locator('#mark-exact').fill(input.command);
    await page.locator('#mark-find').click();
    await page.locator('#mark-color').selectOption('blue');
    await page.locator('#mark-tags').getByLabel('Comando', {exact:true}).check();
    await page.locator('#mark-form button[type="submit"]').click();
    await page.getByText('Marca guardada.', {exact:true}).waitFor(); await idle();
    await page.locator('#task-resources summary').click();
    await page.locator('#task-web-url').fill('https://example.test/issue/DEMO-1234');
    await page.locator('#task-web-label').fill('Gestor de ejemplo');
    await page.locator('#task-web-form button[type="submit"]').click();
    await page.locator('#task-links').getByRole('link', {name:'Gestor de ejemplo ↗', exact:true}).waitFor();
    await page.locator('[data-screen="biblioteca"]').click();
    await page.locator('#results[aria-busy="false"]').waitFor();
    await page.locator('#results .result').filter({has:page.getByRole('heading', {name:'Comandos del laboratorio', exact:true})}).click();
    await idle();
    const docId = 'documentation:demo:guide.md';
    const marks = await api('api/annotations?'+new URLSearchParams({document_id:docId}));
    const mark = marks.items.find(item=>item.quote===input.command);
    await page.locator('#task-link-panel summary').click();
    await page.locator('#task-link-key').fill('demo-1234');
    await page.locator('#task-link-selection').selectOption(mark.id);
    await page.locator('#task-link-form button[type="submit"]').click();
    await page.getByText('Vínculo guardado en DEMO-1234.', {exact:true}).waitFor();
    await page.locator('#task-link-selection').selectOption('');
    await page.locator('#task-link-form button[type="submit"]').click();
    await page.waitForFunction(async url => (await (await fetch(url+'api/tasks?key=DEMO-1234')).json()).item.links.length===3, input.url);
    await page.locator('[data-screen="tareas"]').click();
    await page.locator('#results[aria-busy="false"]').waitFor();
    await page.locator('#results .result').filter({hasText:'DEMO-1234'}).click();
    await idle(); await page.locator('#task-resources summary').click();
    await page.locator('#task-links .task-link-row').nth(2).waitFor();
    for(const width of [1280,1440,1920]) {
      await page.setViewportSize({width,height:1000});
      for(const theme of ['light','dark','latte']) {
      await page.locator('#theme').selectOption(theme);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      if(input.scope==='personal') await page.screenshot({path:path.join(input.screenshots, 'task-'+width+'-'+theme+'.png'),fullPage:true});
    }
    }
    await page.setViewportSize({width:720,height:1000});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.setViewportSize({width:1440,height:1000});
    await page.locator('#task-links button').filter({hasText:input.command.slice(0,20)}).click();
    await idle();
    assert.equal(await page.locator('#reader-title').innerText(), 'Comandos del laboratorio');
    await page.locator('#back').click();
    await page.waitForFunction(()=>document.querySelector('#reader-title').textContent.startsWith('DEMO-1234'));
    await idle();
    const fresh = (await data()).item;
    const concurrent = await page.request.post(input.url+'api/tasks', {headers:{Origin:new URL(input.url).origin}, data:{...Object.fromEntries(['key','title','body','status','project','tags','links','version'].map(key=>[key,fresh[key]])), title:'Edición simultánea'}});
    assert.equal(concurrent.status(),201);
    await page.locator('#task-edit').click();
    await page.locator('#task-body').fill(body+'\nBorrador conservado.');
    await page.locator('#task-editor button[type="submit"]').click();
    await page.waitForFunction(()=>document.getElementById('task-message').textContent.startsWith('La tarea cambió'));
    assert((await page.locator('#task-body').inputValue()).includes('Borrador conservado'));
    await page.reload(); await page.locator('#results[aria-busy="false"]').waitFor();
    await page.locator('#results .result').filter({hasText:'DEMO-1234'}).click();
    await idle();
    assert((await page.locator('#reader-body').innerText()).includes(input.command));
    assert.equal(await page.locator('.saved-mark').count(),1);
    await page.locator('#task-resources summary').click();
    const before = (await data()).item.links.length;
    await page.locator('#task-links .task-link-row').first().getByRole('button',{name:'Quitar vínculo',exact:true}).click();
    await page.waitForFunction(async arg => (await (await fetch(arg.url+'api/tasks?key=DEMO-1234')).json()).item.links.length===arg.before-1,{url:input.url,before});
    const wrong = input.scope==='personal' ? 'work' : 'personal';
    assert.equal((await page.request.get(input.url+'api/content?'+new URLSearchParams({id:'task:'+wrong+':DEMO-1234'}))).status(),400);
    assert.deepEqual(externalRequests,[]);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({scope:input.scope, checks:['create-read-mark-task','web-and-authorized-page-fragment-links','exact-anchor-and-history','optimistic-conflict-preserves-draft','reload-retains-body-and-marks','remove-link','three-themes','no-external-fetch-or-scope-leak']}));
  } finally { await browser.close(); }
}
main().catch(error=>{console.error(error.stack.replaceAll(input.url,'<fixture>/'));process.exitCode=1;});
