// Quick smoke test for js/ai.js (run with node)
const fs = require('fs');

// ---- mock browser globals ----
let fetchCalls = [];
global.fetch = async function (url, opts) {
    fetchCalls.push({ url, opts });
    return {
        ok: true,
        status: 200,
        async json() {
            return { choices: [{ message: { content: '## 考点定位\n这是讲解' } }] };
        }
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

// ---- mock window.ACP with the deps ai.js needs ----
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
            ansArr: ['B'],
            analysis: '原解析',
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

// ---- load ai.js ----
const src = fs.readFileSync('js/ai.js', 'utf8');
new Function('window', src)(window);

const fails = [];

// 1. config defaults
const cfg = ACP.loadAIConfig();
if (cfg.apiKey !== '' || cfg.baseUrl.indexOf('dashscope.aliyuncs.com') < 0 || cfg.model !== 'qwen-plus') {
    fails.push('loadAIConfig defaults wrong: ' + JSON.stringify(cfg));
}

// 2. save/load round-trip
ACP.saveAIConfig({ apiKey: 'sk-test', baseUrl: 'https://example.com/v1/', model: 'qwen-max' });
const cfg2 = ACP.loadAIConfig();
if (cfg2.apiKey !== 'sk-test' || cfg2.baseUrl !== 'https://example.com/v1' || cfg2.model !== 'qwen-max') {
    fails.push('save/load round-trip wrong: ' + JSON.stringify(cfg2));
}

// 3. aiCall: url, headers, body shape
ACP.saveAIConfig({ apiKey: 'sk-test', baseUrl: 'https://example.com/v1/', model: 'qwen-max' });
ACP.aiCall(ACP.ID_MAP['1-0001'], ['A'], ACP.loadAIConfig())
    .then(() => {
        const c = fetchCalls[0];
        if (!c || c.url !== 'https://example.com/v1/chat/completions') fails.push('aiCall url wrong: ' + (c && c.url));
        if (c && c.opts.headers['Authorization'] !== 'Bearer sk-test') fails.push('auth header wrong');
        if (c && c.opts.headers['Content-Type'] !== 'application/json') fails.push('content-type wrong');
        const body = JSON.parse(c.opts.body);
        if (body.model !== 'qwen-max') fails.push('model wrong: ' + body.model);
        if (!Array.isArray(body.messages) || body.messages.length !== 2) fails.push('messages wrong');
        if (body.messages[0].role !== 'system' || body.messages[1].role !== 'user') fails.push('roles wrong');
        if (body.messages[1].content.indexOf('presence_penalty') < 0) fails.push('prompt missing stem');
        if (body.messages[1].content.indexOf('正确答案】B') < 0) fails.push('prompt missing answer');
        if (body.messages[1].content.indexOf('我的作答】A') < 0) fails.push('prompt missing user answer');

        // 4. keydown listener registered
        if (!listeners.some(([ev]) => ev === 'keydown')) fails.push('keydown listener missing');

        console.log('---', fails.length ? 'FAIL: ' + fails.join('; ') : 'PASS');
        process.exit(fails.length ? 1 : 0);
    })
    .catch(e => { console.log('--- FAIL: ' + e.message); process.exit(1); });
