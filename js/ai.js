/* ============================================================
   ACP — AI 答疑（DashScope / OpenAI 兼容接口）
   用户自带 API Key，浏览器直连，Key 仅存本地 localStorage。
   ============================================================ */
(function (ACP) {

    const AI_KEY = 'acp_ai_config';
    const DEFAULT_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
    const DEFAULT_MODEL = 'qwen-plus';

    const SYSTEM_PROMPT =
        '你是阿里云 ACP 大模型高级工程师认证的资深备考助教。请用简体中文、条理清晰、适合备考复习的方式讲解题目。' +
        '使用 Markdown 格式，必须包含以下四个小节：## 考点定位、## 解题思路、## 选项逐项分析、## 记忆要点。' +
        '语言专业、简洁、不啰嗦，重点讲清"正确答案为什么对、其余选项为什么错"，以及我的作答对错的原因。';

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
        const baseAnalysis = q.analysis ? q.analysis : '（无）';
        return [
            '请讲解下面这道 ACP 备考题。',
            '',
            `【题目】${q.stem}`,
            `【题型】${q.multi ? '多选题' : '单选题'}`,
            '【选项】',
            opts,
            '',
            `【正确答案】${correct}`,
            `【我的作答】${mine}`,
            `【题库原解析】${baseAnalysis}`,
            '',
            '请按"考点定位 / 解题思路 / 选项逐项分析 / 记忆要点"的结构讲解，重点说明我的作答为什么对或错，以及其余选项为什么不对。'
        ].join('\n');
    }

    /* ---------- 调用核心 ---------- */

    async function aiCall(q, userSel, cfg) {
        const base = (cfg.baseUrl || DEFAULT_BASE).replace(/\/+$/, '');
        const resp = await fetch(base + '/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + cfg.apiKey
            },
            body: JSON.stringify({
                model: cfg.model || DEFAULT_MODEL,
                messages: [
                    { role: 'system', content: SYSTEM_PROMPT },
                    { role: 'user', content: buildPrompt(q, userSel) }
                ],
                temperature: 0.2,
                max_tokens: 1600
            })
        });

        if (!resp.ok) {
            let msg = `请求失败（HTTP ${resp.status}）`;
            if (resp.status === 401) msg = 'API Key 无效或无权限（401），请检查 Key 是否填写正确、是否过期';
            else if (resp.status === 404) msg = '接口地址或模型名错误（404），请检查接口地址与模型';
            else if (resp.status === 429) msg = '调用频率或额度受限（429），请稍后再试';
            else {
                try {
                    const j = await resp.json();
                    const m = j.message || (j.error && j.error.message);
                    if (m) msg = m;
                } catch (e) {}
            }
            throw new Error(msg);
        }

        const j = await resp.json();
        const content = j && j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
        if (!content) throw new Error('返回内容为空，请重试');
        return content;
    }

    /* 对渲染后的 HTML 做最小安全处理：拦掉 javascript: 链接 */
    function sanitizeAIHtml(html) {
        return String(html)
            .replace(/href="\s*javascript:[^"]*"/gi, 'href="#"')
            .replace(/on\w+="[^"]*"/gi, '');
    }

    /* 渲染 markdown：优先复用学习模块的渲染器，缺省退化为纯文本 */
    function renderAIMarkdown(text) {
        if (typeof ACP.mdToHtml === 'function') return sanitizeAIHtml(ACP.mdToHtml(text));
        return '<pre>' + ACP.esc(text) + '</pre>';
    }

    /* ---------- 答疑入口（供解析框按钮调用） ---------- */

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
        wrap.innerHTML = `
      <div class="ai-loading">
        <span class="ai-spin"></span>
        <span>正在调用 <b>${ACP.esc(cfg.model || DEFAULT_MODEL)}</b> 生成讲解…</span>
      </div>`;

        aiCall(q, userSel, cfg)
            .then(text => {
                const body = renderAIMarkdown(text);
                wrap.innerHTML = `
          <div class="ai-result">
            <div class="ai-result-head">
              <span>🤖 模型讲解</span>
              <span class="ai-model-tag">${ACP.esc(cfg.model || DEFAULT_MODEL)}</span>
            </div>
            <div class="ai-result-body">${body}</div>
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
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + apiKey
                },
                body: JSON.stringify({
                    model,
                    messages: [{ role: 'user', content: '只回复两个字：OK' }],
                    max_tokens: 8
                })
            });
            if (!resp.ok) {
                let msg = `HTTP ${resp.status}`;
                try {
                    const j = await resp.json();
                    const m = j.message || (j.error && j.error.message);
                    if (m) msg = m;
                } catch (e) {}
                throw new Error(msg);
            }
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

})(window.ACP);
