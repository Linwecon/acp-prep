// Browser smoke checks and visual previews. Requires Playwright and an installed Edge browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const output = process.env.WORKSPACE_SCREENSHOTS || path.join(os.tmpdir(), 'acp-workspace-preview');

(async () => {
    fs.mkdirSync(output, { recursive: true });
    const server = http.createServer((req, res) => {
        const name = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        const file = path.resolve(root, '.' + (name === '/' ? '/index.html' : name));
        if (!file.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
        fs.readFile(file, (err, bytes) => {
            if (err) { res.writeHead(404).end(); return; }
            const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png' };
            res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
            res.end(bytes);
        });
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${server.address().port}`;
    let browser;
    try {
        browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', headless: true });
        for (const width of [320, 390, 768, 1440]) {
            const context = await browser.newContext({ viewport: { width, height: width > 860 ? 1050 : 844 }, hasTouch: width <= 640 });
            const page = await context.newPage();
            // Exercise real dialog markup with an offline SDK stub; never contact accounts or AI providers.
            await page.addInitScript(() => {
                window.supabase = { createClient: () => ({ auth: {
                    getSession: async () => ({ data: { session: null } }), getUser: async () => ({ data: { user: null } }),
                    onAuthStateChange: () => {}, signOut: async () => ({})
                } }) };
            });
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            await page.route('**/*', route => {
                if (route.request().url().startsWith(base + '/')) return route.continue();
                if (route.request().url().endsWith('/auth/v1/health')) return route.fulfill({ status: 200, body: '{}' });
                if (route.request().url().endsWith('/chat/completions')) return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: ' + JSON.stringify({ choices: [{ delta: { content: '先看题干中的限制条件，再逐项排除不符合要求的选项。这是一条离线界面测试回复。' } }] }) + '\n\ndata: [DONE]\n\n' });
                return route.abort();
            });
            async function screenshot(name) {
                if (width === 1440 || width === 390) await page.screenshot({ path: path.join(output, `${name}-${width}.png`), animations: 'disabled' });
            }
            async function noOverflow() {
                const ok = await page.evaluate(() => {
                    const c = document.getElementById('content');
                    const toast = document.querySelector('.toast.show');
                    return c.scrollWidth <= c.clientWidth + 2 && document.documentElement.scrollWidth <= innerWidth + 2
                        && (!toast || toast.getBoundingClientRect().height < 150);
                });
                if (!ok) console.log(await page.evaluate(() => ({ view: ACP.state.ui.view, content: [document.getElementById('content').scrollWidth, document.getElementById('content').clientWidth], toast: document.querySelector('.toast').getBoundingClientRect().toJSON(), elements: [...document.querySelectorAll('#content *')].filter(el => el.getBoundingClientRect().right > innerWidth + 1).slice(0, 8).map(el => el.outerHTML.slice(0, 170)) })));
                assert.ok(ok, `layout overflow at ${width}px`);
            }
            await page.goto(base, { waitUntil: 'load' });
            await page.locator('.landing-headline').waitFor();
            assert.ok(await page.locator('.landing').evaluate(el => el.scrollWidth <= el.clientWidth + 2), `welcome overflows at ${width}px`);
            await screenshot('welcome');
            await page.locator('.landing-card').nth(1).click();
            await page.waitForSelector('#landing', { state: 'detached' });
            await page.locator('.workspace-heading').waitFor();
            await noOverflow();
            assert.equal(await page.locator('.chapter-card').count(), 12);
            assert.equal(await page.locator('.workspace-stats .t-value').first().innerText(), '0 题');
            await screenshot('workspace');
            await page.locator('.continue-card .btn-primary').click();
            await page.waitForSelector('.practice-card');
            const label = await page.evaluate(() => {
                const q = ACP.state.ui.pool[ACP.state.ui.idx];
                return q.options.find(o => !q.ansArr.includes(o.label)).label;
            });
            await page.locator(`.opt[data-label="${label}"]`).click();
            await page.locator('#submitBtn').click();
            await page.locator('.analysis-box.show').waitFor();
            await noOverflow();
            if (width <= 640) {
                assert.ok(await page.evaluate(() => {
                    const actions = document.querySelector('.practice-card .q-actions').getBoundingClientRect();
                    const nav = document.querySelector('.mobile-nav').getBoundingClientRect();
                    return actions.top >= 0 && actions.bottom <= nav.top + 1 && actions.right <= innerWidth + 1;
                }), 'practice buttons overlap bottom navigation');
                assert.equal(await page.locator('[data-mobile-nav="chapter"][aria-current="page"]').count(), 1);
            }
            await screenshot('practice');
            await page.evaluate(() => ACP.go('dashboard'));
            assert.match(await page.locator('.continue-card .btn-primary').innerText(), /继续练习/);
            assert.equal(await page.locator('.workspace-stats .t-value').first().innerText(), '1 题');
            await page.evaluate(() => ACP.go('tutorial'));
            const id = await page.evaluate(() => NOTEBOOK_INDEX.chapters[0].items[0].id);
            await page.evaluate(id => ACP.openTutorial(id), id);
            await page.locator('#nbArticle').waitFor();
            await page.getByRole('button', { name: '放大正文字号', exact: true }).click();
            assert.equal(await page.locator('.nb-md p').first().evaluate(el => getComputedStyle(el).fontSize), '17px');
            await noOverflow();
            await screenshot('reader');
            await page.goto(base, { waitUntil: 'load' });
            assert.equal(await page.locator('#landing').count(), 0, 'return visits skip welcome screen');
            assert.equal(await page.evaluate(() => ACP.readingSize), 17);
            await page.evaluate(() => ACP.toggleTheme());
            await noOverflow();
            await screenshot('workspace-dark');
            for (const theme of ['', 'dark']) {
                const suffix = theme ? '-dark' : '';
                await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
                await page.evaluate(() => { ACP.go('study'); ACP.backToGallery(); });
                await page.locator('.gallery-card').first().waitFor();
                await noOverflow();
                await screenshot('knowledge' + suffix);
                await page.locator('.study-outline .ring-svg').waitFor({ state: 'visible' });
                await noOverflow();
                await page.locator('.gallery-card').first().click();
                await page.locator('.lx-module').first().waitFor();
                assert.equal(await page.locator('.lx-chapter-intro').getAttribute('open'), null);
                await page.locator('.lx-chapter-intro > summary').click();
                assert.ok(await page.locator('.chapter-intro-content blockquote p').count() >= 3, 'chapter introduction paragraphs stay separate');
                await page.locator('.lx-chapter-intro > summary').click();
                const answers = page.locator('.knowledge-answers').first();
                assert.equal(await answers.getAttribute('open'), null, 'self-test answers start hidden');
                await answers.locator('summary').click();
                assert.notEqual(await answers.getAttribute('open'), null);
                await page.locator('#knowledge-module').selectOption('0');
                await noOverflow();
                await screenshot('course' + suffix);
                await page.locator('.lx-kp-done').first().click();
                await page.locator('.lx-mode-btn[data-mode="exam"]').click();
                await noOverflow();
                await page.evaluate(() => ACP.go('tutorial'));
                await page.locator('.nb-row').first().waitFor();
                await noOverflow();
                await screenshot('tutorials' + suffix);
                await page.evaluate(() => ACP.go('fav'));
                if (!theme) {
                    await page.locator('.collection-empty').waitFor();
                    await screenshot('collection-empty');
                    await page.evaluate(() => ACP.toggleFav(ACP.BANK[0].id));
                    await page.evaluate(() => ACP.go('fav'));
                }
                await page.locator('.collection-card').first().waitFor();
                await noOverflow();
                await screenshot('favorites' + suffix);
                await page.evaluate(() => ACP.go('wrong'));
                await page.locator('.collection-card').first().waitFor();
                await noOverflow();
                await screenshot('wrong' + suffix);
                await page.evaluate(() => { ACP.state.exam = null; ACP.go('exam'); });
                await noOverflow();
                await screenshot('exam-setup' + suffix);
                await page.locator('.exam-start-row button').click();
                assert.equal(await page.locator('.sheet-cell').count(), 75);
                assert.equal(await page.locator('.answer-sheet[open]').count(), 0);
                await noOverflow();
                await screenshot('exam-active' + suffix);
                await page.locator('.answer-sheet > summary').click();
                await page.locator('.sheet-cell').nth(1).click();
                assert.equal(await page.evaluate(() => ACP.state.exam.idx), 1);
                await page.evaluate(() => {
                    const q = ACP.state.exam.pool[1];
                    q.ansArr.forEach(label => ACP.examOpt(label));
                    ACP.submitExam(true);
                });
                await page.locator('.exam-score-header').waitFor();
                await noOverflow();
                await screenshot('exam-result' + suffix);
                await page.locator('.review-item').first().click();
                await noOverflow();
                await screenshot('exam-review' + suffix);
                if (width <= 640) assert.ok(await page.locator('.exam-question .q-actions').evaluate(el => el.getBoundingClientRect().bottom <= document.querySelector('.mobile-nav').getBoundingClientRect().top + 1));
                await page.evaluate(() => ACP.sync.openAuth());
                await page.locator('#authForm').waitFor({ state: 'visible' });
                await screenshot('login' + suffix);
                await page.locator('#tabSignUp').click();
                await page.locator('#authRegPassword').fill('local-test-only');
                const originalType = await page.locator('#authRegPassword').getAttribute('type');
                await page.locator('#authSignUpPage .pwd-toggle').first().click();
                assert.equal(await page.locator('#authRegPassword').getAttribute('type'), originalType === 'password' ? 'text' : 'password');
                await screenshot('register' + suffix);
                const dialogFits = id => page.locator(id).evaluate(async el => {
                    await Promise.all(el.getAnimations().map(animation => animation.finished.catch(() => {})));
                    const r = el.getBoundingClientRect();
                    return r.left >= -1 && r.right <= innerWidth + 1 && r.top >= -1 && r.bottom <= innerHeight + 1 && el.scrollWidth <= el.clientWidth + 2;
                });
                assert.ok(await dialogFits('#authModal'), `auth dialog overflow at ${width}px`);
                await page.locator('#authModal .text-link').focus();
                await page.keyboard.press('Tab');
                assert.ok(await page.locator('#authModal .modal-close').evaluate(el => el === document.activeElement), 'Tab wraps to first dialog control');
                await page.keyboard.press('Shift+Tab');
                assert.ok(await page.locator('#authModal .text-link').evaluate(el => el === document.activeElement), 'Shift+Tab wraps to last dialog control');
                await page.locator('#authRegEmail').focus();
                await page.keyboard.press('Escape');
                assert.equal(await page.locator('#authModal.show').count(), 0);
                await page.evaluate(() => ACP.openAISettings());
                assert.ok(await dialogFits('#aiModal'), `settings dialog overflow at ${width}px`);
                await screenshot('settings' + suffix);
                await page.locator('#aiKey').fill('offline-preview-only');
                await page.evaluate(() => ACP.saveAISettings());
                await page.evaluate(() => ACP.openAIChat(ACP.BANK[0].id));
                await page.locator('#aiChatModal.show').waitFor();
                await page.locator('#aiChatInput').fill('这道题应该怎样分析？');
                await page.locator('#aiChatSendBtn').click();
                await page.waitForFunction(() => document.getElementById('aiChatBody').textContent.includes('这是一条离线界面测试回复'));
                assert.ok(await dialogFits('#aiChatModal'), `chat overflow at ${width}px`);
                if (width <= 860) assert.ok(await page.locator('#aiChatModal').evaluate(el => el.getBoundingClientRect().bottom <= document.querySelector('.mobile-nav').getBoundingClientRect().top), 'assistant leaves mobile navigation accessible');
                await screenshot('assistant' + suffix);
                await page.keyboard.press('Escape');
                assert.equal(await page.locator('#aiChatModal.show').count(), 0);
                await page.evaluate(() => ACP.openNotes());
                assert.ok(await dialogFits('#notesModal'), `notes dialog overflow at ${width}px`);
                await screenshot('notes' + suffix);
                await page.keyboard.press('Escape');
                // Search and jump are exercised without sending any remote requests.
                await page.locator('#searchInput').fill('模型');
                await page.locator('.sr-item').first().waitFor();
                await page.locator('.sr-item').first().click();
                await page.locator('.practice-card').waitFor();
                await noOverflow();
            }
            await page.goto(base + '/admin.html', { waitUntil: 'load' });
            await page.waitForFunction(() => document.getElementById('listWrap').textContent.trim() !== '加载中…');
            await page.evaluate(() => { document.documentElement.dataset.theme = ''; });
            assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), `admin overflows at ${width}px`);
            await screenshot('admin');
            await page.locator('.admin-theme-switch').click();
            await screenshot('admin-dark');
            assert.deepEqual(errors, [], 'browser errors');
            console.log(`PASS ${width}px: all learning, exam, collection, account, AI, search and admin surfaces in both themes`);
            await context.close();
        }
        console.log('Previews: ' + output);
    } finally {
        if (browser) await browser.close();
        await new Promise(resolve => server.close(resolve));
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
