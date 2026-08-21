/* ============================================================
   ACP — Utility functions
   ============================================================ */
(function (ACP) {

    function esc(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&#62;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function shuffle(arr) {
        for (let i = arr.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
    }

    function toast(msg) {
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.classList.add('show');
        clearTimeout(ACP.state.toastTimer);
        ACP.state.toastTimer = setTimeout(() => t.classList.remove('show'), 1800);
    }

    function setCrumb(title, sub) {
        document.getElementById('crumb').innerHTML =
            esc(title) + (sub ? `<span class="crumb-sub">${esc(sub)}</span>` : '');
    }

    function normAnsArr(ans) {
        if (!ans) return [];
        if (ans.includes(',')) return ans.split(',').map(s => s.trim()).filter(Boolean);
        return ans.split('').filter(c => /[A-G]/.test(c));
    }

    function compareQuestionsByDifficulty(a, b) {
        return (a.difficultySort - b.difficultySort)
            || (a.difficultyScore - b.difficultyScore)
            || (parseInt(a.ch) - parseInt(b.ch))
            || String(a.seq).localeCompare(String(b.seq));
    }

    function chapterName(ch) {
        return ACP.CHAPTERS[ch] || `第 ${ch} 章`;
    }

    function escapeRegExp(text) {
        return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    /* 生成 uuid v4（考试成绩记录等需要合法 uuid 的场景） */
    function uuid() {
        try { if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID(); } catch (e) {}
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    function analysisHTML(q, correct) {
        return `
    <div class="analysis-verdict">
      ${correct ? '✓ 回答正确' : '✗ 回答错误'}
      <span class="verdict-ans">正确答案：${q.ansArr.join(', ')}</span>
    </div>
    ${q.analysis
      ? `<div class="analysis-text"><span class="a-label">解析</span>${esc(q.analysis)}</div>`
      : `<div class="analysis-empty">暂无解析</div>`}
    <div class="ai-wrap" id="ai-${q.id}">
      ${typeof ACP.aiPanelHTML === 'function' ? ACP.aiPanelHTML(q.id) : ''}
    </div>`;
    }

    ACP.esc = esc;
    ACP.shuffle = shuffle;
    ACP.toast = toast;
    ACP.setCrumb = setCrumb;
    ACP.normAnsArr = normAnsArr;
    ACP.compareQuestionsByDifficulty = compareQuestionsByDifficulty;
    ACP.chapterName = chapterName;
    ACP.escapeRegExp = escapeRegExp;
    ACP.analysisHTML = analysisHTML;
    ACP.uuid = uuid;

})(window.ACP);