/* ============================================================
   ACP — Data layer (build bank, stats)
   ============================================================ */
(function (ACP) {

    function buildBank() {
        if (!ACP.DATA_READY) return;
        Object.entries(ACP.CHAPTER_QUESTIONS).forEach(([ch, qs]) => {
            ACP.BY_CH[ch] = [];
            qs.forEach(q => {
                const ans = String(q.answer || '').replace(/\s/g, '');
                const ansArr = ACP.normAnsArr(ans);
                // 数据源中存在同章同 seq 的撞号题目：id 唯一化，两题都保留
                let id = ch + '-' + q.seq;
                if (ACP.ID_MAP[id]) id += 'b';
                const item = {
                    id,
                    ch,
                    seq: q.seq,
                    stem: q.stem || '',
                    options: (q.options || []).map(o => ({ label: o.option_label, text: o.option_text })),
                    answer: ans,
                    ansArr,
                    analysis: q.analysis || '',
                    multi: ansArr.length > 1 || q.type === 2,
                    difficultyScore: Number(q.difficulty_score || 99),
                    difficultySort: Number(q.difficulty_sort || 999),
                    difficultyLabel: q.difficulty_label || '进阶'
                };
                ACP.BANK.push(item);
                ACP.BY_CH[ch].push(item);
                ACP.ID_MAP[item.id] = item;
            });
        });
    }

    function chStats(ch) {
        const qs = ACP.BY_CH[ch] || [];
        let done = 0, correct = 0;
        qs.forEach(q => {
            const p = ACP.prog(q.id);
            if (p && p.d > 0) { done++; if (p.c) correct++; }
        });
        return { total: qs.length, done, correct, acc: done ? Math.round(correct / done * 100) : null };
    }

    function globalStats() {
        let done = 0, correct = 0, wrong = 0;
        ACP.BANK.forEach(q => {
            const p = ACP.prog(q.id);
            if (p && p.d > 0) { done++; if (p.c) correct++; }
            if (p && p.w > 0) wrong++;
        });
        return {
            done, wrong,
            fav: ACP.state.store.fav.length,
            acc: done ? Math.round(correct / done * 100) : null,
            pct: ACP.TOTAL ? Math.round(done / ACP.TOTAL * 100) : 0
        };
    }

    ACP.buildBank = buildBank;
    ACP.chStats = chStats;
    ACP.globalStats = globalStats;

})(window.ACP);