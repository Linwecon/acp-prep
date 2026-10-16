// Offline regression coverage for account isolation, synchronization failures and learning state.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = name => fs.readFileSync(path.join(__dirname, '..', 'js', name + '.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const pause = () => new Promise(resolve => setTimeout(resolve, 5));

function harness({ user = 'A', store = {}, rows = {} } = {}) {
    const memory = new Map([['acp_v2_store', JSON.stringify({ p: {}, fav: [], exams: [], owner: user, ...store })]]);
    const logs = [], writes = [], reads = [];
    const control = { readError: null, writeError: null, signOutError: null, gate: null };
    const db = { user_progress: [], favorites: [], user_meta: [], exam_records: [], ...clone(rows) };
    let listener;
    const sb = {
        auth: {
            getSession: async () => ({ data: { session: user ? { user: { id: user } } : null } }),
            getUser: async () => ({ data: { user: { email: 'test@example.invalid' } } }),
            onAuthStateChange: cb => { listener = cb; },
            signOut: async () => ({ error: control.signOutError })
        },
        from(table) {
            let op = 'select', filters = [], range = [0, 999], input, order, ascending = true;
            const q = {
                select() { return q; }, eq(k, v) { filters.push([k, v]); return q; },
                order(k, opts = {}) { order = k; ascending = opts.ascending !== false; return q; },
                range(a, b) { range = [a, b]; return q; }, limit(n) { range = [0, n - 1]; return q; },
                delete() { op = 'delete'; return q; }, upsert(value) { op = 'upsert'; input = clone(Array.isArray(value) ? value : [value]); return q; },
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
                        writes.push({ table, op, rows: input });
                        if (op === 'delete') db[table] = db[table].filter(r => !filters.every(([k, v]) => r[k] === v));
                        else for (const row of input) {
                            const keys = table === 'exam_records' ? ['id'] : ['user_id', table === 'user_meta' ? 'key' : 'question_id'];
                            const i = db[table].findIndex(r => keys.every(k => r[k] === row[k]));
                            if (i < 0) db[table].push(row); else db[table][i] = row;
                        }
                        return { error: null };
                    })().then(resolve, reject);
                }
            };
            return q;
        }
    };
    const context = vm.createContext({
        window: { SUPABASE_CONFIG: { url: 'https://test.invalid', anonKey: 'test' }, supabase: { createClient: () => sb } },
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
