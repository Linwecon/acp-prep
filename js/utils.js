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
      <button class="ai-ask-btn" type="button" onclick="ACP.aiAsk('${q.id}')" title="调用大模型逐项讲解本题">
        <span class="ai-ico">🤖</span> AI 答疑
        <span class="ai-hint">让大模型讲透这道题</span>
      </button>
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

})(window.ACP);