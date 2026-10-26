// Optional browser acceptance. Use a disposable demo server, never the owner's viewer.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

async function main() {
  const url = process.env.SB_VIEWER_TEST_URL;
  assert(url && new URL(url).hostname === '127.0.0.1', 'Select a disposable loopback demo URL');
  const browser = await chromium.launch({headless: true,
    ...(process.env.SB_TEST_BROWSER ? {executablePath: process.env.SB_TEST_BROWSER} : {})});
  let stage = 'initial';
  let page;
  try {
    page = await browser.newPage({reducedMotion: 'reduce'});
    page.setDefaultTimeout(5000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.locator('#results[aria-busy="false"]').waitFor({state: 'attached'});
    const original = await (await page.request.get(url + 'api/items')).json();
    assert(original.items.length, 'Demo needs at least one readable document');
    const cases = [
      ['empty', 'empty-catalog', [], 'La colección seleccionada está vacía', []],
      ['ready', 'no-matches', [], 'No hay resultados con estos filtros', []],
      ['unavailable', 'unavailable', [], 'No se pudo leer el contenido', ['invalid-content', 'ledger-catalog-mismatch']],
      ['partial', 'ready', original.items, 'Lectura parcial', ['unavailable']],
      ['partial', 'partial', [], 'La búsqueda está incompleta', ['invalid-content']],
      ['limited', 'limited', [], 'límite de escaneo', ['scan-limit']],
    ];
    let current;
    await page.route('**/api/items?*', route => route.fulfill({json: current}));
    let checked = 0;
    for (const width of [1440, 820, 390]) {
      await page.setViewportSize({width, height: 1000});
      // Start each responsive layout from a fresh document rather than a scrolled prior one.
      if (current) {
        await page.reload();
        await page.locator('#results[aria-busy="false"]').waitFor({state: 'attached'});
      }
      for (const theme of ['light', 'dark', 'latte']) {
        await page.bringToFront();
        await page.locator('#theme').selectOption(theme);
        for (const [status, result_state, items, expected, codes] of cases) {
          stage = `${width}/${theme}/${status}/${items.length}`;
          current = {...original, items, total: items.length, next_offset: null, result_state,
            truncated: status === 'limited', errors: codes.map(code => ({kind: 'note', source: 'personal', code})),
            diagnostics: {...original.diagnostics, status, codes}};
          await page.bringToFront();
          await page.locator('#refresh').focus();
          await Promise.all([
            page.waitForResponse(r => r.url().includes('/api/items?')),
            page.locator('#refresh').press('Enter')
          ]);
          await page.locator('#results[aria-busy="false"]').waitFor({state: 'attached'});
          const content = await page.locator('main').innerText();
          assert(content.includes(expected), `${width}/${theme}/${status}: missing state message`);
          assert.equal(await page.locator('#warning').getAttribute('role'), 'status');
          if (codes.length) {
            assert.equal(await page.locator('#warning').isVisible(), true);
            assert((await page.locator('#warning').innerText()).includes(codes[0]));
            const retry = page.getByRole('button', {name: 'Reintentar lectura', exact: true});
            await retry.focus();
            await Promise.all([
              page.waitForResponse(r => r.url().includes('/api/items?')),
              retry.press('Enter')
            ]);
            await page.locator('#results[aria-busy="false"]').waitFor({state: 'attached'});
          } else assert.equal(await page.locator('#warning').isVisible(), false);
          if (items.length) assert.equal(await page.locator('#results button.result').count(), items.length);
          else if (codes.length) assert(!content.includes('Prueba otro término o limpia la selección'));
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Horizontal overflow');
          checked++;
        }
      }
    }
    // A running old Python process can serve newly installed static files.
    current = {...original};
    delete current.diagnostics;
    await page.locator('#refresh').click();
    await page.locator('#results[aria-busy="false"]').waitFor({state: 'attached'});
    assert((await page.locator('#warning').innerText()).includes('Reinicia el visor'));
    assert.equal(await page.locator('#count').innerText(), 'No disponible');
    current = {...original, diagnostics: {...original.diagnostics, status: 'partial', codes: ['unavailable']}};
    await page.locator('#refresh').click();
    await page.locator('#results[aria-busy="false"]').waitFor({state: 'attached'});
    await page.locator('#results button.result').first().focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#reader-body').textContent.length > 0);
    await page.locator('#marks-panel[aria-busy="false"]').waitFor();
    assert((await page.locator('#reader-body').innerText()).length > 0);
    await page.locator('#back').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#results button.result').first().isVisible(), true);
    assert.deepEqual(errors, []);
    console.log(`${checked} viewer state/theme/viewport cases passed; keyboard refresh/retry/open/back; old-server warning; no page errors`);
  } catch(error) {
    throw new Error(stage + ': ' + error.message.replaceAll(url, '<demo-session>/'));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
