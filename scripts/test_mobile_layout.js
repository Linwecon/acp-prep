// Real-browser layout regression: NODE_PATH must include Playwright if not installed locally.
// Run: node scripts/test_mobile_layout.js (uses installed Edge; BROWSER_CHANNEL overrides it).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..');

(async () => {
    const server = http.createServer((req, res) => {
        const name = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        const file = path.resolve(ROOT, '.' + (name === '/' ? '/index.html' : name));
        if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
        const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png' };
        fs.readFile(file, (err, body) => {
            if (err) { res.writeHead(404).end(); return; }
            res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
            res.end(body);
        });
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let browser;
    try {
        browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', headless: true });
        const page = await browser.newPage();
        const base = `http://127.0.0.1:${server.address().port}`;
        // No CDN, account, or cloud requests during layout verification.
        await page.route('**/*', route => route.request().url().startsWith(base + '/') ? route.continue() : route.abort());
        await page.goto(base + '/#tutorial', { waitUntil: 'load' });
        const ids = await page.evaluate(() => NOTEBOOK_INDEX.chapters.flatMap(c => c.items.map(i => i.id)));
        const failures = [];
        let checks = 0;
        async function check(label) {
            const problems = await page.evaluate(() => {
                const content = document.getElementById('content');
                const result = [];
                if (content.scrollWidth > content.clientWidth + 2) result.push(`page overflow ${content.scrollWidth}/${content.clientWidth}`);
                const article = document.querySelector('.nb-article');
                if (article && article.getBoundingClientRect().right > content.getBoundingClientRect().right + 2) result.push('article extends past viewport');
                if (content.scrollWidth > content.clientWidth + 2) {
                    const limit = content.getBoundingClientRect().right;
                    const culprits = [...content.querySelectorAll('*')].filter(el => {
                        if (el.getBoundingClientRect().right <= limit + 2) return false;
                        for (let p = el.parentElement; p && p !== content; p = p.parentElement) {
                            if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(p).overflowX)) return false;
                        }
                        return true;
                    }).slice(0, 4).map(el => el.outerHTML.slice(0, 140));
                    result.push(...culprits);
                }
                document.querySelectorAll('.tbl-wrap, .lx-code pre, .nb-md pre').forEach(el => {
                    if (el.scrollWidth <= el.clientWidth + 2) return;
                    if (!['auto', 'scroll'].includes(getComputedStyle(el).overflowX)) result.push('wide table/code cannot scroll');
                    el.scrollLeft = 20;
                    if (el.scrollLeft === 0) result.push('wide table/code rejects horizontal scrolling');
                    el.scrollLeft = 0;
                });
                return result;
            });
            checks++;
            if (problems.length) failures.push(`${label}: ${[...new Set(problems)].join('; ')}`);
        }
        for (const width of [320, 390, 768, 1280]) {
            await page.setViewportSize({ width, height: 844 });
            for (const id of ids) {
                await page.evaluate(id => ACP.openTutorial(id), id);
                await page.waitForSelector('#nbArticle');
                if (process.env.LAYOUT_SCREENSHOT_DIR && width === 390 && id === 'c2-2-3') {
                    fs.mkdirSync(process.env.LAYOUT_SCREENSHOT_DIR, { recursive: true });
                    await page.screenshot({ path: path.join(process.env.LAYOUT_SCREENSHOT_DIR, 'tutorial-mobile.png') });
                    const pre = page.locator('.nb-md pre').first();
                    await pre.scrollIntoViewIfNeeded();
                    await page.screenshot({ path: path.join(process.env.LAYOUT_SCREENSHOT_DIR, 'tutorial-code-mobile.png') });
                }
                await check(`${width}px ${id}`);
                await page.evaluate(() => ACP.nbToggleToc());
                await check(`${width}px ${id} TOC`);
            }
            // Knowledge chapters use a separate document renderer and CSS rules.
            await page.evaluate(() => ACP.go('study'));
            for (let ch = 0; ch < 12; ch++) {
                await page.evaluate(ch => ACP.openStudyChapter(ch), ch);
                await check(`${width}px study ${ch + 1}`);
            }
        }
        // Exercise actual learning controls and the signed-in toolbar with a local SDK stub.
        await page.evaluate(async () => {
            window.__learningWrites = [];
            window.supabase = { createClient: () => ({
                auth: {
                    getSession: async () => ({ data: { session: { user: { id: 'layout-user' } } } }),
                    getUser: async () => ({ data: { user: { email: 'long-account-name@example.invalid' } } }),
                    onAuthStateChange: () => {}, signOut: async () => ({})
                },
                from: table => {
                    const q = { select: () => q, eq: () => q, order: () => q, range: async () => ({ data: [] }), limit: async () => ({ data: [] }),
                        upsert: async rows => { window.__learningWrites.push({ table, rows }); return {}; } };
                    return q;
                }
            }) };
            await ACP.sync.init();
            ACP.go('study');
            ACP.openStudyChapter(0);
        });
        for (const width of [320, 390]) {
            await page.setViewportSize({ width, height: 844 });
            assert.ok(await page.evaluate(() => {
                const bar = document.querySelector('.topbar');
                return bar.scrollWidth <= bar.clientWidth + 2;
            }), `signed-in toolbar overflows at ${width}px`);
        }
        await page.locator('.lx-kp-done').first().click();
        await page.locator('.lx-mode-btn[data-mode="exam"]').click();
        await page.evaluate(() => ACP.sync.syncNow());
        assert.ok(await page.evaluate(() => Object.values(ACP.state.store.studyDone).some(Boolean)));
        assert.ok(await page.evaluate(() => window.__learningWrites.some(w => w.table === 'user_meta' && w.rows.some(r => r.key.startsWith('study_done:') && r.value === true))));
        await page.evaluate(id => ACP.openTutorial(id), ids[0]);
        await page.waitForSelector('#nbArticle');
        await page.locator('#nbDoneBtn').click();
        await page.evaluate(() => ACP.sync.syncNow());
        assert.ok(await page.evaluate(id => window.__learningWrites.some(w => w.table === 'user_meta' && w.rows.some(r => r.key === 'tutorial:' + id && r.value.d === 1)), ids[0]));
        assert.equal(failures.length, 0, '\n' + failures.join('\n'));
        console.log(`PASS ${checks} layout checks: 24 tutorials with TOC open/closed and 12 knowledge chapters at 320/390/768/1280px`);
        console.log('PASS signed-in mobile toolbar and knowledge/tutorial controls publish sync metadata');
    } finally {
        if (browser) await browser.close();
        await new Promise(resolve => server.close(resolve));
    }
})().catch(err => { console.error(err); process.exitCode = 1; });
