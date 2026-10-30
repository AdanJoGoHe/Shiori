// Only the disposable server created by check-workspace-workflow.py.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

async function main() {
  assert.equal(new URL(input.url).hostname, '127.0.0.1');
  const browser = await chromium.launch({headless: true,
    ...(process.env.SB_TEST_BROWSER ? {executablePath: process.env.SB_TEST_BROWSER} : {})});
  const context = await browser.newContext({viewport: {width:1440, height:1000}, reducedMotion:'reduce',
    permissions:['clipboard-read', 'clipboard-write']});
  const page = await context.newPage(), errors = [], checks = [];
  page.setDefaultTimeout(8000);
  page.on('pageerror', error => errors.push(error.message));
  const check = value => checks.push(value);
  const idle = () => page.locator('#results[aria-busy="false"]').waitFor();
  const home = () => page.locator('#home-journal[aria-busy="false"]').waitFor();
  try {
    await page.goto(input.url);
    await home();
    await page.locator('#home-pages[aria-busy="false"]').waitFor();
    await page.locator('#home-fragments[aria-busy="false"]').waitFor();
    assert.equal(await page.locator('h1').innerText(), 'Inicio');
    assert.match(await page.locator('#memory-scope').innerText(), input.scope === 'work' ? /trabajo/ : /personal/);
    assert.match(await page.locator('#home-journal').innerText(), /2026-10-30/);
    assert.match(await page.locator('#home-journal').innerText(), /Lector comprobado/);
    assert.equal(await page.locator('#home-pages .result').count(), 2);
    assert.equal(await page.locator('#home-fragments .fragment-result').count(), 2);
    for (const width of [1280, 1440, 1920]) {
      await page.setViewportSize({width, height:1000});
      for (const theme of ['light', 'dark', 'latte']) {
        await page.locator('#theme').selectOption(theme);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Page overflow');
        assert(await page.locator('#search').isVisible());
        const contrasts = await page.locator('#home-fragments .reader-mark').evaluateAll(nodes => {
          const light = value => {
            const channels = value.match(/[0-9.]+/g).slice(0, 3).map(Number).map(c => c / 255);
            const linear = channels.map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
            return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
          };
          return nodes.map(node => {
            const style = getComputedStyle(node), a = light(style.color), b = light(style.backgroundColor);
            return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          });
        });
        assert(contrasts.every(value => value >= 4.5), 'Fragment text contrast');
        assert.equal(await page.locator('.sidebar').evaluate(el => getComputedStyle(el).position), 'sticky');
        if (input.scope === 'personal') await page.screenshot({path:path.join(input.screenshots, `home-${width}-${theme}.png`), fullPage:true});
      }
    }
    check('home-uses-server-day-scope-and-real-bounded-data-in-nine-desktop-layouts');
    await page.setViewportSize({width:720, height:900});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Desktop zoom reflow');
    await page.setViewportSize({width:1440, height:1000});
    await page.locator('#home-fragments').getByRole('button', {name:'Copiar fragmento', exact:true}).first().click();
    await page.getByText('Fragmento copiado.', {exact:true}).waitFor();
    assert(await page.locator('#copy-message').isVisible());
    check('home-copy-feedback-highlight-contrast-and-desktop-zoom-reflow');
    await page.locator('#home-shortcuts').getByRole('button', {name:'Comando', exact:true}).click();
    await page.waitForFunction(() => document.querySelector('#count').textContent === '1 resultado');
    assert.equal(await page.locator('#results .fragment-quote').innerText(), input.command);
    await page.getByRole('button', {name:'Copiar fragmento', exact:true}).click();
    assert.equal((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n'), input.command);
    await page.locator('#project').selectOption('laboratorio');
    await idle();
    await page.locator('#search').fill('kubectl');
    await page.waitForResponse(response => response.url().includes('q=kubectl'));
    await idle();
    const open = page.getByRole('button', {name:'Abrir ubicación', exact:true});
    await open.click();
    await page.locator('#marks-panel[aria-busy="false"]').waitFor();
    assert.equal(await page.locator('#reader-title').innerText(), 'Comandos del laboratorio');
    const historyLength = await page.evaluate(() => history.length);
    await page.locator('#refresh').click();
    await page.locator('#marks-panel[aria-busy="false"]').waitFor();
    assert.equal(await page.evaluate(() => history.length), historyLength, 'Refresh must not add a reader entry');
    await page.locator('#back').click();
    await page.waitForFunction(() => !document.body.classList.contains('reading'));
    await idle();
    assert.equal(await page.locator('#search').inputValue(), 'kubectl');
    assert.equal(await page.locator('#project').inputValue(), 'laboratorio');
    assert.equal(await page.locator('#fragment-categories [data-category="comando"]').getAttribute('aria-pressed'), 'true');
    await page.goForward();
    await page.locator('#marks-panel[aria-busy="false"]').waitFor();
    assert.equal(await page.locator('#reader-title').innerText(), 'Comandos del laboratorio');
    await page.goBack(); await idle();
    await page.locator('#active-filters').getByRole('button', {name:'Quitar filtro: Texto: kubectl', exact:true}).click();
    await idle();
    assert.equal(await page.locator('#search').inputValue(), '');
    assert.equal(new URL(page.url()).search, '');
    check('home-category-exact-copy-open-back-forward-and-individual-filter-removal');
    await page.locator('[data-screen="biblioteca"]').click(); await idle();
    await page.locator('#next').click(); await idle();
    assert.match(await page.locator('#page').innerText(), /^21/);
    await page.locator('[data-screen="diario"]').click();
    await page.locator('#journal-count').getByText(/capturas/).waitFor();
    await page.goBack(); await idle();
    assert.equal(await page.locator('h1').innerText(), 'Biblioteca');
    assert.match(await page.locator('#page').innerText(), /^21/);
    await page.keyboard.press('Control+k');
    assert.equal(await page.locator('#search').evaluate(el=>el===document.activeElement), true);
    check('navigation-restores-paging-and-keyboard-search');
    for (const screen of ['favoritos', 'agent-log']) {
      await page.locator(`[data-screen="${screen}"]`).click();
      await page.locator('#upcoming-panel').waitFor();
      assert.match(await page.locator('#upcoming-title').innerText(), /pendiente/);
    }
    check('unimplemented-destinations-do-not-claim-storage-or-collection');
    await page.locator('[data-screen="inicio"]').click(); await home();
    await page.locator('#search').fill('kubectl');
    await page.waitForFunction(() => document.querySelector('h1').textContent === 'Biblioteca');
    await idle();
    assert.equal(await page.locator('#results .result').count(), 1);
    assert.equal(new URL(page.url()).hash, '#biblioteca');
    check('visible-search-from-home-queries-library-without-query-in-url');
    await page.route('**/api/items?*', route => route.fulfill({status:503, json:{error:'Synthetic failure'}}));
    await page.locator('[data-screen="inicio"]').click(); await home();
    await page.locator('#home-pages[aria-busy="false"]').waitFor();
    assert.match(await page.locator('#home-pages').innerText(), /No se pudo leer/);
    assert.match(await page.locator('#home-journal').innerText(), /Lector comprobado/);
    await page.unroute('**/api/items?*');
    await page.locator('#home-pages').getByRole('button', {name:'Reintentar', exact:true}).click();
    await page.locator('#home-pages .result').first().waitFor();
    await home();
    check('section-failure-keeps-independent-data-and-recovers');
    await page.route('**/api/items?*', async route => {
      const response = await route.fetch(); const data = await response.json();
      await route.fulfill({json:{...data, items:[], total:0, next_offset:null,
        diagnostics:{...data.diagnostics, status:'partial'}}});
    });
    await page.locator('#refresh').click(); await home();
    await page.locator('#home-pages[aria-busy="false"]').waitFor();
    assert.match(await page.locator('#home-pages').innerText(), /No se pudo confirmar/);
    assert.doesNotMatch(await page.locator('#home-pages').innerText(), /Todavía no hay páginas/);
    check('incomplete-catalog-does-not-masquerade-as-empty');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({scope:input.scope, checks}));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.stack); process.exitCode=1; });
