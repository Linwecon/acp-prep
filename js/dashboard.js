/* ============================================================
   ACP — Dashboard view
   ============================================================ */
(function (ACP) {

    function renderDashboard(root) {
        ACP.setCrumb('学习总览', '了解你的整体进度与薄弱章节');
        const g = ACP.globalStats();

        const rows = ACP.CH_IDS.map(ch => ({ ch, ...ACP.chStats(ch) }));
        const priority = rows.filter(r => r.done > 0 && r.acc !== null)
            .sort((a, b) => a.acc - b.acc).slice(0, 2).map(r => r.ch);
        const untouched = rows.filter(r => r.done === 0).map(r => r.ch);

        const R = 46, CIRC = 2 * Math.PI * R;
        const dash = (g.pct / 100) * CIRC;

        root.innerHTML = `
    <div class="stat-grid">
      <div class="stat-tile"><div class="t-label">题库总量</div><div class="t-value">${ACP.TOTAL}<small> 题</small></div><div class="t-sub">${ACP.CH_IDS.length} 个章节</div></div>
      <div class="stat-tile"><div class="t-label">已练习</div><div class="t-value" style="color:var(--accent-text)">${g.done}<small> 题</small></div><div class="t-sub">占题库 ${g.pct}%</div></div>
      <div class="stat-tile"><div class="t-label">最近正确率</div><div class="t-value" style="color:${g.acc === null ? 'var(--text-3)' : g.acc >= 80 ? 'var(--success)' : g.acc >= 60 ? 'var(--warning)' : 'var(--danger)'}">${g.acc === null ? '—' : g.acc + '%'}</div><div class="t-sub">及格线 80 分</div></div>
      <div class="stat-tile"><div class="t-label">待复习错题</div><div class="t-value" style="color:${g.wrong ? 'var(--danger)' : 'var(--text-3)'}">${g.wrong}<small> 题</small></div><div class="t-sub">收藏 ${g.fav} 题</div></div>
    </div>

    <div class="card dash-hero">
      <div class="ring-wrap">
        <svg width="108" height="108">
          <circle cx="54" cy="54" r="${R}" fill="none" stroke="var(--surface-2)" stroke-width="9"/>
          <circle cx="54" cy="54" r="${R}" fill="none" stroke="var(--accent)" stroke-width="9"
                  stroke-linecap="round" stroke-dasharray="${dash} ${CIRC}"/>
        </svg>
        <div class="ring-center"><div class="rc-num">${g.pct}%</div><div class="rc-lbl">完成度</div></div>
      </div>
      <div class="dash-hero-info">
        <h2>${g.done === 0 ? '开始你的第一题吧' : g.acc !== null && g.acc >= 80 ? '状态不错，保持住' : '继续加油'}</h2>
        <p>${untouched.length > 0 ? `还有 ${untouched.length} 个章节未开始` : '全部章节都已覆盖'}${priority.length ? '，建议优先巩固薄弱章节' : ''}</p>
        <div class="hero-actions">
          ${ACP.state.store.last && ACP.ID_MAP[ACP.state.store.last.id] ? `<button class="btn btn-primary" onclick="ACP.resumeLast()">▶ 继续学习</button>` : ''}
          <button class="btn" onclick="ACP.go('exam')">📝 开始模考</button>
          ${g.wrong ? `<button class="btn" onclick="ACP.startGroupPractice('wrong')">✗ 刷错题 (${g.wrong})</button>` : ''}
        </div>
      </div>
    </div>

    <div class="section-title">章节掌握度 <span class="hint">按最近作答正确率着色 · 点击直达刷题</span></div>
    <div class="mastery-list">
      ${rows.map(r => {
        const pct = r.total ? Math.round(r.done / r.total * 100) : 0;
        const accCls = r.acc === null ? 'none' : r.acc >= 80 ? 'good' : r.acc >= 60 ? 'mid' : 'bad';
        const barColor = r.acc === null ? 'var(--accent)' : r.acc >= 80 ? 'var(--success)' : r.acc >= 60 ? 'var(--warning)' : 'var(--danger)';
        return `
        <div class="mastery-row" onclick="ACP.openChapter('${r.ch}')">
          <span class="ch-num">${r.ch}</span>
          <span class="m-name">${ACP.esc(ACP.chapterName(r.ch))}</span>
          <span class="m-bar-wrap">
            <span class="m-bar"><i style="width:${pct}%;background:${barColor}"></i></span>
            <span class="m-num">${r.done}/${r.total}</span>
          </span>
          <span class="m-acc ${accCls}">${r.acc === null ? '—' : r.acc + '%'}</span>
          ${priority.includes(r.ch) ? '<span class="m-priority">优先</span>' : ''}
        </div>`;
      }).join('')}
    </div>`;
    }

    function resumeLast() {
        const last = ACP.state.store.last;
        if (!last || !ACP.ID_MAP[last.id]) return;
        const ch = last.ch;
        ACP.state.ui.mode = 'single';
        ACP.go('chapter', { ch, filter: 'all' });
        const i = ACP.state.ui.pool.findIndex(q => q.id === last.id);
        if (i >= 0) { ACP.state.ui.idx = i; ACP.renderChapter(document.getElementById('contentInner')); }
    }

    ACP.renderDashboard = renderDashboard;
    ACP.resumeLast = resumeLast;

})(window.ACP);