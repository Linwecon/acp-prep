/* ============================================================
   ACP — Sidebar rendering
   ============================================================ */
(function (ACP) {

    function renderSidebar() {
        const sub = document.getElementById('brandSub');
        if (sub) {
            sub.textContent = ACP.DATA_READY
                ? `共 ${ACP.TOTAL} 题 · ${ACP.CH_IDS.length} 章`
                : '题库数据未加载';
        }
        const nav = document.getElementById('chapterNav');
        if (!nav) return;
        nav.innerHTML = ACP.CH_IDS.map(ch => {
            const st = ACP.chStats(ch);
            const pct = st.total ? Math.round(st.done / st.total * 100) : 0;
            return `
      <button class="nav-item ch-item chapter-item-nav" data-ch="${ch}" onclick="ACP.openChapter('${ch}')">
        <span class="ch-num">${ch}</span>
        <span class="ch-body">
          <span class="ch-name">${ACP.esc(ACP.chapterName(ch))}</span>
          <span class="ch-meta">
            <span class="ch-bar"><i class="${pct === 100 ? 'full' : ''}" style="width:${pct}%"></i></span>
            <span class="ch-count">${st.done}/${st.total}</span>
          </span>
        </span>
      </button>`;
        }).join('');
    }

    function renderSidebarBadges() {
        const g = ACP.globalStats();
        const wb = document.getElementById('wrongBadge');
        const fb = document.getElementById('favBadge');
        if (wb) { wb.style.display = g.wrong ? '' : 'none'; wb.textContent = g.wrong; }
        if (fb) { fb.style.display = g.fav ? '' : 'none'; fb.textContent = g.fav; }
        document.querySelectorAll('.chapter-item-nav').forEach(el => {
            const st = ACP.chStats(el.dataset.ch);
            const pct = st.total ? Math.round(st.done / st.total * 100) : 0;
            const bar = el.querySelector('.ch-bar i');
            if (bar) { bar.style.width = pct + '%'; bar.classList.toggle('full', pct === 100); }
            const cnt = el.querySelector('.ch-count');
            if (cnt) cnt.textContent = `${st.done}/${st.total}`;
        });
    }

    function openChapter(ch) {
        ACP.resetPracticeSession();
        ACP.state.ui.ch = ch; ACP.state.ui.filter = 'all'; ACP.state.ui.customTitle = null;
        ACP.state.ui.autoPos = true; // 进入后自动定位到最后一道已作答的题
        ACP.go('chapter', { ch, filter: 'all' });
    }

    function toggleSidebar(force) {
        const sb = document.getElementById('sidebar');
        const ov = document.getElementById('sidebarOverlay');
        if (!sb || !ov) return;
        const open = force !== undefined ? force : !sb.classList.contains('open');
        sb.classList.toggle('open', open);
        ov.classList.toggle('show', open);
    }

    ACP.renderSidebar = renderSidebar;
    ACP.renderSidebarBadges = renderSidebarBadges;
    ACP.openChapter = openChapter;
    ACP.toggleSidebar = toggleSidebar;

})(window.ACP);