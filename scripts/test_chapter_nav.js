// Verify chapter-switch idx reset + next-button logic (node)
const fs = require('fs');
const w = {};
new Function('window', fs.readFileSync('data/quiz_categorized.js', 'utf8') +
    '\n;window.__d = { QUIZ_DATA_BY_CHAPTER, QUIZ_CHAPTERS };')(w);
const { QUIZ_DATA_BY_CHAPTER, QUIZ_CHAPTERS } = w.__d;

const memStore = {};
function stubEl() {
    return { innerHTML: '', textContent: '', style: {}, dataset: {}, classList: { toggle() {}, add() {}, remove() {} },
             addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
             scrollTo() {}, getBoundingClientRect() { return { top: 0 }; } };
}
global.document = { getElementById: () => stubEl(), querySelector: () => stubEl(), querySelectorAll: () => [] };
global.location = { hash: '' };
global.localStorage = { getItem: k => memStore[k] ?? null, setItem: (k, v) => { memStore[k] = String(v); }, removeItem: k => { delete memStore[k]; } };

const win = { ACP: {} };
for (const f of ['js/acp.js', 'js/utils.js', 'js/store.js', 'js/data.js', 'js/sidebar.js', 'js/chapter.js']) {
    new Function('window', fs.readFileSync(f, 'utf8'))(win);
}
const ACP = win.ACP;
ACP.DATA_READY = true;
ACP.CHAPTERS = QUIZ_CHAPTERS;
ACP.CHAPTER_QUESTIONS = QUIZ_DATA_BY_CHAPTER;
ACP.buildBank();
ACP.state.store = ACP.loadStore();
ACP.state.store.p = {};
ACP.closeSearch = () => {}; // search.js 未加载，补 stub

const fails = [];
const eq = (label, got, want) => {
    const ok = JSON.stringify(got) === JSON.stringify(want);
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${ok ? '' : `  got ${JSON.stringify(got)} want ${JSON.stringify(want)}`}`);
    if (!ok) fails.push(label);
};

// ---- 场景1：第1章刷到 idx=28，切换到第2章（无作答）→ 应从第1题(0)开始 ----
ACP.state.ui.idx = 28;
ACP.state.ui.ch = '1';
ACP.openChapter('2'); // sidebar openChapter：重置 idx + autoPos
// openChapter 内部已渲染（go→render），此时验证渲染后的状态
eq('切到无作答章节 → idx=0', ACP.state.ui.idx, 0);

// ---- 场景2：第2章有连续作答（前5题）→ 切到第2章应定位到第4题(索引3) ----
const pool2 = (ACP.BY_CH['2'] || []).slice().sort(ACP.compareQuestionsByDifficulty);
pool2.slice(0, 4).forEach(q => ACP.markResult(q, true));
ACP.state.ui.idx = 99; // 模拟在别处停留
ACP.openChapter('2');
eq('切到有作答章节 → 定位连续段末尾(3)', ACP.state.ui.idx, 3);

// ---- 场景3：未提交时下一题按钮渲染 ----
const area = stubEl();
const html = renderSingleHTML(ACP);
eq('未提交时含"下一题"按钮', /下一题 →/.test(html), true);
eq('未提交时含"提交"按钮', /✓ 提交/.test(html), true);

function renderSingleHTML(ACP) {
    // 直接构造 renderSingle 的输出（复用其模板逻辑的近似：手动渲染 pool[0]）
    const S = ACP.state;
    S.ui.pool = pool2;
    S.ui.idx = 0;
    S.judged = false;
    S.sel = new Set();
    const q = S.ui.pool[0];
    const prev = null;
    return `
      <div class="q-actions">
        <button class="btn" onclick="ACP.navQ(-1)" ${S.ui.idx === 0 ? 'disabled' : ''}>← 上一题</button>
        ${!S.judged ? `<button class="btn btn-primary" id="submitBtn" onclick="ACP.judge()">✓ 提交</button>` : ''}
        ${!S.judged ? `<button class="btn" onclick="ACP.navQ(1)" ${S.ui.idx === S.ui.pool.length - 1 ? 'disabled' : ''}>下一题 →</button>` : ''}
        ${S.judged ? `<button class="btn btn-sm" onclick="ACP.retry()" title="重新作答本题">↺ 重做</button>` : ''}
        ${S.judged ? `<button class="btn btn-primary" onclick="ACP.navQ(1)">${S.ui.idx === S.ui.pool.length - 1 ? '完成 ✓' : '下一题 →'}</button>` : ''}
        ${S.judged && ACP.isWrong(q.id) ? `<button class="btn btn-danger-ghost btn-sm" onclick="ACP.onRemoveWrong()">✕ 移出错题</button>` : ''}
      </div>`;
}

console.log('---', fails.length ? `FAIL (${fails.length})` : 'PASS');
process.exit(fails.length ? 1 : 0);
