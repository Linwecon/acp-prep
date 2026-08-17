/* ============================================================
   ACP — Theme, boot, keyboard
   ============================================================ */
(function (ACP) {
    const S = ACP.state;

    function toggleTheme() {
        const cur = document.documentElement.dataset.theme === 'dark' ? '' : 'dark';
        document.documentElement.dataset.theme = cur;
        localStorage.setItem('acp_v2_theme', cur);
        const label = document.getElementById('themeLabel');
        if (label) label.textContent = cur === 'dark' ? '浅色' : '深色';
    }

    const ACCENT_KEY = 'acp_v2_accent';

    function applyAccent(name, silent) {
        document.body.dataset.accent = name || '';
        try { localStorage.setItem(ACCENT_KEY, name || ''); } catch (e) {}
        document.querySelectorAll('.theme-opt').forEach(el => {
            el.classList.toggle('on', (el.dataset.accent || '') === (name || ''));
        });
        if (!silent) ACP.toast(name ? '配色已切换' : '已恢复默认配色');
    }

    function openThemePicker() {
        applyAccent(localStorage.getItem(ACCENT_KEY) || '', true); // 同步选中态
        const m = document.getElementById('themeModal');
        const o = document.getElementById('themeOverlay');
        if (!m || !o) return;
        m.classList.add('show');
        o.classList.add('show');
        ACP.toggleSidebar(false);
    }

    function closeThemePicker() {
        const m = document.getElementById('themeModal');
        const o = document.getElementById('themeOverlay');
        if (m) m.classList.remove('show');
        if (o) o.classList.remove('show');
    }

    function setAccent(name) { applyAccent(name, false); }

    function resetAllData() {
        if (!confirm('确定清空所有学习记录吗？（进度、错题、收藏都会被清除）')) return;
        localStorage.removeItem(ACP.STORE_KEY);
        localStorage.removeItem('acp_chapter_progress');
        localStorage.removeItem('acp_quiz_progress_glass');
        localStorage.removeItem('acp_quiz_favorites_glass');
        S.store = { v: 2, p: {}, fav: [], last: null };
        ACP.saveStore();
        S.exam = null;
        ACP.toast('已清空全部数据');
        ACP.go('dashboard');
    }

    /* ---------- landing (mode selection) ---------- */
    function enterApp(mode) {
        const landing = document.getElementById('landing');
        if (!landing || landing.classList.contains('hide')) return;
        landing.classList.add('hide');
        ACP.go(mode === 'study' ? 'study' : 'dashboard');
        setTimeout(() => landing.remove(), 460);
    }

    /* ---------- notes modal ---------- */
    function openNotes() {
        const m = document.getElementById('notesModal');
        const o = document.getElementById('notesOverlay');
        if (!m || !o) return;
        m.classList.add('show');
        o.classList.add('show');
        ACP.toggleSidebar(false);
    }

    function closeNotes() {
        const m = document.getElementById('notesModal');
        const o = document.getElementById('notesOverlay');
        if (m) m.classList.remove('show');
        if (o) o.classList.remove('show');
    }

    function copyLink() {
        const url = 'https://linwecon.github.io/acp-prep/';
        const done = () => ACP.toast('链接已复制');
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url).then(done).catch(() => { fallbackCopy(url); done(); });
        } else { fallbackCopy(url); done(); }
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

    /* ---------- keyboard ---------- */
    document.addEventListener('keydown', e => {
        if (e.target.tagName === 'INPUT') return;
        if (e.key === 'Escape') { ACP.closeNotes(); ACP.closeThemePicker(); return; }
        if (S.ui.view === 'chapter' && S.ui.mode === 'single' && S.ui.pool.length) {
            const q = S.ui.pool[S.ui.idx];
            if (e.key === 'ArrowLeft') { ACP.navQ(-1); e.preventDefault(); }
            else if (e.key === 'ArrowRight') { ACP.navQ(1); e.preventDefault(); }
            else if (/^[a-gA-G]$/.test(e.key)) {
                const label = e.key.toUpperCase();
                if (q.options.some(o => o.label === label)) ACP.onOpt(label);
            } else if (e.key === 'Enter') {
                if (!S.judged) ACP.judge();
                else if (S.judged) ACP.navQ(1);
            }
        } else if (S.ui.view === 'exam' && S.exam && (S.exam.state === 'on' || S.exam.state === 'review')) {
            if (e.key === 'ArrowLeft') { ACP.examNav(-1); e.preventDefault(); }
            else if (e.key === 'ArrowRight') { ACP.examNav(1); e.preventDefault(); }
        }
    });

    /* ---------- boot ---------- */
    function boot() {
        ACP.DATA_READY = typeof QUIZ_CHAPTERS !== 'undefined' && typeof QUIZ_DATA_BY_CHAPTER !== 'undefined';
        ACP.CHAPTERS = ACP.DATA_READY ? QUIZ_CHAPTERS : {};
        ACP.CHAPTER_QUESTIONS = ACP.DATA_READY ? QUIZ_DATA_BY_CHAPTER : {};

        ACP.buildBank();

        ACP.CH_IDS = Object.keys(ACP.CHAPTERS).sort((a, b) => parseInt(a) - parseInt(b));
        ACP.TOTAL = ACP.BANK.length;

        S.store = ACP.loadStore();

        ACP.renderSidebar();
        ACP.renderSidebarBadges();

        const themeSaved = localStorage.getItem('acp_v2_theme') || '';
        document.documentElement.dataset.theme = themeSaved;
        const themeLabel = document.getElementById('themeLabel');
        if (themeLabel) themeLabel.textContent = themeSaved === 'dark' ? '浅色' : '深色';

        // 配色主题（body[data-accent]）
        applyAccent(localStorage.getItem(ACCENT_KEY) || '', true);

        // landing: fill dynamic quiz stats
        const quizDesc = document.getElementById('lcQuizDesc');
        if (quizDesc && ACP.TOTAL) {
            quizDesc.innerHTML = `${ACP.TOTAL} 题章节练习 · 模拟考试<br>错题本 · 收藏夹`;
        }

        // deep link: #study / #quiz / #exam (可带参数如 #study?ch=0) 跳过落地页
        const hash = location.hash;
        if (hash.startsWith('#study') || hash.startsWith('#quiz') || hash.startsWith('#exam')) {
            const landing = document.getElementById('landing');
            if (landing) landing.remove();
            ACP.go(hash.startsWith('#study') ? 'study' : (hash.startsWith('#exam') ? 'exam' : 'dashboard'));
            return;
        }

        ACP.go('dashboard');
    }

    ACP.toggleTheme = toggleTheme;
    ACP.applyAccent = applyAccent;
    ACP.openThemePicker = openThemePicker;
    ACP.closeThemePicker = closeThemePicker;
    ACP.setAccent = setAccent;
    ACP.resetAllData = resetAllData;
    ACP.enterApp = enterApp;
    ACP.openNotes = openNotes;
    ACP.closeNotes = closeNotes;
    ACP.copyLink = copyLink;
    ACP.boot = boot;

})(window.ACP);

ACP.boot();