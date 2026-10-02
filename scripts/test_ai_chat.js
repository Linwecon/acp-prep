// Smoke test for AI follow-up chat in js/ai.js (run with node)
const fs = require('fs');

// ---- mock browser globals ----
let fetchCalls = [];
global.fetch = async function (url, opts) {
    fetchCalls.push({ url, opts });
    const body = JSON.parse(opts.body);
    const lastUser = [...body.messages].reverse().find(m => m.role === 'user');
    const question = lastUser ? lastUser.content : '';
    const reply = '回答：' + question;
    if (body.stream) {
        const stream = new ReadableStream({
            start(controller) {
                (async () => {
                    for (const c of [reply.slice(0, 3), reply.slice(3), ' 补充']) {
                        if (opts.signal && opts.signal.aborted) {
                            const e = new Error('aborted');
                            e.name = 'AbortError';
                            controller.error(e);
                            return;
                        }
                        controller.enqueue(new TextEncoder().encode(
                            'data: ' + JSON.stringify({ choices: [{ delta: { content: c } }] }) + '\n\n'
                        ));
                        await new Promise(r => setTimeout(r, 6));
                    }
                    controller.enqueue(new TextEncoder().encode('data: [DONE]\n\n'));
                    controller.close();
                })();
            }
        });
        return { ok: true, status: 200, body: stream };
    }
    return {
        ok: true, status: 200,
        json: async () => ({ choices: [{ message: { content: reply } }] })
    };
};

const store = {};
global.localStorage = {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; }
};

/* 极简假 DOM：足以让弹窗逻辑跑起来（不校验渲染细节） */
function fakeEl(id) {
    return {
        id, style: {}, dataset: {}, value: '', textContent: '', disabled: false,
        innerHTML: '', scrollTop: 0, scrollHeight: 0,
        classList: { add() {}, remove() {}, contains() { return true; } },
        querySelector: () => null,
        lastElementChild: null,
        insertAdjacentHTML(pos, html) {
            this.innerHTML += html;
            this.lastElementChild = {
                querySelector: () => null,
                classList: { add() {}, remove() {} },
                parentNode: this
            };
        },
        focus() {}
    };
}
const els = {};
let listeners = [];
global.document = {
    addEventListener: (ev, fn) => { listeners.push([ev, fn]); },
    getElementById: id => (els[id] || (els[id] = fakeEl(id)))
};

const ACP = {
    state: {
        session: { '1-0001': { sel: ['C'] } },
        exam: null,
        store: { p: {} }
    },
    ID_MAP: {
        '1-0001': {
            id: '1-0001', ch: '1', seq: '0001', multi: false,
            stem: 'presence_penalty 的作用是什么？',
            ansArr: ['B'], analysis: '官方解析：控制重复。',
            options: [
                { label: 'A', text: '减少重复' },
                { label: 'B', text: '控制长度' },
                { label: 'C', text: '提高确定性' },
                { label: 'D', text: '无作用' }
            ]
        }
    },
    prog: id => ACP.state.store.p[id] || null,
    esc: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&#62;'),
    toast: () => {},
    toggleSidebar: () => {},
    mdToHtml: t => `<p>${t}</p>`
};
global.window = { ACP };

new Function('window', fs.readFileSync('js/ai.js', 'utf8'))(window);

const fails = [];

(async () => {
    const qid = '1-0001';
    ACP.saveAIConfig({ apiKey: 'sk-test', baseUrl: 'https://example.com/v1', model: 'qwen-plus', provider: '' });

    // 1. 未讲解时：system + 题目上下文 + 占位回答 + 本次提问
    let msgs = ACP.buildChatMessages(qid, '为什么选 B？');
    if (msgs.length !== 4) fails.push('no-explain: msg count ' + msgs.length);
    if (msgs[0].content.indexOf('多轮对话') < 0) fails.push('chat system prompt missing');
    if (msgs[1].content.indexOf('presence_penalty') < 0) fails.push('context missing stem');
    if (msgs[1].content.indexOf('我的作答】C') < 0) fails.push('context missing user selection');
    if (msgs[1].content.indexOf('题库参考解析') < 0) fails.push('context missing bank analysis');
    if (msgs[1].content.indexOf('减少重复') < 0) fails.push('context missing options');
    if (msgs[1].content.indexOf('B') < 0 || msgs[1].content.indexOf('控制长度') < 0) fails.push('context options incomplete');
    // 不注入题库标准答案
    if (msgs[1].content.indexOf('【正确答案】') >= 0) fails.push('standard answer leaked');
    if (msgs[3].role !== 'user' || msgs[3].content !== '为什么选 B？') fails.push('last message should be the question');

    // 2. 讲解后：讲解作为锚点 assistant 出现
    ACP.cacheSet(qid, '选B，考点是生成参数。', 'qwen-plus');
    msgs = ACP.buildChatMessages(qid, '再讲细一点');
    if (msgs.length !== 4) fails.push('explain-anchor: msg count ' + msgs.length);
    if (msgs[2].role !== 'assistant' || msgs[2].content !== '选B，考点是生成参数。') fails.push('explain not used as anchor');

    // 3. 多轮历史被带入，且条数受 CTX_ROUNDS 限制（3 锚点 + 10*2 + 1）
    for (let i = 1; i <= 25; i++) ACP.chatSaveRound(qid, '问题' + i, '回答' + i, 'qwen-plus', false);
    if (ACP.chatCount(qid) !== 20) fails.push('round cap wrong: ' + ACP.chatCount(qid));
    msgs = ACP.buildChatMessages(qid, '最新问题');
    const expected = 3 + 10 * 2 + 1;
    if (msgs.length !== expected) fails.push('ctx window wrong: ' + msgs.length + ' != ' + expected);
    if (msgs[msgs.length - 2].content !== '回答25') fails.push('ctx should keep latest rounds');
    if (msgs.some(m => m.content === '回答1')) fails.push('ctx should drop oldest rounds');

    // 4. 截断轮标记持久化
    ACP.chatClear(qid);
    ACP.chatSaveRound(qid, '会被中断的问题', '半截回答', 'qwen-plus', true);
    const saved = ACP.chatGet(qid);
    if (!saved || saved.rounds.length !== 1 || saved.rounds[0].t !== true) fails.push('truncated flag lost');

    // 5. 会话只存本机 key，且与讲解缓存互不影响
    ACP.chatClear(qid);
    if (ACP.chatCount(qid) !== 0) fails.push('chatClear failed');
    if (!ACP.cacheGet(qid)) fails.push('chatClear should keep AI cache');

    // 6. 追问面板入口
    const panel = ACP.aiPanelHTML(qid);
    if (panel.indexOf('继续追问') < 0) fails.push('panel missing follow-up button');

    // 7. 端到端：打开弹窗 → 发送追问 → 流式 → 落盘
    ACP.openAIChat(qid);
    const before = fetchCalls.length;
    await ACP.aiChatQuick({ dataset: { q: '举个实际例子' } });
    if (ACP.chatCount(qid) !== 1) fails.push('e2e round not saved');
    const body = JSON.parse(fetchCalls[before].opts.body);
    if (body.max_tokens !== 1000) fails.push('follow-up max_tokens wrong: ' + body.max_tokens);
    if (body.messages[2].content !== '选B，考点是生成参数。') fails.push('e2e explain anchor missing');
    const round = ACP.chatGet(qid).rounds[0];
    if (round.q !== '举个实际例子' || round.a.indexOf('举个实际例子') < 0) fails.push('e2e round content wrong');
    if (round.t) fails.push('e2e should not be truncated');

    // 8. 第二轮：上下文连续（上一轮问答应出现在 messages 中）
    const before2 = fetchCalls.length;
    await ACP.aiChatQuick({ dataset: { q: '还有吗' } });
    const body2 = JSON.parse(fetchCalls[before2].opts.body);
    if (!body2.messages.some(m => m.content.indexOf('回答：举个实际例子') === 0)) fails.push('previous round not in context');
    if (ACP.chatCount(qid) !== 2) fails.push('second round not saved');

    // 9. 中断生成：部分内容落盘并标记
    const before3 = fetchCalls.length;
    const p = ACP.aiChatQuick({ dataset: { q: '请长篇回答' } });
    setTimeout(() => ACP.aiChatStop(), 9);
    await p;
    const last = ACP.chatGet(qid).rounds[ACP.chatCount(qid) - 1];
    if (last.t !== true) fails.push('abort should mark truncated');
    if (!last.a) fails.push('abort should keep partial text');

    // 10. 清空会话
    ACP.clearAIChat();
    if (ACP.chatCount(qid) !== 0) fails.push('clearAIChat failed');

    // 10b. 浮动窗：像素定位、不依赖遮罩、默认贴右下角
    ACP.openAIChat(qid);
    const modal = els['aiChatModal'];
    if (!/px$/.test(modal.style.left) || !/px$/.test(modal.style.top)) fails.push('float panel not positioned by px');
    if (modal.style.right !== 'auto' || modal.style.bottom !== 'auto') fails.push('float panel must use left/top');
    // 测试环境视口回退 1024x768、面板回退 600x480
    if (parseFloat(modal.style.left) !== 1024 - 600 - 24 ||
        parseFloat(modal.style.top) !== 768 - 480 - 24) {
        fails.push('default float position wrong: ' + modal.style.left + ',' + modal.style.top);
    }
    // 越界位置被拉回可见区域
    const clamped = ACP.applyChatPos(false, { x: -500, y: 99999 });
    if (clamped.x !== 8 || clamped.y !== 768 - 480 - 8) fails.push('clamp failed: ' + JSON.stringify(clamped));

    // 11. 回归：首次讲解的提示词未被改动
    const before4 = fetchCalls.length;
    await ACP.aiStream(ACP.ID_MAP[qid], ['C'], ACP.loadAIConfig(), () => {});
    const b4 = JSON.parse(fetchCalls[before4].opts.body);
    if (b4.messages[0].content.indexOf('240 字') < 0) fails.push('regression: first-explain system prompt changed');
    if (b4.messages[1].content.indexOf('正确/错误') < 0) fails.push('regression: first-explain prompt changed');
    if (b4.max_tokens !== 700) fails.push('regression: first-explain max_tokens changed');

    console.log('---', fails.length ? 'FAIL: ' + fails.join('; ') : 'PASS');
    process.exit(fails.length ? 1 : 0);
})().catch(e => { console.log('--- FAIL: ' + e.message + '\n' + e.stack); process.exit(1); });
