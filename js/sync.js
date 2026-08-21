/* ============================================================
   ACP — 登录 + 云端同步（Supabase）
   - 未配置 / 未登录时完全不影响本地 localStorage 逻辑
   - 登录后：拉取云端 → 合并 → 回推，之后每次数据变更实时推送
   - 只使用公开 anon key，绝不使用 service_role key
   ============================================================ */
(function (ACP) {
    const S = ACP.state;

    const CFG = (typeof window !== 'undefined' && window.SUPABASE_CONFIG) ? window.SUPABASE_CONFIG : null;
    const configured = !!(CFG && CFG.url && CFG.anonKey &&
        !/YOUR-/.test(CFG.url) && !/YOUR-/.test(CFG.anonKey));

    let supabase = null;
    let uid = null;          // 当前登录用户 id
    let syncReady = false;   // 是否已完成首次云端合并

    if (configured && typeof window !== 'undefined' && window.supabase && window.supabase.createClient) {
        supabase = window.supabase.createClient(CFG.url, CFG.anonKey, {
            auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
        });
    }

    function isConfigured() { return configured && !!supabase; }
    function isSignedIn() { return !!uid; }

    function esc(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function uidFromSession(session) { return session && session.user ? session.user.id : null; }

    /* ---------- 合并规则（本地字段 ↔ 云端字段） ----------
       进度合并：done/wrong 取两者较大值（不丢失累计次数）；
       correct/answer 取"最近一次作答"（answered_at 较新者）。
       收藏合并：取并集（删除类操作依赖实时同步，见 README 说明）。
    */
    function mergeProgress(local, cloud) {
        const cloudT = cloud.answered_at ? new Date(cloud.answered_at).getTime() : 0;
        const localT = (local && local.t) || 0;
        const cloudNewer = cloudT > localT;

        const merged = {
            d: Math.max((local && local.d) || 0, cloud.done || 0),
            w: Math.max((local && local.w) || 0, cloud.wrong || 0),
            c: cloudNewer ? (cloud.correct ? 1 : 0) : ((local && local.c) || 0),
            t: Math.max(localT, cloudT)
        };
        const ans = cloudNewer ? cloud.answer : (local && local.a);
        if (ans && ans.length) merged.a = ans;
        return merged;
    }

    function toProgressRow(qid, p) {
        return {
            user_id: uid,
            question_id: qid,
            done: p.d || 0,
            wrong: p.w || 0,
            correct: p.c ? 1 : 0,
            answer: (p.a && p.a.length) ? p.a : null,
            answered_at: p.t ? new Date(p.t).toISOString() : null,
            updated_at: new Date().toISOString()
        };
    }

    function genId() {
        if (ACP.uuid) return ACP.uuid();
        try { if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID(); } catch (e) {}
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    /* ---------- 拉取云端 → 合并到本地 ---------- */
    async function pullAndMerge() {
        if (!isConfigured() || !uid) return;
        const store = S.store;
        store.p = store.p || {};
        store.fav = store.fav || [];
        store.exams = store.exams || [];

        const [progR, favR, metaR, examR] = await Promise.all([
            supabase.from('user_progress').select('*').eq('user_id', uid),
            supabase.from('favorites').select('question_id').eq('user_id', uid),
            supabase.from('user_meta').select('*').eq('user_id', uid),
            supabase.from('exam_records').select('*').eq('user_id', uid).order('created_at', { ascending: false }).limit(100)
        ]);

        (progR.data || []).forEach(r => {
            store.p[r.question_id] = mergeProgress(store.p[r.question_id], r);
        });

        (favR.data || []).forEach(r => {
            if (!store.fav.includes(r.question_id)) store.fav.push(r.question_id);
        });

        const lastRow = (metaR.data || []).find(r => r.key === 'last');
        if (lastRow && lastRow.value && typeof lastRow.value === 'object') {
            const cloudT = lastRow.value.t || 0;
            const localT = (store.last && store.last.t) || 0;
            if (cloudT > localT) store.last = lastRow.value;
        }

        const ids = new Set(store.exams.map(e => e.id));
        (examR.data || []).forEach(r => {
            if (!ids.has(r.id)) { store.exams.push(r); ids.add(r.id); }
        });
        store.exams.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        store.exams = store.exams.slice(0, 100);

        ACP.saveStore();
        syncReady = true;
    }

    /* ---------- 回推（全量）：把合并后的本地数据写回云端，使两端一致 ---------- */
    async function pushAll() {
        if (!isConfigured() || !uid) return;
        const store = S.store;
        store.p = store.p || {};
        store.fav = store.fav || [];
        store.exams = store.exams || [];

        const progRows = Object.entries(store.p).map(([qid, p]) => toProgressRow(qid, p));
        if (progRows.length) {
            await supabase.from('user_progress').upsert(progRows, { onConflict: 'user_id,question_id' });
        }
        if (store.fav.length) {
            const favRows = store.fav.map(qid => ({ user_id: uid, question_id: qid }));
            await supabase.from('favorites').upsert(favRows, { onConflict: 'user_id,question_id' });
        }
        if (store.last) {
            await supabase.from('user_meta').upsert(
                { user_id: uid, key: 'last', value: store.last, updated_at: new Date().toISOString() },
                { onConflict: 'user_id,key' }
            );
        }
        const examRows = store.exams.map(e => ({
            id: e.id, user_id: uid, score: e.score, correct: e.correct, wrong: e.wrong,
            pass: e.pass, time_used: e.time_used, weak_by_ch: e.weak_by_ch || null,
            created_at: e.created_at || new Date().toISOString()
        }));
        if (examRows.length) {
            await supabase.from('exam_records').upsert(examRows, { onConflict: 'id' });
        }
    }

    /* ---------- 单条实时推送 ---------- */
    async function pushProgress(qid) {
        if (!isConfigured() || !uid || !syncReady) return;
        const p = S.store.p && S.store.p[qid];
        if (!p) return;
        const { error } = await supabase.from('user_progress').upsert(toProgressRow(qid, p), { onConflict: 'user_id,question_id' });
        if (error) console.warn('[sync] pushProgress failed', error.message);
    }

    async function pushFav(qid, added) {
        if (!isConfigured() || !uid || !syncReady) return;
        if (added) {
            await supabase.from('favorites').upsert({ user_id: uid, question_id: qid }, { onConflict: 'user_id,question_id' });
        } else {
            await supabase.from('favorites').delete().eq('user_id', uid).eq('question_id', qid);
        }
    }

    async function pushExam(record) {
        if (!isConfigured() || !uid || !syncReady) return;
        await supabase.from('exam_records').upsert({
            id: record.id, user_id: uid, score: record.score, correct: record.correct,
            wrong: record.wrong, pass: record.pass, time_used: record.time_used,
            weak_by_ch: record.weak_by_ch || null, created_at: record.created_at
        }, { onConflict: 'id' });
    }

    async function pushLast() {
        if (!isConfigured() || !uid || !syncReady) return;
        if (!S.store.last) return;
        await supabase.from('user_meta').upsert(
            { user_id: uid, key: 'last', value: S.store.last, updated_at: new Date().toISOString() },
            { onConflict: 'user_id,key' }
        );
    }

    async function clearCloud() {
        if (!isConfigured() || !uid) return;
        await Promise.all([
            supabase.from('user_progress').delete().eq('user_id', uid),
            supabase.from('favorites').delete().eq('user_id', uid),
            supabase.from('exam_records').delete().eq('user_id', uid),
            supabase.from('user_meta').delete().eq('user_id', uid)
        ]);
    }

    /* ---------- 认证 ---------- */
    async function signInGoogle() {
        if (!isConfigured()) { ACP.toast('未配置 Supabase'); return; }
        const { error } = await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: { redirectTo: location.origin + location.pathname }
        });
        if (error) ACP.toast('Google 登录失败：' + error.message);
    }

    async function sendEmailOtp(email) {
        if (!isConfigured()) { ACP.toast('未配置 Supabase'); return; }
        const { error } = await supabase.auth.signInWithOtp({
            email,
            options: { shouldCreateUser: true }
        });
        const hint = document.getElementById('authOtpHint');
        if (error) {
            if (hint) hint.innerHTML = '❌ ' + esc(error.message);
            hint.className = 'auth-msg err';
        } else {
            if (hint) hint.innerHTML = '✓ 已发送，请查收邮箱（邮件里的链接可直接登录；若收到 6 位验证码，在下方输入）';
            hint.className = 'auth-msg ok';
            const box = document.getElementById('authOtpBox');
            if (box) box.style.display = 'block';
        }
    }

    async function verifyEmailOtp(email, token) {
        if (!isConfigured()) { ACP.toast('未配置 Supabase'); return; }
        const { error } = await supabase.auth.verifyOtp({ email, token, type: 'email' });
        const hint = document.getElementById('authOtpHint');
        if (error) {
            if (hint) hint.innerHTML = '❌ 验证失败：' + esc(error.message);
            hint.className = 'auth-msg err';
        }
    }

    async function signOut() {
        if (!isConfigured()) return;
        await supabase.auth.signOut();
        uid = null;
        syncReady = false;
        ACP.toast('已退出登录，数据仍保存在本地');
        renderAuthButton();
    }

    /* ---------- 登录 UI ---------- */
    function renderAuthButton() {
        const area = document.getElementById('authArea');
        if (!area) return;
        if (!isConfigured()) {
            area.innerHTML = '';
            return;
        }
        if (uid) {
            // 已登录：头像（邮箱首字母）+ 邮箱 + 退出
            area.innerHTML = `
          <span class="auth-user" id="authUser" title="已登录">…</span>
          <button class="auth-btn" onclick="ACP.sync.signOut()" title="退出登录">退出</button>`;
            renderAuthUser();
        } else {
            area.innerHTML = `<button class="auth-btn auth-btn-primary" onclick="ACP.sync.openAuth()">登录</button>`;
        }
    }

    function renderAuthUser() {
        const el = document.getElementById('authUser');
        if (!el) return;
        // 用 getSession 读邮箱，兼容旧版本 API
        Promise.resolve(supabase.auth.getUser())
            .then(({ data }) => {
                const u = data && data.user;
                const email = (u && u.email) || '';
                const initial = email ? email[0].toUpperCase() : '👤';
                el.innerHTML = `<span class="auth-avatar">${esc(initial)}</span><span class="auth-email">${esc(email)}</span>`;
                el.title = email;
            })
            .catch(() => {});
    }

    function openAuth() {
        const m = document.getElementById('authModal');
        const o = document.getElementById('authOverlay');
        if (!m || !o) return;
        m.classList.add('show');
        o.classList.add('show');
        ACP.toggleSidebar(false);
    }

    function closeAuth() {
        const m = document.getElementById('authModal');
        const o = document.getElementById('authOverlay');
        if (m) m.classList.remove('show');
        if (o) o.classList.remove('show');
    }

    /* ---------- 启动 ---------- */
    async function init() {
        if (!isConfigured()) return;
        renderAuthButton();

        supabase.auth.onAuthStateChange((event, session) => {
            const newUid = uidFromSession(session);
            const justSignedIn = (event === 'SIGNED_IN') && newUid && newUid !== uid;
            uid = newUid;
            if (event === 'SIGNED_OUT') {
                uid = null;
                syncReady = false;
            }
            renderAuthButton();
            if (justSignedIn) {
                closeAuth();
                ACP.toast('登录成功，正在同步…');
                pullAndMerge().then(pushAll).then(() => {
                    ACP.toast('云端同步完成');
                    ACP.render(); // 刷新当前视图（进度/错题/收藏等）
                    ACP.renderSidebarBadges();
                }).catch(e => { console.warn('[sync] merge failed', e); });
            }
        });

        // 恢复会话：刷新页面后仍是登录态
        try {
            const { data } = await supabase.auth.getSession();
            const session = data && data.session;
            if (session) {
                uid = uidFromSession(session);
                renderAuthButton();
                await pullAndMerge();
                await pushAll();
            }
        } catch (e) {
            console.warn('[sync] getSession failed', e);
        }
    }

    ACP.sync = {
        init, isConfigured, isSignedIn,
        openAuth, closeAuth,
        signInGoogle, sendEmailOtp, verifyEmailOtp, signOut,
        renderAuthButton, renderAuthUser,
        pushProgress, pushFav, pushExam, pushLast, pushAll, clearCloud,
        pullAndMerge,
        _mergeProgress: mergeProgress,
        _genId: genId
    };

})(window.ACP);
