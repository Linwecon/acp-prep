/* Focused choice lessons. Keep legacy written self-assessments untouched. */
(function (ACP) {
    function pack(ch) { return (window.ACP_FOUNDATION || {}).chapters?.[String(ch)]; }
    function current() { return pack(ACP.state.ui.ch)?.items[ACP.state.ui.idx]; }
    function record(q) {
        const r = ACP.state.store.foundationChoice?.answers?.[q.id];
        return r && r.revision === q.revision ? r : {};
    }
    function storage() {
        const s = ACP.state.store;
        s.foundationChoice = s.foundationChoice || { answers: {}, cursors: {} };
        s.foundationChoice.answers = s.foundationChoice.answers || {};
        s.foundationChoice.cursors = s.foundationChoice.cursors || {};
        return s.foundationChoice;
    }
    function write(q, patch) {
        storage().answers[q.id] = { ...record(q), ...patch, revision:q.revision, at:Date.now() };
        ACP.saveStore();
    }
    function stats(ch) {
        const s = {correct:0,wrong:0,pending:0};
        for (const q of pack(ch)?.items || []) {
            const r = record(q);
            if (!r.submitted) s.pending++;
            else if (r.selected === q.answer) s.correct++;
            else s.wrong++;
        }
        return s;
    }
    function directory(ch, p) {
        const esc = ACP.esc;
        return `<details class="fl-directory"><summary>学习目录 <span aria-hidden="true">⌄</span></summary><div class="fl-directory-body">
            ${p.stages.map((name, stage) => `<div class="fl-unit"><p>${esc(name)} <span>${stage*10+1}–${stage*10+10}</span></p><div class="fl-grid">${p.items.filter(q=>q.stage===stage).map(q=>{
                const r=record(q), status=r.submitted ? (r.selected===q.answer?'correct':'wrong') : '';
                return `<button class="fl-number ${status} ${q.number-1===ACP.state.ui.idx?'current':''}" aria-label="第${q.number}题 ${esc(q.topic)} ${status==='correct'?'答对':status==='wrong'?'待复习':'未完成'}" onclick="ACP.foundationGoto(${q.number-1})">${q.number}</button>`;
            }).join('')}</div></div>`).join('')}
            <div class="fl-directory-links"><button onclick="ACP.foundationSummary()">本章回顾</button><button onclick="ACP.go('study');ACP.openStudyChapter(${Number(ch)-1})">回看教材</button><button onclick="ACP.setFilter('all')">章节题库</button></div>
            <small>进度保存在本机当前账号，不计入模拟考试。</small></div></details>`;
    }
    function render(root) {
        const S=ACP.state, ch=String(S.ui.ch||'1'), p=pack(ch), esc=ACP.esc;
        S.ui.ch=ch; S.ui.pool=[];
        if (!p) {root.innerHTML='<div class="empty-state">基础学习内容尚未加载，请刷新重试。</div>';return;}
        S.ui.idx=Math.max(0,Math.min(Number(S.ui.idx)||0,p.items.length-1));
        const q=current(), r=record(q), done=!!r.submitted, correct=r.selected===q.answer;
        ACP.setCrumb(p.title,'基础学习');
        root.innerHTML=`<div class="fl-shell"><header class="fl-header"><div><p class="fl-eyebrow">基础学习</p><h1>${esc(p.title)}</h1></div>${directory(ch,p)}</header>
            <div class="fl-position"><span>${esc(p.stages[q.stage])}</span><span><b>${String(q.number).padStart(2,'0')}</b> / 30</span></div>
            <div class="fl-track" aria-label="当前第${q.number}题，共30题"><i style="width:${q.number/30*100}%"></i></div>
            <article class="fl-card"><div class="fl-question-type">单选题 <span>· ${esc(q.topic)}</span></div><h2 id="fl-question">${esc(q.question)}</h2>
            <div class="fl-options" role="group" aria-labelledby="fl-question">${q.options.map(o=>{
                const selected=r.selected===o.label;
                const status=done ? (o.label===q.answer?'is-correct':selected?'is-wrong':'') : selected?'is-selected':'';
                return `<button class="fl-option ${status}" data-choice="${o.label}" aria-pressed="${selected}" ${done?'disabled':''} onclick="ACP.foundationSelect('${o.label}')"><span class="fl-letter">${o.label}</span><span class="fl-option-text">${esc(o.text)}</span><span class="fl-mark" aria-hidden="true">${done&&o.label===q.answer?'✓':done&&selected?'×':selected?'●':''}</span></button>`;
            }).join('')}</div>
            ${done?`<section class="fl-explanation" aria-label="答案解析"><div class="fl-result ${correct?'correct':'wrong'}" role="status">${correct?'✓ 答对了':'再理解一下'}<span>${correct?'':`你选了 ${esc(r.selected)} · `}正确答案 ${q.answer}</span></div>
                <h3>把这个知识点弄懂</h3><p class="fl-teaching">${esc(q.answer_text)} ${esc(q.explanation)}</p>
                <h3>其他选项错在哪里</h3><div class="fl-reasons">${q.options.filter(o=>o.label!==q.answer).map(o=>`<div><span class="fl-reason-letter">${o.label}</span><p>${esc(o.explanation)}</p></div>`).join('')}</div>
                <details class="fl-source"><summary>对应教材与学习操作</summary><p>${q.sources.map(s=>esc(s.section+' '+s.title)).join('；')}</p><button class="fl-text-button" onclick="ACP.go('study');ACP.openStudyChapter(${Number(ch)-1})">回看教材 →</button><button class="fl-text-button" onclick="ACP.foundationRetry()">重新作答</button></details></section>`:''}
            <footer class="fl-actions"><button class="fl-back" onclick="ACP.foundationGoto(${q.number-2})" ${q.number===1?'disabled':''}>← 上一题</button>
            ${done?`<button class="fl-primary" onclick="${q.number===30?'ACP.foundationSummary()':`ACP.foundationGoto(${q.number})`}">${q.number===30?'完成 · 查看回顾':'下一题 →'}</button>`:`<button class="fl-primary" id="foundationSubmit" onclick="ACP.foundationSubmit()" ${!r.selected?'disabled':''}>提交答案</button>`}</footer></article></div>`;
    }
    ACP.openFoundation=function(ch){ACP.go('chapter',{ch:String(ch),filter:'foundation',idx:ACP.state.store.foundationChoice?.cursors?.[String(ch)]||0});};
    ACP.foundationSelect=function(label){
        const q=current();
        if(!q||record(q).submitted||!q.options.some(o=>o.label===label))return;
        write(q,{selected:label});render(document.getElementById('contentInner'));
        document.querySelector(`[data-choice="${label}"]`)?.focus({preventScroll:true});
    };
    ACP.foundationSubmit=function(){
        const q=current(); if(!q)return;
        const r=record(q); if(r.submitted||!q.options.some(o=>o.label===r.selected))return;
        write(q,{submitted:true,attempts:(r.attempts||0)+1,firstCorrect:r.firstCorrect??(r.selected===q.answer)});
        render(document.getElementById('contentInner'));
        document.querySelector('.fl-result')?.scrollIntoView({block:'nearest',behavior:'smooth'});
    };
    ACP.foundationRetry=function(){const q=current();if(q){write(q,{selected:null,submitted:false});render(document.getElementById('contentInner'));}};
    ACP.foundationGoto=function(idx){
        const S=ACP.state,p=pack(S.ui.ch);if(!p||!Number.isInteger(idx)||idx<0||idx>=p.items.length)return;
        S.ui.idx=idx;storage().cursors[S.ui.ch]=idx;ACP.saveStore();render(document.getElementById('contentInner'));document.getElementById('content').scrollTop=0;
    };
    ACP.foundationSummary=function(){
        const ch=String(ACP.state.ui.ch),p=pack(ch);if(!p)return;
        const s=stats(ch),esc=ACP.esc;
        document.getElementById('contentInner').innerHTML=`<div class="fl-shell"><header class="fl-header"><div><p class="fl-eyebrow">本章回顾</p><h1>${esc(p.title)}</h1></div>${directory(ch,p)}</header><section class="fl-card fl-summary"><h2>${s.pending?`还有 ${s.pending} 题，慢慢学完。`:'这一章，学完了。'}</h2><p>答对 ${s.correct} · 待复习 ${s.wrong} · 未完成 ${s.pending}</p><div class="fl-review-list">${p.items.map((q,i)=>{
            const r=record(q),status=!r.submitted?'未完成':r.selected===q.answer?'答对':'待复习';
            return `<button onclick="ACP.foundationGoto(${i})"><span class="fl-review-number">${String(q.number).padStart(2,'0')}</span><span>${esc(q.topic)}</span><small class="${status==='待复习'?'fl-needs-review':''}">${status} →</small></button>`;
        }).join('')}</div></section></div>`;
        document.getElementById('content').scrollTop=0;
    };
    ACP.renderFoundation=render;ACP.foundationStats=stats;ACP.foundationRecord=record;
})(window.ACP);
