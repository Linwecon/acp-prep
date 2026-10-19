// NODE_PATH may point to the bundled runtime's node_modules. No remote requests.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
(async () => {
    const browser = await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
    try {
        const page = await browser.newPage();
        const errors=[];
        page.on('pageerror', e=>errors.push(e.message));
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.origin !== 'http://acp.local') return route.abort();
            const rel = decodeURIComponent(url.pathname).replace(/^\//,'') || 'index.html';
            if (!(rel === 'index.html' || /^[\w-]+\.css$/.test(rel) || /^(js|data)\/[\w.-]+\.js$/.test(rel) || rel === 'config/supabase.js')) return route.abort();
            const file = path.join(root,rel);
            if (!fs.existsSync(file)) return route.fulfill({status:404,body:''});
            const type = {'.html':'text/html','.js':'text/javascript','.css':'text/css'}[path.extname(file)];
            return route.fulfill({contentType:type,body:fs.readFileSync(file)});
        });
        await page.goto('http://acp.local/#study');
        await page.evaluate(()=>ACP.openStudyChapter(0));
        await page.getByRole('button',{name:'学完本章 · 30题巩固基础'}).click();
        assert.equal(await page.locator('#foundationDraft').count(),1);
        assert.equal(await page.locator('.foundation-answer').count(),0);
        const before = await page.evaluate(()=>({count:ACP.BANK.length,p:JSON.stringify(ACP.state.store.p)}));
        await page.locator('#foundationDraft').fill('根据上下文逐步预测下一个 Token。');
        await page.getByRole('button',{name:'对照参考答案与讲解'}).click();
        assert.equal(await page.locator('.foundation-answer').count(),1);
        await page.getByRole('button',{name:'自评：能独立回答',exact:true}).click();
        await page.getByRole('button',{name:'下一题 →',exact:true}).click();
        await page.locator('#foundationDraft').fill('没有证据却生成了确定说法。');
        await page.reload();
        await page.evaluate(()=>ACP.openFoundation('1'));
        assert.equal(await page.locator('#foundationDraft').inputValue(),'没有证据却生成了确定说法。');
        assert.equal(await page.evaluate(()=>ACP.state.ui.idx),1);
        await page.getByRole('button',{name:'本章回顾',exact:true}).click();
        assert.equal(await page.locator('.foundation-review button').count(),30);
        assert((await page.locator('#contentInner').innerText()).includes('29 题未自评'));
        for (const width of [390,1280]) {
            await page.setViewportSize({width,height:900});
            for (let ch=1; ch<=12; ch++) {
                await page.evaluate(ch=>ACP.openFoundation(String(ch)),ch);
                assert.equal(await page.locator('.foundation-numbers button').count(),30);
                const overflow = await page.evaluate(()=>{const e=document.getElementById('content');return e.scrollWidth>e.clientWidth+2;});
                assert.equal(overflow,false,`${width}px chapter ${ch}: horizontal overflow`);
            }
            await page.evaluate(()=>ACP.openFoundation('1'));
            fs.mkdirSync(path.join(root,'out/foundation-preview'),{recursive:true});
            await page.screenshot({path:path.join(root,`out/foundation-preview/${width}.png`)});
        }
        await page.evaluate(()=>document.documentElement.dataset.theme='dark');
        await page.getByRole('button',{name:'对照参考答案与讲解'}).click();
        await page.screenshot({path:path.join(root,'out/foundation-preview/dark.png')});
        await page.getByRole('button',{name:'章节题库',exact:true}).click();
        assert.equal(await page.locator('#foundationDraft').count(),0);
        const after = await page.evaluate(()=>({count:ACP.BANK.length,p:JSON.stringify(ACP.state.store.p)}));
        assert.deepEqual(after,before,'exam bank and answer records are unchanged');
        assert.deepEqual(errors,[]);
        console.log('PASS: real browser entry, reveal, self-rating, reload/resume, summary, 24 chapter/viewport checks, dark mode, exam separation');
    } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
