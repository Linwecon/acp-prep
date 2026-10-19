/* ============================================================
   ACP — Chapter practice (single & list mode)
   ============================================================ */
(function (ACP) {
    const S = ACP.state;

    function resetPracticeSession() {
        S.session = {};
        S.listJudged = {};
        S.sel = new Set();
        S.judged = false;
    }

    function go(view, opts = {}) {
        S.ui.view = view;
        if (opts.ch !== undefined) S.ui.ch = opts.ch;
        if (opts.filter) S.ui.filter = opts.filter;
        if (opts.mode) S.ui.mode = opts.mode;
        if (opts.pool) { S.ui.pool = opts.pool; S.ui.customTitle = opts.title || null; }
        else if (view === 'chapter' && !opts.keepPool) S.ui.customTitle = null;
        if (opts.idx !== undefined) S.ui.idx = opts.idx;
        render();
        ACP.closeSearch();
        ACP.toggleSidebar(false);
    }

    function render() {
        if (ACP.updateMobileNav) ACP.updateMobileNav();
        document.querySelectorAll('[data-nav]').forEach(el => {
            el.classList.toggle('active', el.dataset.nav === S.ui.view);
        });
        document.querySelectorAll('.chapter-item-nav').forEach(el => {
            el.classList.toggle('active', S.ui.view === 'chapter' && el.dataset.ch === S.ui.ch && !S.ui.customTitle);
        });
        const c = document.getElementById('contentInner');
        // 教程页画布更宽（目录 + 正文两栏），其它视图恢复默认宽度
        c.classList.toggle('is-nb-wide', S.ui.view === 'tutorial');
        c.innerHTML = '';
        if (!ACP.DATA_READY && !(S.ui.view === 'chapter' && S.ui.filter === 'foundation')) {
            ACP.setCrumb('题库加载失败', '请检查 quiz_categorized.js');
            c.innerHTML = `
      <div class="empty-state">
        <div class="icon">⚠</div>
        <h3>题库数据没有成功加载</h3>
        <p>请确认 <code>quiz_categorized.js</code> 存在，且文件内容完整可用。</p>
      </div>`;
            document.getElementById('content').scrollTop = 0;
            return;
        }
        if (S.ui.view === 'dashboard') ACP.renderDashboard(c);
        else if (S.ui.view === 'study') ACP.renderStudy(c);
        else if (S.ui.view === 'tutorial') ACP.renderTutorialView(c);
        else if (S.ui.view === 'chapter') renderChapter(c);
        else if (S.ui.view === 'exam') ACP.renderExam(c);
        else if (S.ui.view === 'wrong') renderGroup(c, 'wrong');
        else if (S.ui.view === 'fav') renderGroup(c, 'fav');
        document.getElementById('content').scrollTop = 0;
        ACP.renderSidebarBadges();
    }

    function buildPool() {
        let base;
        if (S.ui.customTitle && S.ui.pool.length) {
            base = S.ui.pool;
        } else {
            base = (ACP.BY_CH[S.ui.ch] || []).slice();
        }
        let pool = base;
        if (S.ui.filter === 'undone') pool = base.filter(q => !ACP.isDone(q.id));
        else if (S.ui.filter === 'wrong') pool = base.filter(q => ACP.isWrong(q.id));
        else if (S.ui.filter === 'fav') pool = base.filter(q => ACP.isFav(q.id));
        if (S.ui.shuffle) pool = ACP.shuffle(pool.slice());
        else pool = pool.slice().sort(ACP.compareQuestionsByDifficulty);
        return pool;
    }

    /* 定位"连续作答段"末尾：从第 1 题起连续做过的最后一道题。
       跳题查看/作答过的题（如第 90 题）不打断也不作为续做位置。 */
    function findResumeIdx(pool) {
        let pos = -1;
        for (let i = 0; i < pool.length; i++) {
            const p = ACP.prog(pool[i].id);
            if (p && p.d > 0) pos = i;
            else break;
        }
        return pos;
    }

    /* 当前题目：优先会话记录，其次持久化的作答快照（a=选项, c=对错） */
    function questionPrev(q) {
        let prev = S.session[q.id];
        if (!prev) {
            const p = ACP.prog(q.id);
            if (p && p.a && p.a.length && (!q.revisedAt || (p.t || 0) >= q.revisedAt)) {
                prev = { sel: p.a, correct: p.c === 1 };
            }
        }
        return prev;
    }

    function revisionNotice(q) {
        const p = ACP.prog(q.id);
        return q.revisedAt && p && p.d > 0 && (p.t || 0) < q.revisedAt
            ? '<span class="tag">题目已修订 · 请重新作答</span>' : '';
    }

    function renderChapter(root) {
        if (S.ui.filter === 'foundation' && ACP.renderFoundation) { ACP.renderFoundation(root); return; }
        const title = S.ui.customTitle || (S.ui.ch ? `${S.ui.ch} · ${ACP.chapterName(S.ui.ch)}` : '练习');
        S.ui.pool = buildPool();
        if (S.ui.idx >= S.ui.pool.length) S.ui.idx = 0;

        // 进入章节时自动定位到连续作答段末尾（保留刷题进度）；无作答记录则从第 1 题开始
        if (S.ui.autoPos && !S.ui.customTitle && S.ui.filter === 'all') {
            S.ui.autoPos = false;
            const idx = findResumeIdx(S.ui.pool);
            S.ui.idx = idx >= 0 ? idx : 0;
        }

        ACP.setCrumb(title, `${S.ui.pool.length} 题`);

        const filterChips = [
            ['foundation', '基础学习'], ['all', '全部'], ['undone', '未答'], ['wrong', '错题'], ['fav', '收藏']
        ].map(([k, label]) =>
            `<button class="chip ${S.ui.filter === k ? 'active' : ''}" onclick="ACP.setFilter('${k}')">${label}</button>`
        ).join('');

        root.innerHTML = `
    <header class="page-intro"><span class="eyebrow">CHAPTER PRACTICE</span><h1>${ACP.esc(title)}</h1><p>${S.ui.filter === 'foundation' ? '按知识点重新理解基础 · 先作答，再解释原因。基础初选，共 ' : '专注这一题，把知识再巩固一点。共 '}${S.ui.pool.length} 题</p></header>
    <div class="quiz-toolbar">
      ${filterChips}
      <span class="spacer"></span>
      <button class="chip ${S.ui.shuffle ? 'active' : ''}" onclick="ACP.toggleShuffle()" title="随机顺序">${ACP.icon ? ACP.icon('shuffle') : '↝'} 随机</button>
      <button class="chip" onclick="ACP.toggleMode()" title="切换单题/列表">${S.ui.mode === 'single' ? '☰ 列表' : '☝ 单题'}</button>
    </div>
    <div id="quizArea"></div>`;

        if (S.ui.pool.length === 0) {
            document.getElementById('quizArea').innerHTML = `
      <div class="empty-state">
        <div class="icon">🎉</div>
        <h3>当前筛选下没有题目</h3>
        <p>切换筛选条件或选择其他章节</p>
      </div>`;
            return;
        }

        if (S.ui.mode === 'single') renderSingle();
        else renderList();
    }

    function setFilter(f) { S.ui.filter = f; S.ui.idx = 0; if (f === 'foundation') { S.ui.mode = 'single'; S.ui.shuffle = false; } renderChapter(document.getElementById('contentInner')); }
    function toggleShuffle() { S.ui.shuffle = !S.ui.shuffle; S.ui.idx = 0; renderChapter(document.getElementById('contentInner')); }
    function toggleMode() {
        if (S.ui.filter === 'foundation') { ACP.toast('基础学习按知识点逐题进行'); return; }
        S.ui.mode = S.ui.mode === 'single' ? 'list' : 'single';
        renderChapter(document.getElementById('contentInner'));
    }

    /* ---------- single-question mode ---------- */

    function renderSingle() {
        const area = document.getElementById('quizArea');
        const q = S.ui.pool[S.ui.idx];
        const prev = questionPrev(q);
        S.sel = new Set(prev ? prev.sel : []);
        S.judged = !!prev;

        ACP.state.store.last = { ch: q.ch, id: q.id, t: Date.now() };
        ACP.saveStore();
        if (ACP.sync) ACP.sync.pushLast();

        area.innerHTML = `
    <div class="progress-line">
      <div class="progress-track"><i style="width:${((S.ui.idx + 1) / S.ui.pool.length) * 100}%"></i></div>
      <span class="progress-label">${S.ui.idx + 1} / ${S.ui.pool.length}</span>
    </div>
    <div class="card q-card practice-card">
      <div class="q-head">
        <span class="q-index">第 ${S.ui.idx + 1} 题</span>
        <span class="tag ${q.multi ? 'tag-multi' : 'tag-single'}">${q.multi ? '多选' : '单选'}</span>
        <span class="tag">${q.difficultyLabel}</span>
        ${revisionNotice(q)}
        <span class="q-index" style="font-weight:400">#${q.ch}-${q.seq}</span>
        <span class="spacer"></span>
        <button class="fav-btn ${ACP.isFav(q.id) ? 'active' : ''}" id="favBtn" onclick="ACP.onFav()" title="收藏">${ACP.isFav(q.id) ? '已收藏' : '收藏'}</button>
      </div>
      <div class="q-stem">${ACP.esc(q.stem)}</div>
      <div class="options" id="optList">
        ${q.options.map(o => optHTML(q, o, prev)).join('')}
      </div>
      <div class="analysis-box ${prev ? (prev.correct ? 'ok' : 'err') : ''} ${prev ? 'show' : ''}" id="analysisBox">
        ${prev ? ACP.analysisHTML(q, prev.correct) : ''}
      </div>
      <div class="q-actions">
        <button class="btn" onclick="ACP.navQ(-1)" ${S.ui.idx === 0 ? 'disabled' : ''}>← 上一题</button>
        ${!S.judged ? `<button class="btn btn-primary" id="submitBtn" onclick="ACP.judge()">✓ 提交</button>` : ''}
        ${!S.judged ? `<button class="btn" onclick="ACP.navQ(1)" ${S.ui.idx === S.ui.pool.length - 1 ? 'disabled' : ''}>下一题 →</button>` : ''}
        ${S.judged ? `<button class="btn btn-sm" onclick="ACP.retry()" title="重新作答本题">↺ 重做</button>` : ''}
        ${S.judged ? `<button class="btn btn-primary" onclick="ACP.navQ(1)">${S.ui.idx === S.ui.pool.length - 1 ? '完成 ✓' : '下一题 →'}</button>` : ''}
        ${S.judged && ACP.isWrong(q.id) ? `<button class="btn btn-danger-ghost btn-sm" onclick="ACP.onRemoveWrong()">✕ 移出错题</button>` : ''}
        <span class="spacer"></span>
        <span class="kbd-hint"><kbd>A</kbd>-<kbd>${String.fromCharCode(64 + Math.min(q.options.length, 7))}</kbd> 选择 · <kbd>Enter</kbd> 提交 · <kbd>←</kbd><kbd>→</kbd> 翻题</span>
      </div>
    </div>`;
    }

    function optHTML(q, o, prev) {
        let cls = '';
        if (prev) {
            const picked = prev.sel.includes(o.label);
            const isAns = q.ansArr.includes(o.label);
            if (picked && isAns) cls = 'correct';
            else if (picked && !isAns) cls = 'wrong';
            else if (!picked && isAns) cls = 'miss';
        } else if (S.sel.has(o.label)) {
            cls = 'selected';
        }
        return `
    <button class="opt ${cls} ${prev ? 'disabled' : ''}" data-label="${o.label}" onclick="ACP.onOpt('${o.label}')">
      <span class="opt-label">${o.label}</span>
      <span class="opt-text">${ACP.esc(o.text)}</span>
    </button>`;
    }

    function onOpt(label) {
        if (S.judged) return;
        const q = S.ui.pool[S.ui.idx];
        if (q.multi) {
            S.sel.has(label) ? S.sel.delete(label) : S.sel.add(label);
            const btn = document.querySelector(`.opt[data-label="${label}"]`);
            btn.classList.toggle('selected', S.sel.has(label));
        } else {
            S.sel = new Set([label]);
            document.querySelectorAll('.opt[data-label]').forEach(b => {
                b.classList.toggle('selected', b.dataset.label === label);
            });
        }
    }

    function judge() {
        if (S.judged) return;
        const q = S.ui.pool[S.ui.idx];
        if (S.sel.size === 0) { ACP.toast('请先选择答案'); return; }
        const userAns = [...S.sel].sort().join(',');
        const correct = userAns === q.ansArr.slice().sort().join(',');
        S.judged = true;
        S.session[q.id] = { sel: [...S.sel], correct };
        ACP.markResult(q, correct, [...S.sel]);
        renderSingle();
    }

    function retry() {
        const q = S.ui.pool[S.ui.idx];
        if (q) {
            delete S.session[q.id];
            ACP.clearAnswer(q.id); // 清除持久化作答快照，题目恢复未作答状态
            if (ACP.clearAICache) ACP.clearAICache(q.id); // 重做时清掉该题的 AI 解析缓存
        }
        S.judged = false;
        S.sel = new Set();
        renderSingle();
    }

    function navQ(d) {
        const n = S.ui.idx + d;
        if (n < 0 || n >= S.ui.pool.length) {
            if (d > 0) ACP.toast('已经是最后一题 🎉');
            return;
        }
        S.ui.idx = n;
        renderSingle();
    }

    function onFav() {
        const q = S.ui.pool[S.ui.idx];
        ACP.toggleFav(q.id);
        const btn = document.getElementById('favBtn');
        if (btn) { const f = ACP.isFav(q.id); btn.textContent = f ? '已收藏' : '收藏'; btn.classList.toggle('active', f); }
        ACP.renderSidebarBadges();
    }

    function onRemoveWrong() {
        const q = S.ui.pool[S.ui.idx];
        ACP.clearWrong(q.id);
        ACP.toast('已移出错题本');
        if (S.ui.filter === 'wrong') {
            S.ui.pool = S.ui.pool.filter(x => x.id !== q.id);
            if (S.ui.pool.length === 0) { renderChapter(document.getElementById('contentInner')); return; }
            if (S.ui.idx >= S.ui.pool.length) S.ui.idx = S.ui.pool.length - 1;
        }
        renderSingle();
        ACP.renderSidebarBadges();
    }

    /* ---------- list mode ---------- */

    function renderList() {
        const area = document.getElementById('quizArea');
        S.listJudged = {};
        area.innerHTML = S.ui.pool.map((q, i) => {
            const prev = questionPrev(q);
            if (prev) S.listJudged[i] = true;
            return `
    <div class="card list-card" id="lc-${i}">
      <div class="list-head">
        <span class="list-idx">#${i + 1}</span>
        <span class="tag ${q.multi ? 'tag-multi' : 'tag-single'}">${q.multi ? '多选' : '单选'}</span>
        <span class="tag">${q.difficultyLabel}</span>
        ${revisionNotice(q) || (ACP.isDone(q.id) ? `<span class="tag ${ACP.isWrong(q.id) ? 'tag-err' : 'tag-ok'}">${ACP.isWrong(q.id) ? '曾答错' : '已答对'}</span>` : '')}
      </div>
      <div class="q-stem">${ACP.esc(q.stem)}</div>
      <div class="options">
        ${q.options.map(o => listOptHTML(q, i, o, prev)).join('')}
      </div>
      <button class="btn btn-primary btn-sm mini-submit" id="lsub-${i}" onclick="ACP.judgeList(${i})" ${prev ? 'style="display:none;"' : ''}>✓ 提交</button>
      <div class="analysis-box ${prev ? 'show ' + (prev.correct ? 'ok' : 'err') : ''}" id="lana-${i}">${prev ? ACP.analysisHTML(q, prev.correct) : ''}</div>
    </div>`;
        }).join('');
    }

    function listOptHTML(q, i, o, prev) {
        let cls = '';
        if (prev) {
            const picked = prev.sel.includes(o.label);
            const isAns = q.ansArr.includes(o.label);
            if (picked && isAns) cls = 'correct';
            else if (picked && !isAns) cls = 'wrong';
            else if (!picked && isAns) cls = 'miss';
        }
        return `<button class="opt ${cls} ${prev ? 'disabled' : ''}" data-q="${i}" data-label="${o.label}" onclick="ACP.onListOpt(${i},'${o.label}')">
    <span class="opt-label">${o.label}</span>
    <span class="opt-text">${ACP.esc(o.text)}</span>
  </button>`;
    }

    function onListOpt(i, label) {
        if (S.listJudged[i]) return;
        const q = S.ui.pool[i];
        const btn = document.querySelector(`.opt[data-q="${i}"][data-label="${label}"]`);
        if (q.multi) {
            btn.classList.toggle('selected');
        } else {
            document.querySelectorAll(`.opt[data-q="${i}"]`).forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
        }
    }

    function judgeList(i) {
        if (S.listJudged[i]) return;
        const q = S.ui.pool[i];
        const picked = [...document.querySelectorAll(`.opt[data-q="${i}"].selected`)].map(b => b.dataset.label);
        if (picked.length === 0) { ACP.toast('请先选择答案'); return; }
        const correct = picked.sort().join(',') === q.ansArr.slice().sort().join(',');
        S.listJudged[i] = true;
        S.session[q.id] = { sel: picked.slice(), correct };
        ACP.markResult(q, correct, picked);

        const ansSet = q.ansArr;
        document.querySelectorAll(`.opt[data-q="${i}"]`).forEach(b => {
            const l = b.dataset.label;
            const wasPicked = picked.includes(l);
            b.classList.remove('selected');
            b.classList.add('disabled');
            if (wasPicked && ansSet.includes(l)) b.classList.add('correct');
            else if (wasPicked && !ansSet.includes(l)) b.classList.add('wrong');
            else if (!wasPicked && ansSet.includes(l)) b.classList.add('miss');
        });
        const box = document.getElementById('lana-' + i);
        box.className = 'analysis-box show ' + (correct ? 'ok' : 'err');
        box.innerHTML = ACP.analysisHTML(q, correct);
        const sub = document.getElementById('lsub-' + i);
        if (sub) sub.style.display = 'none';
        ACP.renderSidebarBadges();
    }

    /* ---------- wrong / fav group views ---------- */

    function renderGroup(root, kind) {
        const wrongView = kind === 'wrong';
        ACP.setCrumb(wrongView ? '错题本' : '收藏夹', wrongView ? '按章节分组 · 逐个击破' : '你标记的重点题目');
        const pick = q => wrongView ? ACP.isWrong(q.id) : ACP.isFav(q.id);
        const groups = ACP.CH_IDS.map(ch => ({ ch, qs: (ACP.BY_CH[ch] || []).filter(pick) })).filter(g => g.qs.length > 0);
        const total = groups.reduce((s, g) => s + g.qs.length, 0);

        const heading = `<header class="page-intro collection-intro"><div><span class="eyebrow">${wrongView ? 'REVIEW & GROW' : 'YOUR COLLECTION'}</span><h1>${wrongView ? '错题回顾' : '我的收藏'}</h1><p>${wrongView ? '把容易混淆的知识，再理清一次。' : '把值得反复看的题，留在这里。'}</p></div><span class="collection-count">${total}<small> 道题目</small></span></header>`;
        if (total === 0) {
            root.innerHTML = heading + `<div class="empty-state collection-empty">
              <div class="empty-icon">${ACP.icon ? ACP.icon(wrongView ? 'review' : 'star') : '◇'}</div>
              <h2>${wrongView ? '暂时没有需要回顾的错题' : '遇到好题，随手收藏'}</h2>
              <p>${wrongView ? '练习中答错的题目，会自动收录在这里。' : '点击题目右上角的“收藏”，就能在这里集中复习。'}</p>
              <button class="btn btn-primary" onclick="ACP.openChapter(ACP.CH_IDS[0])">去练习几题 →</button>
            </div>`;
            return;
        }
        root.innerHTML = heading + `
          <div class="collection-toolbar"><span>按章节整理 · 共 ${groups.length} 个章节</span><button class="btn btn-primary" onclick="ACP.startGroupPractice('${kind}')">全部重练 →</button></div>
          <div class="collection-grid">${groups.map(g => `
            <button class="collection-card" onclick="ACP.startChapterFilter('${g.ch}','${kind}')">
              <span class="collection-number">${String(g.ch).padStart(2, '0')}</span>
              <span class="collection-main"><b>${ACP.esc(ACP.chapterName(g.ch))}</b><small>${g.qs.length} 道${wrongView ? '错题，值得再看一次' : '收藏题目'}</small></span>
              <span class="collection-arrow">${ACP.icon ? ACP.icon('arrow') : '→'}</span>
            </button>`).join('')}</div>`;
    }

    function startChapterFilter(ch, kind) {
        resetPracticeSession();
        S.ui.customTitle = null;
        go('chapter', { ch, filter: kind === 'wrong' ? 'wrong' : 'fav' });
    }

    function startGroupPractice(kind) {
        const wrongView = kind === 'wrong';
        const pool = ACP.shuffle(ACP.BANK.filter(q => wrongView ? ACP.isWrong(q.id) : ACP.isFav(q.id)));
        if (pool.length === 0) return;
        resetPracticeSession();
        S.ui.ch = null; S.ui.filter = 'all'; S.ui.idx = 0; S.ui.shuffle = false;
        go('chapter', { pool, title: wrongView ? '错题重练（全部）' : '收藏重练（全部）', idx: 0 });
    }

    ACP.resetPracticeSession = resetPracticeSession;
    ACP.go = go;
    ACP.render = render;
    ACP.renderChapter = renderChapter;
    ACP.setFilter = setFilter;
    ACP.toggleShuffle = toggleShuffle;
    ACP.toggleMode = toggleMode;
    ACP.onOpt = onOpt;
    ACP.judge = judge;
    ACP.retry = retry;
    ACP.findResumeIdx = findResumeIdx;
    ACP.questionPrev = questionPrev;
    ACP.navQ = navQ;
    ACP.onFav = onFav;
    ACP.onRemoveWrong = onRemoveWrong;
    ACP.onListOpt = onListOpt;
    ACP.judgeList = judgeList;
    ACP.renderGroup = renderGroup;
    ACP.startChapterFilter = startChapterFilter;
    ACP.startGroupPractice = startGroupPractice;

})(window.ACP);
