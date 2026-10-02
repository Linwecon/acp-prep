/* ============================================================
   ACP — Storage & progress layer (localStorage)
   ============================================================ */
(function (ACP) {

    function loadStore() {
        let s = null;
        try {
            const raw = localStorage.getItem(ACP.STORE_KEY);
            if (raw) s = JSON.parse(raw);
        } catch (e) {}
        if (!s) {
            s = { v: 2, p: {}, fav: [], last: null };
            migrateLegacy(s);
        }
        // 归一化：保证新字段存在，兼容旧版本数据
        s.p = s.p || {};
        s.fav = s.fav || [];
        s.exams = s.exams || [];
        migrateMovedQids(s);
        return s;
    }

    /* 移章题号迁移：治理移章后旧 `章-seq` 记录按台账映射迁移到新编号。
       只迁移、合并，不清空任何记录；无映射的记录原样保留。幂等。 */
    function migrateMovedQids(s) {
        const map = (typeof window !== 'undefined' && window.ACP_QID_MIGRATION) || null;
        if (!map) return;
        let changed = false;
        Object.keys(s.p).forEach(oldId => {
            const newId = map[oldId];
            if (!newId || newId === oldId) return;
            const oldRec = s.p[oldId];
            if (!ACP.ID_MAP[newId]) return;   // 新题号不存在（数据版本较旧），保留原记录
            const newRec = s.p[newId];
            if (!newRec) {
                s.p[newId] = oldRec;          // 原样迁移，保留全部历史
            } else {
                // 两边都有记录：作答次数/错误次数取较大值，最近作答优先
                const newer = ((oldRec.t || 0) > (newRec.t || 0)) ? oldRec : newRec;
                s.p[newId] = {
                    d: Math.max(oldRec.d || 0, newRec.d || 0),
                    w: Math.max(oldRec.w || 0, newRec.w || 0),
                    c: newer.c || 0,
                    t: Math.max(oldRec.t || 0, newRec.t || 0)
                };
                if (newer.a) s.p[newId].a = newer.a;
            }
            delete s.p[oldId];
            changed = true;
        });
        s.fav = (s.fav || []).map(id => (map[id] && ACP.ID_MAP[map[id]]) ? map[id] : id);
        s.fav = Array.from(new Set(s.fav));
        if (s.last && s.last.id && map[s.last.id] && ACP.ID_MAP[map[s.last.id]]) {
            s.last.id = map[s.last.id];
            const q = ACP.ID_MAP[s.last.id];
            if (q) s.last.ch = q.ch;
            changed = true;
        }
        if (changed) {
            try { localStorage.setItem(ACP.STORE_KEY, JSON.stringify(s)); } catch (e) {}
        }
        return changed;
    }

    function saveStore() {
        localStorage.setItem(ACP.STORE_KEY, JSON.stringify(ACP.state.store));
    }

    function migrateLegacy(s) {
        try {
            const chProg = JSON.parse(localStorage.getItem('acp_chapter_progress') || '{}');
            Object.entries(chProg).forEach(([ch, arr]) => {
                (arr || []).forEach(rec => {
                    const id = ch + '-' + rec.seq;
                    if (ACP.ID_MAP[id] && !s.p[id]) {
                        s.p[id] = { d: 1, w: rec.correct ? 0 : 1, c: rec.correct ? 1 : 0 };
                    }
                });
            });
            const flat = JSON.parse(localStorage.getItem('acp_quiz_progress_glass') || '{}');
            Object.entries(flat).forEach(([key, rec]) => {
                const matches = ACP.BANK.filter(q => q.seq === key);
                if (matches.length === 1) {
                    const id = matches[0].id;
                    if (!s.p[id]) {
                        s.p[id] = { d: rec.done || 1, w: rec.wrong || 0, c: (rec.wrong || 0) > 0 ? 0 : 1 };
                    }
                }
            });
            const favs = JSON.parse(localStorage.getItem('acp_quiz_favorites_glass') || '[]');
            favs.forEach(key => {
                const matches = ACP.BANK.filter(q => q.seq === key);
                if (matches.length === 1 && !s.fav.includes(matches[0].id)) s.fav.push(matches[0].id);
            });
        } catch (e) {}
    }

    function prog(id) { return ACP.state.store.p[id] || null; }
    function isDone(id) { const p = ACP.state.store.p[id]; return p && p.d > 0; }
    function isWrong(id) { const p = ACP.state.store.p[id]; return p && p.w > 0; }
    function isFav(id) { return ACP.state.store.fav.includes(id); }

    function markResult(q, correct) {
        const p = ACP.state.store.p[q.id] || (ACP.state.store.p[q.id] = { d: 0, w: 0, c: 0 });
        p.d++;
        if (!correct) p.w++;
        p.c = correct ? 1 : 0;
        saveStore();
        if (ACP.sync) ACP.sync.pushProgress(q.id);
    }

    /* 保存作答快照（用户选了哪些选项，无论对错）+ 作答时间戳 */
    function saveAnswer(q, sel) {
        const p = ACP.state.store.p[q.id] || (ACP.state.store.p[q.id] = { d: 0, w: 0, c: 0 });
        p.a = (sel || []).slice();
        p.t = Date.now();
        saveStore();
        if (ACP.sync) ACP.sync.pushProgress(q.id);
    }

    /* 清除作答快照（重做时调用）：题目恢复未作答状态，保留 d/w/c 统计 */
    function clearAnswer(id) {
        const p = ACP.state.store.p[id];
        if (p) { delete p.a; delete p.t; saveStore(); }
    }

    function clearWrong(id) {
        if (ACP.state.store.p[id]) {
            ACP.state.store.p[id].w = 0;
            saveStore();
            if (ACP.sync) ACP.sync.pushProgress(id);
        }
    }

    function toggleFav(id) {
        const i = ACP.state.store.fav.indexOf(id);
        if (i >= 0) { ACP.state.store.fav.splice(i, 1); ACP.toast('已取消收藏'); }
        else { ACP.state.store.fav.push(id); ACP.toast('已收藏'); }
        saveStore();
        if (ACP.sync) ACP.sync.pushFav(id, i < 0);
    }

    ACP.loadStore = loadStore;
    ACP.saveStore = saveStore;
    ACP.migrateMovedQids = migrateMovedQids;
    ACP.prog = prog;
    ACP.isDone = isDone;
    ACP.isWrong = isWrong;
    ACP.isFav = isFav;
    ACP.markResult = markResult;
    ACP.saveAnswer = saveAnswer;
    ACP.clearAnswer = clearAnswer;
    ACP.clearWrong = clearWrong;
    ACP.toggleFav = toggleFav;

})(window.ACP);