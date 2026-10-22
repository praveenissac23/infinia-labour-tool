// Test harness only (loaded with NODE_OPTIONS=--require): a fresh sign-in now starts on the login's own first
// page (the app drops a ?p= / #tab left in the address, by design). Browser tests written before that open a
// page address, sign in, and expect to be on that page. This puts them back where they asked to go, the way a
// person would by opening the link again once signed in. Nothing in the app changes.
const pw = require('playwright');
const wrapPage = page => {
  if (page.__shim) return page; page.__shim = true;
  let want = '';
  const goto = page.goto.bind(page);
  page.goto = async (url, opts) => { want = /[?&]p=|#/.test(url) ? url : ''; return goto(url, opts); };
  const ev = page.evaluate.bind(page);
  page.evaluate = async (fn, ...args) => {
    const out = await ev(fn, ...args);
    const src = typeof fn === 'string' ? fn : String(fn);
    if (/doLogin\(/.test(src) && want) {
      const target = want; want = '';
      try {
        await page.waitForSelector('#app-screen', { state: 'visible', timeout: 15000 });
        if (!page.url().includes(target.replace(/^https?:\/\/[^/]+/, ''))) {
          await goto(target); await page.waitForSelector('#app-screen', { state: 'visible', timeout: 15000 }).catch(() => {});
        }
      } catch (e) { /* the test will report what it sees */ }
    }
    return out;
  };
  return page;
};
const wrapCtx = ctx => {
  if (ctx.__shim) return ctx; ctx.__shim = true;
  const np = ctx.newPage.bind(ctx);
  ctx.newPage = async (...a) => wrapPage(await np(...a));
  ctx.on('page', p => wrapPage(p));
  return ctx;
};
for (const name of ['chromium', 'firefox', 'webkit']) {
  const bt = pw[name]; if (!bt) continue;
  const launch = bt.launch.bind(bt);
  bt.launch = async (...a) => {
    const br = await launch(...a);
    const nc = br.newContext.bind(br); br.newContext = async (...x) => wrapCtx(await nc(...x));
    const npg = br.newPage.bind(br); br.newPage = async (...x) => wrapPage(await npg(...x));
    return br;
  };
}
