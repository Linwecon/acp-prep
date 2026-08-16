// Verify new-exam-outline quota allocation & stratified sampling (node)
const fs = require('fs');

// --- load data + build bank (mirrors boot) ---
const w = {};
new Function('window', fs.readFileSync('data/quiz_categorized.js', 'utf8') +
    '\n;window.__d = { QUIZ_DATA_BY_CHAPTER, QUIZ_CHAPTERS };')(w);
const { QUIZ_DATA_BY_CHAPTER, QUIZ_CHAPTERS } = w.__d;

const win = {
    ACP: {},
    location: { hash: '' },
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    setInterval: () => 1, clearInterval: () => {},
    confirm: () => true
};
global.document = { getElementById: () => ({ innerHTML: '', textContent: '' }) };
global.location = win.location;
new Function('window', fs.readFileSync('js/acp.js', 'utf8'))(win);
new Function('window', fs.readFileSync('js/utils.js', 'utf8'))(win);
new Function('window', fs.readFileSync('js/store.js', 'utf8'))(win);
new Function('window', fs.readFileSync('js/data.js', 'utf8'))(win);
new Function('window', fs.readFileSync('js/exam.js', 'utf8'))(win);

const ACP = win.ACP;
ACP.DATA_READY = true;
ACP.CHAPTERS = QUIZ_CHAPTERS;
ACP.CHAPTER_QUESTIONS = QUIZ_DATA_BY_CHAPTER;
ACP.buildBank();

const fails = [];
const eq = (label, got, want) => {
    const ok = JSON.stringify(got) === JSON.stringify(want);
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}: got ${JSON.stringify(got)}${ok ? '' : ' want ' + JSON.stringify(want)}`);
    if (!ok) fails.push(label);
};

// 1. quota allocation
const pcts = ACP.EXAM_DOMAINS.map(d => d.pct);
eq('single quota 50', ACP.quotaAlloc(50, pcts), [9, 7, 10, 8, 8, 8]);
eq('multi  quota 25', ACP.quotaAlloc(25, pcts), [4, 4, 5, 4, 4, 4]);

// 2. stratified sampling: run several draws, check totals & per-domain counts
for (let t = 0; t < 200; t++) {
    ACP.state.exam = null;
    ACP.startExam();
    const ex = ACP.state.exam;
    if (!ex) { fails.push('exam not started'); continue; }
    const pool = ex.pool;
    const singles = pool.filter(q => !q.multi).length;
    const multis = pool.filter(q => q.multi).length;
    if (pool.length !== 75) fails.push(`draw ${t}: pool ${pool.length} != 75`);
    if (singles !== 50) fails.push(`draw ${t}: singles ${singles} != 50`);
    if (multis !== 25) fails.push(`draw ${t}: multis ${multis} != 25`);
    // per-domain counts
    const sQ = ACP.quotaAlloc(50, pcts), mQ = ACP.quotaAlloc(25, pcts);
    ACP.EXAM_DOMAINS.forEach((d, i) => {
        const ids = new Set(d.chs.flatMap(ch => (ACP.BY_CH[ch] || []).map(q => q.id)));
        const dSingle = pool.filter(q => ids.has(q.id) && !q.multi).length;
        const dMulti = pool.filter(q => ids.has(q.id) && q.multi).length;
        if (dSingle !== sQ[i]) fails.push(`draw ${t} domain ${d.id} single ${dSingle} != ${sQ[i]}`);
        if (dMulti !== mQ[i]) fails.push(`draw ${t} domain ${d.id} multi ${dMulti} != ${mQ[i]}`);
    });
    // no duplicate questions
    const idSet = new Set(pool.map(q => q.id));
    if (idSet.size !== 75) fails.push(`draw ${t}: duplicates`);
}
console.log('200 draws: all 75 (50+25), per-domain quotas exact, no duplicates ->',
    fails.filter(f => f.includes('draw')).length ? 'CHECK FAILS' : 'OK');

console.log('---', fails.length ? `FAIL (${fails.length}): ` + fails.slice(0, 5).join('; ') : 'PASS');
process.exit(fails.length ? 1 : 0);
