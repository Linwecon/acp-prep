/* ACP — Learning workspace. All figures use actual local or synced progress. */
(function (ACP) {
    function renderDashboard(root) {
        ACP.setCrumb('学习工作台', '每一步，都离目标更近');
        const g = ACP.globalStats();
        const rows = ACP.CH_IDS.map(ch => ({ ch, ...ACP.chStats(ch) }));
        const priority = rows.filter(r => r.done > 0 && r.acc !== null && r.acc < 80)
            .sort((a, b) => a.acc - b.acc).slice(0, 2).map(r => r.ch);
        const last = ACP.state.store.last;
        const resume = last && ACP.ID_MAP[last.id];
        const exam = (ACP.state.store.exams || [])[0];
        const icon = ACP.icon;
        const circumference = 2 * Math.PI * 46;
        root.innerHTML = `
        <header class="workspace-heading">
          <div><span class="eyebrow">YOUR LEARNING SPACE</span><h1>学习工作台<span class="heading-dot">.</span></h1>
          <p>把零散的知识，变成扎实的掌握。</p></div>
          <span class="workspace-badge">${icon('layers')} ACP 大模型认证</span>
        </header>
        <section class="workspace-hero">
          <div class="continue-card">
            <span class="hero-kicker"><i></i> ${g.done ? '保持节奏，继续向前' : '你的备考之旅，从这里开始'}</span>
            <h2>${resume ? '接着上次的进度，<br>再进一步。' : '让每一次练习，<br>都有所收获。'}</h2>
            <p>${resume ? `${ACP.esc(ACP.chapterName(resume.ch))} · 上次练习 #${ACP.esc(resume.seq)}` : `${ACP.CH_IDS.length} 个知识章节 · ${ACP.TOTAL.toLocaleString()} 道练习题<br>从基础到实战，按自己的节奏前进。`}</p>
            <div class="hero-actions">
              <button class="btn btn-primary" onclick="${resume ? 'ACP.resumeLast()' : `ACP.openChapter('${ACP.CH_IDS[0]}')`}">${resume ? '继续练习' : '开始第一章'} ${icon('arrow')}</button>
              <button class="hero-secondary" onclick="ACP.go('study')">先学知识点 ${icon('book')}</button>
            </div>
            <div class="hero-orbit" aria-hidden="true"><span></span><span></span><span></span></div>
          </div>
          <div class="workspace-progress card">
            <div class="progress-card-label">整体练习进度 <span>${ACP.CH_IDS.length} 章</span></div>
            <div class="ring-wrap"><svg width="108" height="108" viewBox="0 0 108 108" aria-hidden="true">
              <circle cx="54" cy="54" r="46" fill="none" stroke="var(--surface-2)" stroke-width="7"/>
              <circle cx="54" cy="54" r="46" fill="none" stroke="var(--accent)" stroke-width="7" stroke-linecap="round" stroke-dasharray="${g.pct / 100 * circumference} ${circumference}"/>
            </svg><div class="ring-center"><div class="rc-num">${g.pct}<small>%</small></div><div class="rc-lbl">已完成</div></div></div>
            <p><b>${g.done}</b> / ${ACP.TOTAL.toLocaleString()} 题</p>
            <span class="progress-card-note">${rows.filter(r => r.done > 0).length} 个章节已开始 · 循序渐进就很好</span>
          </div>
        </section>
        <div class="stat-grid workspace-stats">
          <div class="stat-tile"><span class="stat-icon">${icon('check')}</span><div class="t-label">已练习题目</div><div class="t-value">${g.done}<small> 题</small></div><div class="t-sub">每一道，都算数</div></div>
          <div class="stat-tile"><span class="stat-icon teal">${icon('target')}</span><div class="t-label">最近作答正确率</div><div class="t-value">${g.acc === null ? '—' : g.acc + '<small>%</small>'}</div><div class="t-sub">按每题最近一次作答统计</div></div>
          <button class="stat-tile" onclick="ACP.go('wrong')"><span class="stat-icon amber">${icon('review')}</span><div class="t-label">待巩固错题</div><div class="t-value">${g.wrong}<small> 题</small></div><div class="t-sub">${g.wrong ? '点击回顾，查漏补缺 →' : '在练习中发现薄弱点'}</div></button>
          <div class="stat-tile"><span class="stat-icon violet">${icon('exam')}</span><div class="t-label">最近模考成绩</div><div class="t-value">${exam ? ACP.esc(exam.score) + '<small> 分</small>' : '—'}</div><div class="t-sub">${exam ? (exam.pass ? '已达到 80 分及格线' : '继续巩固薄弱章节') : '准备好了，就试一场'}</div></div>
        </div>
        <div class="workspace-section-head"><div><span class="eyebrow">FIND YOUR FOCUS</span><h2>换一种方式，继续学</h2></div></div>
        <div class="workspace-shortcuts">
          <button class="shortcut-card" onclick="ACP.go('study')"><span class="shortcut-icon">${icon('book')}</span><div><h3>知识精讲</h3><p>串起考点，理解原理</p></div>${icon('arrow')}</button>
          <button class="shortcut-card" onclick="ACP.go('tutorial')"><span class="shortcut-icon teal">${icon('code')}</span><div><h3>官方实战</h3><p>跟着教程，把知识用起来</p></div>${icon('arrow')}</button>
          <button class="shortcut-card" onclick="ACP.go('exam')"><span class="shortcut-icon amber">${icon('exam')}</span><div><h3>模拟考试</h3><p>75 题 · 120 分钟</p></div>${icon('arrow')}</button>
        </div>
        <div class="workspace-section-head"><div><span class="eyebrow">ONE CHAPTER AT A TIME</span><h2>你的章节地图</h2></div><span class="section-caption">${ACP.CH_IDS.length} 个章节，逐个掌握</span></div>
        <div class="chapter-grid">
          ${rows.map(r => {
              const pct = r.total ? Math.round(r.done / r.total * 100) : 0;
              return `<button class="chapter-card ${priority.includes(r.ch) ? 'needs-review' : ''}" onclick="ACP.openChapter('${r.ch}')">
                <div class="chapter-card-top"><span class="chapter-number">${String(r.ch).padStart(2, '0')}</span><span class="chapter-status">${priority.includes(r.ch) ? '建议巩固' : pct === 100 ? '已完成练习' : r.done ? '学习中' : '等待探索'}</span>${icon('arrow')}</div>
                <h3>${ACP.esc(ACP.chapterName(r.ch))}</h3>
                <div class="chapter-track"><i style="width:${pct}%"></i></div>
                <div class="chapter-card-meta"><span>已练 ${r.done}<em> / ${r.total} 题</em></span><span>${r.acc === null ? '开始练习' : `正确率 ${r.acc}%`}</span></div>
              </button>`;
          }).join('')}
        </div>
        <footer class="workspace-footer"><span class="footer-mark">ACP</span> 学一点，进一步。<span>知识学习 · 实战教程 · 章节练习</span></footer>`;
    }
    function resumeLast() {
        const last = ACP.state.store.last;
        if (!last || !ACP.ID_MAP[last.id]) return;
        ACP.state.ui.mode = 'single';
        ACP.go('chapter', { ch: last.ch, filter: 'all' });
        const i = ACP.state.ui.pool.findIndex(q => q.id === last.id);
        if (i >= 0) { ACP.state.ui.idx = i; ACP.renderChapter(document.getElementById('contentInner')); }
    }
    ACP.renderDashboard = renderDashboard;
    ACP.resumeLast = resumeLast;
})(window.ACP);
