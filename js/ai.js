/* ============================================================
   ACP — AI 答疑（DashScope / OpenAI 兼容接口）
   - 用户自带 API Key，浏览器直连，Key 仅存本地 localStorage
   - 流式输出（SSE）逐字显示，结果缓存到本地，跨题跳转复用
   ============================================================ */
(function (ACP) {

    const AI_KEY = 'acp_ai_config';
    const AI_CACHE_KEY = 'acp_ai_cache';
    const AI_CHAT_KEY = 'acp_ai_chat';   // 追问会话：{ [qid]: { model, ts, rounds: [{q,a,ts,t}] } }
    const AI_CHAT_POS_KEY = 'acp_ai_chat_pos'; // 浮动窗口位置 {x,y}
    const CACHE_MAX = 200;
    const CHAT_MAX = 60;        // 最多保留多少道题的追问会话
    const CHAT_ROUNDS_MAX = 20; // 单题最多保留多少轮追问
    const CHAT_CTX_ROUNDS = 10; // 送入上下文的最近轮数（不含锚点）
    const CHAT_CTX_CHARS = 9000;// 上下文字符预算，超出从最早的追问开始丢
    const CHAT_MAX_TOKENS = 1000;
    const DEFAULT_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
    const DEFAULT_MODEL = 'qwen-plus';

    const SYSTEM_PROMPT =
        '你是阿里云 ACP 大模型高级工程师认证的备考助教。用简体中文讲解，全文控制在 240 字以内，' +
        '比一句话解析稍详细一些：先给结论，再用一到两句话解释原因或易错点。' +
        '严格遵循用户给出的输出格式，不要铺垫、不要长篇大论。';

    /* ---------- 追问（题目小助手）专用 ---------- */
    const CHAT_SYSTEM_PROMPT =
        '你是阿里云 ACP 大模型高级工程师认证备考助教，正在围绕一道具体题目与用户多轮对话。\n' +
        '你已掌握本题完整上下文（题干、选项、用户作答、此前的讲解与问答历史）。\n' +
        '回答要求：\n' +
        '1. 简体中文，紧扣本题与此前的讲解，前后保持一致，不要自相矛盾；\n' +
        '2. 全文默认控制在 300 字以内，用户明确要求展开时再详细；\n' +
        '3. 不要原样复述已经讲过的内容，回答用户真正追问的点；\n' +
        '4. 需要举例时给出具体场景或参数，需要区分概念时点明易混点；\n' +
        '5. 不确定就明说不确定，不要编造；具体服务名、参数取值以阿里云官方文档为准；\n' +
        '6. 纯文本输出，不要用 Markdown 标题符号，分点用「1. 2. 3.」或短横线即可。';

    /* ---------- 服务商预设（均为 OpenAI 兼容接口） ---------- */
    const PROVIDERS = [
        { id: 'dashscope', name: '阿里云百炼（推荐）', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-plus', 'qwen-turbo', 'qwen-max', 'qwen-long', 'qwen-flash'], note: '新用户有免费额度' },
        { id: 'siliconflow', name: '硅基流动（免费额度）', baseUrl: 'https://api.siliconflow.cn/v1', models: ['Qwen/Qwen2.5-7B-Instruct', 'Qwen/Qwen2.5-14B-Instruct', 'deepseek-ai/DeepSeek-V3', 'THUDM/glm-4-9b-chat'], note: '注册送免费额度，部分模型长期免费' },
        { id: 'deepseek', name: 'DeepSeek 官方', baseUrl: 'https://api.deepseek.com', models: ['deepseek-chat', 'deepseek-reasoner'], note: '' },
        { id: 'zhipu', name: '智谱 GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-4-plus', 'glm-4-air', 'glm-4-flash'], note: 'glm-4-flash 免费' },
        { id: 'moonshot', name: '月之暗面 Kimi', baseUrl: 'https://api.moonshot.cn/v1', models: ['kimi-latest', 'moonshot-v1-8k', 'moonshot-v1-32k'], note: '' },
        { id: 'baichuan', name: '百川智能', baseUrl: 'https://api.baichuan-ai.com/v1', models: ['Baichuan4', 'Baichuan3-Turbo'], note: '' },
        { id: 'custom', name: '自定义接口', baseUrl: '', models: [], note: '手动填写 Base URL 与模型名' }
    ];

    const ALL_MODELS = [...new Set(PROVIDERS.flatMap(p => p.models))];

    function findProviderByBaseUrl(baseUrl) {
        const b = (baseUrl || '').replace(/\/+$/, '');
        return PROVIDERS.find(p => p.baseUrl && p.baseUrl.replace(/\/+$/, '') === b) || null;
    }

    /* ---------- 配置存取 ---------- */

    function loadAIConfig() {
        try {
            const raw = localStorage.getItem(AI_KEY);
            if (raw) {
                const c = JSON.parse(raw);
                return {
                    apiKey: c.apiKey || '',
                    baseUrl: c.baseUrl || DEFAULT_BASE,
                    model: c.model || DEFAULT_MODEL,
                    provider: c.provider || ''
                };
            }
        } catch (e) {}
        return { apiKey: '', baseUrl: DEFAULT_BASE, model: DEFAULT_MODEL, provider: '' };
    }

    function saveAIConfig(cfg) {
        const c = {
            apiKey: (cfg.apiKey || '').trim(),
            baseUrl: (cfg.baseUrl || DEFAULT_BASE).trim().replace(/\/+$/, ''),
            model: (cfg.model || DEFAULT_MODEL).trim(),
            provider: (cfg.provider || '').trim()
        };
        localStorage.setItem(AI_KEY, JSON.stringify(c));
    }

    /* ---------- 结果缓存（按题目 id） ---------- */

    function loadAICache() {
        try {
            const raw = localStorage.getItem(AI_CACHE_KEY);
            if (raw) return JSON.parse(raw);
        } catch (e) {}
        return {};
    }

    function saveAICacheObj(obj) {
        localStorage.setItem(AI_CACHE_KEY, JSON.stringify(obj));
    }

    function cacheGet(qid) {
        return loadAICache()[qid] || null;
    }

    function cacheSet(qid, text, model, mismatch) {
        const c = loadAICache();
        delete c[qid];
        c[qid] = { text, model: model || DEFAULT_MODEL, mismatch: !!mismatch, ts: Date.now() };
        const keys = Object.keys(c);
        if (keys.length > CACHE_MAX) {
            keys.sort((a, b) => (c[a].ts || 0) - (c[b].ts || 0));
            for (let i = 0; i < keys.length - CACHE_MAX; i++) delete c[keys[i]];
        }
        saveAICacheObj(c);
    }

    function clearAICache(qid) {
        const c = loadAICache();
        if (c[qid]) { delete c[qid]; saveAICacheObj(c); }
    }

    /* ---------- 追问会话存取（按题目隔离，只存本机） ---------- */

    function loadChatStore() {
        try {
            const raw = localStorage.getItem(AI_CHAT_KEY);
            if (raw) {
                const o = JSON.parse(raw);
                if (o && typeof o === 'object') return o;
            }
        } catch (e) {}
        return {};
    }

    function saveChatStore(o) {
        try { localStorage.setItem(AI_CHAT_KEY, JSON.stringify(o)); } catch (e) {}
    }

    function chatGet(qid) {
        const s = loadChatStore()[qid];
        return (s && Array.isArray(s.rounds)) ? s : null;
    }

    function chatCount(qid) {
        const s = chatGet(qid);
        return s ? s.rounds.length : 0;
    }

    /* 追加一轮问答，超出上限时丢弃最早的轮次 */
    function chatSaveRound(qid, question, answer, model, truncated) {
        const store = loadChatStore();
        const prev = store[qid];
        const rounds = (prev && prev.rounds) ? prev.rounds.slice() : [];
        delete store[qid];               // 先删再写，使该题排到最后（便于 LRU 淘汰）
        rounds.push({ q: question, a: answer, ts: Date.now(), t: !!truncated });
        while (rounds.length > CHAT_ROUNDS_MAX) rounds.shift();
        store[qid] = { model: model || DEFAULT_MODEL, ts: Date.now(), rounds: rounds };

        const keys = Object.keys(store);
        if (keys.length > CHAT_MAX) {
            keys.sort((a, b) => (store[a].ts || 0) - (store[b].ts || 0));
            for (let i = 0; i < keys.length - CHAT_MAX; i++) delete store[keys[i]];
        }
        saveChatStore(store);
    }

    function chatClear(qid) {
        const store = loadChatStore();
        if (store[qid]) { delete store[qid]; saveChatStore(store); }
    }

    /* ---------- 作答还原（会话 → 持久化快照 → 考试答案） ---------- */

    function userSelectionFor(qid) {
        const s = ACP.state.session[qid];
        if (s && s.sel && s.sel.length) return s.sel;
        const p = ACP.prog(qid);
        if (p && p.a && p.a.length) return p.a;
        const ex = ACP.state.exam;
        if (ex && ex.pool) {
            const i = ex.pool.findIndex(x => x.id === qid);
            if (i >= 0 && ex.answers[i] && ex.answers[i].length) return ex.answers[i];
        }
        return [];
    }

    /* ---------- 提示词 ---------- */

    function buildPrompt(q, userSel) {
        const opts = q.options.map(o => `${o.label}. ${o.text}`).join('\n');
        const mine = (userSel && userSel.length) ? userSel.join('、') : '（未作答）';
        const optionLines = q.options.map(o => `${o.label}：理由（一到两句话），正确/错误`).join('\n');
        return [
            `【题目】${q.stem}`,
            '【选项】',
            opts,
            '',
            `【我的作答】${mine}`,
            '',
            '请先独立判断，不要参考或迎合任何预先给出的答案。',
            '请严格按下面格式输出，纯文本、不要 Markdown 标题、不要多余解释：',
            '',
            '（先点明本题考点或结论）',
            optionLines,
            '选X，解析考点，详细介绍相关考点。',
            '',
            '要求：每个选项一行；多选题"选"后写全部正确选项（如"选A、C"）；理由要解释原因或易错点，不要只写"错误"。'
        ].join('\n');
    }

    /* ---------- 追问上下文 ---------- */

    /* 锚点提示词：题目本身 + 我的作答 + 题库参考解析（始终保留，不参与裁剪）
       注意：不注入题库标准答案，与首次讲解保持同样的取舍 */
    function buildChatContext(q, userSel) {
        const opts = q.options.map(o => `${o.label}. ${o.text}`).join('\n');
        const mine = (userSel && userSel.length) ? userSel.join('、') : '（未作答）';
        const lines = [
            `【题目】${q.stem}`,
            '【选项】',
            opts,
            '',
            `【我的作答】${mine}`
        ];
        if (q.analysis) lines.push('', '【题库参考解析（可能不完整，仅供参考）】', q.analysis);
        lines.push('', '以上是本题的全部上下文，接下来我会就这道题追问，请据此作答。');
        return lines.join('\n');
    }

    /* 组装本次请求的多轮消息：
       system → 锚点（题目上下文 + 当前 AI 讲解）→ 最近若干轮追问 → 本次提问
       AI 讲解每次从缓存动态读取，因此「重新生成讲解」后追问会自动基于新讲解 */
    function buildChatMessages(qid, question) {
        const q = ACP.ID_MAP[qid];
        const userSel = userSelectionFor(qid);
        const c = cacheGet(qid);
        const ses = chatGet(qid);

        const msgs = [
            { role: 'system', content: CHAT_SYSTEM_PROMPT },
            { role: 'user', content: buildChatContext(q, userSel) },
            { role: 'assistant', content: (c && c.text) ? c.text : '好的，我已阅读本题上下文，请提出你的问题。' }
        ];

        let rounds = (ses && ses.rounds) ? ses.rounds.slice() : [];
        let total = rounds.reduce((n, r) => n + r.q.length + r.a.length, 0);
        while (rounds.length && total > CHAT_CTX_CHARS) {
            const r = rounds.shift();
            total -= r.q.length + r.a.length;
        }
        if (rounds.length > CHAT_CTX_ROUNDS) rounds = rounds.slice(rounds.length - CHAT_CTX_ROUNDS);
        rounds.forEach(r => {
            msgs.push({ role: 'user', content: r.q });
            msgs.push({ role: 'assistant', content: r.a });
        });

        msgs.push({ role: 'user', content: question });
        return msgs;
    }

    /* ---------- 调用核心 ---------- */

    async function errorMessage(resp) {
        if (resp.status === 401) return 'API Key 无效或无权限（401），请检查 Key 是否填写正确、是否过期';
        if (resp.status === 404) return '接口地址或模型名错误（404），请检查接口地址与模型';
        if (resp.status === 429) return '调用频率或额度受限（429），请稍后再试';
        let msg = `请求失败（HTTP ${resp.status}）`;
        try {
            const j = await resp.json();
            const m = j.message || (j.error && j.error.message);
            if (m) msg = m;
        } catch (e) {}
        return msg;
    }

    function requestBody(q, userSel, cfg, stream) {
        return {
            model: cfg.model || DEFAULT_MODEL,
            messages: [
                { role: 'system', content: SYSTEM_PROMPT },
                { role: 'user', content: buildPrompt(q, userSel) }
            ],
            temperature: 0.2,
            max_tokens: 700,
            stream: !!stream
        };
    }

    function postBody(messages, cfg, stream, maxTokens) {
        return {
            model: cfg.model || DEFAULT_MODEL,
            messages: messages,
            temperature: 0.2,
            max_tokens: maxTokens || 700,
            stream: !!stream
        };
    }

    function chatHeaders(cfg) {
        return { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cfg.apiKey };
    }

    /* 非流式（用于测试 / 兜底） */
    async function aiCall(q, userSel, cfg) {
        const base = (cfg.baseUrl || DEFAULT_BASE).replace(/\/+$/, '');
        const resp = await fetch(base + '/chat/completions', {
            method: 'POST',
            headers: chatHeaders(cfg),
            body: JSON.stringify(requestBody(q, userSel, cfg, false))
        });
        if (!resp.ok) throw new Error(await errorMessage(resp));
        const j = await resp.json();
        const content = j && j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
        if (!content) throw new Error('返回内容为空，请重试');
        return content;
    }

    /* 通用流式（SSE）：逐字回调 onChunk(累计文本)，返回完整文本
       - messages 为完整对话数组（首次讲解与追问共用）
       - signal 可选，用于「中断生成」；中断/报错时 error.partial 携带已生成的部分文本 */
    async function streamCompletion(messages, cfg, onChunk, maxTokens, signal) {
        const base = (cfg.baseUrl || DEFAULT_BASE).replace(/\/+$/, '');
        let full = '';
        try {
            const resp = await fetch(base + '/chat/completions', {
                method: 'POST',
                headers: chatHeaders(cfg),
                body: JSON.stringify(postBody(messages, cfg, true, maxTokens)),
                signal: signal || undefined
            });
            if (!resp.ok) throw new Error(await errorMessage(resp));

            // 某些环境不支持 ReadableStream，退回一次性解析
            if (!resp.body || !resp.body.getReader) {
                const j = await resp.json();
                const content = j && j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
                if (!content) throw new Error('返回内容为空，请重试');
                full = content;
                onChunk(full);
                return full;
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                let nl;
                while ((nl = buffer.indexOf('\n')) >= 0) {
                    const line = buffer.slice(0, nl).trim();
                    buffer = buffer.slice(nl + 1);
                    if (!line.startsWith('data:')) continue;
                    const data = line.slice(5).trim();
                    if (data === '[DONE]') continue;
                    try {
                        const j = JSON.parse(data);
                        const delta = j.choices && j.choices[0] && j.choices[0].delta;
                        const content = delta && delta.content;
                        if (content) { full += content; onChunk(full); }
                    } catch (e) {}
                }
            }
            return full;
        } catch (e) {
            if (e) e.partial = full;
            throw e;
        }
    }

    /* 首次讲解：沿用固定格式提示词（对外签名不变） */
    async function aiStream(q, userSel, cfg, onChunk) {
        return streamCompletion(requestBody(q, userSel, cfg, true).messages, cfg, onChunk, 700);
    }

    /* 纯文本渲染：转义 HTML 并保留换行（AI 按固定逐行格式输出） */
    function renderAIResult(text) {
        return ACP.esc(text).replace(/\n/g, '<br>');
    }

    /* 从模型输出的“选X，解析考点…”中提取模型独立作答结果 */
    function parseModelAnswer(text) {
        const m = String(text || '').match(/选\s*([A-G](?:\s*[、,，]\s*[A-G])*)/);
        if (!m) return [];
        return m[1].split(/[、,，\s]+/).filter(Boolean).map(s => s.toUpperCase());
    }

    function sameAnswer(a, b) {
        const A = (a || []).slice().sort().join(',');
        const B = (b || []).slice().sort().join(',');
        return A === B;
    }

    function mismatchNote(modelAns, bankAns) {
        if (!modelAns.length || sameAnswer(modelAns, bankAns)) return '';
        return `
          <div class="ai-verify-note">⚠️ 模型答案与题库答案不一致，请多方验证，以大模型为准。</div>`;
    }

    /* ---------- 解析框内容：有缓存显示缓存，否则显示入口按钮 ---------- */

    /* 追问入口：已讲解结果显示「继续追问」，未讲解显示轻量「题目助手」入口 */
    function followBtnHTML(qid) {
        const n = chatCount(qid);
        return `<button class="btn btn-sm" type="button" onclick="ACP.openAIChat('${qid}')" ` +
            `title="围绕本题无限追问，保留上下文">💬 继续追问${n ? ` · ${n} 轮` : ''}</button>`;
    }

    function aiPanelHTML(qid) {
        const c = cacheGet(qid);
        if (c && c.text) {
            return `
        <div class="ai-result">
          <div class="ai-result-head">
            <span>🤖 模型讲解</span>
            <span class="ai-model-tag">${ACP.esc(c.model || DEFAULT_MODEL)}</span>
            <span class="ai-cached-tag">已缓存</span>
          </div>
          <div class="ai-result-body">${renderAIResult(c.text)}</div>
          ${c.mismatch ? mismatchNote(['X'], ['Y']) : ''}
          <div class="ai-result-foot">
            ${followBtnHTML(qid)}
            <button class="btn btn-sm" onclick="ACP.aiAsk('${qid}')">🔄 重新生成</button>
            <span class="ai-disclaimer">内容由大模型生成，仅供参考，以官方文档为准</span>
          </div>
        </div>`;
        }
        return `
        <div class="ai-entry-row">
        <button class="ai-ask-btn" type="button" onclick="ACP.aiAsk('${qid}')" title="调用大模型简明讲解本题">
          <span class="ai-ico">🤖</span> AI 答疑
          <span class="ai-hint">大模型简明讲解</span>
        </button>
        <button class="ai-chat-link" type="button" onclick="ACP.openAIChat('${qid}')" title="打开题目助手，围绕本题自由追问">💬 题目助手</button>
        </div>`;
    }

    /* ---------- 答疑入口 ---------- */

    function aiAsk(qid) {
        const q = ACP.ID_MAP[qid];
        if (!q) return;
        const wrap = document.getElementById('ai-' + qid);
        // 题目面板不在当前页面时，若助手弹窗正开着本题，仍允许重新生成讲解
        if (!wrap && chatQid !== qid) return;

        const cfg = loadAIConfig();
        if (!cfg.apiKey) {
            openAISettings();
            ACP.toast('请先填写你的 DashScope API Key');
            return;
        }

        const userSel = userSelectionFor(qid);
        const model = cfg.model || DEFAULT_MODEL;

        if (wrap) {
            wrap.innerHTML = `
        <div class="ai-result">
          <div class="ai-result-head">
            <span>🤖 模型讲解</span>
            <span class="ai-model-tag">${ACP.esc(model)}</span>
            <span class="ai-streaming-tag">生成中…</span>
          </div>
          <div class="ai-result-body ai-stream" id="ai-stream-${qid}"></div>
        </div>`;
        }
        const streamEl = wrap ? document.getElementById('ai-stream-' + qid) : null;

        aiStream(q, userSel, cfg, full => {
            if (streamEl) streamEl.textContent = full;
        })
            .then(text => {
                const modelAns = parseModelAnswer(text);
                const mismatch = !sameAnswer(modelAns, q.ansArr);
                cacheSet(qid, text, model, mismatch);
                // 讲解更新后，若助手弹窗正开着本题，同步刷新其首条「AI 讲解」气泡
                if (chatQid === qid) { renderChat(); updateChatHead(); }
                if (wrap) wrap.innerHTML = `
            <div class="ai-result">
              <div class="ai-result-head">
                <span>🤖 模型讲解</span>
                <span class="ai-model-tag">${ACP.esc(model)}</span>
                <span class="ai-cached-tag">已保存</span>
              </div>
              <div class="ai-result-body">${renderAIResult(text)}</div>
              ${mismatch ? mismatchNote(modelAns, q.ansArr) : ''}
              <div class="ai-result-foot">
                ${followBtnHTML(qid)}
                <button class="btn btn-sm" onclick="ACP.aiAsk('${qid}')">🔄 重新生成</button>
                <span class="ai-disclaimer">内容由大模型生成，仅供参考，以官方文档为准</span>
              </div>
            </div>`;
            })
            .catch(err => {
                if (!wrap) return;
                wrap.innerHTML = `
            <div class="ai-error">
              <div>⚠️ 调用失败：${ACP.esc(err.message || '未知错误')}</div>
              <div class="ai-error-actions">
                <button class="btn btn-sm" onclick="ACP.openAISettings()">检查设置</button>
                <button class="btn btn-sm" onclick="ACP.aiAsk('${qid}')">重试</button>
              </div>
            </div>`;
            });
    }

    /* ---------- 题目助手（追问弹窗） ---------- */

    let chatQid = null;      // 当前弹窗对应的题目 id
    let chatBusy = false;    // 是否正在生成回答
    let chatAbort = null;    // 当前请求的 AbortController
    let chatRetryQ = null;   // 生成失败后待重试的问题
    let chatCtxOpen = false; // 本题上下文是否展开
    let chatPos = null;      // 浮动窗当前位置 {x,y}

    function el(id) { return document.getElementById(id); }

    function isChatOpen() {
        const m = el('aiChatModal');
        return !!(m && m.classList.contains('show'));
    }

    function scrollChatBottom() {
        const b = el('aiChatBody');
        if (b) b.scrollTop = b.scrollHeight;
    }

    function autoGrow(input) {
        if (!input) return;
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    }

    function updateInputState() {
        const input = el('aiChatInput');
        const send = el('aiChatSendBtn');
        const stop = el('aiChatStopBtn');
        if (input) input.disabled = chatBusy;
        if (send) send.style.display = chatBusy ? 'none' : '';
        if (stop) stop.style.display = chatBusy ? '' : 'none';
    }

    function updateChatHead() {
        const qid = chatQid;
        const tag = el('aiChatQTag');
        if (!qid || !tag) return;
        const n = chatCount(qid);
        tag.textContent = '#' + qid + (n ? ` · 已追问 ${n} 轮` : '');
    }

    /* 面板已渲染时同步刷新（用于轮数变化）；首次讲解流式生成中不覆盖 */
    function refreshPanel(qid) {
        const wrap = el('ai-' + qid);
        if (!wrap || wrap.querySelector('.ai-stream')) return;
        wrap.innerHTML = aiPanelHTML(qid);
    }

    function msgHTML(role, text, opt) {
        opt = opt || {};
        const avatar = role === 'me' ? '🙋' : '🤖';
        const cls = 'chat-bubble' + (opt.label ? ' first' : '');
        let foot = '';
        if (opt.label) foot += `<span class="chat-bubble-label">${ACP.esc(opt.label)}</span>`;
        if (opt.tip) foot += `<span class="chat-tip">${ACP.esc(opt.tip)}</span>`;
        if (opt.foot) foot += opt.foot;
        return `
        <div class="chat-msg ${role === 'me' ? 'me' : ''}">
          <div class="chat-avatar">${avatar}</div>
          <div class="${cls}">
            <div class="chat-bubble-text${opt.thinking ? ' chat-thinking' : ''}">${text}</div>
            ${foot ? `<div class="chat-bubble-foot">${foot}</div>` : ''}
          </div>
        </div>`;
    }

    function appendMsg(role, html, opt) {
        const body = el('aiChatBody');
        if (!body) return null;
        body.insertAdjacentHTML('beforeend', msgHTML(role, html, opt));
        scrollChatBottom();
        return body.lastElementChild;
    }

    /* 快速追问建议 */
    function quickChips(qid) {
        const sel = userSelectionFor(qid);
        return [
            sel.length ? `我选的是 ${sel.join('、')}，为什么不对？` : '正确选项是怎么推导出来的？',
            '这个结论容易和什么混淆？',
            '举一个实际应用的例子',
            '还有哪些相关考点？'
        ];
    }

    function renderQuick() {
        const box = el('aiChatQuick');
        if (!box || !chatQid) return;
        box.innerHTML = quickChips(chatQid).map(t =>
            `<button class="chat-chip" type="button" data-q="${ACP.esc(t)}" onclick="ACP.aiChatQuick(this)">${ACP.esc(t)}</button>`
        ).join('');
    }

    function renderChatCtx() {
        const qid = chatQid;
        const q = qid ? ACP.ID_MAP[qid] : null;
        if (!q) return;
        const brief = el('aiChatCtxBrief');
        const full = el('aiChatCtxFull');
        const ctxBox = el('aiChatCtx');
        if (brief) {
            brief.innerHTML = `<span class="ctx-label">本题</span>` +
                `<span class="ctx-text">${ACP.esc(q.stem)}</span>` +
                `<span class="ctx-toggle">${chatCtxOpen ? '收起 ∧' : '展开 ∨'}</span>`;
        }
        if (full) {
            full.style.display = chatCtxOpen ? '' : 'none';
            if (chatCtxOpen) {
                const mine = userSelectionFor(qid);
                full.innerHTML = `<div>${ACP.esc(q.stem)}</div>` +
                    `<ul class="ctx-opts">${q.options.map(o => `<li>${ACP.esc(o.label)}. ${ACP.esc(o.text)}</li>`).join('')}</ul>` +
                    `<div class="ctx-my">我的作答：${mine.length ? ACP.esc(mine.join('、')) : '未作答'}</div>`;
            }
        }
        if (ctxBox) ctxBox.className = 'chat-ctx' + (chatCtxOpen ? ' open' : '');
    }

    function toggleChatCtx() { chatCtxOpen = !chatCtxOpen; renderChatCtx(); }

    /* ---------- 浮动窗定位与拖动（非模态：不锁背景、不模糊） ---------- */

    function loadChatPos() {
        try {
            const raw = localStorage.getItem(CHAT_POS_KEY);
            if (raw) {
                const p = JSON.parse(raw);
                if (p && typeof p.x === 'number' && typeof p.y === 'number') return p;
            }
        } catch (e) {}
        return null;
    }

    function saveChatPos(p) { try { localStorage.setItem(CHAT_POS_KEY, JSON.stringify(p)); } catch (e) {} }

    function viewport() {
        return {
            w: (typeof window !== 'undefined' && window.innerWidth) ? window.innerWidth : 1024,
            h: (typeof window !== 'undefined' && window.innerHeight) ? window.innerHeight : 768
        };
    }

    /* 限制在视口内，避免拖出去找不回来 */
    function clampChatPos(p, m) {
        const vp = viewport();
        const w = m.offsetWidth || 600;
        const h = m.offsetHeight || 480;
        const maxX = Math.max(8, vp.w - w - 8);
        const maxY = Math.max(8, vp.h - h - 8);
        return { x: Math.min(Math.max(8, p.x), maxX), y: Math.min(Math.max(8, p.y), maxY) };
    }

    /* 默认贴右下角，尽量不遮挡题目正文 */
    function defaultChatPos(m) {
        const vp = viewport();
        return { x: vp.w - (m.offsetWidth || 600) - 24, y: vp.h - (m.offsetHeight || 480) - 24 };
    }

    function applyChatPos(forceDefault, override) {
        const m = el('aiChatModal');
        if (!m) return null;
        const saved = override || (forceDefault ? null : (chatPos || loadChatPos()));
        const p = clampChatPos(saved || defaultChatPos(m), m);
        chatPos = p;
        m.style.left = p.x + 'px';
        m.style.top = p.y + 'px';
        m.style.right = 'auto';
        m.style.bottom = 'auto';
        return p;
    }

    function resetChatPos() {
        try { localStorage.removeItem(CHAT_POS_KEY); } catch (e) {}
        chatPos = null;
        applyChatPos(true);
        ACP.toast('已复位到默认位置');
    }

    /* 标题栏拖动：鼠标与触屏通用（Pointer Events） */
    function initChatDrag() {
        const m = el('aiChatModal');
        const head = el('aiChatHead');
        if (!m || !head || typeof head.addEventListener !== 'function') return;
        if (head.dataset && head.dataset.dragBound) return;
        if (head.dataset) head.dataset.dragBound = '1';

        let dragging = false;
        let startX = 0, startY = 0, originX = 0, originY = 0, activeId = null;

        const down = e => {
            if (e.button != null && e.button !== 0) return;          // 只响应左键 / 触摸
            if (e.target && e.target.tagName === 'BUTTON') return;    // 不抢按钮点击
            dragging = true;
            activeId = (e.pointerId != null) ? e.pointerId : null;
            startX = e.clientX; startY = e.clientY;
            originX = parseFloat(m.style.left) || 0;
            originY = parseFloat(m.style.top) || 0;
            if (head.setPointerCapture && activeId != null) {
                try { head.setPointerCapture(activeId); } catch (err) {}
            }
            if (e.preventDefault) e.preventDefault();
        };
        const move = e => {
            if (!dragging) return;
            const p = clampChatPos({ x: originX + (e.clientX - startX), y: originY + (e.clientY - startY) }, m);
            chatPos = p;
            m.style.left = p.x + 'px';
            m.style.top = p.y + 'px';
        };
        const up = () => {
            if (!dragging) return;
            dragging = false;
            if (head.releasePointerCapture && activeId != null) {
                try { head.releasePointerCapture(activeId); } catch (err) {}
            }
            activeId = null;
            if (chatPos) saveChatPos(chatPos);
        };

        head.addEventListener('pointerdown', down);
        head.addEventListener('pointermove', move);
        head.addEventListener('pointerup', up);
        head.addEventListener('pointercancel', up);
        head.addEventListener('lostpointercapture', up);
        head.addEventListener('dblclick', () => resetChatPos());
    }

    initChatDrag();

    /* 视口变化时把浮动窗拉回可见区域 */
    if (typeof window !== 'undefined' && window.addEventListener) {
        window.addEventListener('resize', () => {
            const m = el('aiChatModal');
            if (m && m.classList.contains('show')) applyChatPos();
        });
    }

    /* 重绘消息流：AI 讲解（首条）+ 已保存的多轮追问 */
    function renderChat() {
        const body = el('aiChatBody');
        const qid = chatQid;
        if (!body || !qid) return;
        const c = cacheGet(qid);
        const ses = chatGet(qid);
        const rounds = ses ? ses.rounds : [];
        let html = '';
        if (c && c.text) {
            html += msgHTML('assistant', renderAIResult(c.text), {
                label: 'AI 讲解',
                foot: `<button class="btn btn-sm" onclick="ACP.aiAsk('${qid}')">🔄 重新生成讲解</button>`
            });
        }
        rounds.forEach(r => {
            html += msgHTML('me', renderAIResult(r.q), {});
            html += msgHTML('assistant', renderAIResult(r.a), { tip: r.t ? '已中断' : '' });
        });
        if (!c && !rounds.length) {
            html += `<div class="chat-empty">还没有对话内容。<br>
              <b>AI 讲解</b>会作为第一轮回答出现在这里，<br>也可以直接在下面输入你想问的，无限追问、上下文连续。</div>`;
        }
        body.innerHTML = html;
        scrollChatBottom();
    }

    function openAIChat(qid) {
        const q = ACP.ID_MAP[qid];
        const m = el('aiChatModal');
        if (!q || !m) return;

        const cfg = loadAIConfig();
        if (!cfg.apiKey) {
            openAISettings();
            ACP.toast('请先填写你的 DashScope API Key');
            return;
        }

        // 浮动窗已开着同一题：只聚焦输入框，保留用户正在输入的草稿
        if (m.classList.contains('show') && chatQid === qid) {
            const existed = el('aiChatInput');
            if (existed) existed.focus();
            return;
        }

        chatQid = qid;
        chatCtxOpen = false;
        chatRetryQ = null;
        const modelEl = el('aiChatModel');
        if (modelEl) modelEl.textContent = cfg.model || DEFAULT_MODEL;
        renderChatCtx();
        renderChat();
        renderQuick();
        updateChatHead();
        updateInputState();
        m.classList.add('show');
        applyChatPos();
        const input = el('aiChatInput');
        if (input) { input.value = ''; autoGrow(input); setTimeout(() => input.focus(), 60); }
    }

    function closeAIChat() {
        const m = el('aiChatModal');
        if (chatBusy && chatAbort) chatAbort.abort();
        if (m) m.classList.remove('show');
        const qid = chatQid;
        chatQid = null;
        chatRetryQ = null;
        chatCtxOpen = false;
        if (qid) refreshPanel(qid);
    }

    function clearAIChat() {
        const qid = chatQid;
        if (!qid) return;
        if (chatBusy) { ACP.toast('正在生成回答，请先停止'); return; }
        chatClear(qid);
        chatRetryQ = null;
        renderChat();
        renderQuick();
        updateChatHead();
        refreshPanel(qid);
        ACP.toast('已清空本题的追问记录（AI 讲解保留）');
    }

    async function aiChatSend() {
        if (chatBusy) return;
        const input = el('aiChatInput');
        const question = input ? input.value.trim() : '';
        if (!question) { if (input) input.focus(); return; }
        if (input) { input.value = ''; autoGrow(input); }
        await askQuestion(question);
    }

    async function aiChatQuick(btn) {
        if (chatBusy) return;
        const q = btn && btn.dataset ? btn.dataset.q : '';
        if (q) await askQuestion(q);
    }

    function aiChatStop() { if (chatAbort) chatAbort.abort(); }

    async function aiChatRetry() {
        if (chatBusy) return;
        const q = chatRetryQ;
        chatRetryQ = null;
        if (q) await askQuestion(q);
    }

    /* 发起一轮追问：带完整上下文请求 → 流式渲染 → 落盘 */
    async function askQuestion(question) {
        const qid = chatQid;
        if (!qid || !ACP.ID_MAP[qid] || chatBusy) return;

        const cfg = loadAIConfig();
        if (!cfg.apiKey) {
            closeAIChat();
            openAISettings();
            ACP.toast('请先填写你的 DashScope API Key');
            return;
        }

        chatBusy = true;
        updateInputState();
        renderChat();                                   // 只保留已落盘的内容
        appendMsg('me', renderAIResult(question), {});
        const ansEl = appendMsg('assistant', '思考中…', { thinking: true });
        const textEl = ansEl ? ansEl.querySelector('.chat-bubble-text') : null;
        const footEl = ansEl ? ansEl.querySelector('.chat-bubble-foot') : null;

        const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        chatAbort = ctrl;
        try {
            const text = await streamCompletion(
                buildChatMessages(qid, question), cfg,
                full => {
                    if (textEl) {
                        textEl.classList.remove('chat-thinking');
                        textEl.classList.add('chat-cursor');
                        textEl.textContent = full;
                    }
                    scrollChatBottom();
                },
                CHAT_MAX_TOKENS, ctrl ? ctrl.signal : undefined
            );
            chatSaveRound(qid, question, text, cfg.model || DEFAULT_MODEL, false);
            renderChat();                               // 重绘，统一走「已落盘」渲染
            updateChatHead();
            refreshPanel(qid);
        } catch (e) {
            const aborted = !!(e && e.name === 'AbortError');
            const partial = (e && e.partial) || '';
            if (aborted) {
                if (partial) chatSaveRound(qid, question, partial, cfg.model || DEFAULT_MODEL, true);
                if (chatQid === qid) renderChat();
                else ACP.toast('已停止生成');
            } else if (chatQid === qid) {
                chatRetryQ = question;
                if (textEl) {
                    textEl.classList.remove('chat-thinking', 'chat-cursor');
                    textEl.innerHTML = `<div class="chat-err">⚠️ ${ACP.esc((e && e.message) || '未知错误')}</div>`;
                }
                if (footEl) {
                    footEl.innerHTML = `<button class="btn btn-sm" onclick="ACP.aiChatRetry()">🔄 重试</button>` +
                        `<button class="btn btn-sm" onclick="ACP.openAISettings()">检查设置</button>`;
                }
            }
        } finally {
            chatBusy = false;
            chatAbort = null;
            updateInputState();
            scrollChatBottom();
        }
    }

    /* ---------- 设置弹窗 ---------- */

    function populateProviderList() {
        const sel = document.getElementById('aiProvider');
        if (!sel) return;
        sel.innerHTML = PROVIDERS.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
    }

    /* 填充模型下拉框：服务商确定时列出候选，自定义接口时显示手动输入 */
    function populateModelSelect(provider, currentModel) {
        const sel = document.getElementById('aiModel');
        const custom = document.getElementById('aiModelCustom');
        const hint = document.getElementById('aiModelHint');
        const noteEl = document.getElementById('aiProviderNote');
        if (noteEl) noteEl.textContent = provider ? (provider.note || '') : '手动填写 Base URL 与模型名';

        const models = provider && provider.models && provider.models.length ? provider.models : [];
        if (models.length) {
            if (sel) sel.style.display = '';
            if (custom) custom.style.display = 'none';
            if (sel) {
                const options = [...models];
                if (currentModel && !options.includes(currentModel)) options.unshift(currentModel);
                sel.innerHTML = options.map(m => `<option value="${m}">${m}</option>`).join('');
                sel.value = options.includes(currentModel) ? currentModel : models[0];
            }
            if (hint) hint.textContent = '已列出该服务商常用模型，可直接下拉选择';
        } else {
            if (sel) sel.style.display = 'none';
            if (custom) { custom.style.display = ''; custom.value = currentModel || ''; }
            if (hint) hint.textContent = '自定义接口请手动输入模型名';
        }
    }

    function readModelValue() {
        const sel = document.getElementById('aiModel');
        const custom = document.getElementById('aiModelCustom');
        if (custom && custom.style.display !== 'none') return custom.value;
        return sel ? sel.value : '';
    }

    function onProviderChange() {
        const sel = document.getElementById('aiProvider');
        if (!sel) return;
        const p = PROVIDERS.find(x => x.id === sel.value);
        if (!p) return;
        const baseEl = document.getElementById('aiBase');
        const currentModel = readModelValue();
        if (p.id === 'custom') {
            if (baseEl) baseEl.value = '';
            populateModelSelect(null, currentModel);
            return;
        }
        if (baseEl) baseEl.value = p.baseUrl;
        populateModelSelect(p, currentModel);
    }

    function openAISettings() {
        const m = document.getElementById('aiModal');
        const o = document.getElementById('aiOverlay');
        if (!m || !o) return;
        const cfg = loadAIConfig();
        const keyEl = document.getElementById('aiKey');
        const baseEl = document.getElementById('aiBase');
        const sel = document.getElementById('aiProvider');
        if (keyEl) keyEl.value = cfg.apiKey;
        if (baseEl) baseEl.value = cfg.baseUrl;
        populateProviderList();
        const p = findProviderByBaseUrl(cfg.baseUrl);
        if (sel) sel.value = p ? p.id : 'custom';
        populateModelSelect(p, cfg.model);
        const out = document.getElementById('aiTestResult');
        if (out) { out.innerHTML = ''; out.className = 'ai-test-result'; }
        m.classList.add('show');
        o.classList.add('show');
        ACP.toggleSidebar(false);
    }

    function closeAISettings() {
        const m = document.getElementById('aiModal');
        const o = document.getElementById('aiOverlay');
        if (m) m.classList.remove('show');
        if (o) o.classList.remove('show');
    }

    function saveAISettings() {
        const keyEl = document.getElementById('aiKey');
        const baseEl = document.getElementById('aiBase');
        const sel = document.getElementById('aiProvider');
        const model = readModelValue();
        saveAIConfig({
            apiKey: keyEl ? keyEl.value : '',
            baseUrl: baseEl ? baseEl.value : DEFAULT_BASE,
            model: model || DEFAULT_MODEL,
            provider: sel ? sel.value : ''
        });
        closeAISettings();
        ACP.toast(loadAIConfig().apiKey ? 'AI 设置已保存' : '已清除 API Key');
    }

    async function testAIConnection() {
        const keyEl = document.getElementById('aiKey');
        const baseEl = document.getElementById('aiBase');
        const btn = document.getElementById('aiTestBtn');
        const out = document.getElementById('aiTestResult');
        if (!out) return;

        const apiKey = (keyEl ? keyEl.value : '').trim();
        const baseUrl = (baseEl && baseEl.value ? baseEl.value : DEFAULT_BASE).trim().replace(/\/+$/, '');
        const model = (readModelValue() || DEFAULT_MODEL).trim();

        if (!apiKey) {
            out.className = 'ai-test-result err';
            out.innerHTML = '⚠️ 请先填写 API Key';
            return;
        }

        out.className = 'ai-test-result';
        out.innerHTML = '⏳ 测试中…';
        if (btn) btn.disabled = true;
        try {
            const resp = await fetch(baseUrl + '/chat/completions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + apiKey },
                body: JSON.stringify({
                    model,
                    messages: [{ role: 'user', content: '只回复两个字：OK' }],
                    max_tokens: 8
                })
            });
            if (!resp.ok) throw new Error(await errorMessage(resp));
            const j = await resp.json();
            const content = j && j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
            if (!content) throw new Error('返回内容为空');
            out.className = 'ai-test-result ok';
            out.innerHTML = '✅ 连接成功，Key 可用（' + ACP.esc(model) + '）';
        } catch (e) {
            out.className = 'ai-test-result err';
            out.innerHTML = '❌ 失败：' + ACP.esc(e.message || '网络错误');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    /* Escape 关闭浮动窗；追问输入框内 Enter 发送 / Shift+Enter 换行 */
    document.addEventListener('keydown', e => {
        const t = e.target || {};
        const typing = t.tagName === 'INPUT' || t.tagName === 'TEXTAREA';
        if (e.key === 'Escape') {
            // 焦点在页面其它输入框（如搜索框）时不要把浮动窗关掉
            const busyElsewhere = typing && t.id !== 'aiChatInput';
            if (isChatOpen() && !busyElsewhere) closeAIChat();
            else if (!typing) closeAISettings();
            return;
        }
        if (e.key === 'Enter' && t.id === 'aiChatInput' && !e.shiftKey) {
            e.preventDefault();
            aiChatSend();
        }
    });

    document.addEventListener('input', e => {
        if (e.target && e.target.id === 'aiChatInput') autoGrow(e.target);
    });

    ACP.loadAIConfig = loadAIConfig;
    ACP.saveAIConfig = saveAIConfig;
    ACP.openAISettings = openAISettings;
    ACP.closeAISettings = closeAISettings;
    ACP.saveAISettings = saveAISettings;
    ACP.testAIConnection = testAIConnection;
    ACP.onProviderChange = onProviderChange;
    ACP.PROVIDERS = PROVIDERS;
    ACP.aiAsk = aiAsk;
    ACP.aiCall = aiCall;
    ACP.aiStream = aiStream;
    ACP.aiPanelHTML = aiPanelHTML;
    ACP.clearAICache = clearAICache;
    ACP.cacheGet = cacheGet;
    ACP.cacheSet = cacheSet;

    /* 追问 / 题目助手 */
    ACP.openAIChat = openAIChat;
    ACP.closeAIChat = closeAIChat;
    ACP.aiChatSend = aiChatSend;
    ACP.aiChatStop = aiChatStop;
    ACP.aiChatRetry = aiChatRetry;
    ACP.aiChatQuick = aiChatQuick;
    ACP.clearAIChat = clearAIChat;
    ACP.toggleChatCtx = toggleChatCtx;
    ACP.chatGet = chatGet;
    ACP.chatCount = chatCount;
    ACP.chatClear = chatClear;
    ACP.chatSaveRound = chatSaveRound;
    ACP.buildChatMessages = buildChatMessages;
    ACP.applyChatPos = applyChatPos;
    ACP.resetChatPos = resetChatPos;

})(window.ACP);
