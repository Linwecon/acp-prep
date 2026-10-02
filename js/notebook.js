/* ============================================================
   ACP — 官方实战教程文档（Notebook 预转换静态阅读器）
   - 数据由 scripts/build_notebooks.py 预生成，浏览器不执行任何 Python
   - Markdown 复用 js/study.js 的 ACP.mdToHtml，保持教材风格一致
   - 目录导航 / 代码高亮 / 一键复制 / 学习进度 / 原文件下载
   ============================================================ */
(function (ACP) {
    const S = ACP.state;

    let currentId = null;
    let scrollTimer = null;

    /* ---------- 进度存储（沿用 localStorage store） ---------- */
    function tutStore() {
        if (!S.store) return {};
        if (!S.store.tut) S.store.tut = {};
        return S.store.tut;
    }
    function tutRec(id) { return tutStore()[id] || null; }
    function saveTut(id, patch) {
        const t = tutStore();
        t[id] = Object.assign({ d: 0, b: 0, at: 0 }, t[id] || {}, patch, { at: Date.now() });
        ACP.saveStore();
    }

    /* ---------- Python 代码高亮（单遍扫描，避免二次替换破坏结构） ---------- */
    const TOKEN_RE = /(#[^\n]*)|("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')|(![^\n]*)|(@[A-Za-z_]\w*)|\b(def|class|import|from|return|if|elif|else|for|while|in|is|not|and|or|try|except|finally|with|as|lambda|yield|raise|assert|pass|break|continue|global|nonlocal|async|await|del|None|True|False|print|self)\b|\b(\d+\.?\d*)\b/g;

    function escCode(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function nbHighlight(src) {
        return escCode(src).replace(TOKEN_RE, (m, comment, str, shell, deco, kw, num) => {
            if (comment !== undefined) return '<span class="tok-c">' + comment + '</span>';
            if (str !== undefined) return '<span class="tok-s">' + str + '</span>';
            if (shell !== undefined) return '<span class="tok-sh">' + shell + '</span>';
            if (deco !== undefined) return '<span class="tok-d">' + deco + '</span>';
            if (kw !== undefined) return '<span class="tok-k">' + kw + '</span>';
            if (num !== undefined) return '<span class="tok-n">' + num + '</span>';
            return m;
        });
    }

    /* ---------- Markdown：复用现有渲染器并给标题加锚点 id ---------- */
    function nbMdHtml(md, blockIdx) {
        let html = (ACP.mdToHtml ? ACP.mdToHtml(md) : '<pre>' + ACP.esc(md) + '</pre>');
        let h = 0;
        // 渲染器可能已给标题加过 id（按标题文本），这里统一替换为稳定锚点 nb-h-块-序号
        html = html.replace(/<h([1-3])\b([^>]*)>([\s\S]*?)<\/h\1>/g, (m, lvl, attrs, inner) => {
            const keep = String(attrs).replace(/\s*id="[^"]*"/g, '');
            const id = 'nb-h-' + blockIdx + '-' + (h++);
            return '<h' + lvl + keep + ' id="' + id + '">' + inner + '</h' + lvl + '>';
        });
        return html;
    }

    /* ---------- 单元渲染 ---------- */
    function nbBlockHtml(b, i) {
        if (b.t === 'md') {
            return `<section class="nb-block nb-md" id="nb-b-${i}">${nbMdHtml(b.md, i)}</section>`;
        }
        if (b.t !== 'code') return '';
        const exec = b.exec ? `<span class="nb-code-exec">执行 #${b.exec}</span>` : '';
        const outs = (b.outs || []).map(o => {
            if (o.t === 'img') {
                return `<figure class="nb-out-img"><img src="${ACP.esc(o.src)}" alt="运行输出" loading="lazy"></figure>`;
            }
            const cls = o.kind === 'error' ? ' nb-out-err' : '';
            const tag = o.kind === 'error' ? '错误信息' : '运行输出';
            return `<div class="nb-out${cls}"><span class="nb-out-tag">${tag}</span><pre>${ACP.esc(o.text || '')}</pre></div>`;
        }).join('');
        // 代码框与知识点教材一致：macOS 终端风格（三色点标题栏 + 复制按钮在标题栏右侧）
        return `<section class="nb-block nb-code-block" id="nb-b-${i}">
      <div class="nb-code-head"><span class="nb-code-tag">💻 代码${exec}</span></div>
      <div class="lx-code"><pre><code>${nbHighlight(b.src || '')}</code></pre><button class="lx-copy" type="button">复制</button></div>
      ${outs}
    </section>`;
    }

    function nbTocHtml(toc) {
        if (!toc || !toc.length) return '<div class="nb-toc-empty">本篇无标题目录</div>';
        return '<div class="nb-toc-title">目录</div>' + toc.map((e, i) =>
            `<button class="nb-toc-item lvl${e.lvl}${i === 0 ? ' active' : ''}" data-b="${e.b}" data-h="${e.h}">${ACP.esc(e.text)}</button>`
        ).join('');
    }

    /* ---------- 列表页 ---------- */
    function renderTutorial(root) {
        const idx = window.NOTEBOOK_INDEX;
        if (!idx || !idx.chapters || !idx.chapters.length) {
            ACP.setCrumb('官方实战教程', '数据未生成');
            root.innerHTML = `
        <div class="empty-state">
          <div class="icon">📓</div>
          <h3>教程数据未生成</h3>
          <p>请先运行 <code>python scripts/build_notebooks.py</code> 生成 <code>data/notebooks.js</code></p>
        </div>`;
            return;
        }
        const tut = tutStore();
        const all = idx.chapters.reduce((n, c) => n + c.items.length, 0);
        const done = idx.chapters.reduce((n, c) =>
            n + c.items.filter(it => tut[it.id] && tut[it.id].d).length, 0);
        const pct = all ? Math.round(done / all * 100) : 0;

        ACP.setCrumb('官方实战教程', `${all} 篇 · 阿里云 ACP 官方 Notebook`);

        root.innerHTML = `
      <div class="nb">
        <div class="nb-hero">
          <div class="nb-hero-head">
            <span class="nb-hero-title">📓 官方实战教程文档</span>
            <span class="nb-hero-sub">阿里云 ACP 官方教程 Notebook · 讲解 / 代码 / 运行输出完整呈现 · 按章节分类</span>
            <a class="nb-hero-link" href="https://github.com/AlibabaCloudDocs/aliyun_acp_learning"
               target="_blank" rel="noopener" title="前往官方教程仓库下载 .ipynb 源文件">
              ⬇ 教程源文件（官方 GitHub 仓库）
            </a>
          </div>
          <div class="nb-hero-progress">
            <div class="nb-track"><i style="width:${pct}%"></i></div>
            <span class="nb-num">已学完 <b>${done}</b> / ${all} 篇</span>
          </div>
        </div>
        ${idx.chapters.map(c => `
          <div class="nb-group">
            <div class="nb-group-head">
              <span class="nb-group-title">${ACP.esc(c.title)}</span>
              <span class="nb-group-desc">${ACP.esc(c.desc || '')}</span>
              ${(c.chs || []).length ? `<span class="nb-group-chs">相关章节练习：${
                c.chs.map(ch => `<button class="nb-ch-chip" onclick="ACP.openChapter('${ch}')">第${ch}章</button>`).join('')
              }</span>` : ''}
            </div>
            <div class="nb-list">
              ${c.items.map(it => nbRowHtml(it, tut[it.id])).join('')}
            </div>
          </div>`).join('')}
        <div class="nb-foot">内容整理自阿里云官方开源教程（Apache-2.0），仅供学习交流；代码与输出为原始 Notebook 快照，不在浏览器中执行。</div>
      </div>`;
    }

    function orderLabel(order) {
        return /^\d+-\d+$/.test(order || '') ? order.replace('-', '.') : '📓';
    }

    /* 列表行：一行一篇，按顺序排列（不放难度徽标） */
    function nbRowHtml(it, rec) {
        const p = rec ? Math.min(100, Math.round((rec.b || 0) / Math.max(1, (it.blocks || it.cells || 1) - 1) * 100)) : 0;
        const state = rec && rec.d
            ? '<span class="nb-row-state done">✓ 已学完</span>'
            : rec ? `<span class="nb-row-state">阅读至 ${p}%</span>` : '';
        return `<button class="nb-row" onclick="ACP.openTutorial('${it.id}')">
        <span class="nb-row-num">${orderLabel(it.order)}</span>
        <span class="nb-row-main">
          <span class="nb-row-title">${ACP.esc(it.title)}</span>
          <span class="nb-row-desc">${ACP.esc(it.desc || '')}</span>
          <span class="nb-row-meta">⏱ 约 ${it.minutes} 分钟 · ${it.cells} 个单元（${it.code} 段代码${it.outs ? ' · ' + it.outs + ' 条输出' : ''}）</span>
        </span>
        <span class="nb-row-side">
          ${state}
          <span class="nb-row-go">→</span>
        </span>
      </button>`;
    }

    /* ---------- 详情页 ---------- */
    function openTutorial(id) {
        currentId = id;
        try { history.pushState(null, '', '#tutorial?id=' + encodeURIComponent(id)); } catch (e) {}
        ensureContent(id, () => {
            const root = document.getElementById('contentInner');
            renderDetail(root, id);
        });
    }

    function backToTutorials() {
        currentId = null;
        try { history.pushState(null, '', '#tutorial'); } catch (e) {}
        renderTutorial(document.getElementById('contentInner'));
        const c = document.getElementById('content');
        if (c) c.scrollTop = 0;
    }

    function ensureContent(id, cb) {
        window.NOTEBOOK_CONTENT = window.NOTEBOOK_CONTENT || {};
        if (window.NOTEBOOK_CONTENT[id]) { cb(); return; }
        const s = document.createElement('script');
        s.src = 'data/notebooks/' + id + '.js';
        s.onload = () => cb();
        s.onerror = () => {
            ACP.toast('教程内容加载失败，请检查 data/notebooks/' + id + '.js');
            backToTutorials();
        };
        document.head.appendChild(s);
    }

    function renderDetail(root, id) {
        const d = (window.NOTEBOOK_CONTENT || {})[id];
        if (!d) { backToTutorials(); return; }
        const rec = tutRec(id) || { d: 0, b: 0 };
        const mdCount = d.blocks.filter(b => b.t === 'md').length;
        const codeCount = d.blocks.filter(b => b.t === 'code').length;
        const idxItem = findItem(id);
        const chapterTitle = idxItem ? idxItem.chapterTitle : (d.chapterTitle || '');

        ACP.setCrumb(d.title, chapterTitle ? chapterTitle + ' · 官方实战教程' : '官方实战教程');

        root.innerHTML = `
      <div class="nb nb-detail">
        <div class="nb-head">
          <button class="btn btn-sm" onclick="ACP.backToTutorials()">← 返回教程列表</button>
          <div class="nb-head-main">
            <h1 class="nb-title">${ACP.esc(d.title)}</h1>
            <div class="nb-meta">
              ${chapterTitle ? `<span class="chip">${ACP.esc(chapterTitle)}</span>` : ''}
              <span class="chip nb-diff-${d.difficulty}">${d.difficulty}</span>
              <span class="chip">⏱ 约 ${d.minutes} 分钟</span>
              <span class="chip">${mdCount} 段讲解 · ${codeCount} 段代码</span>
            </div>
          </div>
          <div class="nb-actions">
            <button class="btn btn-sm" id="nbTocBtn" onclick="ACP.nbToggleToc()" title="展开 / 收起目录">☰ 目录</button>
            <button class="btn btn-sm ${rec.d ? '' : 'btn-primary'}" id="nbDoneBtn" onclick="ACP.nbMarkDone('${id}')">${rec.d ? '✓ 已学完（点击撤销）' : '标记学完'}</button>
          </div>
        </div>
        <div class="nb-body">
          <aside class="nb-toc" id="nbToc">${nbTocHtml(d.toc)}</aside>
          <article class="nb-article" id="nbArticle">
            ${d.blocks.map(nbBlockHtml).join('')}
            <div class="nb-end">— 本篇结束 · 共 ${d.blocks.length} 个单元 —</div>
          </article>
        </div>
        <button class="nb-back-float" id="nbBackFloat" onclick="ACP.backToTutorials()" title="返回教程列表">←</button>
      </div>`;

        bindCopy(root);
        bindToc(root, d);
        bindProgress(root, d, id);
        const c = document.getElementById('content');
        if (c) c.scrollTop = 0;
        // 续读：恢复到上次阅读位置
        if (rec && rec.b) {
            const el = root.querySelector('#nb-b-' + rec.b);
            if (el) setTimeout(() => el.scrollIntoView({ block: 'start' }), 60);
        }
    }

    function findItem(id) {
        const idx = window.NOTEBOOK_INDEX;
        if (!idx) return null;
        for (const c of idx.chapters) {
            const it = c.items.find(x => x.id === id);
            if (it) return Object.assign({ chapterTitle: c.title }, it);
        }
        return null;
    }

    /* ---------- 交互绑定 ---------- */
    function bindCopy(root) {
        root.querySelectorAll('.nb-code-block').forEach(sec => {
            const btn = sec.querySelector('.lx-code .lx-copy');
            const pre = sec.querySelector('pre code');
            if (!btn || !pre) return;
            btn.addEventListener('click', () => {
                copyText(pre.innerText || pre.textContent || '');
                btn.textContent = '已复制';
                setTimeout(() => { btn.textContent = '复制'; }, 1500);
            });
        });
    }

    /* 目录默认收起，点击「☰ 目录」展开 / 收起 */
    function nbToggleToc() {
        const body = document.querySelector('#contentInner .nb-body');
        if (!body) return;
        body.classList.toggle('toc-open');
        const btn = document.getElementById('nbTocBtn');
        if (btn) {
            const open = body.classList.contains('toc-open');
            btn.classList.toggle('active', open);
            btn.innerHTML = open ? '✕ 收起目录' : '☰ 目录';
        }
    }

    function copyText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
        } else {
            fallbackCopy(text);
        }
    }

    function fallbackCopy(text) {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); } catch (e) {}
        document.body.removeChild(ta);
    }

    function bindToc(root, d) {
        const toc = root.querySelector('#nbToc');
        if (!toc) return;
        toc.addEventListener('click', e => {
            const btn = e.target.closest('.nb-toc-item');
            if (!btn) return;
            const b = btn.dataset.b, h = btn.dataset.h;
            const target = root.querySelector('#nb-h-' + b + '-' + h) || root.querySelector('#nb-b-' + b);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            toc.querySelectorAll('.nb-toc-item').forEach(el => el.classList.remove('active'));
            btn.classList.add('active');
        });
        // 移动端目录跟随：滚动时高亮当前章节
        const content = document.getElementById('content');
        if (!content) return;
        content.addEventListener('scroll', () => {
            const heads = root.querySelectorAll('.nb-md h1[id], .nb-md h2[id], .nb-md h3[id]');
            let cur = null;
            heads.forEach(el => { if (el.getBoundingClientRect().top <= 140) cur = el; });
            if (!cur) return;
            const id = cur.id;
            toc.querySelectorAll('.nb-toc-item').forEach(el => {
                el.classList.toggle('active', ('nb-h-' + el.dataset.b + '-' + el.dataset.h) === id);
            });
        });
    }

    function bindProgress(root, d, id) {
        const content = document.getElementById('content');
        if (!content) return;
        const backFloat = root.querySelector('.nb-back-float');
        content.onscroll = () => {
            // 下滑后显示浮动返回键
            if (backFloat) backFloat.classList.toggle('show', content.scrollTop > 200);
            clearTimeout(scrollTimer);
            scrollTimer = setTimeout(() => {
                // 记录阅读位置：当前视口顶部最近的单元
                let last = 0;
                root.querySelectorAll('.nb-block').forEach(sec => {
                    if (sec.getBoundingClientRect().top <= 160) {
                        const n = parseInt(String(sec.id || '').replace('nb-b-', ''), 10);
                        if (!isNaN(n)) last = n;
                    }
                });
                const atBottom = content.scrollTop + content.clientHeight >= content.scrollHeight - 60;
                const rec = tutRec(id) || {};
                if (atBottom && !rec.d) {
                    saveTut(id, { d: 1, b: last });
                    const btn = document.getElementById('nbDoneBtn');
                    if (btn) { btn.textContent = '✓ 已学完（点击撤销）'; btn.classList.remove('btn-primary'); }
                    ACP.toast('已标记本篇为学完 🎉');
                } else if (last !== rec.b) {
                    saveTut(id, { b: last });
                }
            }, 180);
        };
    }

    function nbMarkDone(id) {
        const rec = tutRec(id) || { d: 0, b: 0 };
        saveTut(id, { d: rec.d ? 0 : 1 });
        const btn = document.getElementById('nbDoneBtn');
        if (btn) {
            btn.textContent = rec.d ? '标记学完' : '✓ 已学完（点击撤销）';
            btn.classList.toggle('btn-primary', !!rec.d);
        }
        ACP.toast(rec.d ? '已取消学完标记' : '已标记为学完 🎉');
    }

    /* ---------- 路由入口（供 chapter.js 的 render 调用） ---------- */
    function renderView(root) {
        const m = location.hash.match(/[?&]id=([^&]+)/);
        if (m) {
            const id = decodeURIComponent(m[1]);
            currentId = id;
            ensureContent(id, () => renderDetail(root, id));
        } else {
            currentId = null;
            renderTutorial(root);
        }
    }

    function popHandler() {
        if (!location.hash.startsWith('#tutorial')) return;
        renderView(document.getElementById('contentInner'));
    }

    window.addEventListener('popstate', popHandler);

    ACP.renderTutorial = renderTutorial;
    ACP.renderTutorialView = renderView;
    ACP.openTutorial = openTutorial;
    ACP.backToTutorials = backToTutorials;
    ACP.nbMarkDone = nbMarkDone;
    ACP.nbToggleToc = nbToggleToc;
    ACP.nbHighlight = nbHighlight;
    ACP.nbBlockHtml = nbBlockHtml;
    ACP.nbTocHtml = nbTocHtml;
    ACP.nbRowHtml = nbRowHtml;
    ACP.nbPopHandler = popHandler;

})(window.ACP);
