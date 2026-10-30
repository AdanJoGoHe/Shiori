// Run through check-annotation-workflow.py; never point this mutation test at a personal viewer.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const documentId = 'documentation:acceptance:guide.md';

async function main() {
  assert.equal(new URL(input.url).hostname, '127.0.0.1');
  const browser = await chromium.launch({headless: true,
    ...(process.env.SB_TEST_BROWSER ? {executablePath: process.env.SB_TEST_BROWSER} : {})});
  const touch = input.phase === 'touch';
  const context = await browser.newContext({viewport: {width: touch ? 390 : 1000, height: 1000},
    hasTouch: touch, isMobile: touch, reducedMotion: 'reduce',
    ...(!touch ? {permissions: ['clipboard-read', 'clipboard-write']} : {})});
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const state = {...input.state, checks: []};
  const check = name => state.checks.push(name);
  const row = id => page.locator(`.saved-mark[data-mark-id="${id}"]`);
  async function api(path) { return (await page.request.get(input.url + path)).json(); }
  async function marks() {
    return (await api('api/annotations?' + new URLSearchParams({document_id: documentId}))).items;
  }
  async function idle() { await page.locator('#marks-panel[aria-busy="false"]').waitFor(); }
  async function activate(locator) {
    if (touch) await locator.tap();
    else { await locator.click({trial: true}); await locator.press('Enter'); }
  }
  async function open() {
    await page.goto(input.url + '#biblioteca');
    await page.locator('#results[aria-busy="false"]').waitFor();
    const button = page.locator('#results button.result').filter({hasText: 'SB-ANNOTATION-ACCEPTANCE'});
    await activate(button);
    await idle();
    assert((await page.locator('#reader-body').innerText()).includes('Datos sintéticos'));
    assert.equal(await page.evaluate(() => globalThis.fixtureExecuted), undefined);
  }
  async function exact(quote, color, tags, title = '', description = '') {
    if (await page.locator('.mark-lookup').getAttribute('open') === null)
      await activate(page.locator('.mark-lookup summary'));
    await page.locator('#mark-exact').fill(quote);
    await activate(page.locator('#mark-find'));
    await page.locator('#mark-form').waitFor();
    assert.equal(await page.locator('#mark-quote').innerText(), quote);
    await page.locator('#mark-color').selectOption(color);
    await page.locator('#mark-title').fill(title);
    await page.locator('#mark-description').fill(description);
    for (const tag of tags) await page.locator(`#mark-tags input[value="${tag}"]`).check();
    await activate(page.locator('#mark-form button[type="submit"]'));
    await page.getByText('Marca guardada.', {exact: true}).waitFor();
    await idle();
  }
  async function fragments(query = input.command) {
    if (await page.locator('#back').isVisible()) await activate(page.locator('#back'));
    await page.locator('#view').selectOption('fragments');
    await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/items?') &&
        new URL(r.url()).searchParams.get('q') === query.replace(/\r?\n/g, ' ')),
      page.locator('#search').fill(query)
    ]);
    await page.locator('#results[aria-busy="false"]').waitFor();
    await page.waitForFunction(() => document.querySelector('#results .fragment-result'));
  }
  try {
    // This title/marker check prevents accidental use against an arbitrary personal deployment.
    if (input.phase !== 'orphan') {
      const doc = await api('api/content?' + new URLSearchParams({id: documentId}));
      assert.equal(doc.item.title, 'SB-ANNOTATION-ACCEPTANCE');
      assert(doc.text.includes('Datos sintéticos'));
    }
    if (input.phase === 'create') {
      await open();
      const target = page.locator('#reader-body p').filter({hasText: input.prose});
      await target.scrollIntoViewIfNeeded();
      const rect = await target.evaluate(node => {
        const r = document.createRange(); r.selectNodeContents(node);
        const b = r.getBoundingClientRect(); return {x: b.x, y: b.y, width: b.width, height: b.height};
      });
      await page.mouse.move(rect.x, rect.y + rect.height / 2);
      await page.mouse.down();
      await page.mouse.move(rect.x + rect.width, rect.y + rect.height / 2, {steps: 12});
      await page.mouse.up();
      assert.equal(await page.evaluate(() => getSelection().toString()), input.prose);
      await activate(page.locator('#mark-selection'));
      await activate(page.locator('#mark-form button[type="submit"]'));
      await page.getByText('Marca guardada.', {exact: true}).waitFor();
      await idle();
      check('native pointer prose selection');
      await exact(input.command, 'green', ['comando', 'informacion-importante'],
        'Ver versión local 😀', 'Consultar una herramienta de desarrollo.');
      state.commandId = (await marks()).find(m => m.quote === input.command).id;
      await activate(row(state.commandId).getByRole('button', {name: 'Editar detalles', exact: true}));
      assert.equal(await page.evaluate(() => document.activeElement.id), 'mark-title');
      assert.equal(await page.locator('#mark-selection-fields').isVisible(), false);
      state.commandTitle = 'Comprobar versión instalada 😀';
      state.commandDescription = 'Consultar herramientas <img src=x onerror="globalThis.fixtureExecuted=true">';
      await page.locator('#mark-title').fill(state.commandTitle);
      await page.locator('#mark-description').fill(state.commandDescription);
      for (const width of [1440, 820, 390]) {
        await page.setViewportSize({width, height: 1000});
        for (const theme of ['light', 'dark', 'latte']) {
          await page.locator('#theme').selectOption(theme);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          if (process.env.SB_TEST_SCREENSHOTS) {
            await page.locator('#mark-form').evaluate(el => el.scrollIntoView({block: 'start'}));
            await page.screenshot({path: require('node:path').join(process.env.SB_TEST_SCREENSHOTS, `named-form-${theme}-${width}.png`)});
          }
        }
      }
      await page.setViewportSize({width: 1000, height: 1000});
      await activate(page.locator('#mark-form button[type="submit"]'));
      await idle();
      assert.equal(await row(state.commandId).locator('h4').textContent(), state.commandTitle);
      assert.equal(await row(state.commandId).locator('img').count(), 0);
      check('create and keyboard-edit optional title/description as inert text');
      await exact('git --version', 'pink', ['comando']);
      await exact('192.0.2.44', 'blue', ['direccion-ip']);
      state.ipId = (await marks()).find(m => m.quote === '192.0.2.44').id;
      await exact('texto repetido', 'violet', ['informacion-importante']);
      await exact('<img src=x onerror="globalThis.fixtureExecuted=true">', 'yellow', []);
      assert.equal(await page.locator('#reader-body img').count(), 0);
      await activate(page.locator(`#reader-body mark[data-mark-id="${state.ipId}"]`));
      await page.locator('#mark-form').waitFor();
      assert.equal(await page.locator('#mark-quote').textContent(), '192.0.2.44');
      await page.locator('#mark-color').selectOption('orange');
      await page.locator('#mark-tags input[value="informacion-importante"]').check();
      await activate(page.locator('#mark-form button[type="submit"]'));
      await idle();
      const edited = (await marks()).find(m => m.id === state.ipId);
      assert.equal(edited.color, 'orange');
      assert.deepEqual(edited.tags.sort(), ['direccion-ip', 'informacion-importante']);
      check('keyboard activation of a highlight edits color/tags without changing ID');
      check('Unicode multiline code, inline IP, repeated quote, overlap and multi-tags');
      assert(await page.locator('#reader-body mark[data-color="pink"]').count());
      const beforeBoundary = (await marks()).map(m => m.id).sort();
      await page.evaluate(() => {
        const range = document.createRange();
        range.selectNodeContents(document.querySelector('#reader-body'));
        range.setEndAfter(document.querySelector('#mark-message'));
        getSelection().removeAllRanges(); getSelection().addRange(range);
      });
      await page.getByText('La selección debe estar completamente dentro del documento.', {exact: true}).waitFor();
      assert.deepEqual((await marks()).map(m => m.id).sort(), beforeBoundary);
      check('cross-boundary selection rejected without losing marks');
      await activate(row(state.ipId).getByRole('button', {name: 'Eliminar marca', exact: true}));
      await page.getByText('Marca eliminada.', {exact: false}).waitFor();
      await idle();
      assert.equal(await page.evaluate(() => document.activeElement.id), 'mark-undo');
      await activate(page.locator('#mark-undo'));
      await page.getByText('Marca recuperada.', {exact: true}).waitFor();
      await idle();
      assert((await marks()).some(m => m.id === state.ipId));
      check('delete/undo preserves ID and keyboard focus');
      await activate(page.locator('#back'));
      await page.locator('#category-manager summary').click();
      await page.getByRole('group', {name: 'Comando', exact: true})
        .getByRole('button', {name: 'Editar', exact: true}).click();
      const renamed = 'Comando <img src=x onerror="globalThis.fixtureExecuted=true">';
      await page.locator('#category-name').fill(renamed);
      await page.locator('#category-color').selectOption('orange');
      await activate(page.locator('#category-save'));
      await page.getByRole('group', {name: renamed, exact: true}).waitFor();
      assert.equal(await page.locator('#category-list img').count(), 0);
      assert.equal((await marks()).find(m => m.id === state.commandId).color, 'green');
      check('category edit preserves explicit mark color');
      state.ids = (await marks()).map(m => m.id).sort();
      await page.reload();
      assert.deepEqual((await marks()).map(m => m.id).sort(), state.ids);
      await fragments();
      await activate(page.locator('#fragment-categories [data-category="comando"]'));
      await activate(page.locator('#fragment-categories [data-category="informacion-importante"]'));
      await page.locator('#fragment-color').selectOption('green');
      await page.locator('#source').selectOption('acceptance');
      await page.locator('#project').selectOption('acceptance');
      await page.locator('#results[aria-busy="false"]').waitFor();
      assert.equal(await page.locator('.fragment-result').count(), 1);
      const result = page.locator('.fragment-result');
      const queryBefore = await page.locator('#search').inputValue();
      assert.equal(await result.locator('.fragment-quote').textContent(), input.command);
      assert.equal(await result.locator('h3').textContent(), state.commandTitle);
      assert.equal(await result.locator('.mark-description').textContent(), state.commandDescription);
      await activate(result.getByRole('button', {name: 'Copiar fragmento', exact: true}));
      await page.getByText('Fragmento copiado.', {exact: true}).waitFor();
      assert.equal((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n'), input.command);
      await activate(result.getByRole('button', {name: 'Abrir ubicación', exact: true}));
      await page.getByText('Fragmento localizado.', {exact: false}).waitFor();
      assert.equal(await page.evaluate(() => getSelection().toString()), input.command);
      await activate(page.locator('#back'));
      assert.equal(await page.locator('#search').inputValue(), queryBefore);
      assert.equal(await page.locator('#fragment-color').inputValue(), 'green');
      assert.equal(await page.locator('#project').inputValue(), 'acceptance');
      check('combined filters, native clipboard, exact overlapped code navigation and Back');
      await fragments('herramientas instalada');
      assert.equal(await page.locator('.fragment-result').count(), 1);
      assert.equal(await page.locator('.fragment-result .fragment-quote').textContent(), input.command);
      check('find exact command by title/description without remembering quote');
    } else if (input.phase === 'restart' || input.phase === 'reattached') {
      await open();
      const items = await marks();
      assert.deepEqual(items.map(m => m.id).sort(), state.ids);
      assert(items.every(m => m.anchor.status === 'resolved'));
      assert.equal(items.find(m => m.id === state.commandId).title, state.commandTitle);
      assert.equal(items.find(m => m.id === state.commandId).description, state.commandDescription);
      if (input.phase === 'reattached') assert(items.every(m => m.anchor.reason === 'reattached'));
      assert(await page.locator('#mark-undo').isDisabled());
      check(input.phase === 'restart' ? 'real server process restart preserves marks and clears undo' :
        'formatting-only edit reattaches without mutation');
    } else if (input.phase === 'ambiguous') {
      const item = (await marks()).find(m => m.id === state.commandId);
      assert.equal(item.anchor.reason, 'ambiguous');
      assert.equal(item.anchor.start, null);
      await page.goto(input.url + '#biblioteca');
      await fragments();
      await page.locator('.fragment-result').filter({hasText: 'texto ambiguo'}).first().waitFor();
      await activate(page.locator('.fragment-result').filter({has: page.getByText(input.command, {exact: true})})
        .getByRole('button', {name: 'Revisar marca', exact: true}));
      await idle();
      await activate(row(state.commandId).getByRole('button', {name: 'Volver a enlazar', exact: true}));
      await exact('Nueva ubicación confirmada 😀', 'green', ['comando', 'informacion-importante'],
        state.commandTitle, state.commandDescription);
      const repaired = (await marks()).find(m => m.id === state.commandId);
      assert.equal(repaired.anchor.status, 'resolved');
      assert.deepEqual(repaired.tags.sort(), ['comando', 'informacion-importante']);
      assert.equal(repaired.title, state.commandTitle);
      state.command = repaired.quote;
      check('ambiguous duplicates never auto-move; reader/search explain and manual repair preserves ID/tags');
    } else if (input.phase === 'orphan') {
      await page.goto(input.url + '#biblioteca');
      await fragments(state.command);
      const result = page.locator('.fragment-result');
      await result.filter({hasText: 'documento no disponible'}).waitFor();
      await activate(result.getByRole('button', {name: 'Revisar marca', exact: true}));
      await idle();
      assert(await page.locator('#mark-find').isDisabled());
      const before = (await marks()).find(m => m.id === state.commandId);
      await activate(row(state.commandId).getByRole('button', {name: 'Editar detalles', exact: true}));
      await page.locator('#mark-title').fill('Aprendizaje recuperable');
      await activate(page.locator('#mark-form button[type="submit"]'));
      await idle();
      const details = (await marks()).find(m => m.id === state.commandId);
      assert.equal(details.title, 'Aprendizaje recuperable');
      for (const key of ['quote', 'revision', 'start', 'end', 'prefix', 'suffix']) assert.equal(details[key], before[key]);
      await activate(row(state.commandId).getByRole('button', {name: 'Eliminar marca', exact: true}));
      await idle();
      await activate(page.locator('#mark-undo'));
      await page.getByText('Marca recuperada.', {exact: true}).waitFor();
      const orphan = (await marks()).find(m => m.id === state.commandId);
      assert.equal(orphan.anchor.reason, 'unavailable');
      assert.equal(orphan.quote, state.command);
      assert.equal(orphan.title, 'Aprendizaje recuperable');
      assert.equal(orphan.description, state.commandDescription);
      check('deleted source retains quote, disables relink selection and permits delete/undo');
    } else if (touch) {
      await open();
      assert.equal((await marks()).find(m => m.id === state.commandId).anchor.reason, 'missing');
      assert((await row(state.commandId).innerText()).includes('Texto desaparecido'));
      await exact('C:\\fixture\\datos', 'orange', ['ruta']);
      await exact(input.command, 'green', ['comando', 'informacion-importante']);
      await exact('192.0.2.44', 'blue', ['direccion-ip']);
      await exact('local', 'pink', []);
      assert((await marks()).some(m => m.quote === 'C:\\fixture\\datos'));
      assert.equal(new Set(await page.locator('#reader-body mark').evaluateAll(nodes => nodes.map(n => n.dataset.color))).size, 6);
      state.contrast = [];
      for (const theme of ['light', 'dark', 'latte']) {
        await page.locator('#theme').selectOption(theme);
        const contrast = await page.locator('#reader-body mark').evaluateAll(nodes => {
          function luminance(rgb) {
            const v = rgb.match(/[\d.]+/g).slice(0, 3).map(Number).map(n => n / 255)
              .map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4);
            return v[0] * .2126 + v[1] * .7152 + v[2] * .0722;
          }
          return nodes.map(n => {const s = getComputedStyle(n), a = luminance(s.color), b = luminance(s.backgroundColor);
            return (Math.max(a,b) + .05) / (Math.min(a,b) + .05);});
        });
        assert(contrast.length && contrast.every(n => n >= 4.5));
        state.contrast.push({theme, minimum: Math.min(...contrast)});
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      }
      await activate(page.locator('#back'));
      await fragments('C:\\fixture\\datos');
      await activate(page.locator('.fragment-result').getByRole('button', {name: 'Abrir ubicación', exact: true}));
      await page.getByText('Fragmento localizado.', {exact: false}).waitFor();
      await page.locator('#reader-body a[data-content-id="documentation:acceptance:other.md"]').tap();
      await page.locator('#reader-title').filter({hasText: 'Synthetic link destination'}).waitFor();
      await idle();
      check('emulated touch exact-text marking and navigation at390px; highlight contrast in three themes');
    }
    assert.deepEqual(errors, []);
    assert.equal(await page.evaluate(() => globalThis.fixtureExecuted), undefined);
    process.stdout.write(JSON.stringify(state));
  } finally { await browser.close(); }
}
main().catch(error => {console.error(error.stack.replaceAll(input.url, '<fixture>/')); process.exitCode = 1;});
