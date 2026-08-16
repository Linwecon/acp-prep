/* ============================================================
   ACP — Data layer (build bank, stats)
   ============================================================ */
(function (ACP) {

    function buildBank() {
        if (!ACP.DATA_READY) return;
        Object.entries(ACP.CHAPTER_QUESTIONS).forEach(([ch, qs]) => {
            ACP.BY_CH[ch] = [];
            qs.forEach(q => {
                // 兼容完整版与压缩版（quiz_categorized.min.js）键名
                const g = (k1, k2) => (q[k1] !== undefined && q[k1] !== null) ? q[k1] : q[k2];
                const ans = String(g('answer', 'a') || '').replace(/\s/g, '');
                const ansArr = ACP.normAnsArr(ans);
                // 数据源中存在同章同 seq 的撞号题目：id 唯一化，两题都保留
                let id = ch + '-' + g('seq', 's');
                if (ACP.ID_MAP[id]) id += 'b';
                const item = {
                    id,
                    ch,
                    seq: g('seq', 's'),
                    stem: g('stem', 't') || '',
                    options: (g('options', 'o') || []).map(o => ({
                        label: o.option_label !== undefined ? o.option_label : o.l,
                        text: o.option_text !== undefined ? o.option_text : o.x
                    })),
                    answer: ans,
                    ansArr,
                    analysis: g('analysis', 'n') || '',
                    multi: ansArr.length > 1 || q.type === 2 || q.y === 2,
                    difficultyScore: Number(g('difficulty_score', 'ds') || 99),
                    difficultySort: Number(g('difficulty_sort', 'dsrt') || 999),
                    difficultyLabel: g('difficulty_label', 'dl') || '进阶'
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