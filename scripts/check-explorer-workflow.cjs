// Called only by the owned Python fixture runner; no owner URL/config input.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

async function main() {
  const {url, profile, phase, date} = input;
  assert.equal(new URL(url).hostname, '127.0.0.1');
  const context = await chromium.launchPersistentContext(profile, {headless: true,
    reducedMotion: 'reduce', viewport: {width: 1000, height: 1000},
    ...(process.env.SB_TEST_BROWSER ? {executablePath: process.env.SB_TEST_BROWSER} : {})});
  const errors = [], requests = [], measurements = [];
  context.on('page', page => page.on('pageerror', error => errors.push(error.message)));
  context.on('request', request => requests.push({url: request.url(), method: request.method()}));
  let page = await context.newPage();
  page.setDefaultTimeout(10000);
  const idle = () => page.locator('#results[aria-busy="false"]').waitFor({state: 'attached'});
  const change = async action => {
    await Promise.all([page.waitForResponse(r => r.url().includes('/api/items?')), action()]);
    await idle();
  };
  const enter = async locator => { await locator.focus(); await locator.press('Enter'); };
  const open = async locator => {
    await enter(locator);
    await page.waitForFunction(() => document.querySelector('#marks-panel')?.getAttribute('aria-busy') === 'false' &&
      document.querySelector('#reader-body').textContent.length > 0);
  };
  try {
    await page.goto(url);
    await idle();
    assert((await page.locator('#results').innerText()).includes('Guide'));
    if (phase === 'restart') {
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'latte');
      assert.equal(await page.locator('#theme').inputValue(), 'latte');
      assert.equal(await page.locator('#search').inputValue(), '');
      assert.deepEqual(await page.evaluate(() => Object.keys(localStorage)), ['second-brain-theme']);
      console.log(JSON.stringify({phase, stable_origin_theme: 'latte', query: 'not persisted'}));
      return;
    }
    // Real API responses and browser paint timings; no mocked listing in this workflow.
    const searchMs = [];
    for (let run = 0; run < 3; run++) {
      const started = performance.now();
      const response = await page.request.get(url + 'api/items?kind=documentation&q=git');
      const data = await response.json();
      searchMs.push(Math.round(performance.now() - started));
      assert.equal(data.total, 25);
      assert.equal(data.items.length, 20);
      assert.equal(data.next_offset, 20);
      assert.equal(data.diagnostics.status, 'partial');
      assert(!JSON.stringify(data.diagnostics).includes('OUTSIDE-SENTINEL'));
      assert(!JSON.stringify(data.diagnostics).includes(profile));
    }
    await change(() => enter(page.getByRole('button', {name: 'Documentación', exact: true})));
    assert.equal(await page.locator('#results button.result').count(), 20);
    await change(() => enter(page.locator('#next')));
    assert.equal(await page.locator('#results button.result').count(), 5);
    await change(() => enter(page.locator('#prev')));
    await change(() => page.locator('#source').selectOption('empty'));
    assert((await page.locator('#results').innerText()).includes('está vacía'));
    await change(() => page.locator('#source').selectOption('acceptance'));
    await change(() => page.locator('#sort').selectOption('title'));
    await open(page.locator('#results button.result').first());
    assert.equal(await page.locator('#reader-title').innerText(), 'Guide 00');
    assert.equal(await page.locator('#reader-body table').count(), 1);
    assert.equal(await page.locator('#reader-body pre').count(), 1);
    assert.equal(await page.locator('#reader-body script, #reader-body img').count(), 0);
    assert.equal(await page.evaluate(() => globalThis.fixtureExecuted), undefined);
    await enter(page.locator('#reader-body a').filter({hasText: 'Fuera'}));
    assert((await page.locator('#warning').innerText()).includes('no está disponible'));
    await enter(page.locator('#reader-body a').filter({hasText: 'Siguiente guía'}));
    await page.waitForFunction(() => document.querySelector('#reader-title').textContent === 'Guide 01');
    await page.waitForFunction(() => document.querySelector('#marks-panel').getAttribute('aria-busy') === 'false');
    await enter(page.locator('#back'));
    await change(() => enter(page.getByRole('button', {name: 'Conocimiento', exact: true})));
    await change(() => page.locator('#search').fill('git version'));
    await enter(page.locator('.extra-filters').locator('..').locator('summary'));
    for (const [id, value] of [['project','acceptance'],['type','command'],['status','verified'],['source_agent','codex']])
      await change(() => page.locator('#' + id).selectOption(value));
    for (const id of ['from', 'to']) await change(() => page.locator('#' + id).fill(date));
    for (const tag of ['synthetic','windows'])
      await change(() => enter(page.locator('#tags').getByRole('button', {name: tag, exact: true})));
    assert.equal(await page.locator('#results button.result').count(), 2);
    await open(page.locator('#results button.result').filter({hasText: 'Synthetic command'}));
    assert((await page.locator('#reader-body').innerText()).includes('Synthetic observable evidence'));
    await enter(page.locator('#reader-body a').filter({hasText: 'other'}));
    await page.waitForFunction(() => document.querySelector('#reader-title').textContent === 'Synthetic other');
    await page.waitForFunction(() => document.querySelector('#marks-panel').getAttribute('aria-busy') === 'false');
    await enter(page.locator('#back'));
    assert.equal(await page.locator('#search').inputValue(), 'git version');
    assert.equal(await page.locator('#type').inputValue(), 'command');
    assert.equal(await page.locator('#from').inputValue(), date);
    assert.equal(await page.locator('#tags [aria-pressed="true"]').count(), 2);

    // Real keyboard tabbing through the native selector, reload and browser-storage failure.
    for (const width of [1440, 820, 390]) {
      await page.setViewportSize({width, height: 1000});
      for (const theme of ['light', 'dark', 'latte']) {
        await page.locator('#theme').focus();
        await page.keyboard.press('Home');
        for (let n = 0; n < ['light','dark','latte'].indexOf(theme); n++) await page.keyboard.press('ArrowDown');
        await page.keyboard.press('Tab');
        assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
        await page.reload(); await idle();
        assert.equal(await page.locator('#theme').inputValue(), theme);
        await change(() => enter(page.getByRole('button', {name: 'Documentación', exact: true})));
        await change(() => page.locator('#sort').selectOption('title'));
        const started = performance.now();
        await open(page.locator('#results button.result').first());
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const renderMs = performance.now() - started;
        const contrast = await page.evaluate(() => {
          const rgb = s => s.match(/[\d.]+/g).slice(0,3).map(Number);
          const luminance = c => c.map(v => {v /= 255; return v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4;})
            .reduce((s,v,i) => s+v*[.2126,.7152,.0722][i],0);
          const ratio = (a,b) => (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
          const result = {};
          for (const selector of ['#reader-body', '#reader-body pre', '#reader-body code', '#reader-body td', '#reader-body a', '#theme', '#search', '.tag', '#warning']) {
            const el = document.querySelector(selector), style = getComputedStyle(el);
            let bg = el;
            while (getComputedStyle(bg).backgroundColor === 'rgba(0, 0, 0, 0)' && bg.parentElement) bg = bg.parentElement;
            result[selector] = ratio(luminance(rgb(style.color)), luminance(rgb(getComputedStyle(bg).backgroundColor)));
          }
          const button = document.querySelector('#refresh'); button.focus();
          result.focus = ratio(luminance(rgb(getComputedStyle(button).outlineColor)), luminance(rgb(getComputedStyle(document.documentElement).backgroundColor)));
          return result;
        });
        for (const [selector, value] of Object.entries(contrast)) assert(value >= (selector === 'focus' ? 3 : 4.5), `${theme}/${selector}: ${value}`);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Horizontal overflow');
        measurements.push({width, theme, render_ms: Math.round(renderMs), contrast});
        if (process.env.SB_TEST_SCREENSHOTS) {
          await page.locator('#reader-title').scrollIntoViewIfNeeded();
          await page.screenshot({path: require('node:path').join(process.env.SB_TEST_SCREENSHOTS, `explorer-${theme}-${width}.png`)});
        }
      }
    }
    assert.deepEqual(await page.evaluate(() => Object.keys(localStorage)), ['second-brain-theme']);
    await page.evaluate(() => localStorage.setItem('second-brain-theme', 'invalid-theme'));
    await page.reload(); await idle();
    assert.equal(await page.locator('#theme').inputValue(), 'light');
    await page.locator('#theme').selectOption('latte');
    await page.close();
    // Override storage only in a separate context, never in product code.
    const blocked = await context.browser().newContext({colorScheme: 'dark'});
    blocked.on('request', request => requests.push({url: request.url(), method: request.method()}));
    await blocked.addInitScript(() => Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('blocked', 'SecurityError');}}));
    page = await blocked.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url); await idle();
    assert.equal(await page.locator('#theme').inputValue(), 'light');
    await page.locator('#theme').selectOption('dark');
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    await page.reload(); await idle();
    assert.equal(await page.locator('#theme').inputValue(), 'light');
    await open(page.locator('#results button.result').first());
    await blocked.close();
    assert.deepEqual(errors, []);
    assert(requests.every(r => new URL(r.url).origin === new URL(url).origin), 'External request');
    assert(requests.every(r => r.method === 'GET'), 'Unexpected viewer mutation');
    console.log(JSON.stringify({phase, search_ms: searchMs, measurements, network: 'same-origin GET only', errors}));
  } finally { await context.close(); }
}
main().catch(error => {console.error(error.stack.replaceAll(input.url, '<fixture>/')); process.exitCode = 1;});
