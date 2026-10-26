// Offline regression coverage for account isolation, synchronization failures and learning state.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = name => fs.readFileSync(path.join(__dirname, '..', 'js', name + '.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const pause = () => new Promise(resolve => setTimeout(resolve, 5));

test('submitted paper survives failed upload, retry and a fresh device; review is immutable', async () => {
    const h = harness();
    await h.ACP.sync.init();
    h.ACP.uuid = () => 'paper-test';
    const question = { id: 'q', ch: '1', multi: false, stem: 'Original question',
        options: [{ label: 'A', text: 'Original option' }], ansArr: ['A'], analysis: 'Original explanation' };
    h.ACP.state.exam = { state: 'on', pool: [question], answers: { 0: ['A'] }, startAt: Date.now() };
    h.control.writeError = 'user_meta';
    h.ACP.submitExam(true);
    h.ACP.submitExam(true);
    await pause();
    assert.equal(h.ACP.state.store.exams.length, 1, 'duplicate submission is ignored');
    question.stem = 'Changed bank question';
    assert.equal(h.ACP.state.store.exams[0].paper.pool[0].stem, 'Original question');
    assert.equal(h.db.exam_records.length, 0, 'summary cannot imply a paper was uploaded');
    assert.ok(h.logs.some(s => s.includes('云端同步失败')));
    h.control.writeError = null;
    await h.ACP.sync.syncNow();
    await h.ACP.sync.syncNow();
    assert.equal(h.db.exam_records.length, 1);
    const other = harness({ rows: h.db });
    await other.ACP.sync.init();
    assert.deepEqual(clone(other.ACP.state.store.exams[0].paper), clone(h.ACP.state.store.exams[0].paper));
    other.ACP.openExamHistory(0);
    assert.equal(other.ACP.state.exam.result.score, 1);
    assert.equal(other.ACP.isExamCorrect(0), true);
    other.ACP.state.exam.state = 'review';
    other.ACP.examOpt('B');
    assert.deepEqual(clone(other.ACP.state.exam.answers[0]), ['A']);
    assert.equal(other.ACP.state.store.p.q.d, 1, 'review does not record a new attempt');
    const stranger = harness({ user: 'B', rows: h.db });
    await stranger.ACP.sync.init();
    assert.equal(stranger.ACP.state.store.exams.length, 0);
});

test('all exam history is retained beyond the former 100 record limit', async () => {
    const records = Array.from({ length: 105 }, (_, i) => ({ id: 'exam-' + i, user_id: 'A',
        score: 80, correct: 60, wrong: 15, pass: true, created_at: new Date(i * 1000).toISOString() }));
    const h = harness({ rows: { exam_records: records } });
    await h.ACP.sync.init();
    assert.equal(h.ACP.state.store.exams.length, 105);
    assert.equal(h.ACP.state.store.exams[0].id, 'exam-104');
    h.ACP.openExamHistory(0);
    assert.equal(h.ACP.state.exam, null, 'summary-only legacy records cannot open as papers');
});

function harness({ user = 'A', store = {}, rows = {}, lateSdk = false } = {}) {
    const memory = new Map([['acp_v2_store', JSON.stringify({ p: {}, fav: [], exams: [], owner: user, ...store })]]);
    const logs = [], writes = [], reads = [];
    const control = { readError: null, writeError: null, signOutError: null, gate: null, subscriptions: 0, credentials: null,
        legacySchema: false, missingColumnAttempts: 0 };
    const db = { user_progress: [], favorites: [], user_meta: [], exam_records: [], ...clone(rows) };
    let listener;
    const sb = {
        auth: {
            getSession: async () => ({ data: { session: user ? { user: { id: user } } : null } }),
            getUser: async () => ({ data: { user: { email: 'test@example.invalid' } } }),
            onAuthStateChange: cb => { listener = cb; control.subscriptions++; },
            signInWithPassword: async credentials => {
                control.credentials = credentials;
                if (listener) listener('SIGNED_IN', { user: { id: 'A' } });
                return { error: null };
            },
            signOut: async () => ({ error: control.signOutError })
        },
        from(table) {
            let op = 'select', filters = [], range = [0, 999], input, order, ascending = true, options = {};
            const q = {
                select() { return q; }, eq(k, v) { filters.push([k, v]); return q; },
                order(k, opts = {}) { order = k; ascending = opts.ascending !== false; return q; },
                range(a, b) { range = [a, b]; return q; }, limit(n) { range = [0, n - 1]; return q; },
                delete() { op = 'delete'; return q; }, upsert(value, opts = {}) { op = 'upsert'; options = opts; input = clone(Array.isArray(value) ? value : [value]); return q; },
                then(resolve, reject) {
                    return (async () => {
                        if (op === 'select') {
                            reads.push({ table, range: [...range] });
                            if (control.gate) await control.gate;
                            if (control.readError === table) return { data: null, error: { message: 'read denied' } };
                            let data = db[table].filter(r => filters.every(([k, v]) => r[k] === v));
                            if (order) data = data.slice().sort((a, b) => (String(a[order]).localeCompare(String(b[order]))) * (ascending ? 1 : -1));
                            return { data: clone(data.slice(range[0], range[1] + 1)), error: null };
                        }
                        if (control.writeError === table) return { error: { message: 'write denied' } };
                        if (control.legacySchema && table === 'user_progress' && op === 'upsert' && input.some(r => 'wrong_updated_at' in r)) {
                            control.missingColumnAttempts++;
                            return { error: { code: 'PGRST204', message: "Could not find the 'wrong_updated_at' column of 'user_progress' in the schema cache" } };
                        }
                        if (control.legacySchema && ['favorites', 'exam_records'].includes(table) && op === 'upsert' && !options.ignoreDuplicates) {
                            return { error: { code: '42501', message: 'new row violates row-level security policy' } };
                        }
                        writes.push({ table, op, rows: input });
                        if (op === 'delete') db[table] = db[table].filter(r => !filters.every(([k, v]) => r[k] === v));
                        else for (const row of input) {
                            const keys = table === 'exam_records' ? ['id'] : ['user_id', table === 'user_meta' ? 'key' : 'question_id'];
                            const i = db[table].findIndex(r => keys.every(k => r[k] === row[k]));
                            if (i < 0) db[table].push(row); else if (!options.ignoreDuplicates) db[table][i] = row;
                        }
                        return { error: null };
                    })().then(resolve, reject);
                }
            };
            return q;
        }
    };
    const context = vm.createContext({
        window: { SUPABASE_CONFIG: { url: 'https://test.invalid', anonKey: 'test' }, supabase: lateSdk ? null : { createClient: () => sb } },
        document: { getElementById: () => null },
        localStorage: { getItem: k => memory.get(k) || null, setItem: (k, v) => memory.set(k, String(v)), removeItem: k => memory.delete(k) },
        fetch: async () => ({ ok: true }), console: { warn() {} }, setTimeout, clearTimeout, clearInterval,
        AbortController, Date
    });
    for (const name of ['acp', 'store', 'exam', 'sync']) vm.runInContext(source(name), context);
    const ACP = context.window.ACP;
    ACP.state.store = ACP.loadStore();
    ACP.toast = text => logs.push(text);
    ACP.render = ACP.renderSidebarBadges = ACP.renderExam = () => {};
    return { ACP, control, db, writes, reads, logs, memory, context,
        loadSdk() { context.window.supabase = { createClient: () => sb }; },
        async emit(event, id) { listener(event, id ? { user: { id } } : null); await pause(); if (id) await ACP.sync.syncNow(); }
    };
}

test('A -> guest -> B -> A preserves separate records and never uploads A to B', async () => {
    const h = harness({ store: { p: { old: { d: 1, w: 0, c: 1 } }, tut: { lesson: { d: 1, at: 1 } }, studyDone: { kp: true } } });
    await h.ACP.sync.init();
    await h.ACP.sync.signOut();
    assert.equal(h.ACP.state.store.p.old, undefined);
    assert.equal(h.ACP.state.store.tut, undefined);
    assert.deepEqual(clone(h.ACP.state.store.studyDone), {});
    await h.emit('SIGNED_IN', 'B');
    assert.equal(h.db.user_progress.some(r => r.user_id === 'B' && r.question_id === 'old'), false);
    assert.equal(h.db.user_meta.some(r => r.user_id === 'B' && r.key === 'tutorial:lesson'), false);
    await h.emit('SIGNED_IN', 'A');
    assert.equal(h.ACP.state.store.p.old.d, 1);
    assert.equal(h.ACP.state.store.studyDone.kp, true);
    assert.equal(h.ACP.state.store.tut.lesson.d, 1);
});

test('legacy guest records remain available without being silently claimed by a login', async () => {
    const h = harness({ user: null, store: { p: { guest: { d: 1 } }, studyDone: { guestKp: true } } });
    await h.ACP.sync.init();
    await h.emit('SIGNED_IN', 'A');
    assert.equal(h.ACP.state.store.p.guest, undefined);
    await h.ACP.sync.signOut();
    assert.equal(h.ACP.state.store.p.guest.d, 1);
    assert.equal(h.ACP.state.store.studyDone.guestKp, true);
});

test('failed pull does not mutate local data, upload, or announce success; retry recovers', async () => {
    const h = harness({ store: { p: { local: { d: 1 } } }, rows: { user_progress: [{ user_id: 'A', question_id: 'cloud', done: 2 }] } });
    h.control.readError = 'user_meta';
    await h.ACP.sync.init();
    assert.equal(h.ACP.state.store.p.cloud, undefined);
    assert.equal(h.writes.length, 0);
    assert.equal(h.logs.includes('云端同步完成'), false);
    assert.ok(h.logs.some(s => s.includes('同步失败')));
    h.control.readError = null;
    assert.equal(await h.ACP.sync.syncNow(), true);
    assert.equal(h.ACP.state.store.p.cloud.d, 2);
});

test('write failures are visible and cannot announce synchronization complete', async () => {
    const h = harness({ store: { p: { q: { d: 1 } } } });
    h.control.writeError = 'user_progress';
    await h.ACP.sync.init();
    assert.equal(h.logs.includes('云端同步完成'), false);
    assert.ok(h.logs.some(s => s.includes('同步失败')));
    h.control.writeError = null;
    assert.equal(await h.ACP.sync.syncNow(), true);
    h.control.writeError = 'favorites';
    assert.equal(await h.ACP.sync.pushFav('q', true), false);
    assert.ok(h.logs.at(-1).includes('同步失败'));
});

test('an in-flight pull for A cannot merge into or upload under B', async () => {
    const h = harness({ store: { p: { a: { d: 1 } } } });
    let release;
    h.control.gate = new Promise(resolve => { release = resolve; });
    const startup = h.ACP.sync.init();
    await pause();
    const switching = h.emit('SIGNED_IN', 'B');
    await pause();
    h.control.gate = null;
    release();
    await Promise.all([startup, switching]);
    assert.equal(h.ACP.state.store.owner, 'B');
    assert.equal(h.ACP.state.store.p.a, undefined);
    assert.equal(h.db.user_progress.some(r => r.user_id === 'B' && r.question_id === 'a'), false);
    assert.equal(h.logs.filter(s => s === '云端同步完成').length, 1);
});

test('pull paginates past the default API row cap', async () => {
    const rows = Array.from({ length: 1205 }, (_, i) => ({ user_id: 'A', question_id: `q${String(i).padStart(4, '0')}`, done: 1, wrong: 0 }));
    const h = harness({ rows: { user_progress: rows } });
    await h.ACP.sync.init();
    assert.equal(Object.keys(h.ACP.state.store.p).length, 1205);
    assert.ok(h.reads.some(r => r.table === 'user_progress' && r.range[0] === 1000));
});

test('tutorial completion, reading position, knowledge cancellation and settings round-trip', async () => {
    const h = harness({ store: {
        tut: { local: { d: 1, b: 4, at: 2000 }, remote: { d: 1, b: 1, at: 1000 } },
        studyDone: { local: true, remote: true }, studyDoneAt: { local: 2000, remote: 1000 }
    }, rows: { user_meta: [
        { user_id: 'A', key: 'tutorial:remote', value: { d: 0, b: 9, at: 3000 }, updated_at: new Date(3000).toISOString() },
        { user_id: 'A', key: 'study_done:remote', value: false, updated_at: new Date(3000).toISOString() },
        { user_id: 'A', key: 'study_settings', value: { mode: 'exam' }, updated_at: new Date(3000).toISOString() }
    ] } });
    await h.ACP.sync.init();
    assert.equal(h.ACP.state.store.tut.remote.d, 0);
    assert.equal(h.ACP.state.store.tut.remote.b, 9);
    assert.equal(h.ACP.state.store.studyDone.remote, false);
    assert.equal(h.ACP.state.store.studySettings.mode, 'exam');
    assert.equal(h.db.user_meta.find(r => r.key === 'tutorial:local').value.b, 4);
    assert.equal(h.db.user_meta.find(r => r.key === 'study_done:local').value, true);
    h.ACP.state.store.tut.local = { d: 0, b: 5, at: 4000 };
    await h.ACP.sync.pushTutorial('local');
    assert.equal(h.db.user_meta.find(r => r.key === 'tutorial:local').value.d, 0);
});

test('exam submission saves this answer, correctness and timestamp as one progress write', async () => {
    const h = harness({ store: { p: { q: { d: 1, w: 0, c: 1, a: ['A'], t: 100 } } } });
    await h.ACP.sync.init();
    h.writes.length = 0;
    h.ACP.state.exam = { state: 'on', pool: [{ id: 'q', ch: '1', multi: false, ansArr: ['A'] }], answers: { 0: ['B'] }, startAt: Date.now() };
    h.ACP.submitExam(true);
    await h.ACP.sync.syncNow();
    const p = h.ACP.state.store.p.q;
    assert.deepEqual(clone(p.a), ['B']);
    assert.equal(p.c, 0);
    assert.equal(p.d, 2);
    assert.ok(p.t > 100);
    assert.deepEqual(clone(h.ACP.state.session.q), { sel: ['B'], correct: false });
    const row = h.writes.find(w => w.table === 'user_progress').rows[0];
    assert.deepEqual(row.answer, ['B']);
    assert.equal(row.correct, 0);
});

test('clear wrong wins over stale counts in either merge direction; a later wrong answer re-adds it', async () => {
    const h = harness({ store: { p: { q: { d: 4, w: 3, c: 0, a: ['A'], t: 100, wt: 100 } } } });
    const merge = h.ACP.sync._mergeProgress;
    h.ACP.clearWrong('q');
    const cleared = clone(h.ACP.state.store.p.q);
    const stale = { done: 4, wrong: 3, correct: 0, answer: ['A'], answered_at: new Date(100).toISOString(), wrong_updated_at: new Date(100).toISOString() };
    assert.equal(merge(cleared, stale).w, 0);
    assert.equal(merge({ d: 4, w: 3, t: 100, wt: 100 }, { ...stale, wrong: 0, wrong_updated_at: new Date(cleared.wt).toISOString() }).w, 0);
    h.ACP.markResult({ id: 'q' }, true, ['B']);
    assert.equal(h.ACP.state.store.p.q.wt, cleared.wt, 'correct answer must not change wrong-state timestamp');
    h.ACP.markResult({ id: 'q' }, false, ['A']);
    assert.equal(h.ACP.isWrong('q'), true);
    assert.ok(h.ACP.state.store.p.q.wt > cleared.wt);
});

test('failed sign-out keeps the current account active', async () => {
    const h = harness();
    await h.ACP.sync.init();
    h.control.signOutError = { message: 'offline' };
    await h.ACP.sync.signOut();
    assert.equal(h.ACP.sync.isSignedIn(), true);
    assert.equal(h.ACP.state.store.owner, 'A');
});

test('late SDK login installs auth listener once and trims the email', async () => {
    const h = harness({ user: null, lateSdk: true });
    await h.ACP.sync.init();
    assert.equal(h.control.subscriptions, 0);
    h.loadSdk();
    const fields = { authEmail: { value: '  test@example.invalid  ' }, authPassword: { value: ' secret ' } };
    h.context.document.getElementById = id => fields[id] || null;
    await h.ACP.sync.signInWithPassword();
    await pause();
    await h.ACP.sync.syncNow();
    assert.equal(h.ACP.state.store.owner, 'A');
    assert.deepEqual(h.control.credentials.email, 'test@example.invalid');
    assert.equal(h.control.credentials.password, ' secret ');
    await Promise.all([h.ACP.sync.init(), h.ACP.sync.init()]);
    assert.equal(h.control.subscriptions, 1);
});

test('new account synchronizes without waiting for a stalled old account request', async () => {
    const h = harness();
    let release;
    h.control.gate = new Promise(resolve => { release = resolve; });
    const startup = h.ACP.sync.init();
    await pause();
    h.control.gate = null;
    try {
        const switching = h.emit('SIGNED_IN', 'B');
        await pause();
        await pause();
        assert.ok(h.logs.includes('云端同步完成'), 'B must complete before A is released');
        assert.equal(h.ACP.state.store.owner, 'B');
        await switching;
    } finally {
        release();
        await startup;
    }
});

test('failed favorite removal survives retry and is understood by another device', async () => {
    const h = harness({ store: { fav: ['q'] }, rows: { favorites: [{ user_id: 'A', question_id: 'q' }] } });
    await h.ACP.sync.init();
    h.control.writeError = 'user_meta';
    h.ACP.toggleFav('q');
    await pause();
    assert.equal(h.ACP.isFav('q'), false);
    h.control.writeError = null;
    await h.ACP.sync.syncNow();
    assert.equal(h.ACP.isFav('q'), false);
    assert.equal(h.db.favorites.length, 0);
    assert.equal(h.db.user_meta.find(r => r.key === 'favorite:q').value, false);
    const other = harness({ store: { fav: ['q'] }, rows: h.db });
    await other.ACP.sync.init();
    assert.equal(other.ACP.isFav('q'), false);
    other.ACP.toggleFav('q');
    await other.ACP.sync.syncNow();
    assert.equal(other.db.user_meta.find(r => r.key === 'favorite:q').value, true);
});

test('favorite cancellation during initial pull is retained and uploaded', async () => {
    const h = harness({ store: { fav: ['q'] }, rows: { favorites: [{ user_id: 'A', question_id: 'q' }] } });
    let release;
    h.control.gate = new Promise(resolve => { release = resolve; });
    const startup = h.ACP.sync.init();
    await pause();
    h.ACP.toggleFav('q');
    release();
    await startup;
    await h.ACP.sync.syncNow();
    assert.equal(h.ACP.isFav('q'), false);
    assert.equal(h.db.favorites.length, 0);
    assert.equal(h.db.user_meta.find(r => r.key === 'favorite:q').value, false);
});

test('deployed legacy schema syncs without the new column or favorite/exam UPDATE policies', async () => {
    const h = harness({ store: {
        p: { q: { d: 2, w: 1, c: 0, a: ['B'], t: 1000, wt: 1000 } }, fav: ['q'],
        exams: [{ id: 'exam', score: 80, correct: 60, wrong: 15, pass: true, created_at: new Date(1000).toISOString() }]
    } });
    h.control.legacySchema = true;
    await h.ACP.sync.init();
    assert.ok(h.logs.includes('云端同步完成'));
    assert.equal(h.control.missingColumnAttempts, 1);
    assert.equal(h.db.user_progress[0].done, 2);
    assert.equal(h.db.user_meta.find(r => r.key === 'progress_wrong:q').value.wrong, 1);
    h.ACP.clearWrong('q');
    await h.ACP.sync.syncNow();
    assert.equal(h.db.user_progress[0].wrong, 0);
    assert.equal(h.db.user_meta.find(r => r.key === 'progress_wrong:q').value.wrong, 0);
    assert.equal(h.control.missingColumnAttempts, 1, 'remember compatibility for subsequent writes');
    assert.equal(h.db.favorites.length, 1);
    assert.equal(h.db.exam_records.length, 1);

    const other = harness({ store: { p: { q: { d: 2, w: 1, c: 0, t: 1000, wt: 1000 } } }, rows: h.db });
    other.control.legacySchema = true;
    await other.ACP.sync.init();
    assert.equal(other.ACP.state.store.p.q.w, 0, 'metadata carries removal to other devices');
    assert.ok(other.logs.includes('云端同步完成'));
    other.ACP.markResult({ id: 'q' }, false, ['C']);
    await other.ACP.sync.syncNow();
    assert.equal(other.db.user_meta.find(r => r.key === 'progress_wrong:q').value.wrong, 1);
});

test('permission errors remain visible and do not trigger schema fallback', async () => {
    const h = harness({ store: { p: { q: { d: 1 } } } });
    h.control.writeError = 'user_progress';
    await h.ACP.sync.init();
    assert.equal(h.control.missingColumnAttempts, 0);
    assert.ok(h.logs.some(s => s.includes('write denied')));
    assert.equal(h.logs.includes('云端同步完成'), false);
});
