/* ============================================================
   ACP — Search
   ============================================================ */
(function (ACP) {
    const S = ACP.state;

    const searchInput = document.getElementById('searchInput');
    const searchResults = document.getElementById('searchResults');

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(S.searchTimer);
            S.searchTimer = setTimeout(runSearch, 200);
        });
        searchInput.addEventListener('keydown', e => {
            if (e.key === 'Escape') closeSearch();
            if (e.key === 'Enter' && S.searchHits.length) {
                e.preventDefault();
                jumpToQuestion(S.searchHits[0].id);
            }
        });
    }

    document.addEventListener('click', e => {
        if (!e.target.closest('.search-wrap')) closeSearch();
    });

    if (searchResults) {
        searchResults.addEventListener('click', e => {
            const item = e.target.closest('[data-jump-id]');
            if (!item) return;
            jumpToQuestion(item.dataset.jumpId);
        });
    }

    function runSearch() {
        const kw = searchInput.value.trim();
        if (kw.length < 2) { S.searchHits = []; closeSearch(); return; }
        const kwLower = kw.toLowerCase();
        const hits = ACP.BANK.filter(q => (q.stem || '').toLowerCase().includes(kwLower)).slice(0, 15);
        S.searchHits = hits;
        if (hits.length === 0) {
            searchResults.innerHTML = `<div class="sr-empty">没有找到相关题目</div>`;
        } else {
            searchResults.innerHTML = hits.map(q => `
        <button class="sr-item" type="button" data-jump-id="${q.id}" title="点击跳转到这道题">
          <span class="sr-ch">${q.ch}章</span>
          <span class="sr-stem">${highlightStem(q.stem, kw)}</span>
        </button>`).join('');
        }
        searchResults.classList.add('show');
    }

    function closeSearch() { if (searchResults) searchResults.classList.remove('show'); }

    function highlightStem(text, kw) {
        if (!kw) return ACP.esc(text);
        const pattern = new RegExp(`(${ACP.escapeRegExp(kw)})`, 'ig');
        return ACP.esc(text).replace(pattern, '<mark class="sr-mark">$1</mark>');
    }

    function jumpToQuestion(id) {
        const q = ACP.ID_MAP[id];
        if (!q) return;
        ACP.state.ui.mode = 'single'; ACP.state.ui.filter = 'all'; ACP.state.ui.shuffle = false; ACP.state.ui.customTitle = null;
        ACP.go('chapter', { ch: q.ch, filter: 'all' });
        const i = ACP.state.ui.pool.findIndex(x => x.id === id);
        if (i >= 0) { ACP.state.ui.idx = i; ACP.renderChapter(document.getElementById('contentInner')); }
        closeSearch();
        if (searchInput) searchInput.blur();
    }

    ACP.closeSearch = closeSearch;
    ACP.jumpToQuestion = jumpToQuestion;

})(window.ACP);