// Smoke test for js/ai.js (run with node)
const fs = require('fs');

// ---- mock browser globals ----
let fetchCalls = [];
global.fetch = async function (url, opts) {
    fetchCalls.push({ url, opts });
    const body = JSON.parse(opts.body);
    if (body.stream) {
        const chunks = [
            'data: {"choices":[{"delta":{"content":"## 考点"}}]}\n\n',
            'data: {"choices":[{"delta":{"content":"\\nRAG 检索增强"}}]}\n\n',
            'data: [DONE]\n\n'
        ];
        const stream = new ReadableStream({
            start(controller) {
                for (const c of chunks) controller.enqueue(new TextEncoder().encode(c));
                controller.close();
            }
        });
        return { ok: true, status: 200, body: stream };
    }
    return {
        ok: true, status: 200,
        json: async () => ({ choices: [{ message: { content: '## 考点\n非流式讲解' } }] })
    };
};

const store = {};
global.localStorage = {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; }
};

let listeners = [];
global.document = {
    addEventListener: (ev, fn) => { listeners.push([ev, fn]); },
    getElementById: () => null
};

const ACP = {
    state: {
        session: {},
        exam: null,
        store: { p: { '1-0001': { a: ['A'], c: 0, d: 1, w: 1 } } }
    },
    ID_MAP: {
        '1-0001': {
            id: '1-0001', ch: '1', seq: '0001', multi: false,
            stem: 'presence_penalty 的作用？',
            ansArr: ['B'], analysis: '原解析',
            options: [
                { label: 'A', text: '减少重复' },
                { label: 'B', text: '控制长度' },
                { label: 'C', text: '提高确定性' },
                { label: 'D', text: '无作用' }
            ]
        }
    },
    prog: id => ACP.state.store.p[id] || null,
    esc: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'),
    toast: () => {},
    toggleSidebar: () => {},
    mdToHtml: t => `<p>${t}</p>`
};
global.window = { ACP };

new Function('window', fs.readFileSync('js/ai.js', 'utf8'))(window);

const fails = [];

// 1. config defaults
const cfg = ACP.loadAIConfig();
if (cfg.apiKey !== '' || cfg.baseUrl.indexOf('dashscope.aliyuncs.com') < 0 || cfg.model !== 'qwen-plus') {
    fails.push('loadAIConfig defaults wrong');
}

// 2. config save/load round-trip (baseUrl normalized + provider kept)
ACP.saveAIConfig({ apiKey: 'sk-test', baseUrl: 'https://example.com/v1/', model: 'qwen-max', provider: 'deepseek' });
const cfg2 = ACP.loadAIConfig();
if (cfg2.apiKey !== 'sk-test' || cfg2.baseUrl !== 'https://example.com/v1' || cfg2.model !== 'qwen-max' || cfg2.provider !== 'deepseek') {
    fails.push('config round-trip wrong: ' + JSON.stringify(cfg2));
}

// 2b. provider presets
const prov = ACP.PROVIDERS;
if (!prov || prov.length < 4) fails.push('PROVIDERS missing');
if (!prov.some(p => p.id === 'dashscope' && p.name.indexOf('推荐') >= 0)) fails.push('dashscope should be recommended');
if (!prov.some(p => p.id === 'siliconflow')) fails.push('siliconflow preset missing');

(async () => {
    const q = ACP.ID_MAP['1-0001'];

    // 3. non-streaming aiCall
    const text1 = await ACP.aiCall(q, ['A'], ACP.loadAIConfig());
    if (text1 !== '## 考点\n非流式讲解') fails.push('aiCall content wrong');
    const b1 = JSON.parse(fetchCalls[0].opts.body);
    if (b1.stream !== false) fails.push('aiCall should not stream');
    if (b1.messages[0].content.indexOf('150 字') < 0) fails.push('system prompt not concise');
    const userMsg = b1.messages[1].content;
    if (userMsg.indexOf('正确/错误') < 0) fails.push('prompt missing per-option format');
    if (userMsg.indexOf('选X') < 0) fails.push('prompt missing final line template');

    // 4. streaming aiStream
    let chunks = [];
    const text2 = await ACP.aiStream(q, ['A'], ACP.loadAIConfig(), full => chunks.push(full));
    if (text2 !== '## 考点\nRAG 检索增强') fails.push('aiStream content wrong: ' + JSON.stringify(text2));
    if (chunks.length < 2) fails.push('aiStream onChunk not called enough');
    const b2 = JSON.parse(fetchCalls[fetchCalls.length - 1].opts.body);
    if (b2.stream !== true) fails.push('aiStream should stream');

    // 5. cache
    ACP.cacheSet('1-0001', '## 考点\n缓存内容', 'qwen-plus');
    if (ACP.cacheGet('1-0001').text !== '## 考点\n缓存内容') fails.push('cacheSet/get wrong');

    // 6. aiPanelHTML: cached shows 重新生成 + 已缓存
    const cached = ACP.aiPanelHTML('1-0001');
    if (cached.indexOf('重新生成') < 0 || cached.indexOf('已缓存') < 0) fails.push('cached panel missing buttons');

    // 7. aiPanelHTML: non-cached shows entry button
    const fresh = ACP.aiPanelHTML('1-9999');
    if (fresh.indexOf('ai-ask-btn') < 0) fails.push('fresh panel missing ask button');

    // 8. clearAICache
    ACP.clearAICache('1-0001');
    if (ACP.cacheGet('1-0001') !== null) fails.push('clearAICache failed');

    // 9. keydown listener
    if (!listeners.some(([ev]) => ev === 'keydown')) fails.push('keydown listener missing');

    console.log('---', fails.length ? 'FAIL: ' + fails.join('; ') : 'PASS');
    process.exit(fails.length ? 1 : 0);
})().catch(e => { console.log('--- FAIL: ' + e.message); process.exit(1); });
