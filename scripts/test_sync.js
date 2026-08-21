// Smoke test for js/sync.js (run with node)
const fs = require('fs');

// ---- mock browser globals ----
global.window = {
    SUPABASE_CONFIG: { url: 'https://abc.supabase.co', anonKey: 'eyJ-real-anon-key' },
    supabase: {
        createClient: () => ({
            auth: {
                getSession: async () => ({ data: { session: null } }),
                getUser: async () => ({ data: { user: null } }),
                onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }),
                signInWithOAuth: async () => ({}),
                signInWithOtp: async () => ({}),
                verifyOtp: async () => ({}),
                signOut: async () => ({})
            },
            from: () => ({
                select: () => ({ eq: () => ({ order: () => ({ limit: () => ({ data: [] }) }), data: [] }) }),
                upsert: async () => ({}),
                delete: async () => ({})
            })
        })
    }
};
global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };

const ACP = {
    state: { store: { p: {}, fav: [], exams: [] } },
    esc: s => String(s),
    toast: () => {},
    toggleSidebar: () => {},
    render: () => {},
    renderSidebarBadges: () => {},
    saveStore: () => {}
};
global.window.ACP = ACP;

new Function('window', fs.readFileSync('js/sync.js', 'utf8'))(window);

const fails = [];

// 1. sync namespace + methods
if (!ACP.sync) fails.push('ACP.sync missing');
for (const m of ['init', 'isConfigured', 'openAuth', 'switchAuthPage', 'togglePassword', 'signInWithPassword', 'signUp', 'signOut', 'pushProgress', 'pushFav', 'pushExam', 'pushAll', 'pullAndMerge', '_mergeProgress']) {
    if (!ACP.sync[m]) fails.push('missing method: ' + m);
}
if (!ACP.sync.isConfigured()) fails.push('should be configured with real-looking config');

// 2. mergeProgress
const m = ACP.sync._mergeProgress;
const t1 = Date.parse('2026-01-01T00:00:00Z');
const t2 = Date.parse('2026-02-01T00:00:00Z');

// 云端较新 → 采用云端 correct/answer
let r = m({ d: 3, w: 2, c: 0, a: ['A'], t: t1 }, { done: 5, wrong: 3, correct: 1, answer: ['B'], answered_at: new Date(t2).toISOString() });
if (r.d !== 5 || r.w !== 3 || r.c !== 1 || JSON.stringify(r.a) !== JSON.stringify(['B']) || r.t !== t2) {
    fails.push('merge newer-cloud wrong: ' + JSON.stringify(r));
}

// 本地较新 → 采用本地 correct/answer
r = m({ d: 4, w: 1, c: 1, a: ['C'], t: t2 }, { done: 2, wrong: 0, correct: 0, answer: ['A'], answered_at: new Date(t1).toISOString() });
if (r.d !== 4 || r.w !== 1 || r.c !== 1 || JSON.stringify(r.a) !== JSON.stringify(['C']) || r.t !== t2) {
    fails.push('merge newer-local wrong: ' + JSON.stringify(r));
}

// 本地为空 → 全用云端
r = m(null, { done: 2, wrong: 1, correct: 0, answer: ['D'], answered_at: new Date(t1).toISOString() });
if (r.d !== 2 || r.w !== 1 || r.c !== 0 || JSON.stringify(r.a) !== JSON.stringify(['D'])) {
    fails.push('merge local-null wrong: ' + JSON.stringify(r));
}

// done/wrong 取较大值（不丢失累计），本地较新
r = m({ d: 9, w: 4, c: 1, a: ['A'], t: t2 }, { done: 2, wrong: 1, correct: 0, answer: ['B'], answered_at: new Date(t1).toISOString() });
if (r.d !== 9 || r.w !== 4) fails.push('merge max wrong: ' + JSON.stringify(r));

console.log('---', fails.length ? 'FAIL: ' + fails.join('; ') : 'PASS');
process.exit(fails.length ? 1 : 0);
