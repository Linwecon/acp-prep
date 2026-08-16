/* ============================================================
   ACP — Exam mode
   ============================================================ */
(function (ACP) {
    const S = ACP.state;

    /* 配额分配：largest remainder（最大余数法），按比例把 total 拆成整数份 */
    function quotaAlloc(total, pcts) {
        const raw = pcts.map(p => total * p / 100);
        const base = raw.map(Math.floor);
        let remain = total - base.reduce((a, b) => a + b, 0);
        const order = raw
            .map((r, i) => [r - base[i], i])
            .sort((a, b) => b[0] - a[0]);
        for (let k = 0; k < remain && k < order.length; k++) base[order[k][1]]++;
        return base;
    }

    function renderExam(root) {
        if (!S.exam || S.exam.state === 'idle') {
            ACP.setCrumb('模拟考试', '新大纲 75 题 · 120 分钟');
            const singles = ACP.BANK.filter(q => !q.multi).length;
            const multis = ACP.BANK.filter(q => q.multi).length;
            const sQuota = quotaAlloc(ACP.EXAM_SINGLE, ACP.EXAM_DOMAINS.map(d => d.pct));
            const mQuota = quotaAlloc(ACP.EXAM_MULTI, ACP.EXAM_DOMAINS.map(d => d.pct));
            root.innerHTML = `
      <div class="card exam-result">
        <div style="font-size:44px;margin-bottom:10px;">📝</div>
        <h2 style="font-size:19px;font-weight:700;margin-bottom:8px;">ACP 模拟考试</h2>
        <p style="color:var(--text-2);font-size:13px;line-height:2;">
          单选 ${ACP.EXAM_SINGLE} 题 × 1 分 + 多选 ${ACP.EXAM_MULTI} 题 × 2 分 = 100 分<br>
          及格线 <b>80 分</b> · 限时 <b>120 分钟</b> · 按新版大纲考点比例从 ${ACP.TOTAL} 题题库抽取<br>
          <span style="color:var(--text-3);font-size:12px">（题库现有单选 ${singles} 题 / 多选 ${multis} 题）</span>
        </p>
        <div class="domain-list">
          ${ACP.EXAM_DOMAINS.map((d, i) => `
            <div class="domain-row">
              <span class="d-name">${d.name}</span>
              <span class="d-bar"><i style="width:${Math.round(d.pct / 20 * 100)}%"></i></span>
              <span class="d-pct">${d.pct}%</span>
              <span class="d-num">抽 ${sQuota[i]} 单选 + ${mQuota[i]} 多选</span>
            </div>`).join('')}
        </div>
        <div class="outline">
          <div class="outline-head">
            <span class="outline-title">📋 新版考试大纲</span>
            <span class="hint">点击知识域展开考点 · 章节直达刷题</span>
            <span class="spacer"></span>
            <button class="btn btn-sm" onclick="ACP.toggleOutlineAll()">展开全部</button>
          </div>
          ${ACP.EXAM_DOMAINS.map((d, di) => `
          <div class="outline-domain${di === 0 ? ' open' : ''}">
            <button class="outline-toggle" onclick="this.parentElement.classList.toggle('open')">
              <span class="ot-name">${ACP.esc(d.name)}</span>
              <span class="ot-pct">${d.pct}%</span>
              <span class="ot-arrow">▾</span>
            </button>
            <div class="outline-body">
              ${d.groups.map(g => `
                <div class="od-group">
                  ${g.title ? `<div class="od-gtitle">${ACP.esc(g.title)}</div>` : ''}
                  <ul class="od-points">
                    ${g.points.map(p => `<li>${ACP.esc(p)}</li>`).join('')}
                  </ul>
                </div>`).join('')}
              <div class="od-chs">
                <span class="od-chs-label">对应章节刷题：</span>
                ${d.chs.map(ch => `<button class="study-chip" onclick="ACP.openChapter('${ch}')">${ch} · ${ACP.esc(ACP.chapterName(ch))}</button>`).join('')}
              </div>
            </div>
          </div>`).join('')}
        </div>
        <button class="btn btn-primary" style="padding:10px 28px;font-size:14px;" onclick="ACP.startExam()">开始考试</button>
      </div>`;
            return;
        }

        if (S.exam.state === 'done') { renderExamResult(root); return; }

        ACP.setCrumb('模拟考试', `第 ${S.exam.idx + 1} / ${S.exam.pool.length} 题`);
        const q = S.exam.pool[S.exam.idx];
        const myAns = S.exam.answers[S.exam.idx] || [];
        const review = S.exam.state === 'review';

        const t = Math.max(0, S.exam.endAt - Date.now());
        const mm = String(Math.floor(t / 60000)).padStart(2, '0');
        const ss = String(Math.floor((t % 60000) / 1000)).padStart(2, '0');

        root.innerHTML = `
    <div class="exam-bar">
      <div class="exam-timer ${t < 600000 ? 'urgent' : ''}">⏱ <span id="examClock">${mm}:${ss}</span></div>
      <span class="exam-meta">已答 ${Object.values(S.exam.answers).filter(a => (a || []).length).length}/${S.exam.pool.length}</span>
      <span class="spacer"></span>
      ${review
        ? `<button class="btn btn-sm" onclick="ACP.backToResult()">← 返回成绩</button>`
        : `<button class="btn btn-primary btn-sm" onclick="ACP.submitExam()">交卷</button>`}
    </div>

    <div class="card answer-sheet">
      <h4>答题卡 · 1-${ACP.EXAM_SINGLE} 单选 / ${ACP.EXAM_SINGLE + 1}-${ACP.EXAM_SINGLE + ACP.EXAM_MULTI} 多选</h4>
      <div class="sheet-grid">
        ${S.exam.pool.map((x, i) => {
          const answered = (S.exam.answers[i] || []).length > 0;
          let cls = answered ? 'answered' : '';
          if (review) {
            const ok = ACP.isExamCorrect(i);
            cls = ok ? 'ok' : 'err';
          }
          if (i === S.exam.idx) cls += ' current';
          return `<button class="sheet-cell ${cls}" onclick="ACP.examJump(${i})">${i + 1}</button>`;
        }).join('')}
      </div>
    </div>

    <div class="card q-card">
      <div class="q-head">
        <span class="q-index">第 ${S.exam.idx + 1} 题</span>
        <span class="tag ${q.multi ? 'tag-multi' : 'tag-single'}">${q.multi ? '多选 · 2分' : '单选 · 1分'}</span>
        <span class="q-index" style="font-weight:400">${ACP.esc(ACP.chapterName(q.ch))}</span>
      </div>
      <div class="q-stem">${ACP.esc(q.stem)}</div>
      <div class="options">
        ${q.options.map(o => {
          let cls = '';
          const picked = myAns.includes(o.label);
          const isAns = q.ansArr.includes(o.label);
          if (review) {
            if (picked && isAns) cls = 'correct';
            else if (picked && !isAns) cls = 'wrong';
            else if (!picked && isAns) cls = 'miss';
          } else if (picked) cls = 'selected';
          return `<button class="opt ${cls} ${review ? 'disabled' : ''}" onclick="ACP.examOpt('${o.label}')">
            <span class="opt-label">${o.label}</span>
            <span class="opt-text">${ACP.esc(o.text)}</span>
          </button>`;
        }).join('')}
      </div>
      ${review ? `<div class="analysis-box show ${ACP.isExamCorrect(S.exam.idx) ? 'ok' : 'err'}">${ACP.analysisHTML(q, ACP.isExamCorrect(S.exam.idx))}</div>` : ''}
      <div class="q-actions">
        <button class="btn" onclick="ACP.examNav(-1)" ${S.exam.idx === 0 ? 'disabled' : ''}>← 上一题</button>
        <button class="btn ${review ? '' : 'btn-primary'}" onclick="ACP.examNav(1)" ${S.exam.idx === S.exam.pool.length - 1 ? 'disabled' : ''}>下一题 →</button>
        <span class="spacer"></span>
        ${q.multi && !review ? `<span class="kbd-hint">多选题点击选项后即保存</span>` : ''}
      </div>
    </div>`;
    }

    function startExam() {
        // 按新版大纲知识域比例分层抽题：单选 50 / 多选 25 分别按域配额
        const sQuota = quotaAlloc(ACP.EXAM_SINGLE, ACP.EXAM_DOMAINS.map(d => d.pct));
        const mQuota = quotaAlloc(ACP.EXAM_MULTI, ACP.EXAM_DOMAINS.map(d => d.pct));
        const singles = [], multis = [];
        ACP.EXAM_DOMAINS.forEach((d, i) => {
            const qs = d.chs.flatMap(ch => ACP.BY_CH[ch] || []);
            singles.push(...ACP.shuffle(qs.filter(q => !q.multi)).slice(0, sQuota[i]));
            multis.push(...ACP.shuffle(qs.filter(q => q.multi)).slice(0, mQuota[i]));
        });
        S.exam = {
            state: 'on',
            pool: [...singles, ...multis],
            answers: {},
            idx: 0,
            endAt: Date.now() + ACP.EXAM_TIME * 1000,
            startAt: Date.now()
        };
        startExamTimer();
        ACP.renderExam(document.getElementById('contentInner'));
    }

    function startExamTimer() {
        stopExamTimer();
        S.exam.timer = setInterval(() => {
            if (!S.exam || S.exam.state === 'done') { stopExamTimer(); return; }
            const left = S.exam.endAt - Date.now();
            if (left <= 0) { submitExam(true); return; }
            const el = document.getElementById('examClock');
            if (el) {
                const mm = String(Math.floor(left / 60000)).padStart(2, '0');
                const ss = String(Math.floor((left % 60000) / 1000)).padStart(2, '0');
                el.textContent = `${mm}:${ss}`;
                el.parentElement.classList.toggle('urgent', left < 600000);
            }
        }, 1000);
    }
    function stopExamTimer() { if (S.exam && S.exam.timer) { clearInterval(S.exam.timer); S.exam.timer = null; } }

    function examOpt(label) {
        if (!S.exam || S.exam.state !== 'on') return;
        const q = S.exam.pool[S.exam.idx];
        let cur = S.exam.answers[S.exam.idx] || [];
        if (q.multi) {
            cur = cur.includes(label) ? cur.filter(l => l !== label) : [...cur, label];
        } else {
            cur = [label];
        }
        S.exam.answers[S.exam.idx] = cur;
        ACP.renderExam(document.getElementById('contentInner'));
    }
    function examNav(d) {
        const n = S.exam.idx + d;
        if (n < 0 || n >= S.exam.pool.length) return;
        S.exam.idx = n;
        ACP.renderExam(document.getElementById('contentInner'));
    }
    function examJump(i) { S.exam.idx = i; ACP.renderExam(document.getElementById('contentInner')); }

    function isExamCorrect(i) {
        const q = S.exam.pool[i];
        const a = (S.exam.answers[i] || []).slice().sort().join(',');
        return a === q.ansArr.slice().sort().join(',');
    }

    function submitExam(auto) {
        if (!S.exam || S.exam.state !== 'on') return;
        const unanswered = S.exam.pool.length - Object.keys(S.exam.answers).filter(k => (S.exam.answers[k] || []).length).length;
        if (!auto && unanswered > 0) {
            if (!confirm(`还有 ${unanswered} 题未作答，确定交卷吗？`)) return;
        }
        stopExamTimer();

        let score = 0, correct = 0;
        const weakByCh = {};
        S.exam.pool.forEach((q, i) => {
            const ok = isExamCorrect(i);
            if (ok) { score += q.multi ? 2 : 1; correct++; }
            else weakByCh[q.ch] = (weakByCh[q.ch] || 0) + 1;
            if ((S.exam.answers[i] || []).length > 0) ACP.markResult(q, ok);
        });

        S.exam.state = 'done';
        S.exam.result = {
            score, correct,
            wrong: S.exam.pool.length - correct,
            pass: score >= 80,
            timeUsed: Math.min(ACP.EXAM_TIME, Math.round((Date.now() - S.exam.startAt) / 1000)),
            weakByCh
        };
        ACP.renderSidebarBadges();
        ACP.renderExam(document.getElementById('contentInner'));
    }

    function renderExamResult(root) {
        const r = S.exam.result;
        ACP.setCrumb('考试成绩', r.pass ? '恭喜通过 🎉' : '继续加油');
        const mm = String(Math.floor(r.timeUsed / 60)).padStart(2, '0');
        const ss = String(r.timeUsed % 60).padStart(2, '0');
        const weak = Object.entries(r.weakByCh).sort((a, b) => b[1] - a[1]);
        const maxWeak = weak.length ? weak[0][1] : 1;

        root.innerHTML = `
    <div class="card exam-result">
      <div class="score-circle ${r.pass ? 'pass' : 'fail'}">
        <div class="score-num">${r.score}</div>
        <div class="score-lbl">分 / 100</div>
      </div>
      <h2 style="font-size:18px;font-weight:700;">${r.pass ? '🎉 已通过（≥80分）' : '未通过（差 ' + (80 - r.score) + ' 分）'}</h2>
      <p style="color:var(--text-3);font-size:12.5px;margin-top:4px;">用时 ${mm}:${ss}</p>
      <div class="score-row">
        <div class="score-cell ok"><div class="v">${r.correct}</div><div class="l">答对</div></div>
        <div class="score-cell err"><div class="v">${r.wrong}</div><div class="l">答错 / 未答</div></div>
        <div class="score-cell acc"><div class="v">${Math.round(r.correct / S.exam.pool.length * 100)}%</div><div class="l">正确率</div></div>
        <div class="score-cell"><div class="v">${S.exam.pool.filter((q, i) => q.multi && isExamCorrect(i)).length}/${ACP.EXAM_MULTI}</div><div class="l">多选得分题</div></div>
      </div>

      ${weak.length ? `
      <div class="section-title" style="margin-top:6px;">薄弱章节 <span class="hint">本次答错分布</span></div>
      <div class="weak-list">
        ${weak.map(([ch, n]) => `
          <div class="weak-row">
            <span class="w-name">${ch} · ${ACP.esc(ACP.chapterName(ch))}</span>
            <span class="w-bar"><i style="width:${(n / maxWeak) * 100}%"></i></span>
            <span class="w-num">错 ${n} 题</span>
            <button class="btn btn-sm" onclick="ACP.openChapter('${ch}')">去巩固</button>
          </div>`).join('')}
      </div>` : '<p style="color:var(--success);font-weight:600;">满分发挥，没有薄弱章节！</p>'}

      <div style="display:flex;gap:8px;justify-content:center;margin-top:14px;">
        <button class="btn btn-primary" onclick="ACP.state.exam.state='review';ACP.state.exam.idx=0;ACP.renderExam(document.getElementById('contentInner'))">🔍 逐题回顾</button>
        <button class="btn" onclick="ACP.startExam()">🔄 再考一次</button>
      </div>

      <div class="review-list">
        ${S.exam.pool.map((q, i) => {
          const ok = isExamCorrect(i);
          const skipped = !(S.exam.answers[i] || []).length;
          return `<button class="review-item" onclick="ACP.state.exam.state='review';ACP.state.exam.idx=${i};ACP.renderExam(document.getElementById('contentInner'))">
            <span class="ri-dot ${skipped ? 'skip' : ok ? 'ok' : 'err'}"></span>
            <span class="ri-num">${i + 1}</span>
            <span class="ri-stem">${ACP.esc(q.stem)}</span>
            <span class="tag ${skipped ? '' : ok ? 'tag-ok' : 'tag-err'}">${skipped ? '未答' : ok ? '正确' : '错误'}</span>
          </button>`;
        }).join('')}
      </div>
    </div>`;
    }

    function backToResult() {
        S.exam.state = 'done';
        ACP.renderExam(document.getElementById('contentInner'));
    }

    function toggleOutlineAll() {
        const wrap = document.querySelector('.outline');
        if (!wrap) return;
        const allOpen = [...wrap.querySelectorAll('.outline-domain')].every(d => d.classList.contains('open'));
        wrap.querySelectorAll('.outline-domain').forEach(d => d.classList.toggle('open', !allOpen));
        const btn = wrap.querySelector('.outline-head .btn');
        if (btn) btn.textContent = allOpen ? '展开全部' : '全部收起';
    }

    ACP.renderExam = renderExam;
    ACP.startExam = startExam;
    ACP.quotaAlloc = quotaAlloc;
    ACP.toggleOutlineAll = toggleOutlineAll;
    ACP.stopExamTimer = stopExamTimer;
    ACP.examOpt = examOpt;
    ACP.examNav = examNav;
    ACP.examJump = examJump;
    ACP.isExamCorrect = isExamCorrect;
    ACP.submitExam = submitExam;
    ACP.backToResult = backToResult;

})(window.ACP);