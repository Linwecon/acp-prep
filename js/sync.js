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
    let epoch = 0;
    let queue = Promise.resolve();
    let syncing = null;
    let syncFailed = false;
    let syncReady = false;   // 是否已完成首次云端合并
    let initialization = null;
    let legacyProgress = false;
    let connState = 'unknown'; // unknown | ok | bad —— Supabase 项目是否可达
    let connInfo = '';         // 不可达时的中文说明（展示在登录弹窗）

    /* 懒加载客户端：即使 CDN 脚本晚于本文件就绪，也能在首次使用时补建 */
    function ensureClient() {
        if (supabase) return supabase;
        if (!configured) return null;
        if (typeof window !== 'undefined' && window.supabase && window.supabase.createClient) {
            supabase = window.supabase.createClient(CFG.url, CFG.anonKey, {
                auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
            });
        }
        return supabase;
    }
    ensureClient();

    function isConfigured() { return configured && !!ensureClient(); }
    function isSignedIn() { return !!uid; }

    /* 探测 Supabase 项目是否可达：被暂停/删除的项目，其域名会解析失败 */
    async function checkConnection() {
        if (!configured) {
            connState = 'bad'; connInfo = '未配置 Supabase';
            return { ok: false, reason: 'unconfigured' };
        }
        if (!ensureClient()) {
            connState = 'bad';
            connInfo = 'Supabase SDK 未加载成功（CDN 可能被网络拦截），请刷新页面或更换网络后重试。';
            return { ok: false, reason: 'sdk' };
        }
        const url = CFG.url.replace(/\/+$/, '') + '/auth/v1/health';
        let timer = null;
        try {
            const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
            timer = ctrl ? setTimeout(() => ctrl.abort(), 10000) : null;
            const res = await fetch(url, {
                headers: { apikey: CFG.anonKey },
                signal: ctrl ? ctrl.signal : undefined
            });
            if (timer) clearTimeout(timer);
            if (!res.ok) {
                connState = 'bad';
                connInfo = 'Supabase 返回 HTTP ' + res.status + '，项目可能已暂停或被限制访问。';
                return { ok: false, reason: 'http', status: res.status };
            }
            connState = 'ok'; connInfo = '';
            return { ok: true };
        } catch (e) {
            connState = 'bad';
            connInfo = '无法连接 Supabase 项目（域名解析失败或网络不通）。常见原因：项目被暂停（免费版长期无活动会自动暂停）、项目已删除、或 URL 填错。请到 Supabase Dashboard 检查并恢复项目。';
            return { ok: false, reason: 'network', message: e && e.message };
        } finally {
            if (timer) clearTimeout(timer);
        }
    }

    function renderConnWarn() {
        const el = document.getElementById('authConn');
        if (!el) return;
        if (connState === 'bad' && connInfo) {
            el.style.display = '';
            el.className = 'auth-msg err auth-conn';
            el.innerHTML = '⚠️ ' + esc(connInfo) +
                ' <a href="#" onclick="ACP.sync.testConnection();return false;">重新检测</a>';
        } else {
            el.style.display = 'none';
            el.innerHTML = '';
        }
    }

    async function testConnection() {
        const r = await checkConnection();
        renderConnWarn();
        ACP.toast(r.ok ? 'Supabase 连接正常' : 'Supabase 连接失败，详见弹窗提示');
        return r;
    }

    function esc(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function uidFromSession(session) { return session && session.user ? session.user.id : null; }

    function millis(value) { return value ? (new Date(value).getTime() || 0) : 0; }

    // 作答快照与错题状态有独立时间戳；移出错题不会被旧设备的累计次数覆盖。
    function mergeProgress(local, cloud) {
        local = local || {};
        const cloudT = millis(cloud.answered_at);
        const localT = local.t || 0;
        const cloudNewer = cloudT > localT || (!local.d && !local.a);
        const localW = local.wt === undefined ? localT : local.wt;
        const cloudW = cloud.wrong_updated_at == null ? cloudT : millis(cloud.wrong_updated_at);
        const merged = {
            d: Math.max(local.d || 0, cloud.done || 0),
            w: cloudW > localW ? (cloud.wrong || 0) : localW > cloudW ? (local.w || 0)
                : (local.w === 0 || cloud.wrong === 0 ? 0 : Math.max(local.w || 0, cloud.wrong || 0)),
            wt: Math.max(localW, cloudW),
            c: cloudNewer ? (cloud.correct ? 1 : 0) : (local.c || 0),
            t: Math.max(localT, cloudT)
        };
        const ans = cloudNewer ? cloud.answer : local.a;
        if (ans && ans.length) merged.a = ans.slice();
        return merged;
    }

    function context() { return { uid, store: S.store, epoch }; }
    function current(c) { return c.uid === uid && c.store === S.store && c.epoch === epoch; }
    function requireCurrent(c) {
        if (!current(c)) { const e = new Error('账号已切换'); e.stale = true; throw e; }
    }
    async function checked(query, c) {
        requireCurrent(c);
        const result = await query;
        requireCurrent(c);
        if (result && result.error) {
            const error = new Error(result.error.message || '云端请求失败');
            error.code = result.error.code;
            throw error;
        }
        return result || {};
    }
    function failed(e) {
        if (e.stale) return;
        console.warn('[sync] failed', e.message);
        if (!syncFailed) ACP.toast('云端同步失败，记录已保存在本机：' + e.message + '；请点击“同步”重试');
        syncFailed = true;
    }
    function enqueue(task) {
        const c = context();
        const job = queue.then(() => { requireCurrent(c); return task(c); });
        queue = job.catch(() => {});
        return job.catch(e => { if (current(c)) failed(e); return false; });
    }
    function toProgressRow(qid, p, c) {
        return {
            user_id: c.uid, question_id: qid, done: p.d || 0, wrong: p.w || 0,
            correct: p.c ? 1 : 0, answer: p.a && p.a.length ? p.a : null,
            answered_at: p.t ? new Date(p.t).toISOString() : null,
            wrong_updated_at: new Date(p.wt === undefined ? (p.t || 0) : p.wt).toISOString(),
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
    async function readAll(table, order, c) {
        const rows = [];
        for (let start = 0; ; start += 500) {
            const r = await checked(supabase.from(table).select('*').eq('user_id', c.uid)
                .order(order).range(start, start + 499), c);
            rows.push(...(r.data || []));
            if (!r.data || r.data.length < 500) return rows;
        }
    }
    function metaRow(key, value, time, c) {
        return { user_id: c.uid, key, value, updated_at: new Date(time || 0).toISOString() };
    }
    function learningRows(c) {
        const s = c.store;
        const rows = Object.entries(s.tut || {}).map(([id, rec]) => metaRow('tutorial:' + id, rec, rec.at, c));
        Object.entries(s.studyDone || {}).forEach(([id, done]) => {
            rows.push(metaRow('study_done:' + id, !!done, (s.studyDoneAt || {})[id], c));
        });
        if (s.studySettings) rows.push(metaRow('study_settings', s.studySettings, s.studySettingsAt, c));
        Object.entries(s.favState || {}).forEach(([id, rec]) => {
            rows.push(metaRow('favorite:' + id, !!rec.added, rec.at, c));
        });
        if (legacyProgress) Object.entries(s.p || {}).forEach(([id, p]) => rows.push(wrongMetaRow(id, p, c)));
        return rows;
    }
    // Older databases store the independent wrong-state timestamp in the existing meta table.
    function wrongMetaRow(id, p, c) {
        return metaRow('progress_wrong:' + id, { wrong: p.w || 0 },
            p.wt === undefined ? (p.t || 0) : p.wt, c);
    }

    async function pullAndMerge(c = context()) {
        if (!isConfigured() || !c.uid) return;
        syncReady = false;
        // 全部读取成功后再更新本地；任何一张表失败都不能开始回推。
        const [progress, favorites, meta, examR] = await Promise.all([
            readAll('user_progress', 'question_id', c), readAll('favorites', 'question_id', c),
            readAll('user_meta', 'key', c),
            checked(supabase.from('exam_records').select('*').eq('user_id', c.uid)
                .order('created_at', { ascending: false }).limit(100), c)
        ]);
        requireCurrent(c);
        const store = c.store;
        store.p = store.p || {};
        store.fav = store.fav || [];
        store.exams = store.exams || [];
        const wrongStates = new Map(meta.filter(r => r.key.startsWith('progress_wrong:') &&
            r.value && typeof r.value.wrong === 'number').map(r => [r.key.slice(15), r]));
        progress.forEach(r => {
            const wrong = wrongStates.get(r.question_id);
            if (wrong && (r.wrong_updated_at == null || millis(wrong.updated_at) > millis(r.wrong_updated_at))) {
                r = { ...r, wrong: wrong.value.wrong, wrong_updated_at: wrong.updated_at };
            }
            store.p[r.question_id] = mergeProgress(store.p[r.question_id], r);
        });
        favorites.forEach(r => { if (!store.fav.includes(r.question_id)) store.fav.push(r.question_id); });
        meta.forEach(r => {
            const time = millis(r.updated_at);
            if (r.key.startsWith('favorite:') && typeof r.value === 'boolean') {
                const id = r.key.slice(9);
                const states = store.favState || (store.favState = {});
                if (!states[id] || time > states[id].at) states[id] = { added: r.value, at: time };
            } else if (r.key === 'last' && r.value && typeof r.value === 'object') {
                if ((r.value.t || 0) > ((store.last || {}).t || 0)) store.last = r.value;
            } else if (r.key.startsWith('tutorial:') && r.value && typeof r.value === 'object') {
                const id = r.key.slice(9);
                store.tut = store.tut || {};
                if (!store.tut[id] || (r.value.at || 0) > (store.tut[id].at || 0)) store.tut[id] = r.value;
            } else if (r.key.startsWith('study_done:') && typeof r.value === 'boolean') {
                const id = r.key.slice(11);
                store.studyDone = store.studyDone || {};
                store.studyDoneAt = store.studyDoneAt || {};
                if (!(id in store.studyDone) || time > (store.studyDoneAt[id] || 0)) {
                    store.studyDone[id] = r.value;
                    store.studyDoneAt[id] = time;
                }
            } else if (r.key === 'study_settings' && r.value && typeof r.value === 'object') {
                if (!store.studySettings || time > (store.studySettingsAt || 0)) {
                    store.studySettings = r.value;
                    store.studySettingsAt = time;
                }
            }
        });
        Object.entries(store.favState || {}).forEach(([id, rec]) => {
            store.fav = store.fav.filter(qid => qid !== id);
            if (rec.added) store.fav.push(id);
        });
        if (ACP.migrateMovedQids) ACP.migrateMovedQids(store);
        const ids = new Set(store.exams.map(e => e.id));
        (examR.data || []).forEach(r => { if (!ids.has(r.id)) { store.exams.push(r); ids.add(r.id); } });
        store.exams.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        store.exams = store.exams.slice(0, 100);
        ACP.saveStore();
        syncReady = true;
    }
    async function upsertRows(table, rows, conflict, c) {
        for (let i = 0; i < rows.length; i += 500) {
            requireCurrent(c);
            const batch = rows.slice(i, i + 500);
            const legacyRows = () => batch.map(({ wrong_updated_at, ...row }) => row);
            // Favorites contain only identity; submitted exams are immutable. Old schemas
            // allow INSERT but have no UPDATE policy for these two tables.
            const options = { onConflict: conflict };
            if (table === 'favorites' || table === 'exam_records') options.ignoreDuplicates = true;
            try {
                await checked(supabase.from(table).upsert(
                    table === 'user_progress' && legacyProgress ? legacyRows() : batch,
                    options), c);
            } catch (e) {
                // Retry only this known schema mismatch; permission/network errors must remain visible.
                if (table !== 'user_progress' || legacyProgress ||
                    !['PGRST204', '42703'].includes(e.code) || !/wrong_updated_at/.test(e.message)) throw e;
                legacyProgress = true;
                await checked(supabase.from(table).upsert(legacyRows(), options), c);
            }
        }
    }
    async function pushAll(c = context()) {
        if (!isConfigured() || !c.uid || !syncReady) return;
        requireCurrent(c);
        const s = c.store;
        await upsertRows('user_progress', Object.entries(s.p || {}).map(([id, p]) => toProgressRow(id, p, c)), 'user_id,question_id', c);
        await upsertRows('favorites', (s.fav || []).map(id => ({ user_id: c.uid, question_id: id })), 'user_id,question_id', c);
        const rows = learningRows(c);
        if (s.last) rows.push(metaRow('last', s.last, s.last.t, c));
        await upsertRows('user_meta', rows, 'user_id,key', c);
        for (const [id, rec] of Object.entries(s.favState || {})) {
            if (!rec.added) await checked(supabase.from('favorites').delete().eq('user_id', c.uid).eq('question_id', id), c);
        }
        await upsertRows('exam_records', (s.exams || []).map(e => ({
            id: e.id, user_id: c.uid, score: e.score, correct: e.correct, wrong: e.wrong,
            pass: e.pass, time_used: e.time_used, weak_by_ch: e.weak_by_ch || null,
            created_at: e.created_at || new Date().toISOString()
        })), 'id', c);
    }
    function syncNow() {
        if (!isConfigured() || !uid) return Promise.resolve(false);
        if (syncing) return syncing;
        const job = enqueue(async c => {
            await pullAndMerge(c);
            try { await pushAll(c); } catch (e) { if (current(c)) syncReady = false; throw e; }
            requireCurrent(c);
            syncFailed = false;
            ACP.toast('云端同步完成');
            ACP.render();
            ACP.renderSidebarBadges();
            return true;
        });
        syncing = job;
        job.finally(() => { if (syncing === job) syncing = null; });
        return job;
    }
    function realtime(task) {
        if (!isConfigured() || !uid) return Promise.resolve(false);
        // Changes made during the initial pull must wait for it, not disappear.
        return enqueue(c => syncReady ? task(c) : false);
    }
    function pushProgress(qid) {
        return realtime(async c => {
            const p = c.store.p && c.store.p[qid];
            if (p) {
                const row = toProgressRow(qid, p, c);
                const wrongRow = wrongMetaRow(qid, p, c);
                await upsertRows('user_progress', [row], 'user_id,question_id', c);
                if (legacyProgress) await upsertRows('user_meta', [wrongRow], 'user_id,key', c);
            }
        });
    }
    function pushFav(qid, added) {
        return realtime(async c => {
            const rec = (c.store.favState || {})[qid];
            if (rec) {
                await upsertRows('user_meta', [metaRow('favorite:' + qid, !!rec.added, rec.at, c)], 'user_id,key', c);
                added = rec.added;
            }
            if (added) await upsertRows('favorites', [{ user_id: c.uid, question_id: qid }], 'user_id,question_id', c);
            else await checked(supabase.from('favorites').delete().eq('user_id', c.uid).eq('question_id', qid), c);
        });
    }
    function pushExam(record) {
        return realtime(c => upsertRows('exam_records', [{
            id: record.id, user_id: c.uid, score: record.score, correct: record.correct,
            wrong: record.wrong, pass: record.pass, time_used: record.time_used,
            weak_by_ch: record.weak_by_ch || null, created_at: record.created_at
        }], 'id', c));
    }
    function pushLast() {
        return realtime(c => c.store.last && upsertRows('user_meta', [metaRow('last', c.store.last, c.store.last.t, c)], 'user_id,key', c));
    }
    function pushTutorial(id) {
        return realtime(c => {
            const rec = (c.store.tut || {})[id];
            return rec && upsertRows('user_meta', [metaRow('tutorial:' + id, rec, rec.at, c)], 'user_id,key', c);
        });
    }
    function pushStudyDone(id) {
        return realtime(c => upsertRows('user_meta', [metaRow('study_done:' + id,
            !!(c.store.studyDone || {})[id], (c.store.studyDoneAt || {})[id], c)], 'user_id,key', c));
    }
    function pushStudySettings() {
        return realtime(c => upsertRows('user_meta', [metaRow('study_settings', c.store.studySettings || {}, c.store.studySettingsAt, c)], 'user_id,key', c));
    }
    function clearCloud() {
        return enqueue(async c => {
            if (!isConfigured() || !c.uid) return;
            for (const table of ['user_progress', 'favorites', 'exam_records', 'user_meta']) {
                await checked(supabase.from(table).delete().eq('user_id', c.uid), c);
            }
        });
    }

    /* ---------- 认证 ---------- */
    function showAuthMsg(msg, cls) {
        const hint = document.getElementById('authOtpHint');
        if (hint) { hint.innerHTML = esc(msg); hint.className = 'auth-msg ' + (cls || ''); }
    }

    function switchAuthPage(page) {
        const signInPage = document.getElementById('authSignInPage');
        const signUpPage = document.getElementById('authSignUpPage');
        const tabSignIn = document.getElementById('tabSignIn');
        const tabSignUp = document.getElementById('tabSignUp');
        if (page === 'signup') {
            if (signInPage) signInPage.style.display = 'none';
            if (signUpPage) signUpPage.style.display = '';
            if (tabSignIn) tabSignIn.classList.remove('active');
            if (tabSignUp) tabSignUp.classList.add('active');
        } else {
            if (signInPage) signInPage.style.display = '';
            if (signUpPage) signUpPage.style.display = 'none';
            if (tabSignIn) tabSignIn.classList.add('active');
            if (tabSignUp) tabSignUp.classList.remove('active');
        }
        showAuthMsg('', '');
    }

    function togglePassword(inputId, btn) {
        const el = document.getElementById(inputId);
        if (!el) return;
        const show = el.type === 'password';
        el.type = show ? 'text' : 'password';
        if (btn) {
            btn.innerHTML = ACP.icon ? ACP.icon(show ? 'eye-off' : 'eye') : (show ? '隐藏' : '显示');
            btn.title = show ? '隐藏密码' : '显示密码';
            btn.setAttribute('aria-label', btn.title);
            btn.setAttribute('aria-pressed', String(show));
        }
    }

    function setBtnLoading(id, loading) {
        const btn = document.getElementById(id);
        if (!btn) return;
        if (loading) {
            if (!btn.dataset.orig) btn.dataset.orig = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span class="spin"></span> ' + (btn.dataset.loading || '处理中…');
        } else {
            btn.disabled = false;
            if (btn.dataset.orig) btn.innerHTML = btn.dataset.orig;
        }
    }

    async function signInWithPassword() {
        if (!isConfigured()) { ACP.toast('未配置 Supabase'); return; }
        await init();
        const email = ((document.getElementById('authEmail') || {}).value || '').trim();
        const password = (document.getElementById('authPassword') || {}).value || '';
        if (!email || !password) { showAuthMsg('请填写邮箱和密码', 'err'); return; }
        setBtnLoading('authPwdBtn', true);
        try {
            const { error } = await supabase.auth.signInWithPassword({ email, password });
            if (error) showAuthMsg('登录失败：' + error.message, 'err');
            // 成功时 onAuthStateChange 会触发 SIGNED_IN，自动关弹窗并同步
        } catch (e) {
            connState = 'bad';
            connInfo = '无法连接 Supabase 项目（域名解析失败或网络不通）。请到 Supabase Dashboard 确认项目是否被暂停。';
            renderConnWarn();
            showAuthMsg('登录失败：' + ((e && e.message) || '网络异常'), 'err');
        } finally {
            setBtnLoading('authPwdBtn', false);
        }
    }

    async function signUp() {
        if (!isConfigured()) { ACP.toast('未配置 Supabase'); return; }
        await init();
        const email = ((document.getElementById('authRegEmail') || {}).value || '').trim();
        const password = (document.getElementById('authRegPassword') || {}).value || '';
        const password2 = (document.getElementById('authRegPassword2') || {}).value || '';
        if (!email || !password) { showAuthMsg('请填写邮箱和密码', 'err'); return; }
        if (password.length < 6) { showAuthMsg('密码至少 6 位', 'err'); return; }
        if (password !== password2) { showAuthMsg('两次输入的密码不一致', 'err'); return; }
        setBtnLoading('authRegBtn', true);
        try {
            const { data, error } = await supabase.auth.signUp({ email, password });
            if (error) { showAuthMsg('注册失败：' + error.message, 'err'); return; }
            if (data && data.session) {
                showAuthMsg('注册成功，正在同步…', 'ok');
            } else {
                showAuthMsg('注册成功，请查收邮箱确认链接后再登录', 'ok');
            }
        } catch (e) {
            connState = 'bad';
            connInfo = '无法连接 Supabase 项目（域名解析失败或网络不通）。请到 Supabase Dashboard 确认项目是否被暂停。';
            renderConnWarn();
            showAuthMsg('注册失败：' + ((e && e.message) || '网络异常'), 'err');
        } finally {
            setBtnLoading('authRegBtn', false);
        }
    }

    async function signOut() {
        if (!isConfigured()) return;
        try {
            const result = await ensureClient().auth.signOut();
            if (result.error) throw new Error(result.error.message);
            await applySession(null, false);
            ACP.toast('已退出登录，账号记录已保留，当前为访客模式');
        } catch (e) { failed(e); }
    }

    /* ---------- 登录 UI ---------- */
    function renderAuthButton() {
        const area = document.getElementById('authArea');
        if (!area) return;
        if (uid && isConfigured()) {
            // 已登录：头像（邮箱首字母）+ 邮箱 + 退出
            area.innerHTML = `
          <span class="auth-user" id="authUser" title="已登录">…</span>
          <button class="auth-btn" onclick="ACP.sync.syncNow()" title="重试云端同步">同步</button>
          <button class="auth-btn" onclick="ACP.sync.signOut()" title="退出登录">退出</button>`;
            renderAuthUser();
        } else {
            // 未登录（或未配置）：始终显示登录入口
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
        const form = document.getElementById('authForm');
        const setup = document.getElementById('authSetup');
        if (isConfigured()) {
            if (form) form.style.display = '';
            if (setup) setup.style.display = 'none';
        } else {
            if (form) form.style.display = 'none';
            if (setup) setup.style.display = '';
        }
        m.classList.add('show');
        o.classList.add('show');
        renderConnWarn();
        ACP.toggleSidebar(false);
    }

    function closeAuth() {
        const m = document.getElementById('authModal');
        const o = document.getElementById('authOverlay');
        if (m) m.classList.remove('show');
        if (o) o.classList.remove('show');
    }

    async function applySession(session, announce) {
        const newUid = uidFromSession(session);
        const sameOwner = (S.store.owner || null) === newUid;
        if (newUid === uid && sameOwner && (!newUid || syncReady || syncing)) return;
        if (newUid !== uid || !sameOwner) {
            epoch++;
            // A stalled request for the previous account cannot block this account.
            queue = Promise.resolve();
            syncing = null;
            syncReady = false;
            syncFailed = false;
            if (ACP.activateAccount) ACP.activateAccount(newUid);
            uid = newUid;
            ACP.render();
            ACP.renderSidebarBadges();
        } else if (!newUid && ACP.activateAccount) {
            ACP.activateAccount(null);
        }
        renderAuthButton();
        if (newUid) {
            if (announce) { closeAuth(); ACP.toast('登录成功，正在同步…'); }
            await syncNow();
        }
    }
    function init() {
        if (initialization) return initialization;
        if (!isConfigured()) {
            renderAuthButton();
            return Promise.resolve();
        }
        initialization = initialize();
        return initialization;
    }
    async function initialize() {
        renderAuthButton();
        if (configured && !ensureClient()) {
            connState = 'bad';
            connInfo = 'Supabase SDK 未加载成功，请刷新页面或更换网络后重试。';
        }
        if (!isConfigured()) return;
        checkConnection().then(r => { if (!r.ok) console.warn('[sync] Supabase 不可达', r.reason); });
        const sb = ensureClient();
        let revision = 0;
        sb.auth.onAuthStateChange((event, session) => {
            const rev = ++revision;
            // 避免在 Supabase auth 锁内调用 getUser / 数据库 API。
            setTimeout(() => {
                if (rev === revision) applySession(session, event === 'SIGNED_IN').catch(failed);
            }, 0);
        });
        const rev = revision;
        try {
            const result = await sb.auth.getSession();
            if (result.error) throw new Error(result.error.message);
            if (rev === revision) {
                const session = result.data && result.data.session;
                if (!session && ACP.activateAccount) ACP.activateAccount(null);
                await applySession(session, false);
            }
        } catch (e) { failed(e); }
        if (window.addEventListener) window.addEventListener('online', () => { if (uid) syncNow(); });
    }

    ACP.sync = {
        init, isConfigured, isSignedIn,
        openAuth, closeAuth, switchAuthPage, togglePassword,
        signInWithPassword, signUp, signOut,
        checkConnection, testConnection,
        renderAuthButton, renderAuthUser,
        pushProgress, pushFav, pushExam, pushLast, pushAll, clearCloud,
        pushTutorial, pushStudyDone, pushStudySettings, syncNow,
        pullAndMerge,
        _mergeProgress: mergeProgress,
        _genId: genId
    };

})(window.ACP);
