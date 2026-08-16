// Verify answer-history persistence, resume-position & retry-reset logic (node)
const fs = require('fs');

// load quiz data
const w = {};
new Function('window', fs.readFileSync('data/quiz_categorized.js', 'utf8') +
    '\n;window.__d = { QUIZ_DATA_BY_CHAPTER, QUIZ_CHAPTERS };')(w);
const { QUIZ_DATA_BY_CHAPTER, QUIZ_CHAPTERS } = w.__d;

// module stubs
const win = { ACP: {}, location: { hash: '' } };
const memStore = {};
global.document = { getElementById: () => ({ innerHTML: '', textContent: '' }), querySelector: () => null, querySelectorAll: () => [] };
global.location = win.location;
global.localStorage = {
    getItem: k => memStore[k] ?? null,
    setItem: (k, v) => { memStore[k] = String(v); },
    removeItem: k => { delete memStore[k]; }
};

for (const f of ['js/acp.js', 'js/utils.js', 'js/store.js', 'js/data.js', 'js/chapter.js']) {
    new Function('window', fs.readFileSync(f, 'utf8'))(win);
}
const ACP = win.ACP;
ACP.DATA_READY = true;
ACP.CHAPTERS = QUIZ_CHAPTERS;
ACP.CHAPTER_QUESTIONS = QUIZ_DATA_BY_CHAPTER;
ACP.buildBank();
ACP.state.store = ACP.loadStore();

const fails = [];
const eq = (label, got, want) => {
    const ok = JSON.stringify(got) === JSON.stringify(want);
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${ok ? '' : `  got ${JSON.stringify(got)} want ${JSON.stringify(want)}`}`);
    if (!ok) fails.push(label);
};

async function main() {
const pool1 = (ACP.BY_CH['1'] || []).slice().sort(ACP.compareQuestionsByDifficulty);
const q1 = pool1[0], q2 = pool1[1], q3 = pool1[2];

/* ============ 1. saveAnswer persistence ============ */
ACP.saveAnswer(q1, ['A']);
await new Promise(r => setTimeout(r, 8));
ACP.saveAnswer(q2, ['B', 'C']);
eq('saveAnswer q1.a', ACP.prog(q1.id).a, ['A']);
eq('saveAnswer q2.a', ACP.prog(q2.id).a, ['B', 'C']);
eq('persisted to localStorage', ACP.loadStore().p[q2.id].a, ['B', 'C']);
eq('counters intact after saveAnswer', [ACP.prog(q1.id).d, ACP.prog(q1.id).w, ACP.prog(q1.id).c], [0, 0, 0]);

/* ============ 2. findResumeIdx: continuous segment semantics ============ */
// user answered questions 1..k in order (k = 5), then jumped to pool[40] and answered it
const k = 5;
pool1.forEach((q, i) => { if (i < k) ACP.markResult(q, i % 2 === 0); });
ACP.markResult(pool1[40], true);
eq('resume = end of continuous segment (28-style)', ACP.findResumeIdx(pool1), k - 1);

// none answered -> -1 (start from question 1)
const pool2 = (ACP.BY_CH['2'] || []).slice().sort(ACP.compareQuestionsByDifficulty);
eq('resume none answered', ACP.findResumeIdx(pool2), -1);

// all answered -> last question
const pool3 = (ACP.BY_CH['11'] || []).slice().sort(ACP.compareQuestionsByDifficulty);
pool3.forEach(q => ACP.markResult(q, true));
eq('resume all answered', ACP.findResumeIdx(pool3), pool3.length - 1);

// skipped middle (answered 0,1,2, 3 skipped, 4 answered) -> 2
const pool4 = (ACP.BY_CH['4'] || []).slice().sort(ACP.compareQuestionsByDifficulty);
[0, 1, 2, 4].forEach(i => ACP.markResult(pool4[i], true));
eq('resume stops at first gap', ACP.findResumeIdx(pool4), 2);

/* ============ 3. questionPrev fallback / priority ============ */
ACP.state.session = {};
let prev = ACP.questionPrev(q2);
eq('questionPrev persisted fallback', prev && prev.sel, ['B', 'C']);
ACP.state.session[q2.id] = { sel: ['D'], correct: true };
prev = ACP.questionPrev(q2);
eq('questionPrev session priority', prev.sel, ['D']);

/* ============ 4. retry reset: clearAnswer ============ */
ACP.state.session = {};
delete ACP.state.session[q2.id];
ACP.markResult(q2, false);          // answered once, wrong
ACP.saveAnswer(q2, ['B', 'C']);     // snapshot exists
eq('before retry: has snapshot', ACP.questionPrev(q2).sel, ['B', 'C']);
ACP.clearAnswer(q2.id);             // what retry() calls
eq('after retry: snapshot gone', ACP.questionPrev(q2), undefined);
const p2b = ACP.prog(q2.id);
eq('after retry: counters kept (d/w/c)', [p2b.d, p2b.w, p2b.c], [2, 2, 0]); // q2 在连续段步骤中已答过一次
eq('after retry: no a/t keys', p2b.a === undefined && p2b.t === undefined, true);

// retry on a wrong question keeps it in wrong-book (counters kept)
eq('still flagged wrong', ACP.isWrong(q2.id), true);

// re-answer after retry saves a fresh snapshot
ACP.saveAnswer(q2, ['A']);
eq('re-answer after retry updates snapshot', ACP.questionPrev(q2).sel, ['A']);

console.log('---', fails.length ? `FAIL (${fails.length}): ` + fails.join('; ') : 'PASS');
process.exit(fails.length ? 1 : 0);
}

main().catch(e => { console.error(e); process.exit(1); });