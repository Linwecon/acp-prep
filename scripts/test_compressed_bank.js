// Verify compressed bank (quiz_categorized.min.js) works with data.js buildBank
const fs = require('fs');
const w = {};
new Function('window', fs.readFileSync('data/quiz_categorized.min.js', 'utf8') +
    '\n;window.__d = { QUIZ_DATA_BY_CHAPTER, QUIZ_CHAPTERS };')(w);
const { QUIZ_DATA_BY_CHAPTER, QUIZ_CHAPTERS } = w.__d;

const win = { ACP: {}, location: { hash: '' } };
const memStore = {};
global.document = { getElementById: () => ({ innerHTML: '', textContent: '' }), querySelector: () => null, querySelectorAll: () => [] };
global.location = win.location;
global.localStorage = {
    getItem: k => memStore[k] ?? null,
    setItem: (k, v) => { memStore[k] = String(v); },
    removeItem: k => { delete memStore[k]; }
};
for (const f of ['js/acp.js', 'js/utils.js', 'js/store.js', 'js/data.js', 'js/exam.js', 'js/chapter.js']) {
    new Function('window', fs.readFileSync(f, 'utf8'))(win);
}
const ACP = win.ACP;
ACP.DATA_READY = true;
ACP.CHAPTERS = QUIZ_CHAPTERS;
ACP.CHAPTER_QUESTIONS = QUIZ_DATA_BY_CHAPTER;
ACP.buildBank();

const fails = [];
const eq = (label, got, want) => {
    const ok = JSON.stringify(got) === JSON.stringify(want);
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${ok ? '' : `  got ${JSON.stringify(got)} want ${JSON.stringify(want)}`}`);
    if (!ok) fails.push(label);
};

eq('total questions', ACP.BANK.length, 1689);
eq('chapters', Object.keys(ACP.BY_CH).length, 12);
const q1 = ACP.BANK[0];
eq('q1 has options', q1.options.length > 0 && !!q1.options[0].text, true);
eq('q1 has stem', !!q1.stem, true);
eq('q1 id format', /^\d+-\d+$/.test(q1.id), true);

// exam draw still works with compressed data
for (let t = 0; t < 30; t++) {
    ACP.state.exam = null;
    ACP.startExam();
    const pool = ACP.state.exam.pool;
    const s = pool.filter(q => !q.multi).length;
    const m = pool.filter(q => q.multi).length;
    if (pool.length !== 75 || s !== 50 || m !== 25) fails.push(`draw ${t}: ${pool.length}/${s}/${m}`);
    if (new Set(pool.map(q => q.id)).size !== 75) fails.push(`draw ${t}: duplicates`);
}
console.log('30 exam draws with compressed bank ->', fails.some(f => f.includes('draw')) ? 'FAIL' : 'OK');

// analysis preserved for new questions (e.g. 9-5001 Batch API)
const fixed = ACP.ID_MAP['9-5001'];
eq('sample new question analysis exists', !!fixed && fixed.analysis.length > 20, true);
eq('sample new question answer', fixed && fixed.ansArr, ['C']);

console.log('---', fails.length ? `FAIL (${fails.length})` : 'PASS');
process.exit(fails.length ? 1 : 0);
