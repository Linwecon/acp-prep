/* ============================================================
   ACP — AI 答疑（DashScope / OpenAI 兼容接口）
   - 用户自带 API Key，浏览器直连，Key 仅存本地 localStorage
   - 流式输出（SSE）逐字显示，结果缓存到本地，跨题跳转复用
   ============================================================ */
(function (ACP) {

    const AI_KEY = 'acp_ai_config';
    const AI_CACHE_KEY = 'acp_ai_cache';
    const CACHE_MAX = 200;
    const DEFAULT_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
    const DEFAULT_MODEL = 'qwen-plus';

    const SYSTEM_PROMPT =
        '你是阿里云 ACP 大模型高级工程师认证的备考助教。请用简体中文、简明扼要地讲解题目：' +
        '直接给结论和要点，不要铺垫、不要复述题目、不要长篇大论。全文控制在 150 字以内。';

    /* ---------- 配置存取 ---------- */

    function loadAIConfig() {
        try {
            const raw = localStorage.getItem(AI_KEY);
            if (raw) {
                const c = JSON.parse(raw);
                return {
                    apiKey: c.apiKey || '',
                    baseUrl: c.baseUrl || DEFAULT_BASE,
                    model: c.model || DEFAULT_MODEL
                };
            }
        } catch (e) {}
        return { apiKey: '', baseUrl: DEFAULT_BASE, model: DEFAULT_MODEL };
    }

    function saveAIConfig(cfg) {
        const c = {
            apiKey: (cfg.apiKey || '').trim(),
            baseUrl: (cfg.baseUrl || DEFAULT_BASE).trim().replace(/\/+$/, ''),
            model: (cfg.model || DEFAULT_MODEL).trim()
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

    function cacheSet(qid, text, model) {
        const c = loadAICache();
        delete c[qid];
        c[qid] = { text, model: model || DEFAULT_MODEL, ts: Date.now() };
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
        const correct = q.ansArr.join('、');
        const mine = (userSel && userSel.length) ? userSel.join('、') : '（未作答）';
        return [
            `【题目】${q.stem}`,
            '【选项】',
            opts,
            '',
            `【正确答案】${correct}`,
            `【我的作答】${mine}`,
            '',
            '请用 Markdown 按下面四行结构讲解，每部分一句话、直接给结论：',
            '## 考点',
            '## 解析',
            '## 我的作答',
            '## 易错点'
        ].join('\n');
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
            max_tokens: 500,
            stream: !!stream
        };
    }

    /* 非流式（用于测试 / 兜底） */
    async function aiCall(q, userSel, cfg) {
        const base = (cfg.baseUrl || DEFAULT_BASE).replace(/\/+$/, '');
        const resp = await fetch(base + '/chat/completions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cfg.apiKey },
            body: JSON.stringify(requestBody(q, userSel, cfg, false))
        });
        if (!resp.ok) throw new Error(await errorMessage(resp));
        const j = await resp.json();
        const content = j && j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
        if (!content) throw new Error('返回内容为空，请重试');
        return content;
    }

    /* 流式（SSE）：逐字回调 onChunk(累计文本)，返回完整文本 */
    async function aiStream(q, userSel, cfg, onChunk) {
        const base = (cfg.baseUrl || DEFAULT_BASE).replace(/\/+$/, '');
        const resp = await fetch(base + '/chat/completions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cfg.apiKey },
            body: JSON.stringify(requestBody(q, userSel, cfg, true))
        });
        if (!resp.ok) throw new Error(await errorMessage(resp));

        // 某些环境不支持 ReadableStream，退回一次性解析
        if (!resp.body || !resp.body.getReader) {
            const j = await resp.json();
            const content = j && j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
            if (!content) throw new Error('返回内容为空，请重试');
            onChunk(content);
            return content;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let full = '';
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
    }

    /* 对渲染后的 HTML 做最小安全处理：拦掉 javascript: 链接与事件属性 */
    function sanitizeAIHtml(html) {
        return String(html)
            .replace(/href="\s*javascript:[^"]*"/gi, 'href="#"')
            .replace(/on\w+="[^"]*"/gi, '');
    }

    function renderAIMarkdown(text) {
        if (typeof ACP.mdToHtml === 'function') return sanitizeAIHtml(ACP.mdToHtml(text));
        return '<pre>' + ACP.esc(text) + '</pre>';
    }

    /* ---------- 解析框内容：有缓存显示缓存，否则显示入口按钮 ---------- */

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
          <div class="ai-result-body">${renderAIMarkdown(c.text)}</div>
          <div class="ai-result-foot">
            <button class="btn btn-sm" onclick="ACP.aiAsk('${qid}')">🔄 重新生成</button>
            <span class="ai-disclaimer">内容由大模型生成，仅供参考，以官方文档为准</span>
          </div>
        </div>`;
        }
        return `
        <button class="ai-ask-btn" type="button" onclick="ACP.aiAsk('${qid}')" title="调用大模型简明讲解本题">
          <span class="ai-ico">🤖</span> AI 答疑
          <span class="ai-hint">大模型简明讲解</span>
        </button>`;
    }

    /* ---------- 答疑入口 ---------- */

    function aiAsk(qid) {
        const q = ACP.ID_MAP[qid];
        const wrap = document.getElementById('ai-' + qid);
        if (!q || !wrap) return;

        const cfg = loadAIConfig();
        if (!cfg.apiKey) {
            openAISettings();
            ACP.toast('请先填写你的 DashScope API Key');
            return;
        }

        const userSel = userSelectionFor(qid);
        const model = cfg.model || DEFAULT_MODEL;

        wrap.innerHTML = `
        <div class="ai-result">
          <div class="ai-result-head">
            <span>🤖 模型讲解</span>
            <span class="ai-model-tag">${ACP.esc(model)}</span>
            <span class="ai-streaming-tag">生成中…</span>
          </div>
          <div class="ai-result-body ai-stream" id="ai-stream-${qid}"></div>
        </div>`;
        const streamEl = document.getElementById('ai-stream-' + qid);

        aiStream(q, userSel, cfg, full => {
            if (streamEl) streamEl.textContent = full;
        })
            .then(text => {
                cacheSet(qid, text, model);
                wrap.innerHTML = `
            <div class="ai-result">
              <div class="ai-result-head">
                <span>🤖 模型讲解</span>
                <span class="ai-model-tag">${ACP.esc(model)}</span>
                <span class="ai-cached-tag">已保存</span>
              </div>
              <div class="ai-result-body">${renderAIMarkdown(text)}</div>
              <div class="ai-result-foot">
                <button class="btn btn-sm" onclick="ACP.aiAsk('${qid}')">🔄 重新生成</button>
                <span class="ai-disclaimer">内容由大模型生成，仅供参考，以官方文档为准</span>
              </div>
            </div>`;
            })
            .catch(err => {
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

    /* ---------- 设置弹窗 ---------- */

    function openAISettings() {
        const m = document.getElementById('aiModal');
        const o = document.getElementById('aiOverlay');
        if (!m || !o) return;
        const cfg = loadAIConfig();
        const keyEl = document.getElementById('aiKey');
        const baseEl = document.getElementById('aiBase');
        const modelEl = document.getElementById('aiModel');
        if (keyEl) keyEl.value = cfg.apiKey;
        if (baseEl) baseEl.value = cfg.baseUrl;
        if (modelEl) modelEl.value = cfg.model;
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
        const modelEl = document.getElementById('aiModel');
        saveAIConfig({
            apiKey: keyEl ? keyEl.value : '',
            baseUrl: baseEl ? baseEl.value : DEFAULT_BASE,
            model: modelEl ? modelEl.value : DEFAULT_MODEL
        });
        closeAISettings();
        ACP.toast(loadAIConfig().apiKey ? 'AI 设置已保存' : '已清除 API Key');
    }

    async function testAIConnection() {
        const keyEl = document.getElementById('aiKey');
        const baseEl = document.getElementById('aiBase');
        const modelEl = document.getElementById('aiModel');
        const btn = document.getElementById('aiTestBtn');
        const out = document.getElementById('aiTestResult');
        if (!out) return;

        const apiKey = (keyEl ? keyEl.value : '').trim();
        const baseUrl = (baseEl && baseEl.value ? baseEl.value : DEFAULT_BASE).trim().replace(/\/+$/, '');
        const model = (modelEl && modelEl.value ? modelEl.value : DEFAULT_MODEL).trim();

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

    /* Escape 关闭设置弹窗 */
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            closeAISettings();
        }
    });

    ACP.loadAIConfig = loadAIConfig;
    ACP.saveAIConfig = saveAIConfig;
    ACP.openAISettings = openAISettings;
    ACP.closeAISettings = closeAISettings;
    ACP.saveAISettings = saveAISettings;
    ACP.testAIConnection = testAIConnection;
    ACP.aiAsk = aiAsk;
    ACP.aiCall = aiCall;
    ACP.aiStream = aiStream;
    ACP.aiPanelHTML = aiPanelHTML;
    ACP.clearAICache = clearAICache;
    ACP.cacheGet = cacheGet;
    ACP.cacheSet = cacheSet;

})(window.ACP);
